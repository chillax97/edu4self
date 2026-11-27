import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, PYTHON, makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, readJSON, readLines, sleep } from "./harness.js";

const CLI = path.join(ENGINE, "edu4self");
const TOPIC = "how-learning-works";
const TASK_LESSON = "hlw-lesson-01";
const TASK_PROBE = "hlw-probe-01";

let browser;

before(async () => {
  browser = await launch();
});

after(async () => {
  await closeBrowser(browser);
});

function localDay(daysAgo) {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  d.setHours(12, 0, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  const ymd = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const offMin = -d.getTimezoneOffset();
  const sign = offMin >= 0 ? "+" : "-";
  const abs = Math.abs(offMin);
  const tz = `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
  return { ymd, iso: `${ymd}T12:00:00${tz}` };
}

function migrateVault(v) {
  execFileSync(PYTHON, [CLI, "migrate", "--vault", v.vault], { env: v.env, stdio: "pipe" });
}

function writeJsonl(file, rows) {
  fs.writeFileSync(file, rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : ""));
}

function appendJsonl(file, rows) {
  fs.appendFileSync(file, rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : ""));
}

async function withServer(v, fn) {
  const port = await freePort();
  const server = await startServer(v, port);
  try {
    return await fn(server);
  } finally {
    await stopServer(server);
    fs.rmSync(v.dir, { recursive: true, force: true });
  }
}

async function openView(url, mode) {
  if (mode === "classic") return openPage(browser, url, { view: "classic" });
  const page = await openPage(browser, url, { view: "bar" });
  if (mode === "back") {
    await page.click('[data-room="back"]');
    await page.waitForSelector(".bx-back");
  }
  return page;
}

async function triggerPoll(page, touchFile) {
  const resp = page.waitForResponse((r) => r.url().endsWith("/api/state"));
  if (touchFile && fs.existsSync(touchFile)) {
    const later = new Date(Date.now() + 5000);
    fs.utimesSync(touchFile, later, later);
  }
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await resp;
  await sleep(100);
}

async function findVisibleButtons(page, rootSel, pattern) {
  return page.evaluate((sel, src, flags) => {
    const re = new RegExp(src, flags);
    const root = sel ? document.querySelector(sel) : document;
    if (!root) return [];
    const btns = [...root.querySelectorAll('button, [role="button"]')];
    return btns
      .filter((b) => {
        if (b.hidden || b.closest("[hidden]")) return false;
        const r = b.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && re.test(b.innerText.trim());
      })
      .map((b) => ({
        text: b.innerText.trim(),
        expanded: b.getAttribute("aria-expanded"),
      }));
  }, rootSel, pattern.source, pattern.flags);
}

async function clickVisibleButton(page, rootSel, pattern) {
  const ok = await page.evaluate((sel, src, flags) => {
    const re = new RegExp(src, flags);
    const root = sel ? document.querySelector(sel) : document;
    if (!root) return false;
    const btns = [...root.querySelectorAll('button, [role="button"]')];
    const target = btns.find((b) => {
      if (b.hidden || b.closest("[hidden]")) return false;
      const r = b.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && re.test(b.innerText.trim());
    });
    if (!target) return false;
    target.scrollIntoView({ block: "center" });
    target.click();
    return true;
  }, rootSel, pattern.source, pattern.flags);
  assert.ok(ok, `missing clickable button matching ${pattern} in ${rootSel || "document"}`);
}

function makeMetGrade({ id = "g-1000000001", attempt = "ans1", daysAgo = 1, task = TASK_LESSON, skill = "storage-vs-retrieval-strength", passed = true, title = "Solid recall" } = {}) {
  const { iso } = localDay(daysAgo);
  return {
    type: "grade",
    id,
    ts: iso,
    request: `${attempt}.json`,
    request_sha: "a".repeat(40),
    attempt,
    answered: iso,
    topic: TOPIC,
    task,
    kind: "answers",
    honor: true,
    grader: { agent: "claude-code", model: "test-model", session: "sess-1" },
    title,
    detail: "Clear explanation.",
    questions: [
      { q: `${task}#1`, skill, points: { "1a": passed, "1b": passed }, errors: passed ? [] : ["missed key point"], outcome: passed ? "met" : "missed" },
    ],
    passed,
  };
}

