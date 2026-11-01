// The shelf: trophies stack for real, keep the room they were won in, arrive with a fanfare, and print.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, sleep } from "./harness.js";

let v, server, browser;
const sys = (f) => path.join(v.vault, "_system", f);
const day = (n, h) => { const d = new Date(); d.setDate(d.getDate() - n); d.setHours(h, 0, 0, 0); return d; };
const blk = (n, m) => { const e = day(n, 20); return { ts: e.toISOString(), started: new Date(e - m * 60000).toISOString(), block: "lessons", minutes: m }; };
const config = (theme, extra = {}) => fs.writeFileSync(sys("config.json"), JSON.stringify({ theme, goals: { day_minutes: 30, week_days: 7 }, ...extra }));
const writeBlocks = (list) => fs.writeFileSync(sys("blocks.jsonl"), list.map((b) => JSON.stringify(b)).join("\n") + "\n");

before(async () => {
  v = makeVault("Tester");
  const older = [], newer = [];
  for (let n = 40; n >= 2; n--) (n > 25 ? older : newer).push(blk(n, 40));   // 39 days over the goal
  writeBlocks(older); config("library");
  server = await startServer(v, await freePort());
  await fetch(server.url + "api/state");                // the library's first sync: 15 books, quietly
  writeBlocks(older.concat(newer)); config("space");
  await fetch(server.url + "api/state");                // the rest arrive in the space station: patches
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

test("day trophies are drawn as real stacks: one drawing per day, ten to a pile, both rooms on one shelf", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector('.room [data-slot="shelf"] .ks-pile');
  const piles = await page.$$eval('.room [data-slot="shelf"] .ks-pile:has(span.ks-i)', (ps) => ps.map((p) => ({   // day piles (dice are links)
    n: p.querySelectorAll(".ks-i svg").length,
    label: p.getAttribute("aria-label"),
    tops: [...p.querySelectorAll(".ks-i")].map((i) => i.getBoundingClientRect().top),
  })));
  const total = piles.reduce((a, p) => a + p.n, 0);
  assert.equal(total, 39, "every day over the goal is a drawn object, not a number");
  assert.ok(piles.every((p) => p.n <= 10), "ten to a pile");
  assert.ok(piles.some((p) => /books?$/.test(p.label)) && piles.some((p) => /mission patch/.test(p.label)), JSON.stringify(piles.map((p) => p.label)));
  const tall = piles.find((p) => p.n === 10);
  assert.ok(Math.max(...tall.tops) - Math.min(...tall.tops) > 30, "a full pile is visibly taller than one item");
  assert.match(await page.$eval('.room [data-slot="shelf"] .ks-sum', (e) => e.innerText), /15 books · .* mission patches/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("dice pile up too: one drawing per finished die, each one opening its own card", async () => {
  const dies = (await (await fetch(server.url + "api/state")).json()).keepsakes.items.filter((i) => i.kind === "die");
  assert.ok(dies.length >= 2, "the history finishes at least two dies");
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector('.room [data-slot="shelf"] .ks-pile a.ks-i');
  const links = await page.$$eval('.room [data-slot="shelf"] .ks-pile a.ks-i', (l) => l.map((a) => ({ href: a.getAttribute("href"), w: a.querySelector("svg").getBoundingClientRect().width })));
  assert.deepEqual(links.map((l) => l.href).sort(), dies.map((d) => "/card?id=" + d.id).sort());
  assert.ok(links.every((l) => l.w >= 20), "each die is drawn full size, not squeezed: " + JSON.stringify(links));
  assert.equal(await page.$$eval('.room [data-slot="shelf"] .ks-one a[href^="/card?id=die-"]', (l) => l.length), 0, "no die stands alone any more");
  await closePage(page);
});

test("a goal met now drops a new trophy onto the shelf, with a line from the room, once", async () => {
  const p1 = await openPage(browser, server.url, { view: "bar" });     // first visit: the old ones are just there
  await p1.waitForSelector(".ks-pile");
  assert.equal(await p1.$$eval(".ks-i.is-new", (l) => l.length), 0, "history doesn't make a fuss");
  await closePage(p1);
  const started = new Date(Date.now() - 41 * 60000).toISOString().replace(/\.\d+Z$/, "Z");
  const r = await fetch(server.url + "api/blocks", { method: "POST", headers: { "Content-Type": "application/json", Origin: server.url.slice(0, -1) },
    body: JSON.stringify({ block: "lessons", minutes: 40, started }) });
  const won = (await r.json()).keepsakes;
  assert.ok(won.some((id) => id.startsWith("day-")), JSON.stringify(won));
  const p2 = await openPage(browser, server.url, { view: "bar" });
  await p2.waitForSelector(".ks-i.is-new");
  await p2.waitForSelector("#toast:not([hidden])");
  assert.match(await p2.$eval("#toast", (e) => e.innerText), /patch/i, "the space station's own words");
  await closePage(p2);
  const p3 = await openPage(browser, server.url, { view: "bar" });
  await p3.waitForSelector(".ks-pile");
  await sleep(300);
  assert.equal(await p3.$$eval(".ks-i.is-new", (l) => l.length), 0, "only once");
  await closePage(p3);
});

test("a week trophy opens its printable card, in the colours of the room it was won in", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  const href = await page.$eval('.room [data-slot="shelf"] .ks-one .ks-art', (a) => a.getAttribute("href"));
  await closePage(page);
  const card = await browser.newPage();
  card.errors = [];
  card.on("pageerror", (e) => card.errors.push(String(e)));
  await card.goto(server.url + href.slice(1), { waitUntil: "networkidle0" });
  assert.ok(await card.$("button[data-print]"));
  assert.ok(await card.$(".card .art svg"));
  assert.match(await card.$eval(".card", (e) => e.innerText), /focused minutes/);
  assert.deepEqual(card.errors, []);
  await card.close();
});

test("the back room and the classic view show the shelf too", async () => {
  const back = await browser.newPage();
  await back.evaluateOnNewDocument(() => { localStorage.setItem("edu.onboarded.v1", "1"); localStorage.setItem("edu.view.v1", "bar"); localStorage.setItem("edu.bar.room.v1", "back"); });
  await back.goto(server.url, { waitUntil: "networkidle0" });
  await back.waitForSelector(".is-back .ks-card .ks-pile");
  await back.close();
  const classic = await openPage(browser, server.url, { view: "classic" });
  await classic.waitForSelector(".ks-card .ks-pile");
  assert.deepEqual(classic.errors, []);
  await closePage(classic);
});
