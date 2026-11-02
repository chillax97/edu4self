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

// WCAG contrast of every visible text in the room against what's actually behind it (colours blended
// up the tree). Text over a picture (a gradient or SVG with no solid colour) can't be judged and is skipped.
function lowContrast() {
  const parse = (c) => {   // rgb(255 0 0 / .5), rgba(...), or color(srgb 1 0 0 / .5) from color-mix()
    const m = c.match(/[\d.]+/g);
    if (!m) return null;
    const k = c.startsWith("color(") ? 255 : 1;
    return { r: m[0] * k, g: m[1] * k, b: m[2] * k, a: m[3] === undefined ? 1 : +m[3] };
  };
  const over = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const behind = (el) => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const st = getComputedStyle(e), bg = parse(st.backgroundColor);
      if (bg && bg.a > 0) layers.push(bg);
      if (bg && bg.a >= 1) break;
      if (st.backgroundImage !== "none" && (!bg || bg.a < 1)) return null;
    }
    let c = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = layers.length - 1; i >= 0; i--) c = over(layers[i], c);
    return c;
  };
  const bad = [];
  const walker = document.createTreeWalker(document.querySelector(".room"), NodeFilter.SHOW_TEXT);
  const seen = new Set();
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!n.textContent.trim() || seen.has(el)) continue;
    seen.add(el);
    const st = getComputedStyle(el), r = el.getBoundingClientRect();
    if (!r.width || st.visibility === "hidden" || +st.opacity === 0 || el.closest("[aria-hidden=true]")) continue;
    const fg = parse(st.color), bg = behind(el);
    if (!fg || !bg) continue;
    const L1 = lum(over(fg, bg)), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    if (ratio < 3) bad.push(n.textContent.trim().slice(0, 40) + " (" + ratio.toFixed(1) + ")");
  }
  return bad;
}

function setConfig(extra) {
  const c = fs.existsSync(cfgPath) ? readJSON(cfgPath) : {};
  fs.writeFileSync(cfgPath, JSON.stringify({ ...c, ...extra }));
}

before(async () => {
  v = makeVault("Tester");
  cfgPath = path.join(v.vault, "_system", "config.json");
  // ten days of blocks and a graded lesson, so the finish line has a pace and dates to show
  const day = (n) => { const d = new Date(); d.setDate(d.getDate() - n); d.setHours(19, 0, 0, 0); return d; };
  const blocks = [];
  for (let n = 10; n >= 1; n--) blocks.push({ id: "b" + n, ts: new Date(day(n).getTime() + 50 * 60000).toISOString(), started: day(n).toISOString(), block: "lessons", minutes: 50 });
  fs.writeFileSync(path.join(v.vault, "_system", "blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + "\n");
  const st = readJSON(path.join(v.vault, "_system", "state.json")), m = st.topics[0].milestones[0];
  m.steps[0].done = true;
  fs.writeFileSync(path.join(v.vault, "_system", "state.json"), JSON.stringify(st));
  // goals the history above meets, so every room's shelf has trophies on it for the checks below
  fs.writeFileSync(cfgPath, JSON.stringify({ goals: { day_minutes: 45, week_days: 2 } }));
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
    test(`${id} on a ${label}: every slot drawn, readable, nothing spills sideways, no errors, the lesson opens`, async () => {
      setConfig({ theme: id });
      const page = await openPage(browser, server.url, { view: "bar", width: w, height: h, block: true });
      await page.waitForSelector(".room.t-" + id, { timeout: 5000 });
      await sleep(300);
      for (const slot of REQUIRED) {
        assert.ok(await page.$(`.room [data-slot="${slot}"]`), `${id} has its ${slot} slot`);
      }
      assert.ok(await page.$('.room [data-slot="shelf"] .ks-pile'), `${id} shows its shelf of trophies`);
      const job = await page.$eval('.room [data-slot="job"]', (e) => e.innerText.trim());
      assert.ok(job.length > 0, "the job line says something");
      assert.ok(await page.$('.room [data-slot="timer"] .bx-clock'), "the running block shows its timer");
      assert.deepEqual(await page.evaluate(lowContrast), [], `${id}: text too faint to read (contrast below 3:1)`);
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
  assert.equal(await page.$eval("#set-gifts", (e) => e.checked), true, "gifts start on");
  await page.$eval("#set-gifts", (e) => e.scrollIntoView({ block: "center" }));   // out from under the sticky Save bar
  await page.click("#set-gifts");
  await page.click("#set-save");
  await page.waitForSelector(".room.t-library", { timeout: 5000 });
  const c = readJSON(cfgPath);
  assert.equal(c.theme, "library");
  assert.equal(c.theme_lessons, false);
  assert.equal(c.gifts, false);
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
