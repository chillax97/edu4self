import { test, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, readJSON, readLines, sleep } from "./harness.js";

const TASK = "hlw-lesson-01";
let v, server, browser, STATE, INBOX, STATE0;

before(async () => {
  v = makeVault("Tester");
  v.env.EDU4SELF_CLAUDE = path.join(ENGINE, "tests", "fake_claude.py");
  v.env.FAKE_CLAUDE_LOG = path.join(v.dir, "fake-claude.log");
  v.env.FAKE_CLAUDE_SLEEP = "0";
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
beforeEach(() => {
  fs.writeFileSync(STATE, JSON.stringify(STATE0, null, 2));
  fs.writeFileSync(INBOX, "");
});

const fields = () => readJSON(STATE).topics.flatMap((t) => t.queue).find((q) => q.id === TASK).submit.fields;

async function openSubmit(page) {
  await page.evaluate(() => { location.hash = ""; });
  await page.evaluate(() => { location.hash = "#submit=hlw-lesson-01"; });
  await page.waitForSelector("#submit:not([hidden]) #sub-fields textarea");
}

async function fill(page, value) {
  const areas = await page.$$("#sub-fields textarea");
  for (let i = 0; i < areas.length; i++) {
    await areas[i].evaluate((e, val) => { e.value = val; e.dispatchEvent(new Event("input", { bubbles: true })); }, value + " " + (i + 1));
  }
  return areas;
}

test("a closed draft comes back, and submitting clears it", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  assert.equal(fields().length, 3);
  await openSubmit(page);
  await page.type("#sub-fields textarea", "my long answer");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#submit", { hidden: true });
  await openSubmit(page);
  assert.equal(await page.$eval("#sub-fields textarea", (e) => e.value), "my long answer");
  const areas = await fill(page, "answer");
  assert.equal(areas.length, 3);
  if (await page.$("#sub-sure:not([hidden])")) await page.click('#sub-sure input[value="solid"]');
  await page.click("#sub-send");
  await page.waitForSelector("#submit", { hidden: true });
  await openSubmit(page);
  assert.equal(await page.$eval("#sub-fields textarea", (e) => e.value), "");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("Control+Enter in a field submits the form", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await openSubmit(page);
  const areas = await fill(page, "answer");
  if (await page.$("#sub-sure:not([hidden])")) await page.click('#sub-sure input[value="shaky"]');
  const before = readLines(INBOX).length;
  await areas[0].focus();
  await page.keyboard.down("Control");
  await page.keyboard.press("Enter");
  await page.keyboard.up("Control");
  await page.waitForSelector("#submit", { hidden: true });
  for (let i = 0; i < 40 && readLines(INBOX).length <= before; i++) await sleep(100);
  const lines = readLines(INBOX);
  assert.equal(lines.length, before + 1);
  assert.equal(lines.at(-1).task, TASK);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("Claude's reply links a task URL and shows a fenced block", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector("#btn-claude:not([hidden])");
  await page.click("#btn-claude");
  await page.waitForSelector("#claude:not([hidden])");
  const text = "Next: " + server.url + "#submit=hlw-lesson-01\n\n```\nprint(1)\n```";
  await page.$eval("#cl-input", (e, val) => { e.value = val; e.dispatchEvent(new Event("input", { bubbles: true })); }, text);
  await page.focus("#cl-input");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /You said:[\s\S]*print\(1\)/.test(document.querySelector("#cl-log").innerText), { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector(".cl-working"), { timeout: 15000 });
  const hrefs = await page.$$eval("#cl-log a", (as) => as.map((a) => a.getAttribute("href")));
  assert.ok(hrefs.some((h) => h && h.endsWith("#submit=hlw-lesson-01")), "links: " + hrefs.join(", "));
  const pres = await page.$$eval("#cl-log pre", (ps) => ps.map((p) => p.textContent));
  assert.ok(pres.some((t) => t.includes("print(1)")), "pre blocks: " + JSON.stringify(pres));
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
