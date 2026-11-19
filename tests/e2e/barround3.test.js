// The bar on a real learner's night, round 3: the week's nights sit on one line, and the line about the next trophy is a
// quieter line under the house record, set apart from it.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, sleep } from "./harness.js";
import { seedLongDay } from "./longday.js";

const DAY = "2026-11-19";   // a Thursday
let v, server, browser;
const sys = (f) => path.join(v.vault, "_system", f);
const at = (ymd, h, minutes) => { const d = new Date(ymd + "T00:00:00"); d.setHours(h, 0, 0, 0);
  return { id: "b" + ymd + h + minutes, ts: d.toISOString(), started: new Date(d.getTime() - minutes * 60000).toISOString(), block: "lessons", minutes }; };
const back = (n) => { const d = new Date(DAY + "T12:00:00"); d.setDate(d.getDate() - n); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
function blocks(list) {
  fs.writeFileSync(sys("blocks.jsonl"), list.map((b) => JSON.stringify(b)).join("\n") + (list.length ? "\n" : ""));
  fs.rmSync(sys("keepsakes.json"), { force: true });
}
function config(extra = {}) {
  const c = readJSON(sys("config.json"));
  fs.writeFileSync(sys("config.json"), JSON.stringify({ ...c, theme: "bar", goals: { day_minutes: 125, week_days: 4 }, ...extra }));
}
const open = async () => {
  const page = await openPage(browser, server.url, { view: "bar", width: 1440, height: 900, room: "front", hour: 20, date: DAY });
  await page.waitForSelector('.room.t-bar [data-slot="tonight"] .bx-pips');
  return page;
};

before(async () => { v = makeVault("Kim"); server = await startServer(v, await freePort()); browser = await launch(); });
after(async () => { await browser?.close(); await stopServer(server); fs.rmSync(v.dir, { recursive: true, force: true }); });

// a real learner's night: the house record a month back, then a 24-night run up to yesterday, three of them short,
// tonight still at 0, and no caps this week
function realNight(extra = []) {
  seedLongDay(v.vault, { theme: "bar" });
  const list = [];
  for (let n = 40; n >= 36; n--) list.push(at(back(n), 20, 30));       // an old 5-night run: the house record to beat
  for (let n = 24; n >= 1; n--) list.push(at(back(n), 20, n <= 3 ? 30 : 140));   // the run up to yesterday, three short
  blocks([...list, ...extra]);
  config();
}

test("the week's nights sit on one line, still on the first screen", async () => {
  realNight();
  const page = await open();
  const w = await page.evaluate(() => {
    const rects = Array.from(document.querySelectorAll('.room [data-slot="week"] .bx-pips.m i')).map((e) => e.getBoundingClientRect());
    const centres = rects.map((r) => (r.top + r.bottom) / 2);
    return { centres, bottom: Math.max(...rects.map((r) => r.bottom)), h: innerHeight, n: rects.length };
  });
  assert.equal(w.n, 7);
  assert.ok(Math.max(...w.centres) - Math.min(...w.centres) <= 1, "every night's centre within 1 px: " + JSON.stringify(w.centres.map(Math.round)));
  assert.ok(w.bottom <= w.h, `the row ends at ${Math.round(w.bottom)} of ${w.h}`);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("the house record stays the moment; the next trophy is a quieter line set apart under it", async () => {
  realNight();
  const page = await open();
  const t = await page.evaluate(() => {
    const rec = document.querySelector('.room [data-slot="streak"] .bx-record');
    const next = document.querySelector('.room [data-slot="die"] .bx-next');
    if (!rec || !next) return { recText: null, nextStyle: null, nextSize: null, recSize: null, gap: null };
    return {
      recText: rec.innerText,
      nextStyle: getComputedStyle(next).fontStyle,
      nextSize: parseFloat(getComputedStyle(next).fontSize),
      recSize: parseFloat(getComputedStyle(rec).fontSize),
      gap: next.getBoundingClientRect().top - rec.getBoundingClientRect().bottom
    };
  });
  assert.match(t.recText, /house record/i, "the record line speaks on this night");
  assert.notEqual(t.nextStyle, "italic", "the trophy line is not italic");
  assert.ok(t.nextSize < t.recSize, `the trophy line (${t.nextSize} px) is smaller than the record (${t.recSize} px)`);
  assert.ok(t.gap >= 12, `at least 12 px between them (${t.gap} px)`);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
