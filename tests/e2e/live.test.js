// The dashboard keeps up with the vault on its own: whatever Claude or a script writes (state.json, the inbox,
// a block, a checker run, the settings) shows within 5 s without a reload, in the bar and in classic; while nothing changes, it doesn't fetch the whole state.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON, sleep, PYTHON } from "./harness.js";

let v, server, browser, ex, originalTitle;

const sys = (f) => path.join(v.vault, "_system", f);
// the checker starts with the protocol's lines, as every exercise's does
const checkerLines = () => fs.readFileSync(new URL("../../docs/PROTOCOL.md", import.meta.url), "utf8").split("```python\n")[1].split("```")[0].replace('["solution.py"]', '["sol.py"]');
const failingRun = () => {
  fs.writeFileSync(path.join(ex, "check.py"), checkerLines() + "\nimport sys\nprint('1 of 2 pass')\nsys.exit(1)\n");
  try { execFileSync(PYTHON, [path.join(ex, "check.py")], { stdio: "pipe" }); } catch {}
};
// the 5 s budget: the page should notice a change on disk without anyone touching it
const shows = (page, fn, arg) => page.waitForFunction(fn, { timeout: 5000, polling: 100 }, arg);
const within = async (page, fn, arg, msg) => {
  try { await shows(page, fn, arg); } catch { assert.fail(msg); }
};
const countState = (page) => {
  let n = 0;
  page.on("request", (r) => { if (new URL(r.url()).pathname === "/api/state") n++; });
  return { get: () => n, reset: () => { n = 0; } };
};

before(async () => {
  v = makeVault("Kim");
  ex = path.join(v.vault, "how-learning-works", "exercises", "e1");
  fs.mkdirSync(ex, { recursive: true });
  fs.writeFileSync(path.join(ex, "HINTS.md"), "# Hints\n\nOnly the one you need.\n\n## 1 · warm-up\n- Read it twice.\n\n## 2 · the loop\n- Keep a running `total`.\n- Yield after each item.\n");
  fs.writeFileSync(path.join(ex, "sol.py"), "def f():\n    return 1\n");
  fs.writeFileSync(path.join(ex, "check.py"), checkerLines() + "\nprint('1 of 2 checks pass')\n");
  const sp = path.join(v.vault, "_system", "state.json"), st = readJSON(sp);
  st.topics[0].queue[0].exercise = "how-learning-works/exercises/e1";
  originalTitle = st.topics[0].queue[0].title;
  fs.writeFileSync(sp, JSON.stringify(st));
  const cp = sys("config.json"), cfg = readJSON(cp);
  fs.writeFileSync(cp, JSON.stringify({ ...cfg, goals: { ...cfg.goals, day_minutes: 60, week_days: 4 } }));
  server = await startServer(v, await freePort());    // installs _system/edu_trace.py
  browser = await launch();
});
after(async () => {
  await browser?.close();
  await stopServer(server);
  fs.rmSync(v.dir, { recursive: true, force: true });
});

for (const view of ["bar", "classic"]) {
  test(`${view}: every change on disk shows within 5 s, with no reload`, async () => {
    // a known world: no runs, no submissions, no blocks, the usual goal and the lesson's own title
    fs.rmSync(path.join(ex, "trace"), { recursive: true, force: true });
    fs.writeFileSync(sys("inbox.jsonl"), "");
    fs.writeFileSync(sys("blocks.jsonl"), "");
    const cfg0 = readJSON(sys("config.json"));
    cfg0.goals.day_minutes = 60;
    fs.writeFileSync(sys("config.json"), JSON.stringify(cfg0));
    const st0 = readJSON(sys("state.json"));
    st0.topics[0].queue[0].title = originalTitle;
    fs.writeFileSync(sys("state.json"), JSON.stringify(st0));

    const page = await openPage(browser, server.url, { view, width: 1440, height: 900 });
    await sleep(1500);
    // any navigation would drop this; at the end it must still be here
    await page.evaluate(() => { window.__noReload = true; });

    // 1. Claude rewrites the lesson's title in state.json
    const st1 = readJSON(sys("state.json"));
    st1.topics[0].queue[0].title = "A title Claude just wrote";
    fs.writeFileSync(sys("state.json"), JSON.stringify(st1));
    await within(page, () => document.body.innerText.includes("A title Claude just wrote"), undefined,
      `${view}: the new lesson title didn't show within 5 s`);

    // 2. three failing checker runs in a row (before the answer: a task waiting for Claude shows no nudge)
    failingRun(); failingRun(); failingRun();
    await within(page, () => !!document.querySelector(".stuck"), undefined,
      `${view}: the three failing runs didn't show within 5 s`);

    // 3. a finished 35-minute focus block
    const now = new Date();
    fs.appendFileSync(sys("blocks.jsonl"), JSON.stringify({ id: "live-b-" + view, ts: now.toISOString(), started: new Date(now.getTime() - 35 * 60000).toISOString(), block: "lessons", minutes: 35 }) + "\n");
    await within(page, () => /35\s*(m|min)?\s*of 60 min/.test(document.body.innerText), undefined,
      `${view}: the new 35-minute block didn't show within 5 s`);

    // 4. the learner's answer lands in the inbox
    const st2 = readJSON(sys("state.json"));
    fs.appendFileSync(sys("inbox.jsonl"), JSON.stringify({ id: "live-" + view, ts: new Date().toISOString(), task: st2.topics[0].queue[0].id, kind: "answer", answers: {} }) + "\n");
    await within(page, () => /waiting for Claude/i.test(document.body.innerText), undefined,
      `${view}: the new inbox entry didn't show within 5 s`);

    // 5. the learner's goal changes in Settings' file
    const cfg1 = readJSON(sys("config.json"));
    cfg1.goals.day_minutes = 125;
    fs.writeFileSync(sys("config.json"), JSON.stringify(cfg1));
    await within(page, () => /of 125 min/.test(document.body.innerText), undefined,
      `${view}: the new 125-minute goal didn't show within 5 s`);

    assert.equal(await page.evaluate(() => window.__noReload), true, "no reload");
    assert.deepEqual(page.errors, []);
    await closePage(page);
  });
}

test("while nothing changes, the page doesn't fetch the whole state", { timeout: 40000 }, async () => {
  const page = await openPage(browser, server.url, { view: "classic", width: 1440, height: 900 });
  await sleep(2500);
  const state = countState(page);
  await sleep(16000);
  assert.equal(state.get(), 0, `no full state fetch in 16 s of quiet (got ${state.get()})`);
  await closePage(page);
});
