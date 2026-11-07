// The neon sign's subtitle: a name can carry several lines; the next one shows each time the neon blinks.
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
// what the sign shows, and how bright the neon is, every 40 ms for a while
const watch = (page, ms) => page.evaluate((ms) => new Promise((done) => {
  const out = [], t0 = performance.now(), neon = document.querySelector(".bx-neon");
  const id = setInterval(() => {
    out.push([document.querySelector(".bx-neon [data-sub]").textContent, Number(getComputedStyle(neon).opacity)]);
    if (performance.now() - t0 > ms) { clearInterval(id); done(out); }
  }, 40);
}), ms);

test("the sign moves to the next line each time the neon blinks, while it's dim", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  try {
    await page.waitForSelector(".bx-neon [data-sub]");
    const seen = await watch(page, 7500);   // the neon blinks twice every 7 s
    const changes = [];
    for (let k = 1; k < seen.length; k++) if (seen[k][0] !== seen[k - 1][0]) changes.push([seen[k - 1][0], seen[k][0], seen[k][1]]);
    assert.ok(changes.length >= 2 && changes.length <= 3, "changes in 7.5 s: " + JSON.stringify(changes));
    for (const [from, to, opacity] of changes) {
      assert.equal(LINES.indexOf(to), (LINES.indexOf(from) + 1) % LINES.length, "one step at a time");
      assert.ok(opacity < 0.9, "it swapped while the neon was bright: " + opacity);
    }
    assert.deepEqual(page.errors, []);
  } finally { await closePage(page); }
});

test("a running block holds the line it had", async () => {
  const page = await openPage(browser, server.url, { view: "bar", block: true });
  try {
    await page.waitForSelector(".bx-neon [data-sub]");
    const seen = await watch(page, 7500);
    assert.equal(new Set(seen.map((s) => s[0])).size, 1);
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
