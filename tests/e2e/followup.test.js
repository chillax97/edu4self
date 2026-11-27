// Follow-up grading on the dashboard (PROTOCOL.md section 1): a grade that asks one question before the pass
// shows that question on the task's card with a one-field reply box, instead of asking for the whole task again.
import { test, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, readJSON, readLines, legacy } from "./harness.js";

const Q = "You said plants need light. What do they make with it?";
const TASK = "hlw-lesson-01", TOPIC = "how-learning-works";
let v, server, browser, STATE0, INBOX, STATE;

before(async () => {
  v = makeVault("Tester");
  STATE = path.join(v.vault, "_system", "state.json");
  INBOX = path.join(v.vault, "_system", "inbox.jsonl");
  STATE0 = readJSON(STATE);
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await closeBrowser(browser);
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});
beforeEach(() => fs.writeFileSync(INBOX, ""));

// An answer to `task`, graded (processed); the grade asks the question unless followUp is false. `more` adds inbox
// lines and their grades; `only` closes the other tasks, so Up next stays on this one after it is sent.
function graded({ task = TASK, followUp = true, more = [], only = false } = {}) {
  const st = legacy(structuredClone(STATE0), v.vault);
  if (only) st.topics[0].queue.forEach((x) => { if (x.id !== task) x.status = "done"; });
  const lines = [{ id: "ans1", ts: "2026-01-02T10:00:00+00:00", topic: TOPIC, task, kind: "answers", title: "t",
    fields: { "1. Q": "light" }, note: "", honor: false, confidence: "shaky" }];
  st.processed_inbox = ["ans1"];
  st.topics[0].history.push({ date: "2026-01-02", kind: "lesson", title: followUp ? "Almost: one question first" : "Not yet",
    detail: "Close.", evidence: false, inbox: "ans1", ...(followUp ? { follow_up: { q: Q, point: "1a" } } : {}) });
  for (const m of more) {
    lines.push(m.entry);
    if (m.grade) { st.processed_inbox.push(m.entry.id); st.topics[0].history.push(m.grade); }
  }
  fs.writeFileSync(STATE, JSON.stringify(st, null, 2));
  fs.writeFileSync(INBOX, lines.map((l) => JSON.stringify(l) + "\n").join(""));
}
const reply = (id, extra = {}) => ({ id, ts: "2026-01-03T10:00:00+00:00", topic: TOPIC, task: TASK, kind: "follow-up", ref: "ans1",
  title: "t", fields: { [Q]: "sugar" }, note: "", honor: false, ...extra });

test("a follow-up grade shows its question on the card, not the whole task again", async () => {
  graded();
  const page = await openPage(browser, server.url, { view: "classic" });
  const box = await page.waitForSelector(`.hero form[data-followup="${TASK}"]`);
  const text = await box.evaluate((e) => e.textContent);
  assert.match(text, /Almost: one question first/);
  assert.match(text, /What do they make with it\?/);
  assert.equal(await page.$(`.hero [data-submit="${TASK}"]`), null, "no button to send the whole task again");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("the reply posts a follow-up entry, then the card waits for the tutor and the reply can be withdrawn", async () => {
  graded({ only: true });
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector(".hero form[data-followup] textarea");
  await page.click(".hero form[data-followup] button[type=submit]");
  await page.waitForSelector(".hero form[data-followup] .fu-err:not([hidden])");
  assert.equal(readLines(INBOX).length, 1, "an empty reply isn't sent");
  await page.type(".hero form[data-followup] textarea", "Sugar, from light, water and air.");
  await page.click(".hero form[data-followup] button[type=submit]");
  await page.waitForSelector(".hero .hero-submitted");
  const last = readLines(INBOX).pop();
  assert.deepEqual({ kind: last.kind, ref: last.ref, topic: last.topic, task: last.task, fields: last.fields },
    { kind: "follow-up", ref: "ans1", topic: TOPIC, task: TASK, fields: { [Q]: "Sugar, from light, water and air." } });
  assert.equal(last.confidence, undefined, "one question, no how-sure");
  assert.equal(await page.$(".hero form[data-followup]"), null);
  assert.match(await page.$eval(".hero .hero-submitted", (e) => e.textContent), /Reply sent/);
  await page.click(`.hero [data-withdraw="${last.id}"]`);
  await page.waitForSelector(".hero form[data-followup]");      // withdrawn: the question is open again
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a typed reply survives the page refreshing itself", async () => {
  graded();
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.type(".hero form[data-followup] textarea", "half a th");
  // something in the vault changes, so the page fetches the state again and redraws
  const reloaded = page.waitForResponse((r) => r.url().endsWith("/api/state"));
  const later = new Date(Date.now() + 5000); fs.utimesSync(STATE, later, later);
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await reloaded;
  await page.evaluate(() => new Promise((r) => setTimeout(r, 50)));
  assert.equal(await page.$eval(".hero form[data-followup] textarea", (e) => e.value), "half a th");
  assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.matches("form[data-followup] textarea")), true);
  await closePage(page);
});

