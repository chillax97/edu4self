import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, closeBrowser, openPage, closePage, readJSON } from "./harness.js";
import { seedLongDay } from "./longday.js";

const FAKE_CLAUDE = path.join(ENGINE, "tests", "fake_claude.py");
let browser;

before(async () => { browser = await launch(); });
after(async () => { await closeBrowser(browser); });

async function serve(opts = {}) {
  const v = makeVault(opts.name || "Tester");
  if (opts.claude) {
    v.env.EDU4SELF_CLAUDE = FAKE_CLAUDE;
    v.env.FAKE_CLAUDE_LOG = path.join(v.dir, "fake-claude.log");
  }
  if (opts.seed) opts.seed(v.vault);
  const server = await startServer(v, await freePort());
  return { v, server, url: server.url };
}

async function withServe(opts, fn) {
  const s = await serve(opts);
  try { return await fn(s); }
  finally { await stopServer(s.server); fs.rmSync(s.v.dir, { recursive: true, force: true }); }
}

async function withPage(s, opts, fn) {
  const ctx = await browser.createBrowserContext();
  const page = await openPage(ctx, s.url, opts);
  try { return await fn(page); }
  finally { await closePage(page); await ctx.close(); }
}

async function withFirstVisit(s, { width = 1440, height = 900 } = {}, fn) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") page.errors.push(m.text()); });
  await page.setViewport({ width, height });
  await page.goto(s.url, { waitUntil: "networkidle0" });
  await page.waitForSelector("#onboarding:not([hidden])");
  try { return await fn(page); }
  finally { await closePage(page); await ctx.close(); }
}

function editState(s, fn) {
  const p = path.join(s.v.vault, "_system", "state.json");
  const st = readJSON(p);
  fn(st);
  fs.writeFileSync(p, JSON.stringify(st, null, 1));
}

function clearHistory(vault) {
  const p = path.join(vault, "_system", "state.json");
  const st = readJSON(p);
  st.topics.forEach((t) => { t.history = []; });
  fs.writeFileSync(p, JSON.stringify(st, null, 1));
}

const visible = (page, sel) => page.$$eval(sel, (els) => els.some((e) => {
  const s = getComputedStyle(e), r = e.getBoundingClientRect();
  return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity) !== 0 && r.width > 0 && r.height > 0;
})).catch(() => false);

async function railOverflow(page) {
  return page.$$eval(".bq-rail *", (els) => {
    const bad = [];
    for (const e of els) {
      const s = getComputedStyle(e), r = e.getBoundingClientRect();
      if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) continue;
      if (r.width <= 0 || r.height <= 0) continue;
      if (r.bottom > 900.5) bad.push({ tag: e.tagName, cls: (e.className && e.className.baseVal) || e.className || "", bottom: Math.round(r.bottom) });
    }
    return bad;
  });
}

test("A1.1 the focus panel keeps its pickers behind a Change control", async () => {
  await withServe({}, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector(".bq-rail #block", { timeout: 8000 }).catch(() => {});
    assert.ok(await page.$(".bq-rail #block"), "the focus panel is in the right rail");
    const change = await page.$$eval(".bq-rail button, .bq-rail a, .bq-rail [role='button']",
      (els) => { const e = els.find((b) => !b.closest(".bx-music") && /^change\b/i.test((b.textContent || "").trim())); return e ? e.textContent.trim() : null; });
    assert.ok(change, "the focus panel shows a Change control");
    assert.equal(await visible(page, ".bq-rail [data-blk]"), false, "kind pickers are hidden before Change");
    assert.equal(await visible(page, ".bq-rail [data-min]"), false, "length pickers are hidden before Change");
    assert.equal(await visible(page, ".bq-rail [data-water]"), false, "water pickers are hidden before Change");
    await page.evaluate(() => {
      const els = [...document.querySelectorAll(".bq-rail button, .bq-rail a, .bq-rail [role='button']")];
      const e = els.find((b) => !b.closest(".bx-music") && /^change\b/i.test((b.textContent || "").trim()));
      if (e) e.click();
    });
    await page.waitForFunction(() => {
      const e = document.querySelector(".bq-rail [data-blk]");
      if (!e) return false;
      const s = getComputedStyle(e), r = e.getBoundingClientRect();
      return s.display !== "none" && s.visibility !== "hidden" && r.width > 0 && r.height > 0;
    }, { timeout: 4000 }).catch(() => {});
    assert.ok(await visible(page, ".bq-rail [data-blk]"), "kind pickers are visible after Change");
    assert.ok(await visible(page, ".bq-rail [data-min]"), "length pickers are visible after Change");
    assert.ok(await visible(page, ".bq-rail [data-water]"), "water pickers are visible after Change");
  }));
});

