// Rooms: every built-in room draws, fits a phone, keeps its controls working, and dresses the lessons.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, sleep } from "./harness.js";

const ROOMS = fs.readdirSync(path.join(ENGINE, "app", "dashboard", "themes")).sort();
const REQUIRED = ["name", "rooms", "voices", "job", "replies", "block", "music", "tonight", "week", "die"];
const LESSON = "vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html";
let v, server, browser, cfgPath;

function setConfig(extra) {
  const c = fs.existsSync(cfgPath) ? readJSON(cfgPath) : {};
  fs.writeFileSync(cfgPath, JSON.stringify({ ...c, ...extra }));
}

before(async () => {
  v = makeVault("Tester");
  cfgPath = path.join(v.vault, "_system", "config.json");
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

test("there are five built-in rooms", () => {
  assert.deepEqual(ROOMS, ["bar", "library", "space", "tea", "train"]);
});

for (const id of ROOMS) {
  for (const [w, h, label] of [[1440, 1000, "desktop"], [390, 1400, "phone"]]) {
    test(`${id} on a ${label}: every slot drawn, nothing spills sideways, no errors, the lesson opens`, async () => {
      setConfig({ theme: id });
      const page = await openPage(browser, server.url, { view: "bar", width: w, height: h });
      await page.waitForSelector(".room.t-" + id, { timeout: 5000 });
      await sleep(300);
      for (const slot of REQUIRED) {
        assert.ok(await page.$(`.room [data-slot="${slot}"]`), `${id} has its ${slot} slot`);
      }
      const job = await page.$eval('.room [data-slot="job"]', (e) => e.innerText.trim());
      assert.ok(job.length > 0, "the job line says something");
      const spill = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      assert.ok(spill <= 0, `${id} spills ${spill}px sideways at ${w}px`);
      await page.click('.room [data-slot="replies"] [data-submit="hlw-lesson-01"]');
      await page.waitForSelector("#submit:not([hidden])");
      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  }

  test(`${id} dresses the lessons, and the toggle puts them back to plain`, async () => {
    setConfig({ theme: id, theme_lessons: true });
    const on = await (await fetch(server.url + LESSON)).text();
    assert.match(on, /href="\/theme\/lesson\.css"/);
    const css = await fetch(server.url + "theme/lesson.css");
    assert.equal(css.status, 200);
    assert.match(css.headers.get("content-type"), /text\/css/);
    setConfig({ theme_lessons: false });
    assert.doesNotMatch(await (await fetch(server.url + LESSON)).text(), /theme\/lesson\.css/);
  });
}

test("Settings switches the room and turns themed lessons off", async () => {
  setConfig({ theme: "bar", theme_lessons: true });
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector(".room.t-bar");
  await page.click("#btn-settings");
  await page.waitForSelector('input[name="set-theme"][value="library"]');
  assert.equal(await page.$$eval('input[name="set-theme"]', (l) => l.length), ROOMS.length);
  await page.click('input[name="set-theme"][value="library"]');
  await page.click("#set-theme-lessons");
  await page.click("#set-save");
  await page.waitForSelector(".room.t-library", { timeout: 5000 });
  const c = readJSON(cfgPath);
  assert.equal(c.theme, "library");
  assert.equal(c.theme_lessons, false);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a broken room of your own shows its problem in Settings and can't be picked", async () => {
  const d = path.join(v.vault, "themes", "wonky");
  fs.mkdirSync(d, { recursive: true });
  fs.writeFileSync(path.join(d, "theme.json"), JSON.stringify({ name: "Wonky" }));
  fs.writeFileSync(path.join(d, "layout.html"), '<div data-slot="job"></div><script>x()</script>');
  fs.writeFileSync(path.join(d, "theme.css"), ".room p { color: red }");
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.click("#btn-settings");
  await page.waitForSelector('input[name="set-theme"][value="wonky"]');
  assert.equal(await page.$eval('input[name="set-theme"][value="wonky"]', (e) => e.disabled), true);
  const why = await page.$eval('input[name="set-theme"][value="wonky"]', (e) => e.closest("label").innerText);
  assert.match(why, /Can't open/);
  // and a config that points at it anyway falls back to the bar instead of a blank page
  setConfig({ theme: "wonky" });
  const p2 = await openPage(browser, server.url, { view: "bar" });
  await p2.waitForSelector(".room.t-bar", { timeout: 5000 });
  await closePage(p2);
  await closePage(page);
  fs.rmSync(d, { recursive: true, force: true });
});
