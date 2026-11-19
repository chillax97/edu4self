// A real learner's day, in neutral words of the same length: a "From memory" card with three long questions,
// a lesson with a long description, a long effort line, long rules and exercises, no follow-up question, four
// kinds of block, and three nights studied this week below a 125-minute goal (so no cap yet).
import fs from "node:fs";
import path from "node:path";

const ymd = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const monday = () => { const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return d; };

export const LONG = {
  why: "Part 1 of 2. A word list sees the words as a heap, so \"the dog saw the cat\" and \"the cat saw the dog\" look alike. " +
    "The fix is a small marker added to each word, and it explains why a saved list of earlier words only fits at its own places.",
  effort: "2 warm-up + 5 quick questions + 5 short practice problems (python3 rust-basics/exercises/0007a/check.py N) · ~40 min",
  rules: "The form's questions are closed book: no lesson page, no AI. The checker and hints are allowed for the code. " +
    "Open hints from the dashboard's Hints button so they're noted; each checker run is saved for grading.",
  recall: [
    "A saved conversation has one word changed in the middle, nothing added or removed. Which saved parts can you keep, and why?",
    "Text arrives in pieces that can cut a word in half. What do you keep between pieces, and when can you hand a word out?",
    "A plan says: 28 floors, 32 rooms per floor, 4 desks per room, 128 drawers, 2 keys each. Write how many keys one new word needs, as a product, naming each number.",
  ],
};

export function seedLongDay(vault, { theme = "bar" } = {}) {
  const sys = (f) => path.join(vault, "_system", f);
  const st = JSON.parse(fs.readFileSync(sys("state.json"), "utf8")), t = st.topics[0];
  const lesson = t.queue.find((q) => q.kind === "lesson"), probe = t.queue.find((q) => q.kind === "probe");
  Object.assign(lesson, { label: "Lesson 07a", title: "Why a word list can't tell word order", why: LONG.why, effort: LONG.effort, rules: LONG.rules, exercise: true });
  probe.status = "done";   // passed long ago: its questions come back from memory
  t.queue = [lesson, ...t.queue.filter((q) => q !== lesson)];
  st.recall = LONG.recall.map((q, i) => ({ id: "rc-long-" + i, q, from: probe.id, added: "2026-01-01" }));
  st.coach = { date: ymd(new Date()), headline: "Warm-up: 3 of 3, and Friday's slip is fixed.",
    body: "For late binding, say the name is looked up when the function is called, not when it is written down.",
    voices: [{ voice: "critic", text: "Friday the list took up space. Today it doesn't. Good. Stay with it." },
      { voice: "logic", text: "You named the work the saved list skips this time: the old words and their places." }] };
  fs.writeFileSync(sys("state.json"), JSON.stringify(st));
  fs.writeFileSync(sys("inbox.jsonl"), "");
  // three nights this week, 30 minutes each: studied, but below the 125-minute goal, so no cap
  const blocks = [0, 1, 2].map((i) => { const d = monday(); d.setDate(d.getDate() + i); d.setHours(20, 0, 0, 0);
    return { id: "long" + i, ts: d.toISOString(), started: new Date(d.getTime() - 30 * 60000).toISOString(), block: "rust", minutes: 30 }; });
  fs.writeFileSync(sys("blocks.jsonl"), blocks.map((b) => JSON.stringify(b)).join("\n") + "\n");
  fs.rmSync(sys("keepsakes.json"), { force: true });
  const cfg = JSON.parse(fs.readFileSync(sys("config.json"), "utf8"));
  fs.writeFileSync(sys("config.json"), JSON.stringify({ ...cfg, theme, goals: { day_minutes: 125, week_days: 4 },
    blocks: { presets: [25, 50, 90], kinds: [
      { id: "rust", label: "Rust lessons", color: "lesson", minutes: 50 },
      { id: "reading", label: "Reading", color: "reading", minutes: 50 },
      { id: "spanish", label: "Spanish", color: "amber", minutes: 25 },
      { id: "homework", label: "Homework", color: "coral", minutes: 50 },
    ] } }));
}
