// The bar on a real learner's day, not a demo one: a long "From memory" card, a long lesson with rules, no
// follow-up question, four kinds of block and three nights studied without a cap. The test data elsewhere is
// short, so this is where the counter has to hold: the open book, the first move above the fold, the caps'
// caption with the caps, and no sideways scroll.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { makeVault, freePort, startServer, stopServer, launch, openPage, closePage, readJSON } from "./harness.js";
import { seedLongDay } from "./longday.js";

let v, server, browser;

before(async () => { v = makeVault("Kim"); seedLongDay(v.vault, { theme: "bar" }); server = await startServer(v, await freePort()); browser = await launch(); });
after(async () => { await browser?.close(); await stopServer(server); fs.rmSync(v.dir, { recursive: true, force: true }); });

const open = async () => { const page = await openPage(browser, server.url, { view: "bar", width: 1440, height: 900, room: "front" }); await page.waitForSelector(".room .bq-book .bx-recall"); return page; };

test("a long day at 1440x900: an open book, the first move above the fold, the caps' caption with the caps, no sideways scroll", async () => {
  const page = await open();
  const m = await page.evaluate(() => {
    const box = (e) => e && e.getBoundingClientRect();
    const first = document.querySelector('.room [data-slot="replies"] li:not(.is-quiet) .bx-r');
    const job = document.querySelector(".room .bq-pages .bx-job:not(.bx-recall)");
    const pips = [...document.querySelectorAll('.room [data-slot="week"] .bx-pips.m i')].map(box);
    const caption = box(document.querySelector('.room [data-slot="week"] .bx-mono'));
    const pages = document.querySelector(".room .bq-pages");
    return {
      first: first && { text: first.textContent.trim(), top: box(first).top, bottom: box(first).bottom },
      jobLeft: box(job).left, pagesLeft: box(pages).left, pagesW: box(pages).width,
      firstLeft: first && box(first).left,
      capsBottom: Math.max(...pips.map((r) => r.bottom)), captionTop: caption.top, captionText: document.querySelector('.room [data-slot="week"] .bx-mono').innerText,
      scrollW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth, h: innerHeight,
    };
  });
  assert.ok(m.first, "there is a first move under the lesson");
  assert.match(m.first.text, /Open lesson/);
  assert.ok(m.first.top >= 0 && m.first.bottom <= m.h, `the first move (${m.first.text}) is fully above the fold: ${Math.round(m.first.top)}..${Math.round(m.first.bottom)} of ${m.h}`);
  assert.ok(m.firstLeft > m.pagesLeft + m.pagesW / 2, `an open book: the moves sit on the right-hand page (x ${Math.round(m.firstLeft)}, book from ${Math.round(m.pagesLeft)}, ${Math.round(m.pagesW)} wide)`);
  const gap = m.captionTop - m.capsBottom;
  assert.ok(gap >= 0 && gap <= 40, `the caps' caption sits within 40 px of the caps (${Math.round(gap)} px)`);
  assert.ok(m.scrollW <= m.clientW, `no sideways scroll (${m.scrollW} > ${m.clientW})`);
  assert.deepEqual(page.errors, []);
  await closePage(page);
});

test("three nights studied without a cap reads plainly, not as a contradiction", async () => {
  const page = await open();
  const said = await page.$eval('.room [data-slot="week"] .bx-mono', (e) => e.innerText);
  assert.doesNotMatch(said, /no bottle caps yet\s*·\s*\d+ of/i, "nights studied are not set against 'no caps' with a dot");
  assert.match(said, /3 of 4 nights/);
  assert.match(said, /125 min/, "it says what earns a cap");
  await closePage(page);
});

test("the lesson has one main action, and the other moves are quiet links", async () => {
  const page = await open();
  const looks = await page.$$eval('.room [data-slot="replies"] li:not(.is-quiet):not(.is-rest) .bx-r, .room [data-slot="replies"] .bx-rest button', (l) =>
    l.map((e) => { const s = getComputedStyle(e); return { text: e.textContent.trim().slice(0, 20), line: s.textDecorationLine, border: s.borderTopStyle, bg: s.backgroundColor }; }));
  assert.ok(looks.length >= 3, "the lesson's moves are there: " + JSON.stringify(looks));
  const [main, ...rest] = looks;
  assert.ok(main.bg !== "rgba(0, 0, 0, 0)" && main.bg !== "transparent", `the first move is a filled button: ${JSON.stringify(main)}`);
  assert.ok(main.text.startsWith("Open lesson"), `the filled button opens the lesson: ${JSON.stringify(main)}`);
  for (const x of rest) assert.ok(/underline/.test(x.line) && x.border === "none", `${x.text} is a quiet link: ${JSON.stringify(x)}`);
  await closePage(page);
});
