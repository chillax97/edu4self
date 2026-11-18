// The front-room budget: what every room (and classic) shows on its first screen. The next step and its one
// action, the block's countdown once, and nothing that moves forever except the "a block is running" signal.
// The rest (finish line, locked tasks, trophies, the other voices) is one click away and must still be there.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, sleep } from "./harness.js";

const ROOMS = fs.readdirSync(path.join(ENGINE, "app", "dashboard", "themes")).sort();
const VIEWS = [["classic", "classic"], ...ROOMS.map((id) => [id, "bar"])];
const SIZES = [[1440, 900, "desktop"]];   // the dashboard is a desktop page
let v, server, browser, cfgPath;
const sys = (...p) => path.join(v.vault, "_system", ...p);
const day = (n, h = 19) => { const d = new Date(); d.setDate(d.getDate() - n); d.setHours(h, 0, 0, 0); return d; };
const ymd = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

function setConfig(extra) { fs.writeFileSync(cfgPath, JSON.stringify({ ...readJSON(cfgPath), ...extra })); }

// The busiest everyday state: Claude's note with voices, a follow-up question on Up next, a locked task, a
// finish line with a pace, trophies on the shelf, and (per test) a block running on the Up next task.
function seed({ followUp }) {
  const st = readJSON(sys("state.json")), t = st.topics[0], task = t.queue[0];
  t.milestones[0].steps[0].done = true;
  t.queue.push({ id: "later-1", kind: "checkpoint", status: "locked", label: "Recall check", title: "Retrieval, a few days later", unlock: "Opens on Friday." });
  st.coach = { date: ymd(day(1)), headline: "A good first week. One slip, easy to fix.",
    body: "You explained retrieval in your own words. Next is the probe, which tells Claude where to aim.",
    voices: [{ voice: "critic", text: "You said 'remembering' where you meant 'recalling'. Small, but it matters." },
      { voice: "logic", text: "Storage strength and retrieval strength are two different numbers." },
      { voice: "nostalgia", text: "A week ago this was a blank page." }] };
  st.processed_inbox = [];
  if (followUp) {
    st.processed_inbox.push("ans1");
    t.history.unshift({ date: ymd(day(0)), kind: task.kind, title: "Almost: one question first", detail: "Close.", evidence: false, inbox: "ans1",
      follow_up: { q: "You said rereading feels like knowing. Why does that feeling mislead?", point: "1" } });
    fs.writeFileSync(sys("inbox.jsonl"), JSON.stringify({ id: "ans1", ts: day(0, 9).toISOString(), topic: t.id, task: task.id, kind: "answers", title: "t",
      fields: { "1. Q": "a" }, note: "", honor: true, confidence: "shaky" }) + "\n");
  } else fs.writeFileSync(sys("inbox.jsonl"), "");
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  return task.id;
}

