// Records the new-user tour video from a throwaway vault:  node tour.js
// Output: docs/video/tour.mp4 (full) and docs/images/tour.gif (short cut for the README).
// Needs ffmpeg on PATH. The terminal scenes are re-enacted on screen (typed text, not a real shell);
// everything in the browser is the real dashboard driven by a script.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, wavFile, readJSON, readLines, sleep } from "./harness.js";

const W = 1280, H = 800;
const OUT_DIR = path.join(ENGINE, "docs", "video");
const MP4 = path.join(OUT_DIR, "tour.mp4");
const GIF = path.join(ENGINE, "docs", "images", "tour.gif");

// ---------------------------------------------------------------- the overlay (captions, cursor, terminal)
// Injected into every page the tour visits, so it survives navigation.
function overlay() {
  const css = `
  #tour-cap{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(12px);opacity:0;z-index:2147483646;
    max-width:880px;padding:12px 22px;border-radius:14px;background:rgba(12,10,9,.88);color:#fff;
    font:600 20px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;text-align:center;
    box-shadow:0 10px 40px rgba(0,0,0,.45);transition:opacity .35s,transform .35s;pointer-events:none}
  #tour-cap.on{opacity:1;transform:translateX(-50%)}
  #tour-cap small{display:block;font-weight:500;font-size:14px;opacity:.7;margin-top:2px}
  #tour-cur{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;
    transition:transform .6s cubic-bezier(.3,.7,.2,1);filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))}
  .tour-ring{position:fixed;width:40px;height:40px;margin:-20px 0 0 -20px;border-radius:50%;z-index:2147483646;
    border:3px solid #f0a83a;pointer-events:none;animation:tour-ring .5s ease-out forwards}
  @keyframes tour-ring{from{transform:scale(.3);opacity:1}to{transform:scale(1.4);opacity:0}}
  #tour-term{position:fixed;inset:0;z-index:2147483645;background:#0e0c0b;display:flex;align-items:center;justify-content:center}
  #tour-term .win{width:1000px;height:600px;background:#1b1816;border-radius:12px;box-shadow:0 30px 80px rgba(0,0,0,.6);overflow:hidden;border:1px solid #2e2924}
  #tour-term .bar{height:34px;background:#26211e;display:flex;align-items:center;gap:8px;padding:0 14px;color:#a99c8c;font:13px -apple-system,sans-serif}
  #tour-term .bar i{width:12px;height:12px;border-radius:50%;display:inline-block}
  #tour-term pre{margin:0;padding:18px 22px;color:#e9e1d6;font:17px/1.55 ui-monospace,Menlo,monospace;white-space:pre-wrap}
  #tour-term .p{color:#7cc47f} #tour-term .d{color:#a99c8c} #tour-term .a{color:#f0a83a} #tour-term .c{color:#d98c6a}
  #tour-tick{position:fixed;right:0;bottom:0;width:2px;height:2px;z-index:2147483647;pointer-events:none;animation:tour-tick 1s steps(2) infinite}
  @keyframes tour-tick{from{background:rgba(0,0,0,.01)}to{background:rgba(0,0,0,.02)}}
  #tour-card{position:fixed;inset:0;z-index:2147483645;background:#0e0c0b;color:#efe6da;display:flex;flex-direction:column;
    align-items:center;justify-content:center;gap:14px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;text-align:center}
  #tour-card h1{font-size:64px;margin:0;letter-spacing:-.02em} #tour-card p{font-size:24px;margin:0;color:#a99c8c}
  #tour-card code{font:22px ui-monospace,Menlo,monospace;color:#f0a83a;background:#1e1a17;padding:8px 16px;border-radius:10px}`;
  const T = (window.__tour = {
    pos: (() => { try { return JSON.parse(sessionStorage.getItem("tour.pos") || "[640,400]"); } catch { return [640, 400]; } })(),
    el(id, tag = "div") { let e = document.getElementById(id); if (!e) { e = document.createElement(tag); e.id = id; document.body.appendChild(e); } return e; },
    caption(text, sub) {
      const c = T.el("tour-cap");
      if (!text) { c.classList.remove("on"); return; }
      c.innerHTML = text + (sub ? "<small>" + sub + "</small>" : "");
      requestAnimationFrame(() => c.classList.add("on"));
    },
    move(x, y) {
      T.pos = [x, y]; try { sessionStorage.setItem("tour.pos", JSON.stringify(T.pos)); } catch {}
      T.el("tour-cur").style.transform = `translate(${x - 4}px,${y - 2}px)`;
    },
    ring(x, y) { const r = document.createElement("div"); r.className = "tour-ring"; r.style.left = x + "px"; r.style.top = y + "px"; document.body.appendChild(r); setTimeout(() => r.remove(), 600); },
    async term(title, lines) {
      const t = T.el("tour-term");
      t.innerHTML = `<div class="win"><div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i>&nbsp; ${title}</div><pre></pre></div>`;
      const pre = t.querySelector("pre");
      const wait = (ms) => new Promise((r) => setTimeout(r, ms));
      for (const [kind, text, pause] of lines) {
        const line = document.createElement("span");
        line.className = { cmd: "", out: "", dim: "d", ok: "p", claude: "c", ask: "" }[kind] || "";
        pre.appendChild(line);
        if (kind === "cmd" || kind === "ask") {
          const pfx = document.createElement("span"); pfx.className = "p"; pfx.textContent = kind === "cmd" ? "$ " : "> ";
          line.appendChild(pfx);
          const body = document.createElement("span"); line.appendChild(body);
          for (const ch of text) { body.textContent += ch; await wait(28); }
          await wait(250);
        } else {
          line.textContent = text;
        }
        pre.appendChild(document.createTextNode("\n"));
        await wait(pause ?? (kind === "cmd" || kind === "ask" ? 350 : 140));
      }
    },
    termClose() { document.getElementById("tour-term")?.remove(); },
    card(html) { T.el("tour-card").innerHTML = html; },
    cardClose() { document.getElementById("tour-card")?.remove(); },
  });
  const boot = () => {
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
    T.el("tour-tick");
    const cur = T.el("tour-cur");
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l16 11-7 1.5L9.5 21z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    cur.style.transition = "none"; T.move(...T.pos); cur.offsetWidth; cur.style.transition = "";
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
}

// ---------------------------------------------------------------- the vault, as a new user gets it
const v = makeVault("Sam");
const sys = (...p) => path.join(v.vault, "_system", ...p);
const port = await freePort();
const server = await startServer(v, port);
const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
await page.evaluateOnNewDocument(overlay);
page.on("pageerror", (e) => console.error("page error:", String(e)));
page.on("dialog", (d) => d.accept());

const say = (text, sub) => page.evaluate((t, s) => window.__tour.caption(t, s), text, sub || "");
const hush = () => page.evaluate(() => window.__tour.caption(""));
async function point(sel) {
  await page.$eval(sel, (e) => e.scrollIntoView({ block: "center", behavior: "instant" }));
  const { x, y } = await page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.evaluate((x, y) => window.__tour.move(x, y), x, y);
  await sleep(700);
  return { x, y };
}
async function tap(sel, after = 500) {
  const { x, y } = await point(sel);
  await page.evaluate((x, y) => window.__tour.ring(x, y), x, y);
  await page.click(sel);
  await sleep(after);
}
async function typeIn(sel, text, { clear = false, delay = 45 } = {}) {
  await tap(sel, 150);
  if (clear) await page.$eval(sel, (e) => { e.value = ""; e.dispatchEvent(new Event("input", { bubbles: true })); });
  await page.type(sel, text, { delay });
  await sleep(300);
}
async function scrollBy(dy, ms = 1200) {
  await page.evaluate(async (dy, ms) => {
    const sc = document.scrollingElement, from = sc.scrollTop, t0 = performance.now();
    await new Promise((done) => { const step = (t) => { const k = Math.min(1, (t - t0) / ms); sc.scrollTop = from + dy * (0.5 - Math.cos(Math.PI * k) / 2); k < 1 ? requestAnimationFrame(step) : done(); }; requestAnimationFrame(step); });
  }, dy, ms);
}
async function scrollIn(sel, dy, ms = 1200) {
  await page.$eval(sel, async (el, dy, ms) => {
    const from = el.scrollTop, t0 = performance.now();
    await new Promise((done) => { const step = (t) => { const k = Math.min(1, (t - t0) / ms); el.scrollTop = from + dy * (0.5 - Math.cos(Math.PI * k) / 2); k < 1 ? requestAnimationFrame(step) : done(); }; requestAnimationFrame(step); });
  }, dy, ms);
}

fs.mkdirSync(OUT_DIR, { recursive: true });
await page.goto("about:blank");
await page.setContent("<!doctype html><html><head></head><body style='margin:0;background:#0e0c0b'></body></html>");
await page.evaluate(overlay);
// Our own recorder: every frame keeps its real timestamp, so held moments keep their length.
// (puppeteer's page.screencast assumes a steady frame rate and squeezes a 2-minute run into ~1 minute.)
const framesDir = path.join(v.dir, "frames"); fs.mkdirSync(framesDir);
const frames = [];
const cdp = await page.createCDPSession();
cdp.on("Page.screencastFrame", async (f) => {
  const file = path.join(framesDir, String(frames.length).padStart(6, "0") + ".jpg");
  fs.writeFileSync(file, Buffer.from(f.data, "base64"));
  frames.push({ file, ts: f.metadata.timestamp });
  await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: W, maxHeight: H, everyNthFrame: 1 });

// 1. title
await page.evaluate(() => window.__tour.card("<h1>edu4self</h1><p>A learning dashboard on your computer, with Claude as your tutor.</p>"));
await sleep(3000);
await page.evaluate(() => window.__tour.cardClose());

// 2. install
await say("Install: clone the repo and run one command.");
await page.evaluate(() => window.__tour.term("Terminal", [
  ["cmd", "git clone https://github.com/chillax97/edu4self.git && cd edu4self"],
  ["dim", "Cloning into 'edu4self'... done.", 400],
  ["cmd", "./edu4self setup"],
  ["out", "edu4self setup. Press Enter to accept the suggestion in brackets.\n"],
  ["out", "Where should your learning vault go? [~/learn]: ", 700],
  ["out", "What should the dashboard call you? [friend]: Sam", 600],
  ["out", "Made a vault at ~/learn"],
  ["ok", "The dashboard is running at http://127.0.0.1:4747/ and starts at login.", 500],
  ["cmd", "claude plugin marketplace add chillax97/edu4self"],
  ["cmd", "claude plugin install edu4self@edu4self"],
  ["ok", "✔ Installed edu4self", 1400],
]));
await hush();
await page.goto(server.url, { waitUntil: "networkidle0" });

// 3. onboarding
await page.waitForSelector("#onboarding:not([hidden])");
await say("First visit: a 30-second tour of how it works.");
await sleep(1800);
for (let i = 0; i < 3; i++) { await tap("#ob-next", 1600); }
await page.waitForSelector("#onboarding", { hidden: true });

// 4. the bar
await say("The bar: your skills talk you through tonight's work.", "One next step, always. Here it's the example lesson.");
await sleep(4200);
await point(".bx-job h2");
await sleep(1500);
await say("The jukebox starts on a soundscape, made right in your browser.", "No files, no internet. Radio or your own track are one setting away.");
await tap(".bx-music [data-mu='toggle']", 1200);
await tap(".bx-music [data-scape='rain']", 1800);
await tap(".bx-music [data-mu='toggle']", 600);

// 5. the lesson
await say("Open the lesson. It's short, and ends with exercises.");
const lessonHref = await page.$eval(".bx-job a[href*='lessons/']", (a) => a.getAttribute("href")).catch(() => "/vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html");
await page.goto(new URL(lessonHref, server.url).href, { waitUntil: "networkidle0" });
await say("Lesson 01: retrieval beats rereading.");
await sleep(1200);
await scrollBy(900, 2200);
await sleep(700);
await scrollBy(900, 2200);
await sleep(900);
await page.goto(server.url, { waitUntil: "networkidle0" });
await page.waitForSelector(".bx-replies [data-submit='hlw-lesson-01']");

// 6. submit
await say("Close it and answer from memory. Then submit.");
await tap(".bx-replies [data-submit='hlw-lesson-01']", 600);
await page.waitForSelector("#submit:not([hidden])");
const answers = [
  "Retrieval strength is how easy it is to recall right now. Storage strength is how well it's actually learned.",
  "Rereading makes it feel familiar, which feels like knowing. It barely trains recall.",
  "Ten flashcards a night for my Spanish verbs, answered before I flip them.",
];
const areas = await page.$$("#sub-fields textarea");
for (let i = 0; i < areas.length; i++) {
  await page.evaluate((i) => document.querySelectorAll("#sub-fields textarea")[i].setAttribute("data-tour", "a" + i), i);
  await typeIn(`[data-tour="a${i}"]`, answers[i], { delay: 18 });
}
await tap('#sub-sure input[value="shaky"]', 500);
await tap("#sub-send", 900);
await page.waitForSelector("#submit", { hidden: true });
await say("It lands in your inbox. Up next moves on while Claude hasn't graded it yet.");
await sleep(3200);

// 7. Claude grades (re-enacted terminal; the state change below is what Claude writes)
await say("In Claude Code: “check my inbox”.", "Re-enacted and sped up. A real run takes a minute or two.");
const graded = page.evaluate(() => window.__tour.term("~/learn — claude", [
  ["ask", "check my inbox"],
  ["claude", "⏺ 1 new submission: Lesson 01, Retrieval beats rereading", 500],
  ["claude", "⏺ Grading against the lesson's exercises", 600],
  ["out", "    1. retrieval vs storage strength      ✓"],
  ["out", "    2. why rereading feels better         ✓"],
  ["out", "    3. a plan for this week               ✓  specific and testable", 500],
  ["claude", "⏺ Updating state.json: lesson done, evidence logged, probe up next"],
  ["claude", "⏺ edu4self check: OK", 400],
  ["out", "\nGraded 3 of 3. Your dashboard has updated.", 1600],
]));
// meanwhile, write what Claude would write (same shape as a real graded run)
{
  const s = readJSON(sys("state.json"));
  const sub = readLines(sys("inbox.jsonl")).find((e) => e.task === "hlw-lesson-01");
  const t = s.topics[0];
  const lesson = t.queue.find((q) => q.id === "hlw-lesson-01");
  lesson.status = "done";
  t.milestones[0].steps[0] = { title: t.milestones[0].steps[0].title, done: true };
  t.milestones[0].steps[1].current = true;
  t.regions = [{ code: "A", name: "Retrieval practice", level: 2, note: "Explained storage vs retrieval strength from memory." }];
  t.history = [{ date: new Date().toISOString().slice(0, 10), kind: "lesson", title: "Lesson 01: storage vs retrieval strength, from memory", detail: "3 of 3", evidence: true }, ...(t.history || [])];
  s.processed_inbox = [...(s.processed_inbox || []), sub.id];
  s.coach = { date: new Date().toISOString().slice(0, 10), headline: "Three for three, from memory. That's the loop.",
    body: "Your plan for the week is specific enough to check. Next: a short probe about how you study now.",
    voices: [{ voice: "logic", text: "Storage vs retrieval, explained cold. That's the one idea everything else hangs on." },
      { voice: "volition", text: "Ten flashcards a night. Small enough to actually do. Do it." },
      { voice: "regular", text: "First lesson down. Bartender owes you a water." }] };
  s.updated = new Date().toISOString();
  fs.writeFileSync(sys("state.json"), JSON.stringify(s, null, 1));
}
await graded;
await page.reload({ waitUntil: "networkidle0" });
await page.evaluate(() => window.__tour.termClose());

// 8. updated
await say("Graded. The voices react, and the proof is on record.", "Only demonstrated knowledge counts. Reading alone never does.");
await page.waitForSelector("#blk-done:not([hidden])", { timeout: 5000 }).catch(() => {});
await sleep(3000);
if (await page.$("#blk-done:not([hidden])")) await tap("#blk-done [data-close]", 900);
await sleep(2500);
await tap(".bx-r[data-room='back']", 1200);
await say("The back room: milestones, evidence, skills, and your focus time.");
await sleep(1500);
await scrollBy(700, 2400);
await sleep(1500);
await scrollBy(-1400, 1200);
await tap("[data-room='front']", 900);

// 9. Settings
await say("Make it yours in Settings. No terminal, no code.");
await tap("#btn-settings", 900);
await page.waitForSelector("#settings:not([hidden]) #set-name");
await typeIn("#set-day", "90", { clear: true });
await say("Goals, block kinds, water reminders…");
await tap("#set-kind-add", 500);
await typeIn(".set-kind:last-of-type [data-k='label']", "Spanish", { clear: true });
await say("…the names on the bar's neon sign…");
await typeIn("#set-names", "The Night Shift | open till it clicks", { clear: true, delay: 35 });
await say("…your own jokes…");
await typeIn("#set-lines", "regular: The coffee machine has been broken since the last exam.", { delay: 22 });
await say("…and the music: a soundscape, a radio station, or your own track.");
await tap('label.set-src-opt:has(input[value="radio"])', 1800);
await tap('label.set-src-opt:has(input[value="file"])', 900);
const wav = wavFile(v.dir, 6);
const night = path.join(v.dir, "Night Drive.wav"); fs.renameSync(wav, night);
await point(".set-upload");
await (await page.$("#set-mu-file")).uploadFile(night);
await page.waitForSelector(".set-track");
await typeIn("#set-mu-title", "Night Drive", { clear: true });
await sleep(500);
await tap("#set-save", 1200);
await page.waitForSelector("#settings", { hidden: true });
await page.evaluate(() => window.scrollTo(0, 0));
await say("Saved, and live at once: new sign, your track on the jukebox.");
await sleep(1200);
await tap(".bx-music [data-mu='toggle']", 1800).catch(() => {});
await point(".bx-neon");
await sleep(2200);

// 10. classic + a focus block
await say("Prefer calm? Switch to the classic view.");
await tap("#btn-view", 1500);
await say("Start a focus block. Every 25 minutes etches a tile.", "24 tiles make a die, 8 dies a node. A water reminder every 15 minutes, if you want one.");
await tap("#block [data-min='25']", 400);
await tap("#block [data-blk-start]", 2500);
await scrollBy(600, 2000);
await sleep(1600);
await scrollBy(-600, 900);
await hush();

// 11. end card
await page.evaluate(() => window.__tour.card("<h1>edu4self</h1><p>Free and open source. Runs on your computer.</p><code>github.com/chillax97/edu4self</code>"));
await sleep(3500);

await cdp.send("Page.stopScreencast");
const endTs = Date.now() / 1000;
await browser.close();
await stopServer(server);

// ---------------------------------------------------------------- encode
const list = path.join(v.dir, "frames.txt");
fs.writeFileSync(list, frames.map((f, i) => `file '${f.file}'\nduration ${(((frames[i + 1]?.ts) ?? endTs) - f.ts).toFixed(4)}`).join("\n") + `\nfile '${frames.at(-1).file}'\n`);
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-vf", `fps=30,scale=${W}:${H}:flags=lanczos,format=yuv420p`,
  "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-movflags", "+faststart", MP4]);
// README cut: the first visit through grading, smaller and slower frame rate
const pal = path.join(v.dir, "pal.png");
const gifCut = ["-ss", "12", "-t", "46"];
execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...gifCut, "-i", MP4, "-vf", "fps=8,scale=720:-1:flags=lanczos,palettegen=max_colors=96", pal]);
execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...gifCut, "-i", MP4, "-i", pal, "-lavfi", "fps=8,scale=720:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4", GIF]);
fs.rmSync(v.dir, { recursive: true, force: true });
for (const f of [MP4, GIF]) console.log("wrote", path.relative(ENGINE, f), (fs.statSync(f).size / 1e6).toFixed(1) + " MB");
