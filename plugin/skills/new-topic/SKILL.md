---
name: new-topic
description: Start a new learning topic in an edu4self vault and put it on the dashboard. Use when the learner wants to learn something new and the current folder is an edu4self vault.
argument-hint: "What do you want to learn?"
---

The learner wants a new topic: $ARGUMENTS

1. Pick a short folder name (kebab-case) and create it in the vault.
2. Inside it, run the `teach` skill (from mattpocock-skills) for the topic. Treat that folder as the teaching
   workspace: `MISSION.md`, `RESOURCES.md`, `NOTES.md`, `GLOSSARY.md`, `Dashboard.md`, `lessons/`, `probes/`,
   `reference/`, `learning-records/`, `assets/`. If the vault has a `how-learning-works/assets/` folder,
   copy `lesson.css` and `quiz.js` from it for consistent lesson pages.
3. Register the topic in `_system/state.json` as described in section 2 of
   [PROTOCOL.md](../check-inbox/PROTOCOL.md): id, title, tagline, path, colour, milestones with steps, a
   first `todo` task (usually a calibration probe, with `submit.fields`), regions at level 0, and a history
   entry with `evidence: false`. Add a `gate` only if the topic ends in a high-stakes attempt.
   Then put its first units into the vault's `PLAN.md`, taking turns with the other topics
   (PROTOCOL.md, section 5).
4. Set `updated`, write a short `coach` note about the new topic, and run the check command from the vault's
   `CLAUDE.md`. It must exit 0.
5. Tell the learner the topic is on the dashboard and what the first task is, with its `#submit=` link.
