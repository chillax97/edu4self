// The work record in the dashboard: hints open one at a time and are noted next to the checker runs,
// and Settings says what's kept and deletes it only after saying what that costs.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, sleep, PYTHON } from "./harness.js";

let v, server, browser, ex;
const traceFiles = () => (fs.existsSync(path.join(ex, "trace")) ? fs.readdirSync(path.join(ex, "trace")).sort() : []);

before(async () => {
  v = makeVault("Tester");
  ex = path.join(v.vault, "how-learning-works", "exercises", "e1");
  fs.mkdirSync(ex, { recursive: true });
  fs.writeFileSync(path.join(ex, "HINTS.md"), "# Hints\n\nOnly the one you need.\n\n## 1 · warm-up\n- Read it twice.\n\n## 2 · the loop\n- Keep a running `total`.\n- Yield after each item.\n");
  fs.writeFileSync(path.join(ex, "sol.py"), "def f():\n    return 1\n");
  // a checker that starts with the protocol's lines
  const proto = fs.readFileSync(new URL("../../docs/PROTOCOL.md", import.meta.url), "utf8");
  const lines = proto.split("```python\n")[1].split("```")[0].replace('["solution.py"]', '["sol.py"]');
  fs.writeFileSync(path.join(ex, "check.py"), lines + "\nprint('1 of 2 checks pass')\n");
  const sp = path.join(v.vault, "_system", "state.json"), st = readJSON(sp);
  st.topics[0].queue[0].exercise = "how-learning-works/exercises/e1";
  fs.writeFileSync(sp, JSON.stringify(st));
  server = await startServer(v, await freePort());    // installs _system/edu_trace.py
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

test("a hint opens only when asked for, and lands in the record right after the run it followed", async () => {
  // Windows ends printed lines with \r\n; compare the words, not the platform's line ending
  const out = execFileSync(PYTHON, [path.join(ex, "check.py")], { encoding: "utf8" }).replace(/\r\n/g, "\n");
  assert.match(out, /1 of 2 checks pass\n\n\(run saved for your tutor: trace\/.+-run\.json\)/);
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.click('[data-hints="hlw-lesson-01"]');
  await page.waitForSelector("#hints:not([hidden]) [data-hint-n]");
  const before = await page.$eval("#hints-list", (e) => e.innerText);
  assert.match(before, /1 · warm-up[\s\S]*2 · the loop/);
  assert.doesNotMatch(before, /running|Read it twice/, "no hint is on the page before it's opened");
  await page.click('[data-hint-n="2"]');
  await page.waitForFunction(() => /running total/.test(document.querySelector("#hints-list").innerText));
  const after = await page.$eval("#hints-list", (e) => e.innerHTML);
  assert.match(after, /<code>total<\/code>/);
  assert.match(after, /opened/);
  assert.doesNotMatch(await page.$eval("#hints-list", (e) => e.innerText), /Read it twice/, "only the one asked for");
  const files = traceFiles();
  assert.equal(files.length, 2);
  assert.match(files[0], /-run\.json$/);
  assert.match(files[1], /-hint-2\.json$/, "in time order: the run, then the hint");
  assert.equal(readJSON(path.join(ex, "trace", files[1])).task, "hlw-lesson-01");
  await page.keyboard.press("Escape");
  // the bar view has its own way in, and a deep link works too
  await closePage(page);
  const bar = await openPage(browser, server.url + "#hints=hlw-lesson-01", { view: "bar" });
  await bar.waitForSelector("#hints:not([hidden]) .hint.is-open");
  assert.ok(await bar.$('.room [data-hints="hlw-lesson-01"]'), "the bar offers hints too");
  assert.deepEqual(bar.errors, []);
  await closePage(bar);
});

test("Settings shows the record, explains what deleting costs, and deletes only on a second yes", async () => {
  const page = await openPage(browser, server.url + "#settings=record", { view: "classic" });
  await page.waitForSelector("#set-trace-del");
  assert.match(await page.$eval("#set-trace", (e) => e.innerText), /1 checker run and 1 hint opened, across 1 exercise/);
  await page.click("#set-trace-del");
  await page.waitForSelector("#set-trace-yes");
  assert.match(await page.$eval("#set-trace", (e) => e.innerText), /Grades you already got stay[\s\S]*can no longer look back[\s\S]*can't be undone/);
  await page.click("#set-trace-no");
  await page.waitForSelector("#set-trace-del");
  assert.equal(traceFiles().length, 2, "keeping it keeps it");
  await page.click("#set-trace-del");
  await page.waitForSelector("#set-trace-yes");
  await page.click("#set-trace-yes");
  await page.waitForFunction(() => /Nothing saved yet/.test(document.querySelector("#set-trace").innerText));
  assert.deepEqual(traceFiles(), []);
  for (const f of ["HINTS.md", "check.py", "sol.py"]) assert.ok(fs.existsSync(path.join(ex, f)), f + " stays");
  assert.deepEqual(page.errors, []);
  await closePage(page);
  await sleep(50);
});

test("your attempts: every run and hint in order, and a gentle nudge after three failing runs", async () => {
  const proto = fs.readFileSync(new URL("../../docs/PROTOCOL.md", import.meta.url), "utf8");
  const lines = proto.split("```python\n")[1].split("```")[0].replace('["solution.py"]', '["sol.py"]');
  const checker = (pass) => fs.writeFileSync(path.join(ex, "check.py"), lines + (pass ? "\nprint('2 of 2 pass')\n" : "\nimport sys\nprint('1 of 2 pass')\nsys.exit(1)\n"));
  const run = () => { try { execFileSync(PYTHON, [path.join(ex, "check.py")], { stdio: "pipe" }); } catch {} };
  fs.rmSync(path.join(ex, "trace"), { recursive: true, force: true });
  checker(false);
  run(); run();
  let page = await openPage(browser, server.url, { view: "classic" });
  assert.equal(await page.$(".hero .stuck"), null, "two failing runs: no nudge yet");
  await closePage(page);
  run();
  const filesBefore = traceFiles().length;
  page = await openPage(browser, server.url, { view: "classic" });
  await page.waitForSelector(".hero .stuck");
  assert.match(await page.$eval(".hero .stuck", (e) => e.innerText), /3 runs in a row haven't passed yet[\s\S]*Open the next hint: 1 · warm-up/);
  assert.equal(traceFiles().length, filesBefore, "showing the nudge writes nothing");
  await page.click(".hero [data-stuck-hint]");
  await page.waitForFunction(() => /Read it twice/.test(document.querySelector("#hints-list").innerText));
  // the runs and the hints come from two requests that can answer in either order: wait for the runs too
  await page.waitForFunction(() => /Hint 1 opened/.test(document.querySelector("#hints-attempts").innerText));
  const att = await page.$eval("#hints-attempts", (e) => e.innerText);
  assert.match(att, /Run 1: didn't pass[\s\S]*first run[\s\S]*Run 2: didn't pass[\s\S]*(right after|later)[\s\S]*Run 3: didn't pass[\s\S]*Hint 1 opened/);
  assert.match(traceFiles().pop(), /-hint-1\.json$/, "the hint asked for is noted like any other");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => /Open the next hint: 2 · the loop/.test(document.querySelector(".hero .stuck")?.innerText || ""));
  await closePage(page);
  // the bar shows it too
  const bar = await openPage(browser, server.url, { view: "bar" });
  await bar.waitForSelector(".room .bx-stuck");
  assert.deepEqual(bar.errors, []);
  await closePage(bar);
  // a pass resets it
  checker(true);
  run();
  page = await openPage(browser, server.url, { view: "classic" });
  assert.equal(await page.$(".stuck"), null, "a pass ends the nudge");
  await page.click('.hero [data-hints="hlw-lesson-01"]');
  await page.waitForFunction(() => /Run 4: passed/.test(document.querySelector("#hints-attempts").innerText));
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
