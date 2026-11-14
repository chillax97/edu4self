// Rest days: a weekday the learner rests on neither breaks the streak nor adds to it, unless a block was
// finished that day, which counts like any other. Both counters (the chalk board and the bartender's
// "N days in a row") use one rule. The page clock is pinned to Sunday 15 Nov 2026, 14:30.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, readJSON } from "./harness.js";

let v, server, browser;
const sys = (f) => path.join(v.vault, "_system", f);
const TODAY = "2026-11-15";   // a Sunday
const REST = ["sat", "sun"];

// a finished block on a calendar day, written by its local date ("2026-11-09" is a Monday)
const on = (ymd) => {
  const [y, m, d] = ymd.split("-").map(Number), end = new Date(y, m - 1, d, 12, 0, 0);
  return { ts: end.toISOString(), started: new Date(end - 25 * 60000).toISOString(), block: "lessons", minutes: 25 };
};
const nov = (...ds) => ds.map((d) => on("2026-11-" + String(d).padStart(2, "0")));
const oct = (...ds) => ds.map((d) => on("2026-10-" + String(d).padStart(2, "0")));
const WEEK = [9, 10, 11, 12, 13];   // Monday to Friday

function setup(blocks, config, theme) {
  fs.writeFileSync(sys("blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + "\n");
  fs.writeFileSync(sys("config.json"), JSON.stringify({ goals: { day_minutes: 30, week_days: 5 }, theme, ...config }));
}
const open = () => openPage(browser, server.url, { view: "bar", hour: 14, date: TODAY });

// the chalk board: [current run, best]
async function board(rest, blocks) {
  setup(blocks, { streak: { rest_days: rest } }, "bar");
  const page = await open();
  try {
    await page.waitForSelector('.room.t-bar [data-slot="streak"] .bx-chalk');
    return [Number(await page.$eval(".bx-chalk .ch-n > span", (e) => e.textContent)), Number(await page.$eval(".bx-chalk .ch-best b", (e) => e.textContent))];
  } finally { await closePage(page); }
}
// the bartender's line, in a room with no board: the number in "N days in a row", or null
async function line(rest, blocks) {
  setup(blocks, { streak: { rest_days: rest } }, "library");
  const page = await open();
  try {
    await page.waitForSelector(".room");
    const m = /(\d+) days in a row/.exec(await page.$eval(".room", (e) => e.textContent));
    return m ? Number(m[1]) : null;
  } finally { await closePage(page); }
}

before(async () => {
  v = makeVault("Tester");
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await closeBrowser(browser);
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

test("Monday to Friday, nothing on the rest weekend, viewed on Sunday: the streak is 5, not 0", async () => {
  assert.deepEqual(await board(REST, nov(...WEEK)), [5, 5]);
});

test("a block on a rest day counts like any other day: Saturday makes it 6", async () => {
  assert.deepEqual(await board(REST, nov(...WEEK, 14)), [6, 6]);
});

test("a missed working day still breaks it: no Wednesday leaves Thursday and Friday", async () => {
  assert.deepEqual(await board(REST, nov(9, 10, 12, 13)), [2, 2]);
});

test("best bridges a rest weekend, and an earlier run does not hide the current one", async () => {
  // two working weeks with a rest weekend between them: one run of 10; then a gap, then Thursday and Friday
  assert.deepEqual(await board(REST, [...oct(26, 27, 28, 29, 30), ...nov(2, 3, 4, 5, 6), ...nov(12, 13)]), [2, 10]);
  // Friday to Monday with a block on the rest Sunday only: Saturday is bridged, Sunday adds one (2..6, 8, 9 = 7)
  assert.deepEqual(await board(REST, nov(2, 3, 4, 5, 6, 8, 9)), [0, 7]);
});

test("a working day with nothing in it is not bridged, whatever surrounds it", async () => {
  assert.deepEqual(await board(REST, [...oct(26, 27, 28, 29), ...nov(2, 3, 4, 5, 6)]), [0, 5], "Friday 30 Oct is missing");
});

test("with no rest days (the default) nothing changes: the weekend breaks the run", async () => {
  assert.deepEqual(await board([], nov(...WEEK)), [0, 5], "Sunday after an empty Saturday: 0 now, 5 as the best");
  assert.deepEqual(await board([], nov(...WEEK, 14)), [6, 6], "a block on Saturday: Monday to Saturday is six, as ever");
  assert.deepEqual(await board([], [...oct(26, 27, 28, 29, 30), ...nov(2, 3, 4, 5, 6)]), [0, 5], "no bridging over the weekend");
  setup(nov(...WEEK), {}, "bar");   // the key never saved
  const page = await open();
  try {
    await page.waitForSelector(".bx-chalk");
    assert.equal(await page.evaluate(() => fetch("/api/config").then((r) => r.json()).then((j) => JSON.stringify(j.config.streak))), '{"rest_days":[]}');
  } finally { await closePage(page); }
});

test("the board and the bartender's line show the same number", async () => {
  for (const blocks of [nov(...WEEK), nov(...WEEK, 14), nov(9, 10, 12, 13)]) {
    const [onBoard] = await board(REST, blocks);
    assert.equal(await line(REST, blocks), onBoard, "same rule in both rooms");
  }
  const [flat] = await board([], nov(...WEEK, 14));
  assert.equal(await line([], nov(...WEEK, 14)), flat, "and with no rest days");
});

test("Settings: tick the rest days, save, and the choice is kept", async () => {
  setup(nov(...WEEK), {}, "bar");
  const page = await open();
  try {
    await page.click("#btn-settings");
    await page.waitForSelector("#settings:not([hidden]) #set-rest");
    assert.equal((await page.$$('input[name="set-rest"]:checked')).length, 0, "none ticked by default");
    for (const d of REST) {
      const sel = 'input[name="set-rest"][value="' + d + '"]';
      await page.$eval(sel, (e) => e.scrollIntoView({ block: "center" }));
      await page.click(sel);
    }
    await page.$eval("#set-save", (e) => e.scrollIntoView({ block: "center" }));
    await page.click("#set-save");
    await page.waitForSelector("#settings", { hidden: true });
    assert.deepEqual(readJSON(sys("config.json")).streak, { rest_days: REST });
    await page.waitForFunction(() => document.querySelector(".bx-chalk .ch-n > span")?.textContent === "5", { timeout: 5000 });
  } finally { await closePage(page); }
});