function makeInboxAttempt({ id = "ans1", daysAgo = 1, task = TASK_LESSON } = {}) {
  const { iso } = localDay(daysAgo);
  return {
    id,
    ts: iso,
    topic: TOPIC,
    task,
    kind: "answers",
    title: "Lesson 01",
    fields: { "1. Q": "answer" },
    note: "",
    honor: true,
    confidence: "solid",
  };
}

function makeNeedsFixture({ onlyNotReady = true } = {}) {
  const v = makeVault("Tester");
  const stPath = path.join(v.vault, "_system", "state.json");
  const st = readJSON(stPath);
  if (onlyNotReady) {
    st.topics[0].queue.forEach((t) => {
      if (t.id !== TASK_LESSON) t.status = "done";
    });
  }
  fs.writeFileSync(stPath, JSON.stringify(st, null, 1));
  migrateVault(v);
  const keyPath = path.join(v.vault, "_system", "keys", TOPIC, `${TASK_LESSON}.md`);
  fs.writeFileSync(
    keyPath,
    [
      `# Answer key: ${TASK_LESSON}`,
      "",
      "## 1. Why rereading feels better",
      "",
      "Skill: rereading-familiarity",
      "",
      "Required:",
      "- 1a. Familiarity is not storage strength.",
      "",
    ].join("\n")
  );
  return v;
}