test("A1.2 only the Open lesson action wears the accent fill; Start does not", async () => {
  await withServe({}, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector(".bq-rail #block", { timeout: 8000 }).catch(() => {});
    const report = await page.evaluate(() => {
      const norm = (c) => {
        const d = document.createElement("i");
        d.style.cssText = "position:absolute;left:-9999px;color:" + c;
        document.body.appendChild(d);
        const v = getComputedStyle(d).color;
        d.remove();
        return v;
      };
      const room = document.querySelector(".room");
      let accent = "";
      for (const name of ["--accent", "--bar-amber", "--primary"]) {
        accent = room ? getComputedStyle(room).getPropertyValue(name).trim() : "";
        if (accent) break;
      }
      if (!accent) accent = getComputedStyle(document.documentElement).getPropertyValue("--coral").trim();
      accent = norm(accent);
      const isVis = (e) => {
        const s = getComputedStyle(e), r = e.getBoundingClientRect();
        return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity) !== 0 && r.width > 0 && r.height > 0;
      };
      const bg = (e) => norm(getComputedStyle(e).backgroundColor);
      const buttons = [...new Set([...document.querySelectorAll("button, a.btn, .bx-replies a")])].filter(isVis);
      const main = buttons.find((e) => /Open lesson/.test(e.textContent || ""));
      const filled = buttons.filter((e) => bg(e) === accent);
      const start = document.querySelector(".bq-rail [data-blk-start]");
      return {
        accent,
        hasMain: !!main,
        mainText: main ? (main.textContent || "").trim() : null,
        mainFilled: !!main && bg(main) === accent,
        filled: filled.map((e) => (e.textContent || "").trim()),
        startBg: start ? bg(start) : null,
        hasStart: !!start,
      };
    });
    assert.ok(report.hasMain, "the job's main action is Open lesson");
    assert.ok(report.mainFilled, "Open lesson is filled with the accent (" + report.accent + ")");
    assert.deepEqual(report.filled, [report.mainText], "only the main action wears the accent: " + JSON.stringify(report.filled));
    assert.ok(report.hasStart, "the focus Start button exists");
    assert.notEqual(report.startBg, report.accent, "Start is transparent or a different fill: " + report.startBg);
  }));
});

test("A1.3 the right rail stays above the fold at 1440x900, first run and a long day", async () => {
  await withServe({ name: "Tester" }, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector(".bq-rail #block", { timeout: 8000 }).catch(() => {});
    assert.deepEqual(await railOverflow(page), [], "first-run rail fits in 900px");
  }));
  await withServe({ name: "Kim", seed: (v) => seedLongDay(v, { theme: "bar" }) }, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector(".bq-rail #block", { timeout: 8000 }).catch(() => {});
    assert.deepEqual(await railOverflow(page), [], "long-day rail fits in 900px");
  }));
});

test("A3.1 no history means no Updated by Claude in the top bar", async () => {
  await withServe({ seed: clearHistory }, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector("#app > :not(#loading)", { timeout: 8000 });
    const text = await page.$eval(".topbar", (e) => e.innerText);
    assert.doesNotMatch(text, /Updated by Claude/);
  }));
});

test("A3.2 a history entry brings the Updated by Claude pill", async () => {
  await withServe({ seed: (v) => {
    clearHistory(v);
    const p = path.join(v, "_system", "state.json");
    const st = readJSON(p);
    st.topics[0].history.push({ date: "2026-01-02", kind: "lesson", title: "Lesson 01 graded", detail: "d", evidence: true });
    fs.writeFileSync(p, JSON.stringify(st, null, 1));
  } }, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector("#status", { timeout: 8000 });
    await page.waitForFunction(() => /Updated by Claude/.test(document.querySelector(".topbar").innerText), { timeout: 8000 }).catch(() => {});
    assert.match(await page.$eval(".topbar", (e) => e.innerText), /Updated by Claude/);
  }));
});

test("A3.3 with no blocks the finish line promises a date from the first block", async () => {
  await withServe({}, (s) => withPage(s, { view: "classic", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector(".finish .finish-eta", { timeout: 8000 }).catch(() => {});
    assert.ok(await page.$(".finish .finish-eta"), "the finish line is on the page");
    const text = await page.$eval(".finish .finish-eta", (e) => e.innerText);
    assert.match(text, /Your first focus block sets the pace and gives you a date\./);
    assert.doesNotMatch(text, /No focus blocks in the last 4 weeks/);
  }));
});