test("in a room the job card asks the question, and waits after the reply", async () => {
  graded({ only: true });
  const page = await openPage(browser, server.url, { view: "bar" });
  const box = await page.waitForSelector(`.bx-job form[data-followup="${TASK}"]`);
  assert.match(await box.evaluate((e) => e.textContent), /Almost: one question first[\s\S]*What do they make with it\?/);
  assert.equal(await page.$(`.bx-replies [data-submit="${TASK}"]`), null);
  await page.type(".bx-job form[data-followup] textarea", "Sugar");
  await page.click(".bx-job form[data-followup] button[type=submit]");
  await page.waitForSelector(".bx-replies [data-withdraw]");
  assert.equal(readLines(INBOX).pop().kind, "follow-up");
  assert.match(await page.$eval(".bx-job .bx-sent", (e) => e.textContent), /Reply sent/);
  assert.match(await page.$eval(".bx-replies [data-withdraw]", (e) => e.textContent), /Withdraw the reply/);
  assert.equal(await page.$(".bx-job form[data-followup]"), null);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a follow-up on a task further down: its row opens a one-question form", async () => {
  graded({ task: "hlw-probe-01" });
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.click('.q-item [data-submit="hlw-probe-01"]');
  await page.waitForSelector("#submit:not([hidden])");
  const labels = await page.$$eval("#sub-fields .field-label", (ls) => ls.map((l) => l.textContent));
  assert.deepEqual(labels, [Q]);
  assert.equal(await page.$eval("#sub-sure", (e) => e.hidden), true);
  assert.equal(await page.$eval("#sub-honor", (e) => e.hidden), true);
  await page.type("#sub-fields textarea", "Sugar");
  await page.click("#sub-send");
  await page.waitForSelector("#submit", { hidden: true });
  const last = readLines(INBOX).pop();
  assert.deepEqual([last.kind, last.ref, last.task, last.fields], ["follow-up", "ans1", "hlw-probe-01", { [Q]: "Sugar" }]);
  await page.waitForFunction(() => [...document.querySelectorAll(".q-item")].some((q) => /Reply sent/.test(q.textContent)));   // its row waits
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("no reply box when the grade asked no question", async () => {
  graded({ followUp: false });
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector(`.hero [data-submit="${TASK}"]`);
  assert.equal(await page.$("form[data-followup]"), null);
  await closePage(page);
});

test("no second reply box once the reply was graded", async () => {
  graded({ more: [{ entry: reply("fu1"), grade: { date: "2026-01-03", kind: "lesson", title: "Not yet", detail: "d", evidence: false, inbox: "fu1" } }] });
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector(`.hero [data-submit="${TASK}"]`);         // a plain not yet: the task again
  assert.equal(await page.$("form[data-followup]"), null);
  await closePage(page);
});

test("a newer answer to the whole task closes the old question", async () => {
  graded({ more: [{ entry: { id: "ans2", ts: "2026-01-04T10:00:00+00:00", topic: TOPIC, task: TASK, kind: "answers", title: "t",
    fields: { "1. Q": "x" }, note: "", honor: false, confidence: "solid" },
    grade: { date: "2026-01-04", kind: "lesson", title: "Not yet", detail: "d", evidence: false, inbox: "ans2" } }] });
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector(`.hero [data-submit="${TASK}"]`);
  assert.equal(await page.$("form[data-followup]"), null);
  await closePage(page);
});
