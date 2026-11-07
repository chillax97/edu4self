// The neon sign's subtitle: a name can carry several lines that rotate every 30 seconds.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, sleep } from "./harness.js";

let v, server, browser, cfgPath;
const LINES = ["line one", "line two", "line three"];

before(async () => {
  v = makeVault("Tester");
  cfgPath = path.join(v.vault, "_system", "config.json");
  fs.writeFileSync(cfgPath, JSON.stringify({ theme: "bar", bar: { names: [["Bad Tokens", LINES], ["Plain Name", "just one"]] } }));
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

const sub = (page) => page.$eval(".bx-neon [data-sub]", (e) => e.textContent);
const want = (page) => page.evaluate((l) => l[Math.floor(Date.now() / 30000) % l.length], LINES);

test("the sign shows one line, and the next one 30 seconds later", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  try {
    await page.waitForSelector(".bx-neon [data-sub]");
    // a clock we can push forward: Date.now is read at call time, so the page picks it up
    await page.evaluate(() => { const real = Date.now; window.__skew = 0; Date.now = () => real() + window.__skew; });
    await page.waitForFunction((l) => l.includes(document.querySelector(".bx-neon [data-sub]").textContent), {}, LINES);
    const first = await want(page);
    await page.waitForFunction((t) => document.querySelector(".bx-neon [data-sub]").textContent === t, { timeout: 5000 }, first);
    await page.evaluate(() => { window.__skew += 30000; });
    const next = await want(page);
    assert.notEqual(next, first);
    await page.waitForFunction((t) => document.querySelector(".bx-neon [data-sub]").textContent === t, { timeout: 6000 }, next);
    assert.equal(await sub(page), next);
    assert.deepEqual(page.errors, []);
  } finally { await closePage(page); }
});

test("a running block holds the line it had", async () => {
  const page = await openPage(browser, server.url, { view: "bar", block: true });
  try {
    await page.waitForSelector(".bx-neon [data-sub]");
    await page.evaluate(() => { const real = Date.now; window.__skew = 0; Date.now = () => real() + window.__skew; });
    const held = await sub(page);
    await page.evaluate(() => { window.__skew += 30000; });
    await sleep(2800);
    assert.equal(await sub(page), held);
  } finally { await closePage(page); }
});

test("Settings shows both shapes and saves them back the same way", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  try {
    await page.click("#btn-settings");
    await page.waitForSelector("#settings:not([hidden]) #set-names");
    assert.equal(await page.$eval("#set-names", (e) => e.value), "Bad Tokens | line one\n| line two\n| line three\nPlain Name | just one");
    await page.click("#set-save");
    await page.waitForSelector("#settings", { hidden: true });
    assert.deepEqual(readJSON(cfgPath).bar.names, [["Bad Tokens", LINES], ["Plain Name", "just one"]]);

    // typing: one line stays a string, two become a list
    await page.click("#btn-settings");
    await page.waitForSelector("#settings:not([hidden]) #set-names");
    await page.$eval("#set-names", (e) => { e.value = "A | solo\nB | x\n| y\nC"; });
    await page.click("#set-save");
    await page.waitForSelector("#settings", { hidden: true });
    assert.deepEqual(readJSON(cfgPath).bar.names, [["A", "solo"], ["B", ["x", "y"]], ["C", ""]]);
  } finally { await closePage(page); }
});
