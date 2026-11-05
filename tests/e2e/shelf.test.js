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
  const piles = await page.$$eval('.room [data-slot="shelf"] .ks-pile:has(button[data-ks^="day-"])', (ps) => ps.map((p) => ({   // day piles
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
  assert.match(await page.$eval('.room [data-slot="shelf"] .ks-sum', (e) => e.innerText), /15 books, \d+ mission patches: days you reached your daily goal of 30 minutes[\s\S]*: one for every 10 focused hours[\s\S]*Click one/,
    "the caption says what each trophy stands for");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("dice pile up too: one drawing per finished die, each one opening its own card", async () => {
  const dies = (await (await fetch(server.url + "api/state")).json()).keepsakes.items.filter((i) => i.kind === "die");
  assert.ok(dies.length >= 2, "the history finishes at least two dies");
  const page = await openPage(browser, server.url, { view: "bar" });
  const sel = '.room [data-slot="shelf"] .ks-pile button[data-ks^="die-"]';
  await page.waitForSelector(sel);
  const links = await page.$$eval(sel, (l) => l.map((a) => ({ id: a.dataset.ks, w: a.querySelector("svg").getBoundingClientRect().width })));
  assert.deepEqual(links.map((l) => l.id).sort(), dies.map((d) => d.id).sort());
  assert.ok(links.every((l) => l.w >= 20), "each die is drawn full size, not squeezed: " + JSON.stringify(links));
  assert.equal(await page.$$eval('.room [data-slot="shelf"] .ks-one [data-ks^="die-"]', (l) => l.length), 0, "no die stands alone any more");
  await page.click(sel + '[data-ks="die-2"]');
  await page.waitForSelector("#ks-detail:not([hidden])");
  const text = await page.$eval("#ks-detail", (e) => e.innerText);
  assert.match(text, /stands for 10 focused hours/);
  assert.match(text, /die number 2: focused hours 10 to 20/);
  assert.equal(await page.$eval('#ks-detail a[href^="/card"]', (a) => a.getAttribute("href")), "/card?id=die-2", "the printable card is one click on");
  await closePage(page);
});

test("clicking a day trophy shows the day it was earned, stamped in the words of the room it came from", async () => {
  const items = (await (await fetch(server.url + "api/state")).json()).keepsakes.items;
  const book = items.find((i) => i.kind === "day" && i.theme === "library");
  const patch = items.find((i) => i.kind === "day" && i.theme === "space");
  const page = await openPage(browser, server.url, { view: "bar" });        // the space station is the room now
  for (const [it, word] of [[book, "checked out"], [patch, "flown"]]) {
    await page.$eval(`.room [data-slot="shelf"] button[data-ks="${it.id}"]`, (b) => b.click());   // patches fan out; the arrows below reach the hidden ones
    await page.waitForSelector("#ks-detail:not([hidden])");
    const stamp = await page.$eval("#ks-detail .ks-stamp", (e) => e.textContent);
    const date = new Date(it.ts.slice(0, 10) + "T12:00:00").toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
    assert.equal(stamp, word + " " + date, "a book keeps the library's stamp in the space station");
    const text = await page.$eval("#ks-detail", (e) => e.innerText);
    assert.match(text, /stands for a day you reached your daily goal of 30 minutes/);
    assert.match(text, /you studied 40 focused minutes\. The goal is 30/);
    assert.equal(await page.$$eval('#ks-detail a[href^="/card"]', (l) => l.length), 0, "days have no printable card");
    const days = items.filter((i) => i.kind === "day").sort((a, b) => (a.ts < b.ts ? -1 : 1));
    const at = days.findIndex((d) => d.id === it.id);
    assert.match(await page.$eval("#ks-detail .ks-d-nav", (e) => e.innerText), new RegExp(`${at + 1} of ${days.length}`));
    await page.click('#ks-detail .ks-d-nav [aria-label="Later"]');
    assert.match(await page.$eval("#ks-detail .ks-d-nav", (e) => e.innerText), new RegExp(`${at + 2} of ${days.length}`), "the arrows step to the next day");
    await page.keyboard.press("Escape");
    assert.equal(await page.$eval("#ks-detail", (e) => e.hidden), true);
  }
  assert.deepEqual(page.errors, []);
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
  await page.click('.room [data-slot="shelf"] .ks-one .ks-art');
  await page.waitForSelector("#ks-detail:not([hidden])");
  assert.match(await page.$eval("#ks-detail", (e) => e.innerText), /a week you studied on 7 days or more[\s\S]*studied on 7 days\. The goal is 7/i);
  const href = await page.$eval('#ks-detail a[href^="/card"]', (a) => a.getAttribute("href"));
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
  await back.evaluateOnNewDocument(() => { localStorage.setItem("edu.onboarded.v1", "1"); sessionStorage.setItem("edu.giftask.later", "1"); localStorage.setItem("edu.view.v1", "bar"); localStorage.setItem("edu.bar.room.v1", "back"); });
  await back.goto(server.url, { waitUntil: "networkidle0" });
  await back.waitForSelector(".is-back .ks-card .ks-pile");
  await back.close();
  const classic = await openPage(browser, server.url, { view: "classic" });
  await classic.waitForSelector(".ks-card .ks-pile");
  assert.deepEqual(classic.errors, []);
  await closePage(classic);
});
