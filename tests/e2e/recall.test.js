// The recall warm-up: a few questions from memory before Up next, "Not now" for today, and after a
// gap of three days the same card is the welcome back, built only from work already passed.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, readLines } from "./harness.js";

let v, server, browser;
const sys = (f) => path.join(v.vault, "_system", f);
// A question is shown only once its task passed 3+ days ago; `added` dates the pass where no graded
// submission does (the unit tests cover the rule itself).
const OLD = "2026-01-01";
const QUESTIONS = [
  { id: "rc-1", q: "In one line: what is storage strength?", from: "hlw-lesson-01", added: OLD },
  { id: "rc-2", q: "Why does rereading feel better than it works?", from: "hlw-lesson-01", added: OLD },
  { id: "rc-probe", q: "What did the probe ask you about your study habits?", from: "hlw-probe-01", added: OLD },
];

before(async () => {
  v = makeVault("Tester");
  const st = readJSON(sys("state.json"));
  st.recall = QUESTIONS;
  for (const t of st.topics[0].queue) if (t.id === "hlw-lesson-01" || t.id === "hlw-probe-01") t.status = "done";
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

test("Not now hides the warm-up for today, in this browser only", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector("section.recall");
  await page.click('[data-recall="later"]');
  await page.waitForFunction(() => !document.querySelector("section.recall"));
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector(".hero");
  assert.equal(await page.$("section.recall"), null, "still hidden after a reload");
  assert.deepEqual(page.errors, []);
  await closePage(page);
  const other = await browser.createBrowserContext();       // another browser hasn't said "not now"
  const fresh = await openPage(other, server.url, { view: "classic" });
  await fresh.waitForSelector("section.recall");
  await closePage(fresh);
  await other.close();
});

test("a normal day: up to three questions before Up next, answered from memory into the inbox", async () => {
  const ctx = await browser.createBrowserContext();
  const page = await openPage(ctx, server.url, { view: "classic" });
  await page.waitForSelector("section.recall");
  const order = await page.evaluate(() => {
    const all = [...document.querySelectorAll("section.recall, .hero")];
    return all.map((e) => (e.matches(".recall") ? "recall" : "hero"));
  });
  assert.deepEqual(order, ["recall", "hero"], "the card sits before Up next");
  const card = await page.$eval("section.recall", (e) => e.innerText);
  assert.match(card, /From memory[\s\S]*3 quick questions[\s\S]*about two minutes/i);
  assert.doesNotMatch(card, /Welcome back|5 minutes/);
  await page.click('[data-recall="go"]');
  await page.waitForSelector("#submit:not([hidden])");
  assert.equal(await page.$eval("#sub-sure", (e) => e.hidden), true, "no confidence question on a warm-up");
  assert.equal(await page.$eval("#sub-rules", (e) => e.hidden), true, "nothing shown but the questions");
  const areas = await page.$$("#sub-fields textarea");
  assert.equal(areas.length, 3);
  await areas[0].type("How well it's really learned");
  await areas[1].type("I don't remember");
  await page.click("#sub-send");
  await page.waitForSelector("#submit", { hidden: true });
  const e = readLines(sys("inbox.jsonl")).pop();
  assert.equal(e.kind, "recall");
  assert.deepEqual(e.recall, ["rc-1", "rc-2", "rc-probe"]);
  assert.equal(e.fields["In one line: what is storage strength?"], "How well it's really learned");
  assert.equal(e.comeback, undefined);
  await page.waitForFunction(() => !document.querySelector("section.recall"));     // sent today: gone
  assert.deepEqual(page.errors, []);
  await closePage(page);
  await ctx.close();
});

test("after three days away the card is the welcome back, from passed work only", async () => {
  // the lesson was passed (graded) eight days ago; the last block was five days ago
  const day = (n) => new Date(Date.now() - n * 864e5).toISOString().replace(/\.\d+Z$/, "Z");
  const st = readJSON(sys("state.json"));
  st.topics[0].queue[0].status = "done";
  st.topics[0].queue.find((t) => t.id === "hlw-probe-01").status = "todo";      // the probe is not passed
  st.processed_inbox = ["old-sub"];
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  fs.writeFileSync(sys("inbox.jsonl"), JSON.stringify({ id: "old-sub", ts: day(8), topic: st.topics[0].id, task: "hlw-lesson-01", kind: "answers", fields: { a: "b" } }) + "\n");
  fs.writeFileSync(sys("blocks.jsonl"), JSON.stringify({ id: "b1", ts: day(5), started: day(5), block: "lessons", minutes: 25 }) + "\n");
  const ctx = await browser.createBrowserContext();
  const page = await openPage(ctx, server.url, { view: "bar" });
  await page.waitForSelector(".bx-recall.is-comeback");
  const card = await page.$eval(".bx-recall", (e) => e.innerText);
  assert.match(card, /Welcome back/i);
  assert.match(card, /About 5 minutes[\s\S]*already passed/);
  assert.match(card, /storage strength/);
  assert.doesNotMatch(card, /probe ask you/, "not from work that isn't passed yet");
  assert.ok(await page.$eval('.room [data-slot="job"]', (e) => !!e.querySelector(".bx-recall + .bx-job")), "before the job");
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /when will you|pick a day|come back on/i, "never asks for a return date");
  await page.click('.bx-recall [data-recall="go"]');
  await page.waitForSelector("#submit:not([hidden])");
  assert.match(await page.$eval("#sub-intro", (e) => e.textContent), /easy start/);
  await (await page.$$("#sub-fields textarea"))[0].type("how well it's stored");
  await page.click("#sub-send");
  await page.waitForSelector("#submit", { hidden: true });
  const e = readLines(sys("inbox.jsonl")).pop();
  assert.equal(e.comeback, true);
  assert.deepEqual(e.recall, ["rc-1", "rc-2"]);
  // the classic view frames it the same way
  const c2 = await browser.createBrowserContext();
  fs.writeFileSync(sys("inbox.jsonl"), readLines(sys("inbox.jsonl")).slice(0, 1).map((x) => JSON.stringify(x)).join("\n") + "\n");
  const classic = await openPage(c2, server.url, { view: "classic" });
  await classic.waitForSelector("section.recall.is-comeback");
  assert.match(await classic.$eval("section.recall", (e) => e.innerText), /Warm-up[\s\S]*about 5 minutes/i);
  assert.deepEqual(page.errors, []);
  assert.deepEqual(classic.errors, []);
  await closePage(page);
  await closePage(classic);
  await ctx.close();
  await c2.close();
});

