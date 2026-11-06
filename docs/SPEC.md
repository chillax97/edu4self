# edu4self product spec

Version 1.0 · status: shipped · owner: the maintainers (see [CONTRIBUTING.md](../CONTRIBUTING.md))

## 1. Problem

**Who.** A self-directed adult learning a demanding subject alone, outside a course: a developer moving
into a new field, a student preparing for an exam, someone learning a language for a move. They already
use an AI assistant and would happily be taught by it.

**What goes wrong today.** Chat-based tutoring has no memory and no structure. Each session starts from
zero; nobody tracks what was proven versus merely read; the learner decides every day what to do next and
often decides "nothing". Progress is invisible, so motivation decays. Study habits default to rereading,
the method the research rates least useful.

**What it costs.** Weeks of effort that don't stick, and courses abandoned around the second week.

**What success looks like.** The learner opens one page, sees one next step, does it, and submits it. The
tutor grades it the same day with the full history in view. A month later the learner can point at what
they can now do, not at hours spent. The failure that matters most is **false proof**: the dashboard
claiming mastery that a closed-book test would not confirm. Under-crediting is cheaper than
over-crediting, so the system errs that way.

**Why this problem.** Motivation and memory aren't separate problems. A visible record of *demonstrated*
ability is both the motivator and the measurement, as long as it can't be gamed by time spent.

## 2. Users

| persona | situation | needs most |
|---|---|---|
| **The career switcher** | learning a technical field in the evenings, alone | a clear next step, honest feedback, proof it is working |
| **The exam preparer** | fixed date, high stakes, limited retakes | a readiness signal before spending an attempt (the optional gate) |
| **The tinkerer** | wants to make the tool their own | settings without code; a codebase small enough to read in an evening |

Non-users: classrooms and teachers managing many learners; anyone who needs the data in the cloud.

## 3. Goals and non-goals

**Goals**
1. A complete learn → submit → grade → next loop with an AI tutor that keeps state across sessions.
2. A dashboard that a non-programmer can install with one command and customize without a terminal.
3. Separate *effort* (focus blocks) from *evidence* (demonstrated ability), visibly.
4. Local-first: no account, no network calls, plain files the learner owns.
5. Small and readable: Python standard library, vanilla JavaScript, no build step.

