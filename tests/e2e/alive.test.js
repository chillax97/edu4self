// The bar, alive: the room is drawn once and patched after that, so a poll restarts nothing; what changed
// is marked (data-new, a one-shot data-event) and gets its sound; the streak sits on the chalk board.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, sleep } from "./harness.js";

let v, server, browser, cfgPath;
const sys = (f) => path.join(v.vault, "_system", f);

before(async () => {
  v = makeVault("Tester");
  cfgPath = sys("config.json");
  // thirteen days in a row up to yesterday, nothing yet today: the streak reads 13, and today's block makes 14
  const blocks = [];
  for (let n = 13; n >= 1; n--) {
    const d = new Date(); d.setDate(d.getDate() - n); d.setHours(12, 0, 0, 0);
    blocks.push({ id: "b" + n, started: d.toISOString(), ts: new Date(d.getTime() + 25 * 60000).toISOString(), block: "lessons", minutes: 25 });
  }
  fs.writeFileSync(sys("blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + "\n");
  fs.writeFileSync(cfgPath, JSON.stringify({ theme: "bar" }));
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

async function open() {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector('.room.t-bar [data-slot="streak"] .bx-chalk', { timeout: 5000 });
  return page;
}
// what the page does when you come back to the tab: one fresh load of the state
const poll = (page) => page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));

test("the streak is on the chalk board, not in a Willpower line", async () => {
  const page = await open();
  try {
    assert.equal(await page.$eval(".bx-chalk .ch-n > span", (e) => e.textContent), "13");
    assert.equal(await page.$eval(".bx-chalk .ch-best b", (e) => e.textContent), "13");
    assert.match(await page.$eval(".bx-chalk", (e) => e.getAttribute("aria-label")), /^13 nights running\. house record: 13\.$/);
    const log = await page.$eval('.room [data-slot="voices"]', (e) => e.textContent);
    assert.doesNotMatch(log, /days in a row/);
    assert.match(await page.$eval(".room", (e) => e.dataset.phase), /^(morning|day|evening|late)$/);
  } finally { await closePage(page); }
});

test("a poll with nothing new rewrites nothing in the room", async () => {
  const page = await open();
  try {
    await poll(page);   // the first poll after opening drops the "new" flag from lines you've now seen, once
    await sleep(800);
    await page.evaluate(() => { document.querySelectorAll(".room [data-slot] *").forEach((e) => { e.__kept = true; }); });
    await poll(page);
    await sleep(800);
    const lost = await page.evaluate(() => [...document.querySelectorAll('.room [data-slot]:not([data-slot="clock"]):not([data-slot="block"]):not([data-slot="music"]) *')].filter((e) => !e.__kept).length);
    assert.equal(lost, 0, "elements were redrawn by a poll that changed nothing");
  } finally { await closePage(page); }
});

test("a new block: fuel, week tile and stones are marked new, the board draws day 14, a milestone, and each logs its sound", async () => {
  const page = await open();
  try {
    await page.evaluate(() => { window.__roomSounds = []; });
    const started = new Date(Date.now() - 45 * 60000).toISOString();
    const r = await page.evaluate((s) => fetch("/api/blocks", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ block: "lessons", minutes: 40, started: s }) }).then((x) => x.status), started);
    assert.ok(r === 200 || r === 201, "block saved: " + r);
    await poll(page);
    await page.waitForFunction(() => document.querySelector(".bx-chalk .ch-n > span")?.textContent === "14", { timeout: 5000 });
    assert.equal(await page.$$eval('.room [data-slot="tonight"] .bx-pips i[data-new]', (l) => l.length), 2, "40 minutes is two new fuel segments");
    assert.equal(await page.$$eval('.room [data-slot="week"] .bx-pips i[data-new]', (l) => l.length), 1);
    assert.ok(await page.$$eval('.room [data-slot="die"] .die i[data-new]', (l) => l.length) >= 1);
    assert.ok(await page.$(".bx-chalk .ch-s[data-new]"), "the new chalk stroke");
    assert.ok(await page.$(".bx-chalk .ch-ul"), "14 is a milestone: underlined");
    assert.ok(await page.$(".bx-chalk .ch-star[data-new]"), "14 beats the best of 13");
    assert.equal(await page.$eval(".bx-chalk .ch-best b", (e) => e.textContent), "14");
    assert.match(await page.$eval(".room", (e) => e.dataset.event || ""), /\bmile\b/);
    await sleep(1200);
    const names = await page.evaluate(() => window.__roomSounds.map((s) => s.name));
    for (const n of ["fuel", "week", "stone", "scratch", "tap", "underline", "star"]) assert.ok(names.includes(n), n + " sound: " + names.join(","));
  } finally { await closePage(page); }
});

test("room sounds are off until Settings turns them on, and saving keeps the choice", async () => {
  const page = await open();
  try {
    await page.evaluate(() => document.querySelector("#btn-settings").click());
    await page.waitForSelector("#set-room-sounds", { timeout: 5000 });
    assert.equal(await page.$eval("#set-room-sounds", (e) => e.checked), false);
    const c = await page.evaluate(() => fetch("/api/config").then((r) => r.json()));
    assert.equal(c.config.room_sounds, false);
  } finally { await closePage(page); }
  fs.writeFileSync(cfgPath, JSON.stringify({ theme: "bar", room_sounds: true }));
  const page2 = await open();
  try {
    await page2.evaluate(() => document.querySelector("#btn-settings").click());
    await page2.waitForSelector("#set-room-sounds", { timeout: 5000 });
    assert.equal(await page2.$eval("#set-room-sounds", (e) => e.checked), true);
  } finally { await closePage(page2); }
});
