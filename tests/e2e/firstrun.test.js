// The first try: on a first visit, one idea, hidden, answered from memory, checked here, graded by Claude
// on request, then the learner picks their own topic or the example. Never again once done or skipped.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, readLines } from "./harness.js";

let withClaude, noClaude, browser;
const LOG = () => path.join(withClaude.v.dir, "fake-claude.log");
const runs = () => (fs.existsSync(LOG()) ? readLines(LOG()) : []);
const inbox = (v) => readLines(path.join(v.vault, "_system", "inbox.jsonl"));

before(async () => {
  const a = makeVault("Tester");
  a.env.EDU4SELF_CLAUDE = path.join(ENGINE, "tests", "fake_claude.py");
  a.env.FAKE_CLAUDE_LOG = path.join(a.dir, "fake-claude.log");
  a.env.FAKE_CLAUDE_SLEEP = "0.4";
  withClaude = { v: a, server: await startServer(a, await freePort()) };
  const b = makeVault("Tester");   // EDU4SELF_CLAUDE points at nothing: no Claude Code
  noClaude = { v: b, server: await startServer(b, await freePort()) };
  browser = await launch();
});
after(async () => {
  await closeBrowser(browser);
  for (const s of [withClaude, noClaude]) { await stopServer(s?.server); fs.rmSync(s.v.dir, { recursive: true, force: true }); }
});

// a first visit: a fresh browser context (its own localStorage) with no onboarded key; openPage sets the key,
// so this doesn't use it
async function firstVisit(url, { width = 1440, height = 1000, ctx } = {}) {
  const page = await (ctx || await browser.createBrowserContext()).newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  await page.setViewport({ width, height });
  await page.goto(url, { waitUntil: "networkidle0" });
  await page.waitForSelector("#onboarding:not([hidden])");
  await stageOnly(page, "the idea");
  return page;
}
// The first try is a stage of its own: the dashboard is neither visible nor clickable behind it, and the card is
// opaque from the first frame (no fade from transparent). Probes a grid of points with elementFromPoint.
async function stageOnly(page, step) {
  const r = await page.evaluate(() => {
    const o = document.querySelector("#onboarding"), dash = ["header.topbar", "#app", "footer", "#cl-gate"].map((q) => document.querySelector(q));
    const hits = [];
    for (const x of [0.03, 0.25, 0.5, 0.75, 0.97]) for (const y of [0.03, 0.3, 0.6, 0.97]) {
      const el = document.elementFromPoint(innerWidth * x, innerHeight * y);
      if (el && !o.contains(el) && el !== document.body && el !== document.documentElement) hits.push((el.className || el.tagName).toString().slice(0, 40));
    }
    return { hits, hidden: dash.every((d) => !d || getComputedStyle(d).visibility === "hidden"),
      opacity: [getComputedStyle(o).opacity, getComputedStyle(o.querySelector(".dialog")).opacity] };
  });
  assert.deepEqual(r.hits, [], step + ": only the stage is under the pointer");
  assert.ok(r.hidden, step + ": the dashboard is hidden");
  assert.deepEqual(r.opacity, ["1", "1"], step + ": the card is opaque");
}
async function answer(page, text, sure = "shaky") {
  assert.match(await page.$eval(".ft-face", (e) => e.innerText), /Pulling an idea out of your head/);
  await page.click("#ob-next");   // Hide it and test me
  await page.waitForSelector('.ob-slide[data-step="1"]:not([hidden])');
  assert.equal(await page.$eval('.ob-slide[data-step="0"]', (e) => e.hidden), true, "the idea is out of sight");
  await stageOnly(page, "the question");
  assert.equal(await page.$eval("#ob-next", (e) => e.textContent), "I don't remember");
  await page.type("#ft-answer", text);
  assert.equal(await page.$eval("#ob-next", (e) => e.textContent), "Check my answer");
  await page.click("#ob-next");
  assert.match(await page.$eval("#ft-error", (e) => e.textContent), /how sure/, "how sure is asked, as on every answer");
  await page.click(`input[name="ft-sure"][value="${sure}"]`);
  await page.click("#ob-next");
  await page.waitForSelector('.ob-slide[data-step="2"]:not([hidden])');
  await stageOnly(page, "the check");
}