before(async () => {
  v = makeVault("Kim");
  v.env.EDU4SELF_CLAUDE = path.join(ENGINE, "tests", "fake_claude.py");   // Claude Code is set up: no setup banner
  cfgPath = sys("config.json");
  const blocks = [];
  for (let n = 10; n >= 1; n--) blocks.push({ id: "b" + n, ts: new Date(day(n).getTime() + 50 * 60000).toISOString(), started: day(n).toISOString(), block: "lessons", minutes: 50 });
  fs.writeFileSync(sys("blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + "\n");
  fs.writeFileSync(cfgPath, JSON.stringify({ goals: { day_minutes: 45, week_days: 2 } }));
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

// a block running on `task`, 17 minutes in, in the front room
async function open(view, w, h, task) {
  const page = await openPage(browser, server.url, { view, width: w, height: h });
  await page.evaluate((id) => { const n = Date.now(); localStorage.setItem("edu.bar.room.v1", "front"); localStorage.setItem("edu.block.v1", JSON.stringify({ block: "lessons", minutes: 50, start: n - 17 * 60000, end: n + 33 * 60000, water: 15, served: 1, drunk: 0, task: id })); }, task);
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector("#app > :not(#loading)");
  await page.waitForFunction(() => document.body.classList.contains("blk-on"));
  await sleep(1200);   // the voices arrive and the countdown ticks
  return page;
}

// What the first screen holds. Countdowns are text like 32:56 (a time of day, 2:43 PM, is not one).
function firstScreen() {
  const inView = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && r.top >= 0 && r.bottom <= innerHeight && s.visibility !== "hidden" && !el.closest("[hidden]"); };
  const countdowns = [];
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    const el = n.parentElement;
    if (/\b\d{1,2}:\d{2}\b(?!\s?[AP]M)/i.test(n.textContent) && inView(el)) countdowns.push(n.textContent.trim().slice(0, 30));
  }
  const job = document.querySelector(".room .bx-job h2, #app .hero h2");
  const action = document.querySelector('.room [data-slot="job"] form[data-followup] button[type=submit], .hero form[data-followup] button[type=submit]') ||
    document.querySelector('.room [data-slot="replies"] .bx-r, .hero .hero-actions .btn');
  // endless animations, except on the room's "a block is running" signal (data-part="running")
  const endless = document.getAnimations().filter((a) => {
    const t = a.effect && a.effect.target;
    return t && t.nodeType === 1 && a.playState === "running" && a.effect.getComputedTiming().iterations === Infinity && !t.closest('[data-part~="running"]');
  }).map((a) => (a.animationName || "?") + " on " + (t => t.className && t.className.baseVal === undefined ? t.className : t.tagName)(a.effect.target));
  return { job: !!job && inView(job), jobText: job && job.textContent.trim().slice(0, 40), action: !!action && inView(action), actionText: action && action.textContent.trim().slice(0, 30), countdowns, endless };
}

for (const followUp of [true, false]) {
  for (const [id, view] of VIEWS) {
    for (const [w, h, label] of SIZES) {
      test(`${id} on a ${label}, ${followUp ? "a follow-up waiting" : "plain Up next"}: next step and its action on the first screen, one countdown, nothing else moving`, async () => {
        const task = seed({ followUp });
        setConfig({ theme: id === "classic" ? "bar" : id });
        const page = await open(view, w, h, task);
        const s = await page.evaluate(firstScreen);
        assert.ok(s.job, `${id}/${label}: the next step's title is on the first screen`);
        assert.ok(s.action, `${id}/${label}: its action (${s.actionText}) is on the first screen`);
        if (followUp) assert.match(s.actionText, /Send reply/, "with a follow-up waiting, the reply is the action");
        assert.equal(s.countdowns.length, 1, `${id}/${label}: the countdown shows once, not ${JSON.stringify(s.countdowns)}`);
        assert.deepEqual(s.endless, [], `${id}/${label}: only the running signal moves during a block`);
        assert.deepEqual(page.errors, []);
        await closePage(page);
      });
    }
  }
}

// Click as a person would: bring the control into view, make sure nothing (the sticky top bar) covers it, click.
// page.click alone only checks the viewport, so it can press the top bar sitting over a control.
async function clickInSight(page, sel) {
  await page.$eval(sel, (e) => e.scrollIntoView({ block: "nearest" }));
  const covered = await page.$eval(sel, (e) => { const r = e.getBoundingClientRect(), h = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return e.contains(h) ? "" : (h ? h.id || h.className || h.tagName : "nothing"); });
  assert.equal(covered, "", `${sel} is covered by ${covered} once scrolled into view`);
  await page.click(sel);
}

for (const id of ROOMS) {
  test(`${id}: what left the front room is one click away (back room: finish line, locked task, trophies) and every voice is there on "more"`, async () => {
    const task = seed({ followUp: true });
    setConfig({ theme: id });
    const page = await open("bar", 1440, 900, task);
    for (const slot of ["finish", "doors", "shelf", "timer"]) {
      assert.equal(await page.$eval(`.room [data-slot="${slot}"]`, (e) => e.innerHTML.trim()).catch(() => ""), "", `${id}: no ${slot} in the front room`);
    }
    const shown = await page.$$eval(".room .bx-log .bx-line", (l) => l.filter((e) => e.getBoundingClientRect().height > 0).length);
    assert.ok(shown <= 3, `${id}: at most the host and two voices before "more" (${shown})`);
    const all = await page.$$eval(".room .bx-log .bx-line", (l) => l.length);
    if (all > 3) {
      await clickInSight(page, ".room .bx-log [data-voices-more]");
      assert.equal(await page.$$eval(".room .bx-log .bx-line", (l) => l.filter((e) => e.getBoundingClientRect().height > 0).length), all, "more shows every voice");
    }
    await clickInSight(page, '.room [data-slot="rooms"] [data-room="back"]');
    await page.waitForSelector(".room.is-back");
    const back = await page.$eval(".room", (e) => e.innerText.toLowerCase());
    assert.match(back, /finish line/, "the finish line is in the back room");
    assert.match(back, /retrieval, a few days later/, "the locked task is in the back room");
    assert.ok(await page.$(".room.is-back .ks-pile"), "the trophies are in the back room");
    assert.deepEqual(page.errors, []);
    await closePage(page);
  });
}
