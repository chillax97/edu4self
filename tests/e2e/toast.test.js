// The toaster: one place for every notice. Toasts stack bottom right (newest in front), wait while the
// pointer is on them, close on their button, and keep the old #toast element's text for older checks.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, openPage, closePage, sleep } from "./harness.js";

let v, server, browser;
before(async () => {
  v = makeVault("Kim");
  v.env.EDU4SELF_CLAUDE = path.join(ENGINE, "tests", "fake_claude.py");
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
});

const live = (page) => page.$$eval("#toast > li:not([data-removed])", (l) => l.map((t) => ({
  text: t.innerText.replace(/\s+/g, " ").trim(), front: t.dataset.front === "true", r: t.getBoundingClientRect().toJSON() })));

for (const [w, view] of [[1440, "classic"], [720, "bar"]]) {
  test(`${view} at ${w}px: toasts stack bottom right, newest in front, three at most in sight`, async () => {
    const page = await openPage(browser, server.url, { view, width: w, height: 900 });
    for (const n of [1, 2, 3, 4]) await page.evaluate((n) => window.edu4self.toast("<b>Notice " + n + "</b>", 20000), n);
    await sleep(400);
    const ts = await live(page);
    assert.equal(ts.length, 4, "every toast is kept until it closes");
    assert.ok(ts[3].front && /Notice 4/.test(ts[3].text), "the newest is in front");
    const front = ts[3].r;
    assert.ok(front.right >= w - 40 && front.right <= w, `bottom right: right edge at ${front.right}`);
    // low on the right: in the corner, or lifted just clear of a control under it (the last test), never past half the screen
    assert.ok(front.bottom > 900 / 2 && front.bottom <= 900 - 16, `bottom right: bottom edge at ${front.bottom}`);
    const seen = await page.$$eval("#toast > li", (l) => l.filter((t) => getComputedStyle(t).opacity > 0.05).length);
    assert.equal(seen, 3, "three in sight, the oldest waits behind");
    assert.match(await page.$eval("#toast", (e) => e.innerText), /Notice 4/, "#toast still holds the text");
    assert.equal(await page.$eval("#toast", (e) => e.getAttribute("aria-live")), "polite");
    assert.deepEqual(page.errors, []);
    await closePage(page);
  });
}

test("a toast waits while the pointer is on it, then closes on time", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.evaluate(() => window.edu4self.toast("<b>Hold on</b>", 1200));
  await page.waitForSelector("#toast > li[data-mounted]");
  await sleep(450);   // in place, as a person would see it before pointing at it
  await page.hover("#toast > li");
  await sleep(2200);
  assert.equal((await live(page)).length, 1, "still there after its time, while hovered");
  await page.mouse.move(10, 10);
  await page.waitForFunction(() => !document.querySelector("#toast > li:not([data-removed])"), { timeout: 4000 });
  await sleep(400);
  assert.equal(await page.$eval("#toast", (e) => e.hidden), true, "an empty toaster is hidden");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a toast closes on its button, and the others stay", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.evaluate(() => { window.edu4self.toast("<b>First</b>", 20000); window.edu4self.toast("<b>Second</b>", 20000); });
  await page.waitForFunction(() => document.querySelectorAll("#toast > li").length === 2);
  await page.hover("#toast");   // the stack opens on hover, so every close button can be reached
  await sleep(300);
  await page.click('#toast > li[data-front="true"] button[aria-label="Close"]');
  await page.waitForFunction(() => document.querySelectorAll("#toast > li").length === 1, { timeout: 2000 });
  assert.match((await live(page))[0].text, /First/);
  await page.keyboard.press("Tab");   // nothing breaks after a close; keyboard focus still moves
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a toast never sits on the page's own controls (the bar's jukebox at the bottom right of a 1440×1000 screen)", async () => {
  const page = await openPage(browser, server.url, { view: "bar", width: 1440, height: 1000 });
  await page.evaluate(() => window.edu4self.toast("<b>Settings saved.</b>", 20000));
  await sleep(700);
  const under = () => page.evaluate(() => {
    const t = document.querySelector("#toast > li[data-front='true']").getBoundingClientRect();
    return [...document.querySelectorAll("button, a[href], input, select, textarea")].filter((e) => {
      if (e.closest("#toast")) return false;
      const b = e.getBoundingClientRect();
      return b.width && b.height && b.right > t.left && b.left < t.right && b.bottom > t.top && b.top < t.bottom;
    }).map((e) => e.dataset.mu || e.id || e.className);
  });
  assert.deepEqual(await under(), [], "the toast is lifted clear of the controls under it");
  await page.mouse.wheel({ deltaY: 120 });   // and stays clear as the page scrolls
  await sleep(700);
  assert.deepEqual(await under(), []);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
