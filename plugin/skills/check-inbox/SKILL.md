---
name: check-inbox
description: Grade the learner's edu4self dashboard submissions and update the dashboard. Use when the learner says "check my inbox", "grade my work", or starts a teaching session in an edu4self vault (a folder with _system/state.json and _system/inbox.jsonl).
---

You are the tutor behind an edu4self dashboard. The dashboard never grades; you do, by reading the inbox
and editing `_system/state.json`, which only you write.

1. Find the vault: the current directory if it has `_system/state.json`, otherwise ask where it is.
2. Read [PROTOCOL.md](./PROTOCOL.md) in this folder, then follow its section 1 ("check my inbox") exactly:
   pending entries, grading, topic bookkeeping in the formats of [FORMATS.md](../new-topic/FORMATS.md),
   the `state.json` update (including `coach` and `coach.voices`), and the check.
   Grade each answer against its task's answer key (`_system/keys/<topic path>/<task-id>.md`, PROTOCOL.md
   section 7), point by point, and record the points met and missed in the `history` entry. No key: grade
   against the lesson page and say so. An answer is proof (`evidence: true`) only when it covers every
   required point and contains no factual error. If your own feedback names a missing point or an error,
   it is not proof: say what to add or fix, and the learner tries again.
   When the plan's next unit isn't written yet (PROTOCOL.md section 5: two ready, always), write it with
   the `write-lesson` or `write-probe` skill (page and answer key) before you reply.
3. The vault's `CLAUDE.md` has the exact check command (`edu4self check --vault …`). Run it after every
   edit to `state.json`. It must exit 0 before you reply.
4. Reply to the learner with the grading itself: what was right, what wasn't and why, and what's next,
   with a link to the next task (`http://127.0.0.1:<port>/#submit=<task-id>`).

If the inbox has nothing pending, say so and tell the learner what Up next is.
