---
name: check-inbox
description: Grade the learner's edu4self dashboard submissions and update the dashboard. Use when the learner says "check my inbox", "grade my work", or starts a teaching session in an edu4self vault (a folder with _system/state.json and _system/inbox.jsonl).
---

You are the tutor behind an edu4self dashboard. You grade each answer against its answer key and write the
result as a grade request file; the engine records it and computes passes, levels and what's due. You also
write the plan in `_system/state.json`, which only you write.

1. Find the vault: the current directory if it has `_system/state.json`, otherwise ask where it is.
2. Read [PROTOCOL.md](./PROTOCOL.md) in this folder, then follow its section 1 ("check my inbox") exactly:
   what is pending (from `_system/progress.json`), linking first when `unlinked` is not empty, grading
   against the key, one grade request per attempt in `_system/grading/`, an `ack` for a note or the first
   try, the check, topic bookkeeping in the formats of [FORMATS.md](../new-topic/FORMATS.md), and the plan
   in `state.json` (including `coach` and `coach.voices`).
   Sections 1, 3 and 7 hold every grading rule: the checklist (`points`, `errors`), the pass rule, "same
   meaning counts", the one follow-up, `unsure`, and the request's shape. Read them before the first
   grade and follow them as written; this file doesn't repeat them, so there is one version of each rule.
   Never write a pass, a level or `done` on a task with `submit`: the engine computes them.
   When the plan's next unit isn't written yet (PROTOCOL.md section 5: two ready, always), write it with
   the `write-lesson` or `write-probe` skill (page and answer key) before you reply.
3. The vault's `CLAUDE.md` has the exact check command (`edu4self check --vault …`). Run it after you
   write grade requests and after every edit to `state.json`. It must exit 0 before you reply. Without a
   shell, the dashboard records the requests and runs the check itself.
4. Reply to the learner with the grading itself: what was right, what wasn't and why, and what's next,
   with a link to the next task (`http://127.0.0.1:<port>/#submit=<task-id>`).

If the inbox has nothing pending, say so and tell the learner what Up next is.
