// Can the page run Claude? It says so when it opens, before any lesson: a note at the top with the fix, and the
// buttons that need Claude greyed out with the reason. The stand-in (tests/fake_claude.py) plays a Claude Code
// that's missing, signed out, or signed in; nothing here needs an account or the network.
// SHOTS=<folder> also saves a picture of the note in the bar and in the classic page.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, openPage, closePage, sleep } from "./harness.js";

const FAKE = path.join(ENGINE, "tests", "fake_claude.py");
let v, server, broken, brokenServer, browser;

before(async () => {
  v = makeVault("Tester");
  v.env.EDU4SELF_CLAUDE = path.join(v.dir, "claude.py");          // not there yet: Claude Code is "not installed"
  v.env.FAKE_CLAUDE_SIGNED_OUT = path.join(v.dir, "signed-out");  // signed out while this file exists
  server = await startServer(v, await freePort());
  broken = makeVault("Tester");
  broken.env.EDU4SELF_CLAUDE = FAKE;
  broken.env.FAKE_CLAUDE_FAIL = "1";                               // every run ends with an error
  brokenServer = await startServer(broken, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  await stopServer(brokenServer);
  for (const x of [v, broken]) fs.rmSync(x.dir, { recursive: true, force: true });
});

const submit = (page) => page.evaluate(() => fetch("/api/inbox", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ topic: "how-learning-works", task: "hlw-lesson-01", kind: "answers", fields: { 1: "ease now vs lasting" }, confidence: "shaky" }) }).then((r) => r.status));
const gate = (page) => page.$eval("#cl-gate", (e) => (e.hidden ? "" : e.innerText));
const focus = (page) => page.evaluate(() => window.dispatchEvent(new Event("focus")));
async function shot(page, name) {
  if (!process.env.SHOTS) return;
  fs.mkdirSync(process.env.SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(process.env.SHOTS, name), clip: { x: 0, y: 0, width: 1440, height: 520 } });
}

test("without Claude Code: the note is there from the start, in both views, and Grade is greyed out", async () => {
  let page = await openPage(browser, server.url, { view: "classic" });
  assert.equal(await submit(page), 201);
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector("#cl-gate:not([hidden])");
  assert.match(await gate(page), /Claude Code isn't set up, so nothing here can be graded yet/);
  assert.match(await gate(page), /claude\.com\/claude-code/);
  await page.waitForSelector("#btn-grade:not([hidden])");
  assert.equal(await page.$eval("#btn-grade", (e) => e.disabled), true, "the top bar's Grade is greyed out");
  assert.equal(await page.$eval("#btn-grade", (e) => e.title), "Needs Claude Code");
  assert.equal(await page.$eval("#btn-note", (e) => e.hidden), false, "the note to Claude stands in for the chat");
  assert.equal(await page.$("[data-claude=grade]"), null, "nothing on the page can start a grade");
  await shot(page, "login-banner-classic.png");
  assert.deepEqual(page.errors, []);
  await closePage(page);

  page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector("#cl-gate:not([hidden])");
  assert.match(await gate(page), /isn't set up/);
  assert.equal(await page.$eval("#btn-grade", (e) => !e.hidden && e.disabled), true, "the bar's Grade is greyed out");
  assert.equal(await page.$("[data-claude=grade]"), null);
  await shot(page, "login-banner-bar.png");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("installed but signed out: the note says how to sign in; once signed in, it goes and Grade works", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector("#cl-gate:not([hidden])");
  fs.writeFileSync(path.join(v.dir, "signed-out"), "");
  fs.copyFileSync(FAKE, v.env.EDU4SELF_CLAUDE);                    // "installed" now
  await focus(page);                                                // coming back to the tab asks again
  await page.waitForFunction(() => /isn't signed in/.test(document.querySelector("#cl-gate").innerText));
  assert.match(await gate(page), /claude auth login/);
  assert.equal(await page.$eval("#btn-grade", (e) => e.disabled && e.title), "Sign in to Claude Code first");
  assert.equal(await page.$eval("#btn-claude", (e) => e.hidden), true);

  fs.rmSync(path.join(v.dir, "signed-out"));                       // signed in, in a terminal
  await sleep(5500);                                                // the server asks again at most every 5 s
  await focus(page);
  await page.waitForSelector("#cl-gate", { hidden: true });
  assert.equal(await page.$eval("#btn-grade", (e) => e.disabled), false);
  assert.equal(await page.$eval("#btn-claude", (e) => e.hidden), false);

  await page.click("#btn-grade");                                   // and a run that works ends with "done"
  await page.waitForFunction(() => { const t = document.querySelector("#toast"); return t && !t.hidden && /Claude/.test(t.innerText); }, { timeout: 15000 });
  assert.match(await page.$eval("#toast", (e) => e.innerText), /Claude is done/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("signed in from the start: no note, Grade is live", async () => {
  // the server above is signed in by now; a fresh tab sees that at once
  const page = await openPage(browser, server.url, { view: "classic" });
  assert.equal(await submit(page), 201);
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector("#btn-grade:not([hidden])");
  assert.equal(await gate(page), "");
  assert.equal(await page.$eval("#btn-grade", (e) => e.disabled), false);
  assert.equal(await page.$(".cl-why"), null, "no reason shown when nothing's wrong");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a run that fails doesn't end with 'Claude is done', even when the check after it passes", async () => {
  const page = await openPage(browser, brokenServer.url, { view: "classic" });
  assert.equal(await submit(page), 201);
  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForSelector("#btn-grade:not([hidden]):not([disabled])");
  await page.click("#btn-grade");
  await page.waitForFunction(() => /Check OK/.test(document.querySelector("#cl-log").innerText), { timeout: 15000 });
  await page.waitForFunction(() => { const t = document.querySelector("#toast"); return t && !t.hidden && /Claude/.test(t.innerText); }, { timeout: 15000 });
  const toast = await page.$eval("#toast", (e) => e.innerText);
  assert.doesNotMatch(toast, /done/i);
  assert.match(toast, /Claude finished with a problem/);
  await closePage(page);
});
