// The bar as a place: you look down at the counter. The sign earns its light, the caps are this week's real
// keepsakes, the glass sits with its water line, and the room ends tidily with or without a follow-up.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON } from "./harness.js";

let v, server, browser;
const sys = (...p) => path.join(v.vault, "_system", ...p);
const ymd = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const monday = () => { const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return d; };
const weekDay = (i) => { const d = monday(); d.setDate(d.getDate() + i); return d; };
const block = (d, minutes) => ({ id: "b" + d.getTime() + minutes, ts: d.toISOString(), started: new Date(d.getTime() - minutes * 60000).toISOString(), block: "lessons", minutes });

// a fresh record: these blocks and the trophies they earn, nothing left from the test before
function seed(blocks, theme = "bar") {
  fs.writeFileSync(sys("blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + (blocks.length ? "\n" : ""));
  fs.rmSync(sys("keepsakes.json"), { force: true });
  fs.writeFileSync(sys("config.json"), JSON.stringify({ theme, goals: { day_minutes: 45, week_days: 4 } }));
}
const today = () => { const d = new Date(); d.setHours(0, 30, 0, 0); return d; };
const open = async (opts = {}) => { const page = await openPage(browser, server.url, { view: "bar", width: 1440, height: 900, room: "front", ...opts }); await page.waitForSelector(".room .bq-book, .room:not(.t-bar)"); return page; };
const dayCaps = async () => (await (await fetch(server.url + "api/state")).json()).keepsakes.items.filter((k) => k.kind === "day").map((k) => k.date).sort();
const caps = (page) => page.$$eval('.room [data-slot="week"] .bx-pips.m i', (l) => l.map((e) => ({ day: e.dataset.day, cap: !!e.querySelector(".bx-daycap svg"), letter: e.querySelector(".bx-d").textContent, on: e.classList.contains("on"), top: Math.round(e.getBoundingClientRect().top) })));

before(async () => { v = makeVault("Kim"); server = await startServer(v, await freePort()); browser = await launch(); });
after(async () => { await browser?.close(); await stopServer(server); fs.rmSync(v.dir, { recursive: true, force: true }); });

const sign = (page) => page.$eval(".room .bx-neon", (e) => ({ lit: e.classList.contains("is-lit"), glow: getComputedStyle(e).textShadow !== "none" }));

test("the sign stays dim until tonight's goal is met", async () => {
  seed([block(today(), 20)]);
  const page = await open();
  assert.deepEqual(await sign(page), { lit: false, glow: false });
  assert.equal(await page.$(".room .bx-lit-line"), null, "the bartender says nothing yet");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("the sign lights when tonight's goal is met, with the bartender's line", async () => {
  seed([block(today(), 50)]);
  const page = await open();
  assert.deepEqual(await sign(page), { lit: true, glow: true });
  const line = await page.$eval(".room .bx-lit-line", (e) => e.innerText);
  assert.match(line, /bartender/i);
  assert.match(line, /goal/i);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("no keepsakes this week: seven bare places, no caps, and the line says so", async () => {
  const last = weekDay(-3);
  seed([block(last, 50)]);   // last week's cap stays in the back room
  const page = await open();
  const c = await caps(page);
  assert.equal(c.length, 7);
  assert.equal(c.filter((x) => x.cap).length, 0);
  assert.deepEqual(c.map((x) => x.letter), [..."MTWTFSS"]);
  assert.match(await page.$eval('.room [data-slot="week"]', (e) => e.innerText), /no bottle caps yet/i);
  await closePage(page);
});

test("some days: a cap exactly on the days with a real keepsake, left loosely, each day still named", async () => {
  seed([block(weekDay(0), 50), block(weekDay(2), 50), block(weekDay(4), 20)]);   // the 20 minutes showed up but won nothing
  const page = await open();
  const c = await caps(page), real = await dayCaps();
  assert.deepEqual(c.filter((x) => x.cap).map((x) => x.day), real);
  assert.deepEqual(real, [ymd(weekDay(0)), ymd(weekDay(2))]);
  assert.ok(c[4].on && !c[4].cap, "a day studied below the goal is marked, without a cap");
  assert.ok(new Set(c.map((x) => x.top)).size >= 3, "not a neat row");
  // told apart by shape as well as colour: a cap is a drawing, a bare day is a ring with no drawing
  const looks = await page.$$eval('.room [data-slot="week"] .bx-pips.m i', (l) => l.map((e) => getComputedStyle(e, "::before").borderTopStyle));
  assert.equal(looks[1], "dashed", "a bare day is a dashed ring");
  assert.equal(looks[4], "solid", "a day studied is a solid ring");
  assert.match(await page.$eval('.room [data-slot="week"]', (e) => e.innerText), /2 bottle caps/i);
  await page.click(`.room [data-ks="day-${real[0]}"]`);
  await page.waitForSelector("#ks-detail:not([hidden])");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("the whole week earned: seven caps", async () => {
  seed([0, 1, 2, 3, 4, 5, 6].map((i) => block(weekDay(i), 50)));
  const page = await open();
  const c = await caps(page);
  assert.deepEqual(c.filter((x) => x.cap).map((x) => x.day), await dayCaps());
  assert.equal(c.filter((x) => x.cap).length, 7);
  await closePage(page);
});

test("the glass sits with its water line and Drank it, and drinking empties it", async () => {
  seed([]);
  const page = await open({ block: true });
  await page.evaluate(() => { const b = JSON.parse(localStorage.getItem("edu.block.v1")); b.served = 1; b.drunk = 0; localStorage.setItem("edu.block.v1", JSON.stringify(b)); window.dispatchEvent(new StorageEvent("storage", { key: "edu.block.v1" })); });   // as another tab would
  await page.waitForSelector(".room .bx-round .bx-glass.full");
  assert.equal(await page.$(".room .bq-juke .blk-water"), null, "the water line is not repeated in the jukebox");
  const box = await page.$eval(".room .bx-round", (r) => {
    const R = r.getBoundingClientRect(), inside = (s) => { const b = r.querySelector(s).getBoundingClientRect(); return b.width > 0 && b.left >= R.left - 1 && b.right <= R.right + 1 && b.top >= R.top - 1 && b.bottom <= R.bottom + 1; };
    return { glass: inside(".bx-glass"), text: inside("[data-water-text]"), btn: inside(".btn[data-drink]"), words: r.innerText };
  });
  assert.deepEqual([box.glass, box.text, box.btn], [true, true, true]);
  assert.match(box.words, /glass is waiting/i);
  assert.doesNotMatch(box.words, /💧/);
  await page.click(".room .bx-round .btn[data-drink]");
  await page.waitForFunction(() => !document.querySelector(".room .bx-glass").classList.contains("full"));
  assert.equal(await page.$eval(".room .bx-round .btn[data-drink]", (b) => b.hidden), true);
  assert.match(await page.$eval(".room .bx-round [data-water-text]", (e) => e.textContent), /1 of 1 drunk/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("no follow-up: the replies take the right page, the rest fold into one button, and both columns end together", async () => {
  seed([block(today(), 20)]);
  const page = await open();
  const g = await page.evaluate(() => {
    const r = (s) => document.querySelector(s).getBoundingClientRect(), book = r(".room .bq-pages"), list = r('.room [data-slot="replies"]');
    return { right: list.left > book.left + book.width / 2 - 1, mat: r(".room .bq-mat").bottom, rail: r(".room .bq-rail").bottom,
      brackets: /\[/.test(document.querySelector('.room [data-slot="replies"]').innerText),
      shown: [...document.querySelectorAll('.room [data-slot="replies"] li')].filter((l) => l.getBoundingClientRect().height > 0).length,
      all: document.querySelectorAll('.room [data-slot="replies"] li').length };
  });
  assert.ok(g.right, "on the right page");
  assert.ok(Math.abs(g.mat - g.rail) <= 1, `both columns end on one line (${g.mat}, ${g.rail})`);
  assert.equal(g.brackets, false);
  assert.ok(g.shown < g.all, "the other things are folded");
  await page.click('.room [data-replies-more]');
  assert.equal(await page.$$eval('.room [data-slot="replies"] li', (l) => l.every((e) => e.getBoundingClientRect().height > 0)), true);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("the next die is said in plain words, and every text is on the bar's type scale", async () => {
  seed([block(today(), 50)]);
  const page = await open();
  const die = await page.$eval('.room [data-slot="die"]', (e) => e.innerText);
  assert.match(die, /about 9 hours more at the bar earns your next die/i);
  assert.doesNotMatch(die, /25-minute|slot per|#1/);
  const sizes = await page.evaluate(() => { const out = new Set(), w = document.createTreeWalker(document.querySelector(".room"), NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) { const e = n.parentElement; if (n.textContent.trim() && e.getBoundingClientRect().width > 0 && !e.closest("[aria-hidden=true]")) out.add(parseFloat(getComputedStyle(e).fontSize)); } return [...out]; });
  assert.deepEqual(sizes.filter((s) => ![12, 14, 17, 22, 32, 48].includes(s)), []);
  await closePage(page);
});

test("another room keeps its own water line and its plain week", async () => {
  seed([block(weekDay(0), 50)], "library");
  const page = await open({ block: true });
  assert.ok(await page.$(".room.t-library"));
  assert.equal(await page.$(".room .bx-round"), null);
  assert.ok(await page.$(".room .blk-water [data-water-text]"), "the line is in the block card");
  assert.equal(await page.$('.room [data-slot="week"] svg'), null);
  assert.match(await page.$eval('.room [data-slot="replies"]', (e) => e.innerText), /\[/, "its replies keep their brackets");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
