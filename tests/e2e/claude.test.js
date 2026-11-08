// Claude, in the page: grading, chatting and starting a topic without a terminal.
// A stand-in (tests/fake_claude.py) plays Claude Code, so nothing here needs an account or the network.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, readLines } from "./harness.js";

let v, server, browser;
const LOG = () => path.join(v.dir, "fake-claude.log");
const runs = () => (fs.existsSync(LOG()) ? readLines(LOG()) : []);

before(async () => {
  v = makeVault("Tester");
  v.env.EDU4SELF_CLAUDE = path.join(ENGINE, "tests", "fake_claude.py");
  v.env.FAKE_CLAUDE_LOG = LOG();
  v.env.FAKE_CLAUDE_SLEEP = "0.6";   // long enough to see "working"
  server = await startServer(v, await freePort());
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

async function waitIdle(page) {
  await page.waitForFunction(() => !document.querySelector(".cl-working"), { timeout: 15000 });
}

test("with Claude Code installed, the top bar has Claude and a New topic button, not the note", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.waitForSelector("#btn-claude:not([hidden])");
  assert.equal(await page.$eval("#btn-note", (e) => e.hidden), true);
  assert.equal(await page.$eval("#btn-topic", (e) => e.hidden), false);
  assert.equal(await page.$eval("#btn-grade", (e) => e.hidden), true, "nothing to grade yet");
  const text = await page.$eval("body", (e) => e.innerText);
  assert.doesNotMatch(text, /check my inbox|Open Claude Code/i, "no terminal instructions");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("submit, then Grade: Claude grades in the page and the dashboard updates", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.click('.bx-replies [data-submit="hlw-lesson-01"]');
  await page.waitForSelector("#submit:not([hidden])");
  await (await page.$$("#sub-fields textarea"))[0].type("ease now vs lasting");
  await page.click('#sub-sure input[value="shaky"]');
  await page.click("#sub-send");
  await page.waitForSelector("#submit", { hidden: true });
  await page.waitForSelector("#btn-grade:not([hidden])");
  assert.match(await page.$eval("#btn-grade", (e) => e.textContent), /Grade 1/);

  await page.click("#btn-grade");
  await page.waitForSelector("#claude:not([hidden])");
  await page.waitForSelector(".cl-working");
  await waitIdle(page);
  const log = await page.$eval("#cl-log", (e) => e.innerText);
  assert.match(log, /Reading _system\/inbox\.jsonl/);
  assert.match(log, /Graded 1 submission/);
  assert.match(log, /Check OK/);
  assert.equal(runs().at(-1).args[runs().at(-1).args.indexOf("-p") + 1], "check my inbox");
  assert.equal(fs.realpathSync(runs().at(-1).cwd), fs.realpathSync(v.vault));
  // the page reloaded the state Claude wrote
  await page.waitForFunction(() => document.querySelector("#btn-grade").hidden);
  assert.equal(readJSON(path.join(v.vault, "_system", "state.json")).coach.headline, "Graded by the fake tutor.");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("chat: Enter sends, the next message resumes the same conversation, New conversation forgets it", async () => {
  const page = await openPage(browser, server.url, { view: "classic" });
  await page.click("#btn-claude");
  await page.waitForSelector("#claude:not([hidden])");
  await page.click("#cl-new");
  await page.type("#cl-input", "what should I do tonight?");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /You said: what should I do tonight/.test(document.querySelector("#cl-log").innerText));
  await waitIdle(page);
  assert.match(await page.$eval("#cl-log", (e) => e.innerText), /You said: what should I do tonight\?/);
  await page.type("#cl-input", "and after that?");
  await page.click("#cl-send");
  await page.waitForFunction(() => /You said: and after that/.test(document.querySelector("#cl-log").innerText));
  await waitIdle(page);
  const [a, b] = runs().slice(-2).map((r) => r.args);
  assert.ok(!a.includes("--resume"), "first message starts fresh");
  assert.ok(b.includes("--resume"), "second message continues: " + b.join(" "));
  await page.click("#cl-new");
  await page.waitForSelector(".cl-empty");
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("New topic: say what and why, Claude starts with the new-topic skill, teach as the fallback", async () => {
  const page = await openPage(browser, server.url, { view: "bar" });
  await page.click("#btn-topic");
  await page.waitForSelector("#newtopic:not([hidden])");
  await page.click('#nt-form button[type="submit"]');
  assert.equal(await page.$eval("#nt-error", (e) => e.hidden), false, "empty topic refused");
  await page.type("#nt-what", "Spanish, for a move to Madrid");
  await page.type("#nt-more", "20 minutes a day");
  await page.click('#nt-form button[type="submit"]');
  await page.waitForSelector("#newtopic", { hidden: true });
  // the stand-in echoes only the prompt's last 200 characters; the full prompt is checked from its run log below
  await page.waitForFunction(() => /You said:/.test(document.querySelector("#cl-log").innerText));
  await waitIdle(page);
  const p = runs().at(-1).args;
  const prompt = p[p.indexOf("-p") + 1];
  assert.match(prompt, /teach skill/);
  assert.match(prompt, /Spanish, for a move to Madrid\nMore about me: 20 minutes a day/);
  assert.match(prompt, /^Start a new topic with the edu4self new-topic skill \(if it isn't installed, the teach skill\)/);
  assert.match(prompt, /stays in that room's theme/);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("a sandboxed lesson can load its own fonts (the maths in lessons uses them)", async () => {
  const dir = path.join(v.vault, "how-learning-works", "assets");
  fs.writeFileSync(path.join(dir, "Math.woff2"), "wOF2 not really a font");
  fs.writeFileSync(path.join(v.vault, "how-learning-works", "lessons", "fonts.html"),
    "<!doctype html><style>@font-face{font-family:M;src:url(../assets/Math.woff2) format('woff2')}" +
    "p{font-family:M}</style><p>x</p>");
  const page = await browser.newPage();
  const logs = [];
  page.on("console", (m) => logs.push(m.text()));
  page.on("requestfailed", (r) => logs.push("failed " + r.url() + " " + r.failure()?.errorText));
  await page.goto(server.url + "vault/how-learning-works/lessons/fonts.html", { waitUntil: "networkidle0" });
  assert.equal(await page.evaluate(() => window.origin), "null", "the page is sandboxed");
  assert.deepEqual(logs.filter((l) => /CORS|failed .*Math\.woff2/.test(l)), [], "the font wasn't blocked");
  await closePage(page);
});

test("lessons run sandboxed: the quiz still works, but the page can't call the dashboard", async () => {
  const page = await browser.newPage();   // a plain tab: openPage seeds localStorage, which a sandboxed page can't touch
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  await page.goto(server.url + "vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html", { waitUntil: "networkidle0" });
  assert.equal(await page.evaluate(() => window.origin), "null", "opaque origin");
  await page.click('.quiz button.opt[data-correct="1"]');
  assert.match(await page.$eval(".quiz .verdict", (e) => e.textContent), /correct/);
  const status = await page.evaluate(() => fetch("/api/claude", { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"kind":"grade"}' }).then((r) => r.status, () => "blocked"));
  assert.ok(status === 403 || status === "blocked", "lesson reached the API: " + status);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});