test("first try with Claude: quick check at once, the answer in the inbox, Claude's grade in the card, then the example", async () => {
  const { v, server } = withClaude;
  const page = await firstVisit(server.url);
  await answer(page, "Pulling it out of your head makes it stick for weeks; rereading just feels familiar.");
  assert.match(await page.$eval("#ft-verdict", (e) => e.textContent), /All three key points/);
  assert.equal((await page.$$(".ft-keys .is-hit")).length, 3);
  await page.waitForSelector("#ft-grade-go");
  assert.match(await page.$eval("#ft-grade", (e) => e.innerText), /quick check.*can be fooled.*real grade comes from Claude.*Only Claude can keep it as proof/s);
  assert.match(await page.$eval("#ft-grade", (e) => e.innerText), /uses a little of your Claude plan/, "the cost is next to the button");
  const saved = inbox(v).filter((e) => e.task === "first-try");
  assert.equal(saved.length, 1);
  assert.equal(saved[0].kind, "answers");
  assert.equal(saved[0].topic, "how-learning-works");
  assert.equal(saved[0].confidence, "shaky");
  assert.equal(runs().length, 0, "nothing runs Claude until the learner asks");

  await page.click("#ft-grade-go");
  await page.waitForSelector(".ft-g-badge", { timeout: 15000 });
  assert.match(await page.$eval("#ft-grade", (e) => e.innerText), /Graded by Claude, and kept in your record.*First try graded by the fake tutor.*Not proof yet/s);
  const run = runs().at(-1);
  assert.match(run.args[run.args.indexOf("-p") + 1], /^Grade only my first try/, "the grade-only run, not the full check my inbox");
  assert.ok(run.args.includes("--disallowedTools") && run.args[run.args.indexOf("--disallowedTools") + 1].includes("WebFetch"), "fenced like grading");

  await page.click("#ob-next");   // Try the example lesson
  await page.waitForSelector("#onboarding", { hidden: true });
  assert.equal(await page.$eval("#app", (e) => getComputedStyle(e).visibility), "visible", "the dashboard appears after the pick");
  assert.match(await page.$eval(".bx-job h2", (e) => e.textContent), /Retrieval beats rereading/);
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector("#app > :not(#loading)");
  assert.equal(await page.$eval("#onboarding", (e) => e.hidden), true, "never again once done");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("first try, own topic: what they type goes straight to New topic with Claude", async () => {
  const { server } = withClaude;
  const page = await firstVisit(server.url, { width: 390, height: 844 });
  await page.click("#ob-next");
  await page.click("#ob-next");   // I don't remember: nothing is saved, the idea comes back
  await page.waitForSelector('.ob-slide[data-step="2"]:not([hidden])');
  assert.match(await page.$eval("#ft-verdict", (e) => e.textContent), /That's fine/);
  assert.equal(await page.$eval("#ft-grade", (e) => e.hidden), true, "no answer, nothing to grade");
  await page.type("#ft-what", "Rust, for a CLI tool by March");
  await page.click("#ft-own-go");
  await page.waitForSelector("#onboarding", { hidden: true });
  await page.waitForSelector("#claude:not([hidden])");
  await page.waitForFunction(() => /New topic: Rust, for a CLI tool by March/.test(document.querySelector("#cl-log").innerText));
  await page.waitForFunction(() => !document.querySelector(".cl-working"), { timeout: 15000 });
  assert.match(runs().at(-1).args[runs().at(-1).args.indexOf("-p") + 1], /new-topic skill[\s\S]*Rust, for a CLI tool by March/);
  assert.equal(await page.evaluate(() => localStorage.getItem("edu.onboarded.v1")), "1");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("first try without Claude: the quick check still runs, the card says plainly where the real grade comes from", async () => {
  const { v, server } = noClaude;
  const page = await firstVisit(server.url);
  await answer(page, "no idea really, maybe reading twice is better", "guessed");
  assert.match(await page.$eval("#ft-verdict", (e) => e.textContent), /None of the key points yet/);
  await page.waitForFunction(() => /saved in your inbox/.test(document.querySelector("#ft-grade").innerText));
  const g = await page.$eval("#ft-grade", (e) => e.innerText);
  assert.match(g, /real grade, and the proof, come from Claude/);
  assert.match(g, /isn't set up on this computer/);
  assert.equal(await page.$("#ft-grade-go"), null, "no grade button without Claude");
  assert.equal(inbox(v).filter((e) => e.task === "first-try").length, 1, "the answer waits for ✦ Grade");
  // the own-topic branch without Claude opens the New topic fallback with what they typed
  await page.type("#ft-what", "Spanish");
  await page.click("#ft-own-go");
  await page.waitForSelector("#newtopic:not([hidden])");
  assert.match(await page.$eval("#nt-body", (e) => e.innerText), /needs Claude Code/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("Skip and Escape end it for good; a returning user never sees it", async () => {
  const { server } = noClaude;
  const ctx = await browser.createBrowserContext();
  const page = await firstVisit(server.url, { ctx });
  await page.click("#ob-skip");
  await page.waitForSelector("#onboarding", { hidden: true });
  assert.equal(await page.evaluate(() => localStorage.getItem("edu.onboarded.v1")), "1");
  await closePage(page);
  const p2 = await ctx.newPage();
  await p2.goto(server.url, { waitUntil: "networkidle0" });
  assert.equal(await p2.$eval("#onboarding", (e) => e.hidden), true, "skipped once: not shown again");
  await p2.evaluate(() => localStorage.clear());   // a first visit again, for Escape
  await p2.reload({ waitUntil: "networkidle0" });
  await p2.waitForSelector("#onboarding:not([hidden])");
  await p2.keyboard.press("Escape");
  await p2.waitForSelector("#onboarding", { hidden: true });
  assert.equal(await p2.evaluate(() => localStorage.getItem("edu.onboarded.v1")), "1");
  await closePage(p2);
  await ctx.close();
  const back = await openPage(browser, server.url);   // openPage sets the key, as an existing user has it
  assert.equal(await back.$eval("#onboarding", (e) => e.hidden), true);
  assert.deepEqual(back.errors, []);
  await closePage(back);
});