**Non-goals (v1)**
- Hosting, sync or multi-device. (A vault in a synced folder works, but isn't designed for.)
- Multiple learners per vault.
- An AI inside the app. The tutor is Claude Code, outside the app, invoked by the learner.
- Spaced-repetition flashcards. Recall checks are scheduled by the tutor, not by an algorithm.
- Windows login-service automation (manual `serve` works).

## 4. Principles

Each principle comes from evidence or from a failure observed while building the first version.

1. **Retrieval over review.** Practice testing and spacing are the two techniques rated most useful
   across ages and subjects (Dunlosky et al., 2013). Recall attempts raise long-term retention more than
   rereading does, even though rereading feels better (Roediger & Karpicke, 2006; Bjork & Bjork, 2020).
   So every lesson ends in closed-book questions, probes test before teaching, and recall checks return
   days later.
2. **Proof is not time.** Time on the die and evidence on the log are drawn separately and can't be
   converted into each other. Only the tutor can mark evidence, and only for demonstrated ability.
3. **One next step.** The page leads with a single primary action. Everything else is secondary or
   behind a click (progressive disclosure).
4. **Honest under-crediting.** When in doubt, the tutor records understanding but not proof, and schedules
   a check. The first live run of the protocol did exactly this on an ambiguous signal.
5. **Gentle, not guilt.** After 3+ idle days the page proposes one 25-minute block, not a backlog.
   Missed water is never mentioned again. Fun blocks ("play") count toward the die.
6. **Respect attention.** Water reminders sound once per interval with no repeat nagging; notifications
   fire only when the tab is in the background. Animations stop under `prefers-reduced-motion`.
7. **The learner owns the data.** Everything is plain JSON, Markdown and HTML in a folder they chose.

## 5. Functional requirements

| id | requirement | verified by |
|---|---|---|
| FR-1 | `./edu4self setup` creates a vault, starts the dashboard at login (macOS, Linux) and opens it | `tests/test_server.py` CliTest; manual on macOS |
| FR-2 | The dashboard shows the first `todo` task without a pending submission as **Up next** | e2e "submitting answers" |
| FR-3 | The learner submits answers or notes; they append to `_system/inbox.jsonl`; a pending one can be withdrawn | unit `test_submission_and_withdraw`, e2e |
| FR-4 | The tutor processes the inbox per [PROTOCOL.md](PROTOCOL.md) and edits only `state.json` | live run with Claude Code (CHANGELOG 1.0.0) |
| FR-5 | `edu4self check` validates `state.json` and every internal link; exit 0 = valid | unit ValidatorTest |
| FR-6 | Focus blocks: kind, duration (presets or 1–240 min), start/stop, survive reloads, saved on completion, idempotent across tabs | unit `test_blocks`, e2e focus block |
| FR-7 | Die / node / rack visualisation from all blocks; per-die details on click | existing behaviour, e2e smoke |
| FR-8 | Water rounds every 15 or 30 min (or off) during a block; counts saved with the block | unit `test_blocks` (validation) |
| FR-9 | Two views (bar, classic) with the same data; each browser remembers its choice; Settings sets the default | e2e first visit, classic |
| FR-10 | Bar view: voices comment on real data (time, streak, die, inbox, proof age, music) plus tutor-written lines (`coach.voices`) | e2e voices check |
| FR-11 | Jukebox plays a built-in soundscape (default, offline), a radio stream, or one learner-supplied track on loop; a track resumes where it stopped and supports seek, ±1 min, random spot; volume; one tab plays at a time | e2e soundscape (measured signal, no offsite requests), radio, jukebox |
| FR-12 | Settings panel edits name, default view, goals, block presets and kinds, water, music (upload/replace/remove), bar names, gags, custom lines, voice names and colours, Obsidian; validated server-side; reset keeps music | e2e Settings, unit config tests |
| FR-13 | A broken `config.json` never breaks the page; defaults are used and the problem is shown in Settings | unit `test_broken_config_file_falls_back_to_defaults` |
| FR-14 | Claude Code plugin with `check-inbox`, `new-topic`, `customize` skills; installing it also installs the `teach` skill | `claude plugin validate`; sandboxed install |
| FR-16 | The page runs Claude Code: Grade (inbox), a chat panel, and New topic; one run at a time, live progress, check after every run; without Claude Code the page shows terminal steps instead. Runs are fenced to the vault (no shell, instruction files locked, no web while grading) | unit `ClaudeTest`, e2e `claude.test.js` (stand-in), real probes |
| FR-17 | Rooms: five built-in rooms (bar, library, space station, night train, tea house) and the learner's own in `<vault>/themes/`, picked in Settings. A room sets layout, palette, fonts, words, voices, jokes, sound, and optionally the lessons' look (on by default, can be turned off). Themed but recognizable: core learning words are never renamed. A room can't run code or load anything; a broken one is listed with its errors, never applied, and `edu4self check` reports it | unit `test_themes.py`, e2e `rooms.test.js` (every room at desktop and phone width, contrast, Settings) |
| FR-21 | (Removed 2026-11-06.) No room sharing: rooms aren't exported or imported from Settings, the API or the CLI. A room gets into a vault only by being written into `themes/<id>/`, and it's checked when loaded | unit `NoRoomSharingTest`, e2e `rooms.test.js` |
| FR-20 | `edu4self mcp`: an MCP server (stdio, standard library) any MCP client can use. Read tools for progress (with answers waiting to be graded), next task with its rules, proven work; one write tool, a note to the tutor through the dashboard's inbox. No tool submits or grades The server tells the connected tool to say, the first time it reads progress, that it goes to its own model | unit `test_mcp.py`; tried with Claude Code and Codex CLI |
| FR-19 | Reminders by mail only: after 3, 7, 15 and 30 days without a study action (block, answer, note), then every 30 days, each step once; it praises what was done and offers one small task for today; 09:00 to 22:00, never during a running block. A Sunday recap every week, saved to `recaps/` and mailed when set up. Mail credentials live outside the vault | unit `test_reminders.py`, e2e `rooms.test.js` (Settings, presence) |
| FR-18 | Trophies: a day that meets the daily goal, a week that meets the weekly goal and every finished die earn a trophy drawn by the room it was won in, kept with that drawing when the room changes. Day and die trophies are drawn stacked (piles of ten, in the room's stack style: pile, fan, heap or row). History is awarded once, quietly. A week or die won now gets a printable card and, if the learner said yes (asked once by setup or the page; off until then, the gift waits), a Claude-made gift (one fenced run, no web). Rooms define their trophies in `theme.json` | unit `test_keepsakes.py`, e2e `shelf.test.js`, contrast in `rooms.test.js` |
| FR-22 | Work record: every run of an exercise's checker saves its output, exit code and the learner's code to `<exercise>/trace/<time>-run.json`, without ever changing or stopping the checker. Hints are opened one at a time in the page and each one is saved there too (`-hint-<n>.json`), so the folder reads in time order. The tutor reads it whole at grading, with the learner's comments, and plans from it. Settings shows what's kept and deletes it after saying what that costs; only files the record wrote are deleted. Never sent over MCP | unit `test_trace.py`, e2e `hints.test.js` |
| FR-23 | "How sure are you?": the submit form asks guessed, shaky or solid (required for answers and done, stored as `confidence`). The tutor names a mismatch with the grade and the work record in one line. After 3 graded answers the progress page shows how often "solid" passed. Never asked of the checker | unit `test_bad_submissions`, `test_calibration_counts_only_graded_answers`; e2e "the submit form asks how sure you are", "how often solid passed" |
| FR-24 | Recall warm-up: the tutor writes one-line questions from passed work (`recall` in state.json). Each day the page asks up to 3 before Up next, the ones not asked for the longest; answers go to the inbox as kind `recall`; "Not now" hides it for today. After 3+ days without a block, answer or note it becomes the welcome back: about 5 minutes, passed work only, newest pass first. Nothing asks for a return date. A missed recall pulls the next recall check forward in `PLAN.md` | unit `test_learning.py` (RecallPickTest, RecallSchemaTest); e2e `recall.test.js` |
| FR-25 | Your attempts: for a task with an `exercise`, the Hints window lists every run (passed or not, time since the run before) and every hint opened, in order. After 3 failing runs in a row with no pass since, the task shows a nudge offering the next unopened hint. Reading only; nothing is written | unit `test_learning.py` StuckTest; e2e `hints.test.js` |
| FR-26 | The job comes first. The room's own lines never restate what the room already shows (tonight's minutes, the week's nights, the next task, the die's count, the finish line). Each line folds to one line with its badge and name, the host's note to its headline and two lines with "more"; a click, a tap or Enter opens it in place, and the classic coach card folds the same way. With a 210-word note and six voices the job starts at most 700px down at 1440x1000 and 1266px at 390x844 in every room. The tutor keeps the note short (PROTOCOL section 1) and the checker warns past 60 words or 4 voices. |
| FR-15 | `edu4self doctor` reports Python, vault, server, service, Claude Code and teach skill, each with a fix | manual |

## 6. Non-functional requirements

- **Privacy:** binds to 127.0.0.1; `Host` and `Origin` checks on every request; no outbound requests
  from the server or page, and no third-party assets at runtime. Claude Code, when you use it, talks to
  Anthropic as it always does, and a chat may search the web. The one opt-in exception: a radio station the learner picks, which
  the browser streams directly while it plays.
- **Dependencies:** Python 3.9+ standard library; browser-native JS/CSS. Node is needed only for the
  browser tests.
- **Portability:** macOS and Linux first-class; Windows runs `serve` manually.
- **Accessibility:** keyboard reachable controls, visible focus, `aria-live` status, reduced-motion
  support, readable contrast in both themes. Phone width (390 px) without sideways scrolling.
- **Robustness:** append-only logs with de-duplication; atomic writes for config; uploads streamed to a
  temp file then swapped in; music served with HTTP Range so seeking works.
- **Size:** the whole client is three files under 150 KB, plus 113 KB of fonts.

## 7. Data contracts

| file | writer | contract |
|---|---|---|
| `_system/state.json` | tutor only | [PROTOCOL.md §3](PROTOCOL.md#3-schema-reference) |
| `_system/inbox.jsonl` | dashboard, append-only | `{id, ts, topic, task, kind, title, fields, note, honor, confidence?}`, a recall `{…, kind: "recall", task: "recall", recall: [ids], comeback?}` and `{id, ts, kind: "withdraw", ref}` |
| `_system/blocks.jsonl` | dashboard, append-only | `{id, ts, started, block, minutes, task?, water_served?, water_drunk?}` |
| `_system/config.json` | Settings panel or learner | [CUSTOMIZING.md](CUSTOMIZING.md) |

## 8. Success measures

For a learner (visible on the dashboard itself): days a week with a block (goal 4), focused minutes a
day (goal 120), and evidence entries per week. For the project: a newcomer reaches a graded first
lesson within 20 minutes of cloning; `doctor` explains every failed setup step it can detect.

## 9. Risks

| risk | mitigation |
|---|---|
| The tutor over-credits (false proof) | protocol rules, `evidence` reserved for demonstrated ability, recall checks after a gap |
| A bad `state.json` blanks the page | `edu4self check` after every edit; the page shows a clear error instead of crashing |
| A Settings change breaks the tutor's check | removed block kinds are a note, not an error; covered by a test |
| A user publishes copyrighted music | no music ships; uploads stay in the vault, which `.gitignore` excludes |
| Trademark trouble | no third-party marks in the product (see decisions) |

## 10. Decisions

- **The code and the data live apart.** The repo is the engine; the vault is the learner's. `git pull`
  can never overwrite progress.
- **The tutor is outside the app.** Claude Code already has file access, skills and the learner's trust.
  The app stays a viewer with a few write endpoints.
- **"Focus blocks", never "Pomodoro".** The Pomodoro Technique® and Pomodoro® are registered
  trademarks of Francesco Cirillo, whose guidelines restrict software built on them. edu4self's blocks
  are plain timeboxing with free lengths, and it does not use or reference those marks in the product.
- **Original voice names.** The bar view is inspired by *Disco Elysium*'s skill-voice dialogue, but uses
  its own characters and names (Logic, Willpower, The archivist, The body, …). Players of that game
  will recognise the idea; no names, text or assets are taken from it.
- **Depend on, don't vendor, the teach skill.** It is maintained upstream (MIT); the plugin declares it
  as a dependency so users get fixes.

## 11. Roadmap (not committed)

Windows login service · an optional local "recall check" scheduler · export of the evidence log as a
shareable page · translations of the dashboard UI.

## References

- Bjork, R. A., & Bjork, E. L. (2020). Desirable difficulties in theory and practice. *Journal of Applied
  Research in Memory and Cognition*, 9(4), 475–479.
- Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., & Willingham, D. T. (2013). Improving students'
  learning with effective learning techniques. *Psychological Science in the Public Interest*, 14(1), 4–58.
- Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning. *Psychological Science*, 17(3), 249–255.
- Wittbrodt, M. T., & Millard-Stafford, M. (2018). Dehydration impairs cognitive performance: a
  meta-analysis. *Medicine & Science in Sports & Exercise*, 50(11), 2360–2368. (Why the water rounds exist:
  the effect is small but real, and largest for attention.)
- Cirillo, F. Pomodoro® trademark guidelines. <https://www.pomodorotechnique.com/pomodoro-trademark-guidelines/>
- Anthropic. Claude Code plugins and marketplaces. <https://code.claude.com/docs/en/plugin-marketplaces>
