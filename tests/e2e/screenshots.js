// Rebuilds the README screenshots and the plugin icon from a demo vault:  node screenshots.js
// Everything is generated; no personal data is involved.
import fs from "node:fs";
import path from "node:path";
import { ENGINE, makeVault, freePort, startServer, stopServer, launch, wavFile, readJSON } from "./harness.js";

const OUT = path.join(ENGINE, "docs", "images");
const day = (n, h = 20, m = 0) => { const d = new Date(); d.setDate(d.getDate() - n); d.setHours(h, m, 0, 0); return d; };
const iso = (d) => d.toISOString().replace(/\.\d+Z$/, "Z");
const ymd = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

const v = makeVault("Sam");
const sys = (...p) => path.join(v.vault, "_system", ...p);

// two weeks of focus blocks
const kinds = ["lessons", "lessons", "practice", "reading", "lessons", "play", "free"];
const blocks = [];
for (let n = 14; n >= 1; n--) {
  if (n % 5 === 3) continue;                       // a few days off
  const count = 1 + (n % 3);
  for (let i = 0; i < count; i++) {
    const start = day(n, 18 + i, 10), minutes = [50, 25, 60, 45][(n + i) % 4];
    blocks.push({ id: "d" + n + i, ts: iso(new Date(start.getTime() + minutes * 60000)), started: iso(start), block: kinds[(n * 3 + i) % kinds.length], minutes,
      water_served: Math.floor(minutes / 15), water_drunk: Math.floor(minutes / 15) - (i % 2) });
  }
}
fs.writeFileSync(sys("blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + "\n");

// graded history, a second topic with a readiness gate
const s = readJSON(sys("state.json"));
const t = s.topics[0];
t.queue[0].status = "done";
t.milestones[0].steps[0] = { title: t.milestones[0].steps[0].title, done: true };
t.milestones[0].steps[1].current = true;
t.regions = [{ code: "A", name: "Retrieval practice", level: 2, note: "Explained storage vs retrieval strength from memory." },
  { code: "B", name: "Spacing and review", level: 1, note: "Knows the idea; no schedule yet." }];
t.history.unshift({ date: ymd(day(2)), kind: "lesson", title: "Lesson 01: storage vs retrieval strength, from memory", detail: "3 of 3", evidence: true });
fs.mkdirSync(path.join(v.vault, "spanish", "lessons"), { recursive: true });
fs.writeFileSync(path.join(v.vault, "spanish", "MISSION.md"), "# Mission: Spanish for a move to Madrid\n");
["0001-present-tense-cold", "0002-ordering-and-paying", "0003-numbers-by-ear"].forEach((f, i) =>
  fs.writeFileSync(path.join(v.vault, "spanish", "lessons", f + ".html"), `<title>Lesson 0${i + 1} - ${["Present tense, cold", "Ordering and paying", "Numbers by ear"][i]}</title>`));
s.topics.unshift({
  id: "spanish", title: "Spanish", tagline: "Conversational Spanish for a move to Madrid, and the DELE B1.", path: "spanish", color: "#d6336c",
  phase: "Building", block: "practice",
  gate: { level: "AMBER", label: "Book the DELE B1 after two more mock orals", why: "Reading and listening are at B1 in mocks; speaking passed 1 of 3 realistic orals." },
  milestones: [{ id: "M1", title: "Survive a day in Madrid", goal: "A 10-minute unscripted conversation", estimate: "4 lessons + an oral", status: "active",
    steps: [{ title: "Present tense, cold", done: true }, { title: "Ordering, asking, paying", done: true }, { title: "Past tenses in stories", done: false, current: true },
      { title: "Phone calls and appointments", done: false }, { title: "Mock oral", done: false }] }],
  queue: [
    { id: "es-lesson-04", kind: "lesson", status: "todo", label: "Lesson 04", title: "Telling a story in the past", why: "Preterite vs imperfect, learned by telling three short stories out loud and writing one from memory.", href: "/vault/spanish/MISSION.md", effort: "25 min · 4 exercises",
      submit: { type: "answers", fields: ["Story 1", "Story 2", "Which tense, and why?"] } },
    { id: "es-recall-02", kind: "checkpoint", status: "locked", label: "Recall check", title: "Ordering and paying, cold", unlock: "Opens on Friday. Ask Claude then." }
  ],
  regions: [{ code: "A", name: "Speaking", level: 2, note: "Fluent on rehearsed topics; stalls on the past tense." },
    { code: "B", name: "Listening", level: 3, note: "Follows slow podcasts without a transcript." }, { code: "C", name: "Writing", level: 2, note: "Short emails, a few agreement slips." }],
  history: [{ date: ymd(day(1)), kind: "probe", title: "Ordered dinner and paid, no notes", detail: "mock role-play, 2 slips", evidence: true },
    { date: ymd(day(4)), kind: "lesson", title: "Present tense, 40 verbs cold", detail: "38 of 40", evidence: true },
    { date: ymd(day(9)), kind: "lesson", title: "Numbers and prices, by ear", detail: "", evidence: true }]
});
s.coach = { date: ymd(day(1)), headline: "Dinner ordered and paid, no notes. Two slips, both fixable.",
  body: "You used the right tense every time but once. Next up is telling stories in the past, which is where your speaking stalls.",
  voices: [{ voice: "critic", text: "\"Yo pagó.\" You paid, he paid, nobody knows who paid. Watch the endings." },
    { voice: "logic", text: "Preterite for what happened, imperfect for how it was. That's most of lesson 04." },
    { voice: "nostalgia", text: "Two weeks ago you counted to twenty with pauses. Tonight you argued about a bill." }] };
s.updated = new Date().toISOString();
fs.writeFileSync(sys("state.json"), JSON.stringify(s, null, 1));

const port = await freePort();
const server = await startServer(v, port);
const wav = wavFile(v.dir, 4);
const up = await fetch(server.url + "api/music", { method: "POST", headers: { "Content-Type": "audio/wav", "X-Filename": "Night-Drive.wav" }, body: fs.readFileSync(wav) });
if (!up.ok) throw new Error("music upload failed");
const cfg = (await up.json()).config;
cfg.music.title = "Night Drive"; cfg.music.subtitle = "your own track";
await fetch(server.url + "api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config: cfg }) });

const browser = await launch();
async function shot(name, { width = 1440, height = 1000, view = "bar", block = false, room = "front", fn, full = false } = {}) {
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 2 });
  await page.evaluateOnNewDocument((o) => {
    localStorage.clear();
    localStorage.setItem("edu.onboarded.v1", "1");
    localStorage.setItem("edu.view.v1", o.view);
    localStorage.setItem("edu.bar.room.v1", o.room);
    localStorage.setItem("edu.proofs.seen.v1", "[]");
    localStorage.setItem("edu.music.v1", JSON.stringify({ file: "Night-Drive.wav", t: 1, vol: 0.6, on: false }));
    if (o.block) { const now = Date.now(); localStorage.setItem("edu.block.v1", JSON.stringify({ block: "practice", minutes: 50, start: now - 17 * 60000, end: now + 33 * 60000, water: 15, served: 1, drunk: 0, task: "es-lesson-04" })); }
  }, { view, room, block });
  await page.goto(server.url, { waitUntil: "networkidle0" });
  await page.waitForSelector("#app > :not(#loading)");
  await page.evaluate(() => { const o = document.getElementById("blk-done"); if (o) o.hidden = true; document.body.style.overflow = ""; });
  await new Promise((r) => setTimeout(r, 4500));   // let the dialogue finish animating in
  if (fn) await fn(page);
  await page.screenshot({ path: path.join(OUT, name), fullPage: full });
  await page.close();
  console.log("wrote docs/images/" + name);
}

fs.mkdirSync(OUT, { recursive: true });
await shot("bar.png", { block: true });
await shot("backroom.png", { room: "back", full: true });
await shot("classic.png", { view: "classic", full: true });
await shot("settings.png", { view: "classic", fn: async (p) => { await p.click("#btn-settings"); await p.waitForSelector("#set-name"); await new Promise((r) => setTimeout(r, 400)); } });
await shot("phone.png", { width: 390, height: 844, block: true });

// plugin icon: the favicon mark at 1024 px
const icon = await browser.newPage();
await icon.setViewport({ width: 512, height: 512, deviceScaleFactor: 2 });
const svg = fs.readFileSync(path.join(ENGINE, "app", "dashboard", "index.html"), "utf8").match(/<link rel="icon" href="data:image\/svg\+xml,([^"]+)"/)[1];
await icon.setContent(`<body style="margin:0;background:transparent"><img src="data:image/svg+xml,${svg}" width="512" height="512"></body>`);
await icon.screenshot({ path: path.join(ENGINE, "plugin", ".claude-plugin", "icon.png"), omitBackground: true });
console.log("wrote plugin/.claude-plugin/icon.png");

await browser.close();
await stopServer(server);
fs.rmSync(v.dir, { recursive: true, force: true });