test("A3.4 an empty first answer is I don't remember and does not look primary", async () => {
  await withServe({}, (s) => withFirstVisit(s, {}, async (page) => {
    await page.click("#ob-next");
    await page.waitForSelector('.ob-slide[data-step="1"]:not([hidden])');
    assert.equal(await page.$eval("#ob-next", (e) => e.textContent.trim()), "I don't remember");
    await page.waitForFunction(() => getComputedStyle(document.querySelector("#ob-next")).backgroundColor !== getComputedStyle(document.querySelector("#ft-own-go")).backgroundColor, { timeout: 2000 }).catch(() => {});
    const colors = await page.evaluate(() => {
      const bg = (sel) => getComputedStyle(document.querySelector(sel)).backgroundColor;
      return { next: bg("#ob-next"), primary: bg("#ft-own-go") };
    });
    assert.notEqual(colors.next, colors.primary, "the empty-answer button is not the primary fill: " + JSON.stringify(colors));
    await page.type("#ft-answer", "Pulling it out of my head makes it stick.");
    assert.equal(await page.$eval("#ob-next", (e) => e.textContent.trim()), "Check my answer");
  }));
});

test("A3.5 the welcome card calls the quick check a warm-up, not proof", async () => {
  await withServe({ claude: true }, (s) => withFirstVisit(s, {}, async (page) => {
    await page.click("#ob-next");
    await page.waitForSelector('.ob-slide[data-step="1"]:not([hidden])');
    await page.type("#ft-answer", "Recalling it builds the memory; rereading only feels familiar.");
    await page.click('input[name="ft-sure"][value="shaky"]');
    await page.click("#ob-next");
    await page.waitForSelector('.ob-slide[data-step="2"]:not([hidden])');
    await page.waitForSelector("#ft-grade-go", { timeout: 12000 });
    const text = await page.$eval('.ob-slide[data-step="2"]', (e) => e.innerText);
    assert.match(text, /It counts as a warm-up, not proof yet/);
    assert.doesNotMatch(text, /Only Claude can keep it as proof/);
  }));
});

test("A3.7 a house record of zero is not shown", async () => {
  await withServe({}, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector(".room .bq-run", { timeout: 8000 }).catch(() => {});
    assert.ok(await page.$(".room"), "the bar room is on the page");
    const text = await page.$eval(".room", (e) => e.innerText);
    assert.doesNotMatch(text, /house record\s*0(?!\d)/i);
  }));
});

test("A4.1 a Proved card closes the Claude drawer", async () => {
  await withServe({ claude: true }, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector("#btn-claude:not([hidden])", { timeout: 12000 });
    await page.click("#btn-claude");
    await page.waitForSelector("#claude:not([hidden])");
    await page.waitForFunction(() => localStorage.getItem("edu.proofs.seen.v1") !== null, { timeout: 10000 });
    editState(s, (st) => { st.topics[0].history.push({ date: "2026-02-02", kind: "lesson", title: "Passed.", detail: "x", evidence: true }); });
    await page.waitForSelector("#blk-done:not([hidden])", { timeout: 15000 });
    assert.match(await page.$eval("#blk-done-title", (e) => e.textContent), /Proved\./);
    assert.equal(await page.$eval("#claude", (e) => e.hidden), true, "the Claude drawer is closed");
  }));
});

test("A4.2 a title that already ends in a full stop gets no second one", async () => {
  await withServe({}, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForFunction(() => localStorage.getItem("edu.proofs.seen.v1") !== null, { timeout: 10000 });
    editState(s, (st) => { st.topics[0].history.push({ date: "2026-02-02", kind: "lesson", title: "Passed.", detail: "x", evidence: true }); });
    await page.waitForSelector("#blk-done:not([hidden])", { timeout: 15000 });
    const body = await page.$eval("#blk-done-body", (e) => e.textContent);
    assert.match(body, /Passed\. x/);
    assert.doesNotMatch(body, /Passed\.\./);
  }));
});

