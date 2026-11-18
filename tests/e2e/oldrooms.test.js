// A room saved in a vault for the engine as it was before the shared room base (3169b40) keeps its layout.
// The fixtures are the bar and the tea house exactly as they shipped then.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, sleep } from "./harness.js";

const OLD = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "fixtures", "old-rooms");
let v, server, browser;
const config = (theme) => fs.writeFileSync(path.join(v.vault, "_system", "config.json"), JSON.stringify({ theme }));

before(async () => {
  v = makeVault("Kim");
  for (const id of ["bar", "tea"]) fs.cpSync(path.join(OLD, id), path.join(v.vault, "themes", id), { recursive: true });
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => { await browser?.close(); await stopServer(server); fs.rmSync(v.dir, { recursive: true, force: true }); });

for (const id of ["bar", "tea"]) {
  test(`an old ${id} saved in the vault keeps its columns, its job and its running block`, async () => {
    config(id);
    const page = await openPage(browser, server.url, { view: "bar", width: 1440, height: 900, room: "front", block: true });
    await page.waitForSelector(".room.t-" + id, { timeout: 5000 });
    await sleep(300);
    const look = await page.evaluate(() => {
      const box = (s) => { const r = document.querySelector(s).getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width }; };
      return { job: box('.room [data-slot="job"]'), block: box('.room [data-slot="block"]'), sideways: document.documentElement.scrollWidth - innerWidth,
        title: document.querySelector('.room [data-slot="job"] h2')?.innerText, styled: getComputedStyle(document.querySelector(".room .bx-juke")).position };
    });
    assert.ok(look.block.left >= look.job.right - 1, `the block stands beside the job (job ends ${look.job.right}, block starts ${look.block.left})`);
    assert.ok(look.block.top < look.job.bottom && look.job.top < look.block.bottom, "and on the same rows");
    assert.ok(look.job.width >= 400 && look.job.width <= 1000, `the job keeps a column's width (${look.job.width})`);
    assert.ok(look.title, "the job names the task");
    assert.equal(look.styled, "relative", "the room's parts have their styling");
    assert.ok(look.sideways <= 0, "nothing spills sideways");
    const clock = () => page.$eval('.room [data-slot="block"] [data-clock]', (e) => e.textContent);
    const first = await clock();
    await page.waitForFunction((t) => document.querySelector('.room [data-slot="block"] [data-clock]').textContent !== t, { timeout: 4000 }, first);
    await page.click('.room [data-slot="replies"] [data-submit="hlw-lesson-01"]');
    await page.waitForSelector("#submit:not([hidden])");
    assert.ok(await page.$('link#room-compat[href="room-compat.css"]'), "it runs with the old room styles");
    assert.deepEqual(page.errors, []);
    await closePage(page);
  });
}

test("a built-in room does not load the old room styles, and leaving an old room drops them", async () => {
  fs.rmSync(path.join(v.vault, "themes", "tea"), { recursive: true, force: true });
  config("tea");
  const page = await openPage(browser, server.url, { view: "bar", width: 1440, height: 900, room: "front" });
  await page.waitForSelector(".room.t-tea", { timeout: 5000 });
  assert.equal(await page.$("#room-compat"), null);
  await closePage(page);
  config("bar");   // the old bar is still in the vault
  const old = await openPage(browser, server.url, { view: "bar", width: 1440, height: 900, room: "front" });
  await old.waitForSelector("#room-compat");
  await old.evaluate(async () => { await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config: { theme: "tea" } }) }); });
  await old.reload({ waitUntil: "networkidle0" });
  await old.waitForSelector(".room.t-tea", { timeout: 5000 });
  assert.equal(await old.$("#room-compat"), null);
  await closePage(old);
});
