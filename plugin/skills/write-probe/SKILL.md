---
name: write-probe
description: Write a probe, checkpoint or spaced recall check for a topic in an edu4self vault and put it on the dashboard. Use to measure what the learner knows before teaching, to test a milestone, or to check days later that a passed lesson stuck.
argument-hint: "Which topic, and what should it measure?"
---

A **probe** measures and teaches nothing. Its answers decide what to teach and what to skip, so it
only works unaided. A **checkpoint** is the same at the end of a milestone; a **recall check** is a
checkpoint on one passed lesson, a few units after it. Write it for: $ARGUMENTS

1. **Pick the atoms.** List the separate things to measure: for a calibration probe, the
   prerequisites the mission needs; for a checkpoint, the milestone's skills; for a recall check, the
   lesson's core idea. Read `MISSION.md`, the learning records and `PLAN.md` first. *Done when each
   atom is one skill a single question can show or fail to show.*
2. **Write the questions,** one atom each, so a wrong answer names the missing piece. Ask the learner
   to produce (explain, compute, predict, write), never to recognize; no options to pick from, no
   hints, no worked example nearby. Build from easy to hard and stop at about 10 minutes. On a recall
   check, ask it differently from the lesson's own exercises.
3. **Write the page** at `<topic>/probes/NNNN-<slug>.md`, in the shape of the vault's example probe
   (`how-learning-works/probes/0001-*.md`):
   - frontmatter `tags: [probe, ...]`, `status: open`, `rules: no-lookup` (or what is allowed);
   - `# Probe NNNN: <title>` (`Checkpoint`, `Recall check` for the others);
   - **What this measures**, in one line, and that "I don't know" is a useful answer;
   - **Rules**: from memory, nothing looked up, no running code, no AI, unless the rules say so;
   - **Questions**, numbered;
   - a last line: submit the answers from the dashboard, then press Grade.
   Words stay plain. A probe is a measurement, so it wears no room jokes; the room's look comes from
   the dashboard.
4. **Put it on the dashboard.** Add the task to the topic's `queue` in `_system/state.json`
   (PROTOCOL.md section 3): `kind: "probe"` or `"checkpoint"`, `label` (`Probe 02`, `Checkpoint M1`,
   `Recall check`), `title`, `why` (what it decides), `href: "/vault/<topic>/probes/<file>"`,
   `effort`, `rules` (one line, the same as the page), and `submit: {type: "answers", intro, fields}`
   with one field per question, numbered as in the page. `calculator: true` only when the rules allow
   one and the question isn't testing mental arithmetic. A recall check stays `locked` with an
   `unlock` line until its slot in the plan comes up.
5. **Plan and check.** Slot it in `PLAN.md` (PROTOCOL.md section 5: a recall check goes a few units
   after its lesson, never right after), add a line under Changes, set `updated`, and run the check
   command from the vault's `CLAUDE.md`.

**Done when** every question tests exactly one atom, every question has a matching `submit` field,
the check exits 0, and the learner has its link, `http://127.0.0.1:<port>/#submit=<task-id>`, with one
line on why doing it unaided matters.