for (const mode of ["classic", "back"]) {
  test(`skills card (${mode}): clicking a region shows percent and dates, survives poll, clicking again hides it`, async () => {
    const v = makeVault("Tester");
    migrateVault(v);
    writeJsonl(path.join(v.vault, "_system", "inbox.jsonl"), [makeInboxAttempt({ id: "ans1", daysAgo: 1 })]);
    appendJsonl(path.join(v.vault, "_system", "grades.jsonl"), [makeMetGrade({ id: "g-1000000001", attempt: "ans1", daysAgo: 1 })]);

    const lastMet = localDay(1).ymd;
    const dueDate = localDay(-2).ymd;
    const expectedSentence = new RegExp(`About \\d+% sure\\.\\s+Last right 1 day ago \\(${lastMet}\\), asked again in 2 days \\(${dueDate}\\)\\.`);

    await withServer(v, async (server) => {
      const page = await openView(server.url, mode);
      const rootSel = mode === "back" ? ".bx-back" : "#app";

      const beforeBtns = await findVisibleButtons(page, rootSel, /Retrieval practice/);
      assert.ok(beforeBtns.length >= 1, "region row button exists");
      assert.equal(beforeBtns[0].expanded, "false");
      const beforeText = await page.$eval(rootSel, (e) => e.innerText);
      assert.doesNotMatch(beforeText, expectedSentence);

      await clickVisibleButton(page, rootSel, /Retrieval practice/);
      await page.waitForFunction(
        (sel, src) => new RegExp(src).test(document.querySelector(sel)?.innerText || ""),
        {},
        rootSel,
        expectedSentence.source
      );
      const openBtns = await findVisibleButtons(page, rootSel, /Retrieval practice/);
      assert.equal(openBtns[0].expanded, "true");
      const openText = await page.$eval(rootSel, (e) => e.innerText);
      assert.match(openText, /Storage and retrieval strength/);
      assert.match(openText, expectedSentence);

      await triggerPoll(page, path.join(v.vault, "_system", "state.json"));
      const afterPollBtns = await findVisibleButtons(page, rootSel, /Retrieval practice/);
      assert.equal(afterPollBtns[0].expanded, "true", "open region survives poll redraw");
      assert.match(await page.$eval(rootSel, (e) => e.innerText), expectedSentence);

      await clickVisibleButton(page, rootSel, /Retrieval practice/);
      await page.waitForFunction(
        (sel, src) => !new RegExp(src).test(document.querySelector(sel)?.innerText || ""),
        {},
        rootSel,
        expectedSentence.source
      );
      const closedBtns = await findVisibleButtons(page, rootSel, /Retrieval practice/);
      assert.equal(closedBtns[0].expanded, "false");
      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  });

  test(`skills card (${mode}): legacy region is greyed with re-checking label and unlinked topic shows link line`, async () => {
    const v = makeVault("Tester");
    const stPath = path.join(v.vault, "_system", "state.json");
    const st = readJSON(stPath);
    st.topics[0].regions = [
      { code: "A", name: "Retrieval practice", level: 1, note: "Old estimate" },
      { code: "B", name: "Spacing and review", level: 2, note: "Old estimate" },
    ];
    st.topics.push({
      id: "spanish",
      title: "Spanish",
      tagline: "Everyday conversation.",
      path: "spanish",
      color: "#d97706",
      phase: "Phase 1",
      block: "lessons",
      milestones: [],
      queue: [],
      regions: [{ code: "S", name: "Speaking", level: 1, note: "Old speaking level" }],
      history: [],
    });
    fs.mkdirSync(path.join(v.vault, "spanish"), { recursive: true });
    fs.writeFileSync(stPath, JSON.stringify(st, null, 1));
    migrateVault(v);

    writeJsonl(path.join(v.vault, "_system", "inbox.jsonl"), [makeInboxAttempt({ id: "ans1", daysAgo: 1 })]);
    appendJsonl(path.join(v.vault, "_system", "grades.jsonl"), [makeMetGrade({ id: "g-1000000002", attempt: "ans1", daysAgo: 1 })]);

    await withServer(v, async (server) => {
      const page = await openView(server.url, mode);
      const rootSel = mode === "back" ? ".bx-back" : "#app";
      const text = await page.$eval(rootSel, (e) => e.innerText);

      assert.match(text, /Spacing and review[\s\S]*earlier estimate, re-checking/i);
      assert.match(text, /Your tutor links this topic to skills next session\./);

      const legacyCount = await page.$$eval(`${rootSel} .is-legacy`, (els) => els.length);
      assert.ok(legacyCount >= 2, `expected legacy greyed elements for Region B and unlinked topic, got ${legacyCount}`);
      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  });
}

for (const mode of ["classic", "front"]) {
  test(`not-ready next step (${mode}): shows needs line, Skip dialog cancels cleanly, Skip posts skip and makes task ready`, async () => {
    const v = makeNeedsFixture({ onlyNotReady: true });
    const inboxPath = path.join(v.vault, "_system", "inbox.jsonl");

    await withServer(v, async (server) => {
      const page = await openView(server.url, mode);
      const jobSel = mode === "front" ? ".bx-job" : ".hero";
      const actionSel = mode === "front" ? ".bx-replies" : ".hero";

      const jobText = await page.$eval(jobSel, (e) => e.innerText);
      assert.match(jobText, /Needs Storage and retrieval strength first\./);

      const skipPattern = /Skip Storage and retrieval strength/;
      const skipBtns = await findVisibleButtons(page, actionSel, skipPattern);
      assert.equal(skipBtns.length, 1, "one Skip button for the needed skill");

      await clickVisibleButton(page, actionSel, skipPattern);
      await page.waitForFunction(() => /Your tutor treats it as known for this topic/.test(document.body.innerText));

      const dlgText = await page.evaluate(() => {
        const dlgs = [...document.querySelectorAll('.overlay:not([hidden]), dialog[open], [role="dialog"]')];
        const hit = dlgs.find((d) => /Your tutor treats it as known for this topic/.test(d.innerText));
        return hit ? hit.innerText : "";
      });
      assert.match(dlgText, /Skip Storage and retrieval strength\?/);
      assert.match(dlgText, /doesn't raise its level\./);

      await clickVisibleButton(page, null, /^Cancel$/);
      await page.waitForFunction(() => !/Your tutor treats it as known for this topic/.test(document.body.innerText));
      assert.deepEqual(fs.existsSync(inboxPath) ? readLines(inboxPath) : [], [], "Cancel posts nothing");

      await clickVisibleButton(page, actionSel, skipPattern);
      await page.waitForFunction(() => /Your tutor treats it as known for this topic/.test(document.body.innerText));
      await clickVisibleButton(page, null, /^Skip$/);
      await page.waitForFunction(
        (sel) => !/Needs Storage and retrieval strength first/.test(document.querySelector(sel)?.innerText || ""),
        {},
        jobSel
      );

      const inbox = readLines(inboxPath);
      assert.equal(inbox.length, 1);
      assert.equal(inbox[0].kind, "skip");
      assert.equal(inbox[0].topic, TOPIC);
      assert.equal(inbox[0].task, TASK_LESSON);
      assert.equal(inbox[0].skill, "storage-vs-retrieval-strength");
      assert.equal(inbox[0].note, "");

      const afterSkipBtns = await findVisibleButtons(page, actionSel, skipPattern);
      assert.equal(afterSkipBtns.length, 0, "Skip action is gone once ready");
      assert.match(await page.$eval(jobSel, (e) => e.innerText), /Retrieval beats rereading/);
      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  });

  test(`next step selection (${mode}): skips a not-ready first todo task in favour of a later ready todo task`, async () => {
    const v = makeNeedsFixture({ onlyNotReady: false });

    await withServer(v, async (server) => {
      const page = await openView(server.url, mode);
      const jobSel = mode === "front" ? ".bx-job" : ".hero";
      const jobText = await page.$eval(jobSel, (e) => e.innerText);

      assert.match(jobText, /How you study now/);
      assert.doesNotMatch(jobText, /Needs Storage and retrieval strength first/);

      if (mode === "classic") {
        const qText = await page.$$eval(".q-item", (els) => els.map((e) => e.innerText).join("\n"));
        assert.match(qText, /Retrieval beats rereading[\s\S]*Needs Storage and retrieval strength first\./);
        const queueSkips = await findVisibleButtons(page, "#app", /Skip Storage and retrieval strength/);
        assert.equal(queueSkips.length, 0, "no Skip button on non-next queue rows");
      } else {
        await page.click("[data-replies-more]");
        await page.waitForFunction(() => /Retrieval beats rereading/.test(document.querySelector(".bx-replies").innerText));
        const repliesText = await page.$eval(".bx-replies", (e) => e.innerText);
        assert.match(repliesText, /Retrieval beats rereading[\s\S]*Needs Storage and retrieval strength first\./);
        const roomSkips = await findVisibleButtons(page, ".bx-replies", /Skip Storage and retrieval strength/);
        assert.equal(roomSkips.length, 0, "no Skip reply when next step is ready");
      }

      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  });
}

for (const mode of ["classic", "back"]) {
  test(`dispute (${mode}): appears once per grade, sends dispute without confidence check, never on legacy items`, async () => {
    const v = makeVault("Tester");
    migrateVault(v);
    writeJsonl(path.join(v.vault, "_system", "inbox.jsonl"), [makeInboxAttempt({ id: "ans1", daysAgo: 2 })]);
    appendJsonl(path.join(v.vault, "_system", "grades.jsonl"), [
      makeMetGrade({ id: "g-2222222222", attempt: "ans1", daysAgo: 2, passed: false, title: "Needs another pass" }),
    ]);

    const inboxPath = path.join(v.vault, "_system", "inbox.jsonl");

    await withServer(v, async (server) => {
      const page = await openView(server.url, mode);
      const rootSel = mode === "back" ? ".bx-back" : "#app";

      const disputeBtns = await findVisibleButtons(page, rootSel, /^Dispute$/);
      assert.equal(disputeBtns.length, 1, "one Dispute button for the single grade, none for the legacy entry");

      const legacyHasDispute = await page.evaluate((sel) => {
        const root = document.querySelector(sel);
        const items = [...root.querySelectorAll("li, tr, .ev-item, .history-item, .log-item")];
        const legacy = items.find((el) => /Vault created from the edu4self template/.test(el.innerText));
        if (!legacy) return false;
        return [...legacy.querySelectorAll("button")].some((b) => b.innerText.trim() === "Dispute");
      }, rootSel);
      assert.equal(legacyHasDispute, false, "legacy item never has a Dispute button");

      await clickVisibleButton(page, rootSel, /^Dispute$/);
      await page.waitForSelector("#submit:not([hidden])");

      const dlgText = await page.$eval("#submit", (e) => e.innerText);
      assert.match(dlgText, /Dispute this grade/);
      assert.match(dlgText, /Say what you think the grade missed\. A fresh grader looks at your answer again, without this grade\./);
      assert.equal(await page.$eval("#sub-sure", (e) => e.hidden), true, "no confidence check on dispute");
      assert.equal(await page.$eval("#sub-send", (e) => e.innerText.trim()), "Send dispute");

      await page.type("#submit textarea", "I covered both points in my answer.");
      await page.click("#sub-send");
      await page.waitForSelector("#submit", { hidden: true });

      await page.waitForFunction(
        () => /Dispute sent\. A fresh grader will look at your answer again\./.test(document.querySelector("#toast")?.innerText || ""),
        { timeout: 8000 }
      );

      await page.waitForFunction(
        (sel) => /Disputed: a fresh grader will look again/.test(document.querySelector(sel)?.innerText || ""),
        {},
        rootSel
      );

      const afterBtns = await findVisibleButtons(page, rootSel, /^Dispute$/);
      assert.equal(afterBtns.length, 0, "Dispute button removed after disputing");

      const disputes = readLines(inboxPath).filter((e) => e.kind === "dispute");
      assert.equal(disputes.length, 1);
      assert.equal(disputes[0].topic, TOPIC);
      assert.equal(disputes[0].task, TASK_LESSON);
      assert.equal(disputes[0].ref, "g-2222222222");
      assert.equal(disputes[0].note, "I covered both points in my answer.");
      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  });
}

for (const mode of ["classic", "front"]) {
  test(`rejected grade request (${mode}): shows reason in top status bar and clears when removed`, async () => {
    const v = makeVault("Tester");
    migrateVault(v);
    const gradingDir = path.join(v.vault, "_system", "grading");
    fs.mkdirSync(gradingDir, { recursive: true });
    const req1 = path.join(gradingDir, "bad-01.json");
    const req2 = path.join(gradingDir, "bad-02.json");
    const badPayload = (attempt) => JSON.stringify({
      attempt,
      grader: { agent: "claude-code", model: "test-model", session: "sess-1" },
      title: "Bad grade",
      detail: "Unknown attempt",
      questions: [],
    });
    fs.writeFileSync(req1, badPayload("missing-attempt-01"));

    await withServer(v, async (server) => {
      const page = await openView(server.url, mode);
      const alertSel = '.topbar [role="alert"]';
      await page.waitForSelector(alertSel, { timeout: 5000 });

      const first = await page.$eval(alertSel, (e) => ({ text: e.innerText.trim(), title: e.getAttribute("title") || "" }));
      assert.match(first.text, /A grade wasn't recorded:/);
      assert.match(first.title, /bad-01\.json/);

      fs.writeFileSync(req2, badPayload("missing-attempt-02"));
      await triggerPoll(page, null);
      await page.waitForFunction(
        (sel) => /\(\+1 more\)/.test(document.querySelector(sel)?.innerText || ""),
        {},
        alertSel
      );
      const both = await page.$eval(alertSel, (e) => ({ text: e.innerText.trim(), title: e.getAttribute("title") || "" }));
      assert.match(both.title, /bad-01\.json/);
      assert.match(both.title, /bad-02\.json/);

      fs.rmSync(req1);
      fs.rmSync(req2);
      await triggerPoll(page, null);
      await page.waitForFunction((sel) => !document.querySelector(sel), {}, alertSel);
      assert.deepEqual(page.errors, []);
      await closePage(page);
    });
  });
}

test("schema-1 vault shows none of the Step 5 elements in classic or room views", async () => {
  const v = makeVault("Tester");
  const stPath = path.join(v.vault, "_system", "state.json");
  const st = readJSON(stPath);
  st.topics[0].regions[0].level = 2;
  st.topics[0].history.unshift({
    date: localDay(1).ymd,
    kind: "lesson",
    title: "Lesson 01 graded",
    detail: "Passed.",
    evidence: true,
  });
  fs.writeFileSync(stPath, JSON.stringify(st, null, 1));

  await withServer(v, async (server) => {
    for (const mode of ["classic", "front", "back"]) {
      const page = await openView(server.url, mode);
      const rootSel = mode === "back" ? ".bx-back" : "#app";
      const text = await page.$eval(rootSel, (e) => e.innerText);

      const regionBtns = await findVisibleButtons(page, rootSel, /Retrieval practice|Spacing and review/);
      assert.equal(regionBtns.filter((b) => b.expanded !== null).length, 0, `${mode}: no region expand buttons on schema 1`);
      assert.equal((await findVisibleButtons(page, rootSel, /^Dispute$/)).length, 0, `${mode}: no Dispute button on schema 1`);
      assert.equal((await findVisibleButtons(page, rootSel, /^Skip /)).length, 0, `${mode}: no Skip button on schema 1`);
      assert.doesNotMatch(text, /Needs .+ first\./);
      assert.doesNotMatch(text, /earlier estimate, re-checking/i);
      assert.equal(await page.$$eval(`${rootSel} .is-legacy`, (els) => els.length), 0, `${mode}: no .is-legacy on schema 1`);
      assert.deepEqual(page.errors, []);
      await closePage(page);
    }
  });
});
