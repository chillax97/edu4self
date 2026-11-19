// The bar's right hand: tonight's goal by the jukebox, big and on the first screen, with what's left said in
// the bar's words and a one-shot pour when a block ends; the week as nights at the bar (won, studied short,
// missed, tonight, still to come), told apart by shape; the house record spoken only when it's in reach.
// The page clock is pinned to Thursday 2026-11-19, 20:30, and every block is dated against it.
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
const poll = (page) => page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));

before(async () => { v = makeVault("Kim"); server = await startServer(v, await freePort()); browser = await launch(); });
after(async () => { await browser?.close(); await stopServer(server); fs.rmSync(v.dir, { recursive: true, force: true }); });

// where tonight sits and how it reads
const tonightBox = (page) => page.evaluate(() => {
  const el = document.querySelector('.room [data-slot="tonight"]'), r = el.getBoundingClientRect();
  const now = el.querySelector(".bx-togo .bx-left"), meter = el.querySelector(".bx-pips.h"), juke = document.querySelector(".room .bq-juke").getBoundingClientRect();
  return { top: r.top, bottom: r.bottom, h: innerHeight, below: r.top - juke.bottom,
    big: now ? parseFloat(getComputedStyle(now).fontSize) : 0, meterW: meter ? meter.getBoundingClientRect().width : 0,
    meterShown: !!meter && getComputedStyle(meter).display !== "none", text: el.innerText.replace(/\s+/g, " ") };
});

for (const long of [false, true]) {
  test(`tonight's goal by the jukebox, on the first screen, big, with progress and what's left (${long ? "a long day" : "a short day"})`, async () => {
    if (long) seedLongDay(v.vault, { theme: "bar" });
    blocks([at(DAY, 19, 50)]);
    config();
    const page = await open();
    const t = await tonightBox(page);
    assert.ok(t.top >= 0 && t.bottom <= t.h, `tonight is fully on the first screen: ${Math.round(t.top)}..${Math.round(t.bottom)} of ${t.h}`);
    assert.ok(t.below >= 0 && t.below <= 48, `tonight sits right under the jukebox (${Math.round(t.below)} px)`);
    assert.ok(t.big >= 32, `what's left reads at a glance (${t.big} px)`);
    assert.ok(t.meterShown && t.meterW >= 240, `a meter shows the way to the goal (${Math.round(t.meterW)} px)`);
    assert.match(t.text, /50 of 125 min/);
    assert.match(t.text, /75 min to tonight's cap/i, "what's left, in the bar's words");
    assert.deepEqual(page.errors, []);
    await closePage(page);
  });
}

test("tonight's goal met: the meter is full and the bar says the cap is won", async () => {
  blocks([at(DAY, 18, 90), at(DAY, 20, 40)]);
  config();
  const page = await open();
  const t = await tonightBox(page);
  assert.match(t.text, /130 of 125 min/);
  assert.match(t.text, /cap/i);
  assert.doesNotMatch(t.text, /min to tonight's cap/i);
  const full = await page.$$eval('.room [data-slot="tonight"] .bx-pips.h i', (l) => l.every((i) => i.classList.contains("on")));
  assert.ok(full, "every segment of the meter is full");
  await closePage(page);
});

test("a block that ends moves the meter once, and nothing in the rail moves forever", async () => {
  blocks([at(DAY, 17, 30)]);
  config();
  const page = await open();
  assert.match((await tonightBox(page)).text, /95 min to tonight's cap/i);
  fs.appendFileSync(sys("blocks.jsonl"), JSON.stringify(at(DAY, 20, 50)) + "\n");
  await poll(page);
  await page.waitForFunction(() => /80 of 125/.test(document.querySelector('.room [data-slot="tonight"]').innerText));
  const moved = await page.$$eval('.room [data-slot="tonight"] .bx-pips.h i[data-new]', (l) => l.length);
  assert.ok(moved >= 1, "the segments the block filled are marked new");
  const anim = await page.evaluate(() => document.getAnimations().filter((a) => a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('[data-slot="tonight"]'))
    .map((a) => a.effect.getComputedTiming().iterations));
  assert.ok(anim.length >= 1, "the new segments pour in");
  assert.ok(anim.every((n) => n !== Infinity), "the pour plays once");
  await sleep(1500);
  const endless = await page.evaluate(() => document.getAnimations().filter((a) => { const t = a.effect && a.effect.target;
    return t && t.nodeType === 1 && t.closest(".bq-rail") && !t.closest('[data-part~="running"]') && a.playState === "running" && a.effect.getComputedTiming().iterations === Infinity; }).length);
  assert.equal(endless, 0, "no endless motion in the rail");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("this week as nights at the bar: won, studied short, missed, tonight and still to come look different, not by colour alone", async () => {
  // Mon won (130 min), Tue studied short (30), Wed missed, Thu tonight (20 so far), Fri to come
  blocks([at(back(3), 20, 130), at(back(2), 20, 30), at(DAY, 19, 20)]);
  config();
  const page = await open();
  const look = await page.$$eval('.room [data-slot="week"] .bx-pips.m i', (l) => l.map((e) => {
    const b = getComputedStyle(e, "::before"), a = getComputedStyle(e, "::after"), d = e.querySelector(".bx-d");
    return { day: e.dataset.day, cls: e.className,
      shape: [!!e.querySelector(".bx-daycap svg"), b.display, b.borderTopStyle, b.borderTopWidth, a.content, a.display, getComputedStyle(d).opacity, getComputedStyle(d).fontWeight, getComputedStyle(d).textDecorationLine].join("|") };
  }));
  const [mon, tue, wed, thu, fri] = look;
  assert.ok(mon.shape.startsWith("true"), "Monday's cap is drawn: " + mon.cls);
  const kinds = { won: mon.shape, short: tue.shape, missed: wed.shape, tonight: thu.shape, coming: fri.shape };
  assert.equal(new Set(Object.values(kinds)).size, 5, "five states, five looks without colour: " + JSON.stringify(kinds, null, 1));
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

// the house record: a past run of five nights a month ago, then the current run
async function recordLine(run) {
  const list = [];
  for (let n = 40; n > 35; n--) list.push(at(back(n), 20, 30));      // five nights in a row, long ago: the record
  for (let n = run - 1; n >= 0; n--) list.push(at(back(n), n === 0 ? 19 : 20, 30));   // the current run, up to tonight
  blocks(list);
  config();
  const page = await open();
  const said = await page.$eval('.room [data-slot="streak"]', (e) => { const r = e.querySelector(".bx-record"); return r && r.getBoundingClientRect().height > 0 ? r.innerText : ""; });
  await closePage(page);
  return said;
}

test("the house record speaks only when it's in reach", async () => {
  assert.equal(await recordLine(3), "", "two nights short: quiet");
  assert.match(await recordLine(4), /one more night/i, "one short of the record");
  const tie = await recordLine(5);
  assert.match(tie, /tied/i);
  assert.match(tie, /one more night and it's yours/i);
  assert.match(await recordLine(6), /new house record/i, "past the record");
});