test("A4.3 tool lines and the check fold into a closed Details block", async () => {
  await withServe({ claude: true }, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector("#btn-claude:not([hidden])", { timeout: 12000 });
    await page.evaluate(async () => {
      const r = await fetch("/api/inbox", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: "how-learning-works", task: "hlw-lesson-01", kind: "answers", fields: { "1": "x" }, confidence: "solid" }),
      });
      return r.status;
    });
    await page.waitForSelector("#btn-grade:not([hidden])", { timeout: 12000 });
    await page.waitForFunction(() => { const b = document.querySelector("#btn-grade"); return b && !b.disabled; }, { timeout: 12000 });
    await page.click("#btn-grade");
    await page.waitForSelector("#claude:not([hidden])");
    await page.waitForFunction(() => /Check OK/.test(document.querySelector("#cl-log")?.textContent || ""), { timeout: 25000 });
    const info = await page.evaluate(() => {
      const log = document.querySelector("#cl-log");
      const details = [...log.querySelectorAll("details")].find((d) => (d.querySelector("summary")?.textContent || "").trim() === "Details");
      const outside = log.cloneNode(true);
      outside.querySelectorAll("details").forEach((d) => d.remove());
      return { hasDetails: !!details, open: details ? details.open : null, inside: details ? details.textContent : "", outside: outside.textContent };
    });
    assert.ok(info.hasDetails, "there is a Details block");
    assert.equal(info.open, false, "the Details block starts closed");
    assert.match(info.inside, /Read|Edit/, "the tool lines are inside Details");
    assert.match(info.inside, /Check OK/, "the check is inside Details");
    assert.match(info.outside, /Graded \d+ submission/, "Claude's reply stays visible outside");
  }));
});

test("A4.4 the learner's own bubble is readable in both looks", async () => {
  await withServe({ claude: true }, async (s) => {
    for (const view of ["bar", "classic"]) {
      await withPage(s, { view, width: 1440, height: 900 }, async (page) => {
        await page.waitForSelector("#btn-claude:not([hidden])", { timeout: 12000 });
        await page.click("#btn-claude");
        await page.waitForSelector("#claude:not([hidden])");
        await page.type("#cl-input", "hello");
        await page.click("#cl-send");
        await page.waitForSelector(".cl-you", { timeout: 12000 });
        const contrast = await page.$eval(".cl-you", (e) => {
          const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
          const parse = (c) => {
            ctx.clearRect(0, 0, 1, 1);
            ctx.fillStyle = c;
            ctx.fillRect(0, 0, 1, 1);
            const d = ctx.getImageData(0, 0, 1, 1).data;
            return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 };
          };
          const blend = (top, bottom) => ({
            r: top.r * top.a + bottom.r * (1 - top.a),
            g: top.g * top.a + bottom.g * (1 - top.a),
            b: top.b * top.a + bottom.b * (1 - top.a),
            a: 1,
          });
          const lum = (c) => {
            const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
            return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
          };
          const bgOf = (el) => {
            let node = el;
            let acc = parse(getComputedStyle(el).backgroundColor);
            while (acc && acc.a < 1 && node.parentElement) {
              node = node.parentElement;
              const p = parse(getComputedStyle(node).backgroundColor);
              if (!p) break;
              acc = blend(acc, p);
            }
            return acc;
          };
          const fg = parse(getComputedStyle(e).color), bg = bgOf(e);
          const hi = Math.max(lum(fg), lum(bg)), lo = Math.min(lum(fg), lum(bg));
          return (hi + 0.05) / (lo + 0.05);
        });
        assert.ok(contrast >= 4.5, view + ": learner bubble contrast " + contrast.toFixed(2));
      });
    }
  });
});

test("A4.5 the saved toast says Press Grade when you're ready", async () => {
  await withServe({ claude: true }, (s) => withPage(s, { view: "bar", width: 1440, height: 900 }, async (page) => {
    await page.waitForSelector("#btn-claude:not([hidden])", { timeout: 12000 });
    await page.waitForSelector('.bx-replies [data-submit="hlw-lesson-01"]', { timeout: 12000 });
    await page.click('.bx-replies [data-submit="hlw-lesson-01"]');
    await page.waitForSelector("#submit:not([hidden])");
    await (await page.$$("#sub-fields textarea"))[0].type("ease now vs lasting");
    await page.click('#sub-sure input[value="solid"]');
    await page.click("#sub-send");
    await page.waitForFunction(() => [...document.querySelectorAll("#toast .toast")].some((t) => /Saved to your inbox/.test(t.innerText)), { timeout: 12000 });
    const text = await page.evaluate(() => {
      const t = [...document.querySelectorAll("#toast .toast")].find((x) => /Saved to your inbox/.test(x.innerText));
      return t ? t.innerText : "";
    });
    assert.match(text, /Press ✦ Grade when you're ready\./);
  }));
});
