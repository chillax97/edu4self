// The bar on a real learner's night: 0 min tonight, a 24-night run up to yesterday, three short nights this week,
// no caps. What's left leads tonight, the week's row is on the first screen with short nights filled by their minutes,
// and the line about the next trophy sits with the run, in plain words.
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

test("at 0 min tonight, what's left is the headline and the bar invites you in", async () => {
  realNight();
  const page = await open();
  const t = await page.evaluate(() => {
    const el = document.querySelector('.room [data-slot="tonight"]'), recs = [];
    el.querySelectorAll("*").forEach((e) => {
      const hasText = Array.from(e.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim().length > 0);
      if (hasText) recs.push({ cls: e.className, inTogo: !!e.closest(".bx-togo"), size: parseFloat(getComputedStyle(e).fontSize), text: e.innerText });
    });
    const biggest = recs.reduce((a, b) => (b.size > a.size ? b : a), recs[0]);
    const togo = el.querySelector(".bx-togo"), now = el.querySelector(".bx-now"), invite = el.querySelector(".bx-invite");
    return { biggest,
      togoText: togo ? togo.innerText : "",
      togoSize: togo ? parseFloat(getComputedStyle(togo).fontSize) : 0,
      nowSize: now ? parseFloat(getComputedStyle(now).fontSize) : 0,
      inviteText: invite ? invite.innerText : "",
      inviteShown: !!invite && invite.getBoundingClientRect().height > 0 };
  });
  assert.match(t.togoText, /125 min to tonight's cap/i);
  assert.ok(t.biggest.inTogo, "the largest text is what's left: " + JSON.stringify(t.biggest));
  assert.ok(t.togoSize > t.nowSize, `what's left (${t.togoSize} px) outreads the count (${t.nowSize} px)`);
  assert.ok(t.inviteShown && t.inviteText.trim().length > 0, "an inviting line at 0 min");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("goal met: the gold state and the jar stay, the invite goes", async () => {
  realNight([at(DAY, 18, 90), at(DAY, 20, 40)]);
  const page = await open();
  const met = await page.evaluate(() => {
    const t = document.querySelector('.room [data-slot="tonight"]'), togo = t.querySelector(".bx-togo.is-met");
    return { togoText: togo ? togo.innerText : "", invite: !!t.querySelector(".bx-invite"),
      full: Array.from(t.querySelectorAll(".bx-pips.h i")).every((i) => i.classList.contains("on")) };
  });
  assert.match(met.togoText, /in the jar/i);
  assert.ok(!met.invite, "no invite once the cap is met");
  assert.ok(met.full, "every segment of the meter is full");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("the week's row of nights is on the first screen, and a short night is filled, not just ringed", async () => {
  realNight();
  const page = await open();
  const shortDay = back(1), comingDay = back(-1);
  const w = await page.evaluate((short, coming) => {
    const row = Array.from(document.querySelectorAll('.room [data-slot="week"] .bx-pips.m i'));
    const bg = (e) => e ? getComputedStyle(e, "::before").backgroundImage : "";
    const bottom = Math.max(...row.map((e) => e.getBoundingClientRect().bottom));
    return { bottom, h: innerHeight,
      shortBg: bg(row.find((e) => e.dataset.day === short)),
      comingBg: bg(row.find((e) => e.dataset.day === coming)) };
  }, shortDay, comingDay);
  assert.ok(w.bottom <= w.h, `the week's nights end at ${Math.round(w.bottom)} of ${w.h}`);
  assert.notEqual(w.shortBg, "none", "a short night shows how far it got");
  assert.notEqual(w.shortBg, w.comingBg, "short and not-yet differ in fill");
  assert.equal(w.comingBg, "none", "a night still to come is empty");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("the line about the next trophy sits with the run, in plain words", async () => {
  realNight();
  const page = await open();
  const n = await page.evaluate(() => {
    const next = document.querySelector('.room [data-slot="die"] .bx-next'), streak = document.querySelector('.room [data-slot="streak"]');
    const r = next && next.getBoundingClientRect();
    return { text: next ? next.innerText : "", gap: r ? r.top - streak.getBoundingClientRect().bottom : 0,
      sameBox: !!next && !!next.closest(".bq-run") && next.closest(".bq-run") === streak.closest(".bq-run"),
      bottom: r ? r.bottom : 0, h: innerHeight };
  });
  assert.ok(n.text.trim().length > 0, "the next trophy is said");
  assert.doesNotMatch(n.text, /\bdie\b|\bdice\b|\bdies\b/i, "no 'die' jargon");
  assert.ok(n.sameBox, "it sits in the run's box");
  assert.ok(n.gap >= 0 && n.gap <= 16, `directly under the run, no gap (${Math.round(n.gap)} px)`);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
