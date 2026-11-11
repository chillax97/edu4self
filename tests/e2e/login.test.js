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
let v, server, broken, brokenServer, waiting, waitingServer, browser;

before(async () => {
  v = makeVault("Tester");
  v.env.EDU4SELF_CLAUDE = path.join(v.dir, "claude.py");          // not there yet: Claude Code is "not installed"
  v.env.FAKE_CLAUDE_SIGNED_OUT = path.join(v.dir, "signed-out");  // signed out while this file exists
  server = await startServer(v, await freePort());
  broken = makeVault("Tester");
  broken.env.EDU4SELF_CLAUDE = FAKE;
  broken.env.FAKE_CLAUDE_FAIL = "1";                               // every run ends with an error
  brokenServer = await startServer(broken, await freePort());
  // every open task already submitted, so the task up next on the page is one waiting to be graded, and its
  // card carries a Grade button of its own (with the reason beside it while Claude can't run)
  waiting = makeVault("Tester");
  waiting.env.EDU4SELF_CLAUDE = path.join(waiting.dir, "claude.py");
  waiting.env.FAKE_CLAUDE_SIGNED_OUT = path.join(waiting.dir, "signed-out");
  const ts = new Date().toISOString();
  fs.writeFileSync(path.join(waiting.vault, "_system", "inbox.jsonl"), ["hlw-lesson-01", "hlw-probe-01"].map((task) =>
    JSON.stringify({ id: "sub-" + task, ts, topic: "how-learning-works", task, kind: "answers", fields: { 1: "x" }, confidence: "shaky" }) + "\n").join(""));
  waitingServer = await startServer(waiting, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  await stopServer(brokenServer);
  await stopServer(waitingServer);
  for (const x of [v, broken, waiting]) fs.rmSync(x.dir, { recursive: true, force: true });
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

// What the greyed Grade looks like: plainly off (no fill, no glow, a not-allowed cursor), with the reason on hover,
// and its label still readable (WCAG 4.5:1 against what's behind it). Returns null when there's no such button.
const offLook = (page, sel) => page.$eval(sel, (el) => {
  const parse = (c) => { const m = c.match(/[\d.]+/g); if (!m) return null; const k = c.startsWith("color(") ? 255 : 1; return { r: m[0] * k, g: m[1] * k, b: m[2] * k, a: m[3] === undefined ? 1 : +m[3] }; };
  const over = (t, u) => ({ r: t.r * t.a + u.r * (1 - t.a), g: t.g * t.a + u.g * (1 - t.a), b: t.b * t.a + u.b * (1 - t.a), a: 1 });
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const layers = []; let opacity = 1;
  for (let e = el; e; e = e.parentElement) { const st = getComputedStyle(e), bg = parse(st.backgroundColor); opacity *= +st.opacity; if (bg && bg.a > 0) layers.push(bg); if (bg && bg.a >= 1) break; }
  let bg = { r: 255, g: 255, b: 255, a: 1 };
  for (let i = layers.length - 1; i >= 0; i--) bg = over(layers[i], bg);
  const st = getComputedStyle(el), fg = parse(st.color); fg.a *= opacity;
  const L1 = lum(over(fg, bg)), L2 = lum(bg);
  return { disabled: el.disabled, title: el.title, fill: parse(st.backgroundColor).a, glow: st.boxShadow, cursor: st.cursor,
    ratio: +((Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)).toFixed(2) };
});
function assertOff(look, where) {
  assert.ok(look, `${where}: a greyed Grade is there`);
  assert.equal(look.disabled, true, `${where}: Grade is disabled`);
  assert.equal(look.fill, 0, `${where}: no accent fill`);
  assert.equal(look.glow, "none", `${where}: no glow`);
  assert.equal(look.cursor, "not-allowed", `${where}: the cursor says no`);
  assert.ok(look.title, `${where}: the reason is on hover`);
  assert.ok(look.ratio >= 4.5, `${where}: the label is readable (contrast ${look.ratio}:1)`);
}
const ROOMS = fs.readdirSync(path.join(ENGINE, "app", "dashboard", "themes")).sort();
const setTheme = (x, theme) => {
  const p = path.join(x.vault, "_system", "config.json"), c = fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : {};
  fs.writeFileSync(p, JSON.stringify({ ...c, theme }));
};

test("the greyed Grade in the top bar reads as off, in classic and in every room", async () => {
  for (const where of ["classic", ...ROOMS]) {
    if (where !== "classic") setTheme(v, where);
    const page = await openPage(browser, server.url, { view: where === "classic" ? "classic" : "bar" });
    await page.waitForSelector("#btn-grade:not([hidden])");
    assertOff(await offLook(page, "#btn-grade"), where + " top bar");
    assert.deepEqual(page.errors, []);
    await closePage(page);
  }
  setTheme(v, "bar");
});

// The green "Submitted just now" line on the card of the task up next. Light green is right on a dark room, but on
// the paper cards (library, tea, train) it was about 1.2:1, so each room has to give it a colour readable on its card.
test("the Submitted line on the task card is readable in every room, whatever Claude's state", async () => {
  for (const where of ROOMS) {
    setTheme(waiting, where);
    const page = await openPage(browser, waitingServer.url, { view: "bar" });
    await page.waitForSelector(".room .bx-sent");
    const line = await offLook(page, ".room .bx-sent");
    assert.ok(line.ratio >= 4.5, `${where}: the Submitted line is readable (contrast ${line.ratio}:1)`);
    assert.deepEqual(page.errors, []);
    await closePage(page);
  }
  setTheme(waiting, "bar");
});

// The card of the task up next (classic: the hero; rooms: the job) and the Grade inside it
const CARD = { classic: ".hero-submitted", bar: ".room .bx-sent" };
const cardGrade = (page, where) => page.$eval(CARD[where], (c) => {
  const b = c.querySelector("button.btn-topic"), why = c.querySelector(".cl-why");
  return { disabled: b.disabled, title: b.title, grades: b.dataset.claude === "grade", why: why ? why.innerText : null };
});

test("the Grade in the card of the task up next: greyed with the reason while Claude is missing or signed out, live once signed in", async () => {
  // missing: classic and every room
  for (const where of ["classic", ...ROOMS]) {
    if (where !== "classic") setTheme(waiting, where);
    const page = await openPage(browser, waitingServer.url, { view: where === "classic" ? "classic" : "bar" });
    const sel = CARD[where === "classic" ? "classic" : "bar"];
    await page.waitForSelector(sel + " .cl-why");
    assert.deepEqual(await cardGrade(page, where === "classic" ? "classic" : "bar"),
      { disabled: true, title: "Needs Claude Code", grades: false, why: "Needs Claude Code, see the note at the top." }, where);
    assertOff(await offLook(page, sel + " .is-off"), where + " card");
    const why = await offLook(page, sel + " .cl-why");
    assert.ok(why.ratio >= 4.5, `${where}: the reason beside Grade is readable (contrast ${why.ratio}:1)`);
    assert.deepEqual(page.errors, []);
    await closePage(page);
  }
  setTheme(waiting, "bar");

  // signed out, then signed in, on one page that's left open
  fs.writeFileSync(path.join(waiting.dir, "signed-out"), "");
  fs.copyFileSync(FAKE, waiting.env.EDU4SELF_CLAUDE);
  const page = await openPage(browser, waitingServer.url, { view: "classic" });
  await sleep(5500);                                                // the server asks again at most every 5 s
  await focus(page);
  await page.waitForFunction(() => /isn't signed in/.test(document.querySelector("#cl-gate").innerText));
  await page.waitForFunction(() => /Sign in/.test(document.querySelector(".hero-submitted .cl-why")?.innerText || ""));
  assert.deepEqual(await cardGrade(page, "classic"),
    { disabled: true, title: "Sign in to Claude Code first", grades: false, why: "Sign in to Claude Code first, see the note at the top." });

  fs.rmSync(path.join(waiting.dir, "signed-out"));
  await sleep(5500);
  await focus(page);
  await page.waitForSelector("#cl-gate", { hidden: true });
  await page.waitForSelector('.hero-submitted [data-claude="grade"]');
  assert.deepEqual(await cardGrade(page, "classic"), { disabled: false, title: "", grades: true, why: null });
  assert.equal(await page.$(".is-off"), null, "nothing looks off once Claude works");
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
