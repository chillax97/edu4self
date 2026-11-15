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
   section 7), point by point, and write the checklist in the `history` entry: `points` (every point id
   of the key, `true` only if the answer states it, in any words, not if it could be inferred) and `errors` (every
   incorrect statement, even a minor one or wording that changes the meaning; `[]` if none). No key:
   grade against the lesson page and say so. The checklist decides the pass: `evidence: true` only when
   every point is `true` and `errors` is empty; the check fails otherwise. When a grade moves a region level, also write `levels` in the `history` entry:
   `{"A": [1, 2]}` (region code: level before, level after), so a pass the check overrules can be undone. If your own feedback names a
   missing point or an error, it is not proof: say what to add or fix, and the learner tries again.
   **Same meaning counts:** a point said in the learner's own words, or framed differently from the lecture
   or the key, is met ("cwnd doubles every round trip" meets "+1 per acknowledged segment" in slow start),
   and so is a correct item outside the lecture's list. Failing a right answer for its wording is a grading
   error.
   **Follow-up:** when no point is missing and there is no error, but one point is only bare (true but thin),
   sloppy (right idea, muddled justification) or unclear, ask one question instead of guessing: `evidence:
   false`, `follow_up: {q, point}` (one targeted question, at most 200 characters), a title like "Almost: one
   question first". A missing point or any error is a plain not yet. A `follow-up` inbox entry (`ref`: the
   answer you asked about) is graded together with that answer against the same key: settled is a pass with
   the full checklist, not settled a plain not yet. Never a second follow-up.
   When the plan's next unit isn't written yet (PROTOCOL.md section 5: two ready, always), write it with
   the `write-lesson` or `write-probe` skill (page and answer key) before you reply.
3. The vault's `CLAUDE.md` has the exact check command (`edu4self check --vault …`). Run it after every
   edit to `state.json`. It must exit 0 before you reply.
4. Reply to the learner with the grading itself: what was right, what wasn't and why, and what's next,
   with a link to the next task (`http://127.0.0.1:<port>/#submit=<task-id>`).

If the inbox has nothing pending, say so and tell the learner what Up next is.
