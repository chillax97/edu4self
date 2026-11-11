// The calculator in the answer form: only on tasks whose state.json entry says calculator: true, read by
// its own parser (no eval), plain errors, keys that stay inside it, and its working sent with the answer.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, readLines } from "./harness.js";

let v, server, browser;
const sys = (f) => path.join(v.vault, "_system", f);

before(async () => {
  v = makeVault("Tester");
  const st = readJSON(sys("state.json"));
  st.topics[0].queue[0].calculator = true;         // the lesson allows one; the probe doesn't
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

async function openForm(page, task) {
  await page.evaluate((t) => document.querySelector('[data-submit="' + t + '"]').click(), task);
  await page.waitForSelector("#submit:not([hidden])");
}
async function calc(page, expr) {
  await page.click(".calc-input", { clickCount: 3 });
  await page.type(".calc-input", expr);
  await page.keyboard.press("Enter");
}
const history = (page) => page.$$eval(".calc-history li", (l) => l.map((e) => e.innerText.replace(/\s+/g, " ").trim()));
const errorText = (page) => page.$eval(".calc-error", (e) => (e.hidden ? "" : e.textContent));

test("a task without the flag has no calculator", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  try {
    await openForm(page, "hlw-probe-01");
    assert.equal(await page.$eval("#sub-calc", (e) => e.hidden), true);
    assert.equal(await page.$(".calc-input"), null);
    assert.deepEqual(page.errors, []);
  } finally { await closePage(page); }
});

test("with the flag the form has one: sums, units, powers and plain errors", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  try {
    await openForm(page, "hlw-lesson-01");
    assert.equal(await page.$eval("#sub-calc", (e) => e.hidden), false);
    assert.match(await page.$eval(".calc-hint", (e) => e.textContent), /KiB, MiB, GiB count in 1024s; KB, MB, GB in 1000s/);
    await calc(page, "2*32*128*2");
    assert.deepEqual(await history(page), ["2*32*128*2 = 16,384 (16 KiB)"]);
    assert.equal(await page.$eval(".calc-input", (e) => e.value), "", "the line is cleared for the next sum");
    await calc(page, "(1+2)*3^2");
    await calc(page, "4 MiB");
    await calc(page, "3 GB / 2**10");
    assert.deepEqual((await history(page)).slice(1), ["(1+2)*3^2 = 27", "4 MiB = 4,194,304 (4 MiB)", "3 GB / 2**10 = 2,929,687.5 (≈ 2.93e6)"]);
    for (const [bad, msg] of [["1/0", /^Can't divide by zero\.$/], ["2**", /^Couldn't read that: something is missing at the end\.$/],
                              ["(1+2", /^Couldn't read that: check the brackets\.$/], ["alert(1)", /^Couldn't read that: "alert" isn't a number or a unit\.$/]]) {
      await calc(page, bad);
      assert.match(await errorText(page), msg, bad);
    }
    assert.equal((await history(page)).length, 4, "errors add nothing to the history");
    assert.equal(await page.$eval("#submit", (e) => e.hidden), false, "Enter in the calculator doesn't send the form");
    assert.equal(await page.$eval("#sub-error", (e) => e.hidden), true);
    // a result goes back into the line; Escape clears the line first, then closes the form
    await page.click('.calc-history [data-calc-use="0"]');
    assert.equal(await page.$eval(".calc-input", (e) => e.value), "16384");
    await page.keyboard.press("Escape");
    assert.equal(await page.$eval(".calc-input", (e) => e.value), "");
    assert.equal(await page.$eval("#submit", (e) => e.hidden), false, "the first Escape only clears");
    await page.keyboard.press("Escape");
    await page.waitForSelector("#submit", { hidden: true });
    await openForm(page, "hlw-lesson-01");
    assert.equal((await history(page)).length, 4, "the working is still there when the form is opened again");
    assert.deepEqual(page.errors, []);
  } finally { await closePage(page); }
});

test("in the bar, typing 3 in the calculator doesn't pick reply 3", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  try {
    await page.waitForSelector(".bx-replies [data-n]");
    await page.evaluate(() => {
      window.__replies = [];
      document.addEventListener("click", (ev) => { const r = ev.target.closest("[data-n]"); if (r) window.__replies.push(r.dataset.n); }, true);
    });
    await openForm(page, "hlw-lesson-01");               // through its reply, so that click is the only one
    assert.equal((await page.evaluate(() => window.__replies)).length, 1);
    await page.evaluate(() => { window.__replies = []; });
    await page.focus(".calc-input");
    await page.keyboard.type("3");
    await page.keyboard.press("2");
    assert.equal(await page.$eval(".calc-input", (e) => e.value), "32");
    assert.deepEqual(await page.evaluate(() => window.__replies), []);
    assert.equal(await page.$eval("#submit", (e) => e.hidden), false);
    assert.deepEqual(page.errors, []);
  } finally { await closePage(page); }
});

test("the working goes to the inbox with the answer; an empty history sends nothing", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  try {
    await openForm(page, "hlw-lesson-01");
    await calc(page, "2*32*128*2");
    await calc(page, "16384*32");
    await page.type("#sub-fields textarea", "512 KiB per word");
    await page.click('#sub-sure input[value="shaky"]');
    await page.click("#sub-send");
    await page.waitForSelector("#submit", { hidden: true });
    const e = readLines(sys("inbox.jsonl")).pop();
    assert.equal(e.task, "hlw-lesson-01");
    assert.deepEqual(e.calc, [{ expr: "2*32*128*2", result: "16,384 (16 KiB)" }, { expr: "16384*32", result: "524,288 (512 KiB)" }]);
    // sent: the next form starts empty, and sends no calc at all
    await page.evaluate((id) => fetch("/api/withdraw", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }), e.id);
    await page.reload({ waitUntil: "networkidle0" });
    await page.waitForSelector("#app > :not(#loading)");
    await openForm(page, "hlw-lesson-01");
    assert.deepEqual(await history(page), []);
    await page.type("#sub-fields textarea", "no sums this time");
    await page.click('#sub-sure input[value="solid"]');
    await page.click("#sub-send");
    await page.waitForSelector("#submit", { hidden: true });
    const last = readLines(sys("inbox.jsonl")).pop();
    assert.equal(last.fields[Object.keys(last.fields)[0]], "no sums this time");
    assert.equal("calc" in last, false);
    assert.deepEqual(page.errors, []);
  } finally { await closePage(page); }
});

