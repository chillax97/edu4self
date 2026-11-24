import { test, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, readJSON } from "./harness.js";

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

function graded({ task = TASK, followUp = true, more = [], only = false } = {}) {
  const st = structuredClone(STATE0);
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

const openBar = async () => {
  const page = await openPage(browser, server.url, { view: "bar", room: "front" });
  await page.waitForSelector('.room [data-slot="replies"] .bx-r');
  return page;
};

const openLessonMove = (page) => page.evaluate(() => {
  const e = [...document.querySelectorAll('.room [data-slot="replies"] .bx-r')].find((x) => x.textContent.trim().startsWith("Open lesson"));
  if (!e) return null;
  const s = getComputedStyle(e);
  return { text: e.textContent.trim(), bg: s.backgroundColor, line: s.textDecorationLine };
});

const formState = (page) => page.evaluate(() => {
  const f = document.querySelector(".room form.followup");
  if (!f) return null;
  const r = f.getBoundingClientRect(), s = getComputedStyle(f);
  return { visible: r.width > 0 && r.height > 0 && s.visibility !== "hidden" && !f.closest("[hidden]"),
    button: !!f.querySelector("button[type=submit]") };
});

test("with a follow-up open, the Open lesson move is a quiet link and the reply is the only filled action", async () => {
  graded();
  const page = await openBar();
  await page.waitForSelector(".room form.followup button[type=submit]");
  const move = await openLessonMove(page);
  assert.ok(move, "there is an Open lesson move");
  assert.ok(move.bg === "rgba(0, 0, 0, 0)" || move.bg === "transparent", `Open lesson is not a filled button: ${JSON.stringify(move)}`);
  assert.match(move.line, /underline/, `Open lesson is underlined: ${JSON.stringify(move)}`);
  assert.deepEqual(await formState(page), { visible: true, button: true });
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("without a follow-up, the Open lesson move stays a filled button", async () => {
  graded({ followUp: false });
  const page = await openBar();
  const move = await openLessonMove(page);
  assert.ok(move, "there is an Open lesson move");
  assert.ok(move.bg !== "rgba(0, 0, 0, 0)" && move.bg !== "transparent", `Open lesson stays filled: ${JSON.stringify(move)}`);
  assert.equal(await page.$(".room form.followup"), null);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
