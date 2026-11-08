---
name: new-topic
description: Start a new learning topic in an edu4self vault and put it on the dashboard. Use when the learner wants to learn something new and the current folder is an edu4self vault.
argument-hint: "What do you want to learn?"
---

The learner wants a new topic: $ARGUMENTS

1. **Ask what's missing, one question at a time:** why they want it (a goal with a date beats a
   subject), what they already know, and how much time they have. *Done when you can write the
   mission's Why and Success lines without guessing.*
2. Pick a short folder name (kebab-case) and create it in the vault with the topic files in
   [FORMATS.md](./FORMATS.md): `MISSION.md`, `RESOURCES.md` (look sources up; lessons are built from
   them), `NOTES.md`, `GLOSSARY.md`, `Dashboard.md`, and the folders `lessons/`, `probes/`,
   `reference/`, `learning-records/`, `assets/`. Copy `lesson.css` and `quiz.js` into `assets/` from
   the vault's `how-learning-works/assets/` if it exists, otherwise from
   `template/how-learning-works/assets/` in the engine (its folder is named in the vault's `CLAUDE.md`).
3. Write the first unit: usually a calibration probe with the `write-probe` skill, because what they
   say they know is a guess until a probe shows it. When the probe has nothing to measure (a subject
   new to them), start with Lesson 01 using the `write-lesson` skill. Write the unit after it too, so
   two are ready.
4. Register the topic in `_system/state.json` as described in section 2 of
   [PROTOCOL.md](../check-inbox/PROTOCOL.md): id, title, tagline, path, colour, milestones with steps,
   the queue from step 3, regions at level 0, and a history entry with `evidence: false`. Add a `gate`
   only if the topic ends in a high-stakes attempt. Then put its units into the vault's `PLAN.md`,
   taking turns with the other topics (PROTOCOL.md, section 5).
5. Set `updated`, write a short `coach` note about the new topic in the learner's room (THEMES.md, "The
   one rule: stay in the room"), and run the check command from the vault's `CLAUDE.md`. It must exit 0.
6. Tell the learner the topic is on the dashboard and what the first task is, with its `#submit=` link.