test("the progress page shows how often solid passed, once three answers are graded", async () => {
  const st = readJSON(sys("state.json"));
  const entry = (id, c) => JSON.stringify({ id, ts: new Date().toISOString(), topic: st.topics[0].id, task: "hlw-lesson-01", kind: "answers", fields: { a: "b" }, confidence: c });
  fs.writeFileSync(sys("inbox.jsonl"), [entry("g1", "solid"), entry("g2", "solid"), entry("g3", "shaky")].join("\n") + "\n");
  st.processed_inbox = ["g1", "g2", "g3"];
  st.topics[0].history = [{ date: "2026-11-01", kind: "lesson", title: "a", evidence: true, inbox: "g1" },
                          { date: "2026-11-02", kind: "lesson", title: "b", evidence: false, inbox: "g2" }];
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  let page = await openPage(browser, server.url, { view: "classic" });
  assert.equal(await page.$(".cal"), null, "two graded answers: not yet");
  await closePage(page);
  st.topics[0].history.push({ date: "2026-11-03", kind: "lesson", title: "c", evidence: true, inbox: "g3" });
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector(".cal");
  assert.match(await page.$eval(".cal", (e) => e.innerText), /You said solid 2 times, and 1 of those passed[\s\S]*Shaky[\s\S]*1 of 1 passed/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
