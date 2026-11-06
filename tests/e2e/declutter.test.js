// The job comes first: a long grade note, six chatty voices and a full night of stats must not push the
// next task down the page, in any room, while every voice stays on screen and opens in place.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON } from "./harness.js";

const ROOMS = fs.readdirSync(path.join(ENGINE, "app", "dashboard", "themes")).sort();
const TITLE = "How big is one word's cache, for a model you haven't seen?";
const RULES = "Questions 1 to 4: closed book. No lesson, no refresher, no code, no AI. A calculator is fine.";
const SENTENCE = "The questions are the win, and the habit is the thing to fix before the next run starts";
const BODY = Array.from({ length: 14 }, () => SENTENCE + ".").join(" ") + " Up next: recall check 06.";   // ~210 words
const VOICES = [
  ["logic", "doubled([]) raises nothing at the call. The body waits for the first next(). Right, and right for the right reason."],
  ["encyclopedia", "yield words hands out a label, not a copy. Three labels, one list, filled to the end by the time anyone looks."],
  ["critic", "items[0], len(items), three runs in a row. The spec's type box said no len(), no [i]. You knew it closed book. Your hands didn't."],
  ["physical", "Six runs on first_long_words. The 19:43 one only lacked the guard. Then you changed two things at once and lost nine minutes."],
  ["gpu", "The join waits for the whole answer before showing a word. That's the thing streaming exists to avoid. The buffer version is how a server does it."],
  ["volition", "Frustrated and done beats calm and stuck. Twenty-five runs, every one saved, all of it graded."],
];
// the room's own lines that only restated a stat or the job, before the declutter
const ECHOES = [/Up next/, /minutes in\b|The goal was|on the clock tonight/, /nights this week|The week's already won/, /\bof 24\b|is blank/, /steps\. At /];
let v, server, browser, cfgPath;

before(async () => {
  v = makeVault("Tester");
  cfgPath = path.join(v.vault, "_system", "config.json");
  const sys = (f) => path.join(v.vault, "_system", f);
  // fourteen days in a row (a long streak), 150 minutes tonight (goal met), a die partly etched
  const blocks = [], now = Date.now();
  for (let n = 13; n >= 1; n--) {
    const d = new Date(); d.setDate(d.getDate() - n); d.setHours(19, 0, 0, 0);
    blocks.push({ id: "b" + n, started: d.toISOString(), ts: new Date(d.getTime() + 50 * 60000).toISOString(), block: "lessons", minutes: 50 });
  }
  for (let i = 0; i < 3; i++) {
    const end = now - (5 + i * 51) * 60000;
    blocks.push({ id: "t" + i, started: new Date(end - 50 * 60000).toISOString(), ts: new Date(end).toISOString(), block: "lessons", minutes: 50 });
  }
  fs.writeFileSync(sys("blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + "\n");
  const st = readJSON(sys("state.json")), t = st.topics[0];
  t.milestones[0].steps[0].done = true;
  Object.assign(t.queue[0], { title: TITLE, rules: RULES });
  st.coach = { date: "2026-11-06", headline: "Python 03b: 21/21, no hints, both trick questions right.", body: BODY,
    voices: VOICES.map(([voice, text]) => ({ voice, text })) };
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  fs.writeFileSync(cfgPath, JSON.stringify({ goals: { day_minutes: 120, week_days: 4 } }));
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

function setConfig(extra) { fs.writeFileSync(cfgPath, JSON.stringify({ ...readJSON(cfgPath), ...extra })); }

async function openRoom(id, w, h) {
  setConfig({ theme: id });
  const page = await openPage(browser, server.url, { view: "bar", width: w, height: h });
  await page.waitForSelector(".room.t-" + id + ' [data-fold="claude-5"]', { timeout: 5000 });
  await page.evaluate(() => document.fonts.ready);
  // the lines fade in one after another; measure once they've all landed
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running" || !a.effect?.target?.closest?.(".bx-log")), { timeout: 5000 });
  return page;
}

for (const id of ROOMS) {
  for (const [w, h, label, limit] of [[1440, 1000, "desktop", 700], [390, 844, "phone", 1266]]) {
    test(`${id} on a ${label}: the job starts within ${limit}px under a long note, and every voice is still there`, async () => {
      const page = await openRoom(id, w, h);
      const top = await page.$eval('.room [data-slot="job"] .bx-job', (e) => Math.round(e.getBoundingClientRect().top + scrollY));
      assert.ok(top <= limit, `${id} ${label}: the job starts at ${top}px, over ${limit}px`);
      assert.match(await page.$eval('.room [data-slot="job"]', (e) => e.textContent), /haven't seen\?/);
      // the room's own lines (not Claude's note and voices) say nothing the screen already says
      const log = await page.$$eval('.room [data-slot="voices"] .bx-line:not([data-fold="coach"]):not([data-fold^="claude-"])', (ls) => ls.map((l) => l.textContent).join("\n"));
      for (const re of ECHOES) assert.doesNotMatch(log, re, `${id}: a line repeats what's on screen (${re})`);
      assert.doesNotMatch(log, /\?\./, "no stray full stop after a question mark");
      // the host's note and all six voices: the name is on screen, not folded away
      const names = await page.$$eval('.room [data-fold="coach"], .room [data-fold^="claude-"]', (ls) => ls.map((l) => {
        const who = l.querySelector(".bx-who"), box = (l.querySelector(".fold:not(.fold-2)") || l).getBoundingClientRect(), r = who.getBoundingClientRect();
        return { name: who.textContent, shown: r.width > 0 && r.height > 0 && r.top >= box.top - 1 && r.bottom <= box.bottom + 1 && getComputedStyle(who).visibility !== "hidden" };
      }));
      assert.equal(names.length, 7, "the host and six voices");
      for (const n of names) assert.ok(n.shown, `${id}: ${n.name}'s name is cut off`);
      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  }

  test(`${id}: a folded line opens in place on a click or Enter, and the note's "more" shows all of it`, async () => {
    const page = await openRoom(id, 1440, 1000);
    const state = (sel) => page.$eval(sel, (l) => { const f = l.querySelector(".fold"); return { cut: f.scrollHeight > f.clientHeight + 1, clip: l.hasAttribute("data-clip"), expanded: l.getAttribute("aria-expanded"), text: f.innerText }; });
    const critic = '.room [data-fold="claude-2"]';
    let s = await state(critic);
    assert.ok(s.clip && s.cut, `${id}: the critic's long line is folded`);
    assert.equal(s.expanded, "false");
    await page.click(critic);
    s = await state(critic);
    assert.ok(!s.cut, "opened: nothing is cut off");
    assert.equal(s.expanded, "true");
    assert.match(s.text, /Your hands didn't\./);
    await page.click(critic);
    assert.ok((await state(critic)).cut, "a second click folds it again");
    // the keyboard: Tab to a line and press Enter
    await page.focus('.room [data-fold="claude-4"]');
    await page.keyboard.press("Enter");
    assert.ok(!(await state('.room [data-fold="claude-4"]')).cut, "Enter opens it");
    // the note: headline always shown, the rest behind "more"
    const more = '.room [data-fold="coach"] .fold-more';
    assert.equal(await page.$eval(more, (b) => b.hidden), false);
    assert.equal(await page.$eval(more, (b) => b.textContent), "more");
    assert.ok((await state('.room [data-fold="coach"]')).cut);
    await page.click(more);
    const c = await state('.room [data-fold="coach"]');
    assert.ok(!c.cut, "more shows the whole note");
    assert.match(c.text, /Up next: recall check 06\./);
    assert.equal(await page.$eval(more, (b) => b.textContent), "less");
    assert.deepEqual(page.errors, []);
    await closePage(page);
  });

  test(`${id}: the Rules line is readable (contrast at least 4.5:1)`, async () => {
    const page = await openRoom(id, 1440, 1000);
    const ratio = await page.$eval('.room [data-slot="job"] .bx-rules', (el) => {
      const parse = (c) => { const m = c.match(/[\d.]+/g); if (!m) return null; const k = c.startsWith("color(") ? 255 : 1; return { r: m[0] * k, g: m[1] * k, b: m[2] * k, a: m[3] === undefined ? 1 : +m[3] }; };
      const over = (t, u) => ({ r: t.r * t.a + u.r * (1 - t.a), g: t.g * t.a + u.g * (1 - t.a), b: t.b * t.a + u.b * (1 - t.a), a: 1 });
      const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
      // the colours behind it, blended up the tree to the first solid one (a picture counts as its base colour)
      const layers = [];
      for (let e = el; e; e = e.parentElement) { const bg = parse(getComputedStyle(e).backgroundColor); if (bg && bg.a > 0) layers.push(bg); if (bg && bg.a >= 1) break; }
      let bg = { r: 255, g: 255, b: 255, a: 1 };
      for (let i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg);
      const fg = over(parse(getComputedStyle(el).color), bg), L1 = lum(fg), L2 = lum(bg);
      return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    });
    assert.ok(ratio >= 4.5, `${id}: Rules text contrast is ${ratio.toFixed(2)}:1`);
    await closePage(page);
  });
}

test("classic view: the coach card shows two lines of a long note and opens on more", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector('.coach[data-fold="coach"] .fold-more:not([hidden])', { timeout: 5000 });
  const cut = () => page.$eval(".coach .fold", (f) => f.scrollHeight > f.clientHeight + 1);
  assert.ok(await cut(), "the long note is folded");
  await page.click(".coach .fold-more");
  assert.ok(!(await cut()), "more opens it");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

for (const id of ROOMS) {
  test(`${id}: each character speaks once, and Claude's voices win over the room's own lines`, async () => {
    const page = await openRoom(id, 1440, 1000);
    const names = await page.$$eval('.room [data-slot="voices"] .bx-line .bx-who', (ws) => ws.map((w) => w.textContent.trim()));
    assert.equal(new Set(names).size, names.length, `${id} repeats a character: ${names.join(", ")}`);
    // Willpower and the Body have a grade voice here and room lines of their own (the streak, water); the grade's wins
    const log = await page.$eval('.room [data-slot="voices"]', (e) => e.textContent);
    assert.match(log, /Frustrated and done beats calm and stuck/);
    assert.match(log, /Six runs on first_long_words/);
    assert.deepEqual(page.errors, []);
    await closePage(page);
  });
}