test("the job card says the calculator is allowed, in the classic view and the room", async () => {
  // the earlier answers are graded away so the lesson is the job again
  fs.writeFileSync(sys("inbox.jsonl"), "");
  const page = await openPage(browser, server.url, { view: "classic" });
  try {
    assert.equal(await page.$eval(".hero .calc-chip", (e) => e.textContent), "Calculator allowed");
    assert.equal(await page.$('.q-item .calc-chip'), null, "the probe in the queue has no chip");
  } finally { await closePage(page); }
  const bar = await openPage(browser, server.url, { view: "bar" });
  try {
    await bar.waitForSelector(".bx-job .bx-meta");
    assert.equal(await bar.$eval(".bx-job .calc-chip", (e) => e.textContent), "Calculator allowed");
    assert.deepEqual(bar.errors, []);
  } finally { await closePage(bar); }
});

test("a recall question can allow the calculator too", async () => {
  const st = readJSON(sys("state.json"));
  st.recall = [{ id: "rc-kv", q: "Bytes of KV cache per word for 32 layers, 128 dims, 2 bytes?", from: "hlw-lesson-01", calculator: true, added: "2026-01-01" }];
  st.topics[0].queue[0].status = "done";        // a question is shown only once its task passed 3+ days ago
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  const page = await openPage(browser, server.url, { view: "classic" });
  try {
    await page.waitForSelector("section.recall");
    await page.click('[data-recall="go"]');
    await page.waitForSelector("#submit:not([hidden])");
    assert.equal(await page.$eval("#sub-calc", (e) => e.hidden), false);
    await calc(page, "2*32*128*2");
    await page.type("#sub-fields textarea", "16 KiB");
    await page.click("#sub-send");
    await page.waitForSelector("#submit", { hidden: true });
    const e = readLines(sys("inbox.jsonl")).pop();
    assert.equal(e.kind, "recall");
    assert.deepEqual(e.calc, [{ expr: "2*32*128*2", result: "16,384 (16 KiB)" }]);
    assert.deepEqual(page.errors, []);
  } finally { await closePage(page); }
});
