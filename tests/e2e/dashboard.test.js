// The dashboard in a real browser: both views, submitting, focus blocks, Settings, music.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import http from "node:http";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, wavFile, readJSON, readLines, sleep } from "./harness.js";

let PORT;

// Click after centring: puppeteer only scrolls when an element is fully off-screen, and Settings
// has a sticky footer that can cover a control sitting at the bottom edge.
async function tap(page, sel) {
  await page.$eval(sel, (e) => e.scrollIntoView({ block: "center" }));
  await page.click(sel);
}
let v, server, browser;

before(async () => {
  v = makeVault("Tester");
  PORT = await freePort();
  server = await startServer(v, PORT);
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

test("first visit: onboarding, then the bar with the example topic", async () => {
  const page = await browser.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  await page.goto(server.url, { waitUntil: "networkidle0" });
  await page.waitForSelector("#onboarding:not([hidden])");
  assert.match(await page.$eval("#ob-title", (e) => e.textContent), /Welcome to edu4self/);
  await page.click("#ob-next"); await page.click("#ob-next"); await page.click("#ob-next");
  assert.equal(await page.$eval("#onboarding", (e) => e.hidden), true);
  assert.ok(await page.$("body.v-bar"), "bar is the default view");
  assert.match(await page.$eval(".bx-neon", (e) => e.textContent), /Cache Miss/);
  assert.match(await page.$eval(".bx-job h2", (e) => e.textContent), /Retrieval beats rereading/);
  // the jukebox has a built-in soundscape, paused: never empty, never online by default
  assert.match(await page.$eval(".bx-music", (e) => e.textContent), /Night shift.*paused/s);
  const voices = await page.$$eval(".bx-who", (els) => els.map((e) => e.textContent));
  assert.ok(voices.includes("Willpower") && voices.includes("Logic"), "voices speak: " + voices.join(", "));
  assert.ok(!voices.some((n) => /Volition|Encyclopedia|Physical instrument/.test(n)), "no borrowed skill names");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

// Web Audio has no element to inspect, so tap the line into the speakers and measure what goes through it
async function listen(page) {
  await page.evaluateOnNewDocument(() => {
    const connect = AudioNode.prototype.connect;
    AudioNode.prototype.connect = function (dest, ...rest) {
      if (dest instanceof AudioDestinationNode) {
        const ctx = this.context;
        if (!ctx.__tap) { ctx.__tap = ctx.createAnalyser(); connect.call(ctx.__tap, dest); window.__tap = ctx.__tap; }
        return connect.call(this, ctx.__tap, ...rest);
      }
      return connect.call(this, dest, ...rest);
    };
  });
}
const level = (page) => page.evaluate(() => {
  if (!window.__tap) return 0;
  const d = new Float32Array(2048); window.__tap.getFloatTimeDomainData(d);
  return Math.sqrt(d.reduce((a, x) => a + x * x, 0) / d.length);
});

test("the soundscape plays, makes real sound, and switches without a file or the internet", async () => {
  const page = await browser.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  const offsite = [];
  page.on("request", (r) => { if (!r.url().startsWith(server.url) && !r.url().startsWith("data:")) offsite.push(r.url()); });
  await listen(page);
  await page.evaluateOnNewDocument(() => { localStorage.setItem("edu.onboarded.v1", "1"); localStorage.setItem("edu.view.v1", "bar"); });
  await page.goto(server.url, { waitUntil: "networkidle0" });
  await page.waitForSelector('.bx-music [data-mu="toggle"]');
  assert.equal(await level(page), 0, "silent until asked");
  for (const id of ["night", "rain", "noise"]) {
    if (id !== "night") {
      await page.click(`.bx-music [data-scape="${id}"]`);
      await page.waitForFunction((id) => document.querySelector(`[data-scape="${id}"]`)?.getAttribute("aria-pressed") === "true", {}, id);
    } else {
      await page.click('.bx-music [data-mu="toggle"]');
    }
    await page.waitForFunction(() => document.body.classList.contains("music-on"));
    // "night" is music with gaps (a chord every 3.3 s that fades before the next), so one 43 ms sample can
    // land in a gap on a slow machine. Audible means: the loudest moment over 1.5 s, after the fade-in.
    await sleep(2000);
    let rms = 0;
    for (let i = 0; i < 15; i++) { rms = Math.max(rms, await level(page)); await sleep(100); }
    assert.ok(rms > 0.002, id + " is audible: loudest rms " + rms.toFixed(4));
  }
  assert.equal(readJSON(path.join(v.vault, "_system", "config.json")).music.scape, "noise");
  await page.click('.bx-music [data-mu="toggle"]');
  await page.waitForFunction(() => !document.body.classList.contains("music-on"));
  // Pause fades out (time constant 0.15 s) and frees the nodes at 0.8 s. A slow machine's audio thread
  // can run behind the page clock, so wait for silence instead of sampling one fixed moment.
  let quiet = Infinity;
  for (let i = 0; i < 30 && quiet >= 0.001; i++) { await sleep(100); quiet = await level(page); }
  assert.ok(quiet < 0.001, "pause is silence within 3 s: rms " + quiet.toFixed(4));
  assert.deepEqual(offsite, [], "nothing loaded from the internet");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("classic view greets by name and has every card", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  assert.match(await page.$eval(".greeting h1", (e) => e.textContent), /, Tester\./);
  const titles = await page.$$eval(".card-title", (els) => els.map((e) => e.textContent.toLowerCase()));
  // a topic with no proof yet is one quiet card, not four empty ones
  for (const want of ["focus block", "finish line · m1", "your topic · not started", "add a topic"]) {
    assert.ok(titles.some((t) => t.includes(want)), "missing card: " + want + " in " + titles.join(" | "));
  }
  assert.ok(!titles.some((t) => t.includes("readiness")), "no gate card when no topic has a gate");
  assert.equal(await page.$eval("#footer-port", (e) => e.textContent), "127.0.0.1:" + PORT);
  // the mission link opens the note as text, since Obsidian is off by default
  const href = await page.$eval(".topic-links a", (a) => a.getAttribute("href"));
  assert.equal(href, "/vault/how-learning-works/MISSION.md");
  const r = await fetch(new URL(href, server.url));
  assert.equal(r.status, 200);
  assert.match(r.headers.get("content-type"), /^text\/plain/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("submitting answers lands in the inbox", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.click('.bx-replies [data-submit="hlw-lesson-01"]');
  await page.waitForSelector("#submit:not([hidden])");
  const areas = await page.$$("#sub-fields textarea");
  assert.equal(areas.length, 3);
  await areas[0].type("How easy it is now vs how long it lasts");
  await page.click("#sub-send");
  await page.waitForSelector("#submit", { hidden: true });
  const inbox = readLines(path.join(v.vault, "_system", "inbox.jsonl"));
  assert.equal(inbox.length, 1);
  assert.equal(inbox[0].task, "hlw-lesson-01");
  assert.equal(inbox[0].fields["1. Retrieval strength vs storage strength, in your own words"], "How easy it is now vs how long it lasts");
  // Up next moves on to the probe; the lesson waits for Claude
  await page.waitForFunction(() => /How you study now/.test(document.querySelector(".bx-job h2").textContent));
  assert.match(await page.$eval(".bx-replies", (e) => e.textContent), /submitted, waiting for Claude/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a focus block starts, shows its clock, and stops", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.click('#block [data-min="25"]');
  await page.click("#block [data-blk-start]");
  await page.waitForSelector("#blk-pill:not([hidden])");
  assert.match(await page.$eval("#blk-pill", (e) => e.textContent), /Lessons/);
  assert.match(await page.$eval("[data-clock]", (e) => e.textContent), /^2[45]:\d\d$/);
  await page.click("#block [data-blk-stop]");   // confirm() is auto-accepted
  await page.waitForSelector("#blk-pill", { hidden: true });
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("Settings: change everything, upload music, survive a restart, then reset", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.click("#btn-settings");
  await page.waitForSelector("#settings:not([hidden]) #set-name");

  const set = async (sel, val) => { await page.$eval(sel, (e) => (e.value = "")); await page.type(sel, val); };
  await set("#set-name", "Ada");
  await set("#set-day", "90");
  await tap(page, 'input[name="set-water"][value="30"]');
  await set(".set-kind[data-kind='1'] [data-k='label']", "Drills");
  await tap(page, "#set-kind-add");
  await set(".set-kind[data-kind='5'] [data-k='label']", "Deep work");
  await set(".set-kind[data-kind='5'] [data-k='minutes']", "45");
  await set("#set-names", "The Test Bar | open late\nSecond Name");
  await set("#set-lines", "regular: The test regular has a test drink.");
  await set('[data-voice="volition"]', "Grit");

  // music: upload a real audio file through the file picker
  const wav = wavFile(v.dir);
  const input = await page.$("#set-mu-file");
  await input.uploadFile(wav);
  await page.waitForSelector(".set-track");
  assert.match(await page.$eval(".set-track", (e) => e.textContent), /Test-Tone\.wav/);
  await set("#set-mu-title", "Test Tone");

  await tap(page, "#set-save");
  await page.waitForSelector("#settings", { hidden: true });

  const cfg = readJSON(path.join(v.vault, "_system", "config.json"));
  assert.equal(cfg.name, "Ada");
  assert.equal(cfg.goals.day_minutes, 90);
  assert.equal(cfg.water.every, 30);
  assert.equal(cfg.blocks.kinds[1].label, "Drills");
  assert.deepEqual(cfg.blocks.kinds[5], { id: "deep-work", label: "Deep work", color: cfg.blocks.kinds[5].color, minutes: 45 });
  assert.deepEqual(cfg.bar.names[0], ["The Test Bar", "open late"]);
  assert.deepEqual(cfg.bar.lines, [{ voice: "regular", text: "The test regular has a test drink." }]);
  assert.equal(cfg.bar.voices.volition.name, "Grit");
  assert.equal(cfg.music.file, "Test-Tone.wav");
  assert.equal(cfg.music.title, "Test Tone");
  assert.ok(fs.existsSync(path.join(v.vault, "_system", "music", "Test-Tone.wav")));

  // the page uses it at once
  await page.waitForFunction(() => /The Test Bar/.test(document.querySelector(".bx-neon").textContent));
  assert.match(await page.$eval(".bx-music", (e) => e.textContent), /Test Tone/);
  const voices = await page.$$eval(".bx-who", (els) => els.map((e) => e.textContent));
  assert.ok(voices.includes("Grit"), "renamed voice shows: " + voices.join(", "));
  assert.deepEqual(page.errors, []);
  await closePage(page);

  // restart the server: everything is on disk, so it all comes back
  await stopServer(server);
  server = await startServer(v, PORT);
  const p2 = await openPage(browser, server.url, { view: "classic" });
  assert.match(await p2.$eval(".greeting h1", (e) => e.textContent), /, Ada\./);
  const kinds = await p2.$$eval("#block [data-blk]", (els) => els.map((e) => e.textContent.trim()));
  assert.deepEqual(kinds, ["Lessons", "Drills", "Reading", "Free", "Play", "Deep work"]);
  assert.equal(await p2.$eval('#block [data-water="30"]', (e) => e.getAttribute("aria-pressed")), "true");
  const mu = await fetch(server.url + "music");
  assert.equal(mu.status, 200);
  assert.match(mu.headers.get("content-type"), /^audio\//);

  // reset: back to defaults, music kept
  await p2.click("#btn-settings");
  await p2.waitForSelector("#settings:not([hidden]) #set-reset");
  await tap(p2, "#set-reset");
  await p2.waitForSelector("#settings", { hidden: true });
  const after = readJSON(path.join(v.vault, "_system", "config.json"));
  assert.equal(after.name, "");
  assert.equal(after.blocks.kinds.length, 5);
  assert.equal(after.music.file, "Test-Tone.wav", "reset keeps the uploaded track");
  // the default look is the bar again, with the default names
  await p2.waitForFunction(() => document.body.classList.contains("v-bar") && /Cache Miss/.test(document.querySelector(".bx-neon").textContent));
  assert.deepEqual(p2.errors, []);
  await closePage(p2);
});

test("the jukebox plays the track, remembers the spot, and a bad setting is refused", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector('.bx-music [data-mu-seek]');   // the uploaded track, not the soundscape
  if (!(await page.evaluate(() => document.body.classList.contains("music-on")))) await page.click('.bx-music [data-mu="toggle"]');
  await page.waitForFunction(() => document.body.classList.contains("music-on"), { timeout: 8000 });
  // let it actually move before pausing: a slow machine can report "playing" at 0:00
  await page.waitForFunction(() => !/^0:00 /.test(document.querySelector(".bx-music [data-mu-time]").textContent), { timeout: 8000 });
  await page.click('.bx-music [data-mu="toggle"]');   // pause: saves the position
  await page.waitForFunction(() => !document.body.classList.contains("music-on"));
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("edu.music.v1")));
  assert.equal(saved.on, false);
  assert.ok(saved.t > 0, "position saved: " + saved.t);
  assert.equal(saved.file, "Test-Tone.wav");

  const r = await page.evaluate(async () => {
    const res = await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: { goals: { day_minutes: 5 } } }) });
    return { status: res.status, body: await res.json() };
  });
  assert.equal(r.status, 400);
  assert.match(r.body.error, /daily goal/);
  page.errors = page.errors.filter((e) => !/status of 400/.test(e));   // that 400 was the point

  // Settings → Remove deletes the file and empties the jukebox
  await page.click("#btn-settings");
  await page.waitForSelector("#set-mu-del");
  await tap(page, "#set-mu-del");
  await page.waitForFunction(() => !document.querySelector(".set-track"));
  assert.equal(fs.existsSync(path.join(v.vault, "_system", "music", "Test-Tone.wav")), false);
  await tap(page, "#settings [data-close]");
  // no file left: back to the soundscape
  await page.waitForFunction(() => /Night shift|Rain|Brown noise/.test(document.querySelector(".bx-music").textContent));
  assert.equal(readJSON(path.join(v.vault, "_system", "config.json")).music.source, "scape");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("radio: pick a station in Settings, and the jukebox streams it", async () => {
  // a stand-in station on another port, so the test never needs the internet
  const wav = fs.readFileSync(wavFile(v.dir, 30));
  const station = http.createServer((q, r) => { r.writeHead(200, { "Content-Type": "audio/wav", "Access-Control-Allow-Origin": "*" }); r.end(wav); });
  await new Promise((ok) => station.listen(0, "127.0.0.1", ok));
  const url = `http://127.0.0.1:${station.address().port}/live.wav`;
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.click("#btn-settings");
  await page.waitForSelector('#settings:not([hidden]) input[name="set-mu-src"][value="radio"]');
  await tap(page, 'input[name="set-mu-src"][value="radio"]');
  // a listed station fills in its address
  await tap(page, 'input[name="set-mu-station"][value="0"]');
  await tap(page, "#set-save");
  await page.waitForSelector("#settings", { hidden: true });
  let m = readJSON(path.join(v.vault, "_system", "config.json")).music;
  assert.equal(m.source, "radio");
  assert.match(m.stream.url, /^https:\/\/stream\.radioparadise\.com\//);
  // another station by address: typing it picks "Another station"
  await page.click("#btn-settings");
  await page.waitForSelector("#settings:not([hidden]) #set-mu-url");
  await tap(page, "#set-mu-url");
  await page.type("#set-mu-url", url);
  await page.type("#set-mu-sname", "Test FM");
  await page.$eval("#set-mu-url", (e) => e.dispatchEvent(new Event("change", { bubbles: true })));
  await tap(page, "#set-save");
  await page.waitForSelector("#settings", { hidden: true });
  m = readJSON(path.join(v.vault, "_system", "config.json")).music;
  assert.deepEqual(m.stream, { url, name: "Test FM" });
  await page.waitForFunction(() => /Test FM/.test(document.querySelector(".bx-music").textContent));
  if (!(await page.evaluate(() => document.body.classList.contains("music-on")))) await page.click('.bx-music [data-mu="toggle"]');
  await page.waitForFunction(() => document.body.classList.contains("music-on"), { timeout: 8000 });
  assert.match(await page.$eval(".bx-music", (e) => e.textContent), /live radio · 127\.0\.0\.1/);
  assert.equal(await page.$(".bx-music [data-mu-seek]"), null, "no scrubber on live radio");
  // a bad address is refused with a reason
  const r = await page.evaluate(async () => {
    const res = await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: { music: { source: "radio", stream: { url: "javascript:alert(1)" } } } }) });
    return { status: res.status, body: await res.json() };
  });
  assert.equal(r.status, 400);
  assert.match(r.body.error, /http/);
  page.errors = page.errors.filter((e) => !/status of 400/.test(e));
  await page.click('.bx-music [data-mu="toggle"]');
  await postReset();
  assert.deepEqual(page.errors, []);
  await closePage(page);
  station.close();
});
async function postReset() {
  // back to a soundscape for the tests after this one
  const cfg = readJSON(path.join(v.vault, "_system", "config.json"));
  cfg.music.source = "scape";
  const r = await fetch(server.url + "api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config: cfg }) });
  assert.equal(r.status, 200);
}

test("phone width: no sideways scrolling in either view or in Settings", async () => {
  for (const view of ["bar", "classic"]) {
    const page = await openPage(browser, server.url, { view, width: 390, height: 844, block: true });
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(over <= 0, view + " overflows by " + over + "px");
    // clipped is as bad as overflowing: every top-bar button must be fully on screen
    const off = await page.$$eval(".topbar-actions .btn", (bs) => bs.filter((b) => { const r = b.getBoundingClientRect(); return r.right > window.innerWidth || r.left < 0; }).map((b) => b.id));
    assert.deepEqual(off, [], view + ": buttons off screen");
    await page.click("#btn-settings");
    await page.waitForSelector("#settings:not([hidden]) #set-name");
    const drawerOver = await page.$eval(".set-drawer", (d) => d.scrollWidth - d.clientWidth);
    assert.ok(drawerOver <= 0, "settings overflows by " + drawerOver + "px");
    await page.click("#settings [data-close]");
    await page.click("#block [data-blk-stop]");   // leave no block running for the next view
    await page.waitForSelector("#blk-pill", { hidden: true });
    assert.deepEqual(page.errors, []);
    await closePage(page);
  }
});
