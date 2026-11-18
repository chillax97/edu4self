# Changelog

All notable changes. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org).

## Unreleased

### Fixed

- A room saved in a vault before the shared room base keeps its layout. Rooms without `"format": 2` load the old
  room rules (`room-compat.css`); no other room does.

### Added

- The bar is rebuilt as a place: you look down at the counter. The job lies in an open book with your reply on
  the right page, the voices talk on the mat, and by your hand stand the jukebox, your glass and this week's
  bottle caps. The neon sign stays dim until tonight's goal is met.
- One shared scale for type, spacing and corners across the classic view and every room, one button component,
  and a neutral room base (`room.css`). The classic view and the rooms now draw the job from the same data.
- Themes can arrange the back room (`back.html`), set the page around the room (`frame`), show short replies
  (`replies`), and lay this week's trophies in the front room (`keepsakes.day.top`, the `round` slot).
- Tokens: one set of colour names (`--primary`, `--primary-ink`, `--destructive`, `--ring`, `--popover`,
  `--border`, …) that every view and room maps onto. A room's palette accent is its primary, so its tabs,
  Start buttons and focus rings follow the palette with no CSS. The table is in `docs/THEMES.md`.
- The toaster: every notice (saved, water, gifts, trophies, Claude is done) stacks bottom right, newest in
  front, three in sight. Pointing at the stack opens it and holds every notice; each one has a close button.
  It never sits on the page's own controls: it lifts itself above any it would cover (the bar's jukebox at
  the fold), and anything scrolled into view stops above it. While a drawer is open the stack moves to the
  left, clear of the drawer's buttons.

### Changed

- The front-room budget: every room and the classic view shows the next step and its action on the first
  screen (desktop 1440×900 and a half-screen window 720×900, beside the terminal; the dashboard is local, so
  phone widths are not a target), the block's countdown once, and tonight, the week and the die. The finish line,
  locked tasks and trophies are in the back room. Past the host and two voices, the rest wait behind
  "Show N more". During a block only the room's running signal moves (the bar's record, the train's hills,
  the station's planet). The rule for room authors is in `docs/THEMES.md`.
- The bar has two columns, the job and the jukebox. The back bar scene left the front room.
- Classic puts Up next first, then Claude's note and the finish line.

### Fixed

- `serve` prints its URL at once when its output goes to a file or pipe (an agent running it in the background,
  the login service's log); the line used to sit in the buffer.
- `setup` without a login service lists "Start the dashboard: `./edu4self serve --open`" as a step before the
  dashboard's address, and says "Press Enter" only when it will ask something.
- AGENTS.md: the agent runs the plugin commands only when setup says they are still to do, and Windows agents
  are told to use `python edu4self`.
- `serve` no longer looks up 127.0.0.1's name in DNS as it starts; on a Mac with slow reverse DNS that held the start
  for about 35 s.
- `setup` asks its questions only when both its input and its output are a terminal: on Windows an agent's empty
  input (NUL) counted as one.
- On macOS, `setup` and `install` warn when edu4self or the vault is in Documents, Desktop or Downloads, which
  macOS may keep a login service out of, and say how to move it.
- README setup steps give the Windows form (`python edu4self`), clone from the home folder, and tell a fresh Mac
  about Apple's Command Line Tools prompt.
- CI runs a stranger's first run (setup, check, serve, status, doctor: `tests/first_run.py`) on Linux, Windows
  and macOS for every push.

## 1.6.0 - 2026-11-16

### Added

- Rest days: `streak.rest_days` (a list of weekdays, `"mon"` to `"sun"`, default none; Settings → Goals → Rest days)
  keeps a rest from breaking the streak. A rest day with no block is skipped, one with a block counts as a
  normal day. The chalk board (current run, best) and the bartender's "days in a row" lines use one rule.
  See [docs/CUSTOMIZING.md](docs/CUSTOMIZING.md).
- The honesty test's SAF questions in the small set now have point-listed answer keys (`evals/grading/saf/keys.json`):
  required points (with the lecturer's reason or mechanism as its own point), wrong answers, and what is not required,
  written from the question and the reference answer alone. `run.py` uses one when a question has it and keeps the
  lecturer's notes as the key otherwise. The keys are part of the grading-inputs hash, so a run made before this
  cannot be resumed and a new run is needed.
- A third grading outcome, the follow-up (PROTOCOL.md sections 1 and 3, the `check-inbox` skill): when no key point
  is missing and there is no error, but one point is only bare, sloppy or unclear, the tutor asks one question
  (`history[].follow_up: {q, point}`, at most 200 characters, `evidence: false`) instead of tossing a coin. The
  reply is a `follow-up` inbox entry (`ref`: the graded answer), graded with the original against the same key:
  a pass, or a plain not yet, never a second question. The check refuses a follow-up on a pass or on the grade of
  a reply, and the server takes a reply only for an answer whose grade asked one. A pass on follow-up counts as a
  pass in "How sure vs how it went".
- The dashboard asks the follow-up question. While a task's latest answer has a grade with a question and no reply,
  its card (Up next, the room's job card) shows "Almost: one question first", the question and a one-field reply box
  with **Send reply**, instead of the button that sends the whole task again; a task further down the list gets
  **Answer the question**, which opens a one-question form. The reply needs no "How sure are you?". Once sent the
  card says **Reply sent** and waits for the tutor like any submission, and it can be withdrawn the same way, which
  opens the question again. A reply being typed survives the page refreshing itself. `/api/state` now gives a
  `follow-up` entry's `ref` in `inbox.all_submissions`.
- Section 1 now says it outright: same meaning counts. A point said in other words or framed differently from the
  lecture or the key is met, and failing a right answer for its wording is a grading error.
- The honesty test knows the follow-up: `run.py` records it as a verdict of its own (with the question),
  `--replies good|bad` answers each question with a scripted reply and grades it in a second run, and `score.py`
  reports over-asked, under-called and the follow-up rate, and scores against policy labels with `--labels`.
- The honesty test's `run.py --repeat N` grades every answer N times, each time in a fresh vault, and `score.py`
  reports the flip rate: the share of answers whose pass / not-pass verdict changed across repeats (a follow-up
  counts as not pass), and the 3-way flip rate (pass / follow-up / not yet). Rows get a `repeat` field only with
  N above 1, so older run folders score as before; `--resume` goes by answer and repeat.
  A run without follow-ups scores exactly as before.

### Removed

- The honesty test (`evals/grading/`, the `honesty-test` skill and its tests) moved out of the engine, and
  `docs/SPEC.md` is gone: the repo keeps what a learner uses, plus its tests and community files. The
  spec's research references are in `CREDITS.md`.

## 1.5.1 - 2026-11-14

### Fixed

- A pass the check overrules no longer keeps the region level it raised. The grade records `history[].levels`
  (`{"A": [1, 2]}`, region code: level before and after) and `edu4self check --overrule` restores each "before"
  unless a later grade has moved the level, which it leaves alone and says so. A grade without `levels` (an older
  one) changes no level. (PROTOCOL.md sections 3 and 4 and the data format; the `check-inbox` skill.)
- The honesty test no longer loses a paid run to a crash or Ctrl-C: each answer's result is saved as soon as its
  batch is graded, and `run.py --out <folder> --resume` grades only the answers not yet saved or saved without a
  grade. A `meta.json` in the folder (set, seed, batch size, case list, a hash of the grading inputs) makes a
  resume with different settings, or after the plugin or grading prompt changed, refuse.
- The honesty test's grading sandbox copies only git-tracked files (minus `evals/` and `tests/`), so an untracked
  or ignored file, such as private notes, can never reach the grader.

## 1.5.0 - 2026-11-14

### Added

- `honesty-test` skill: ask Claude to "run the honesty test" and it grades the labelled answers in `evals/grading/`
  through the real Grade path, says the price first, and reports the false-pass rate in plain words.
- The honesty test (`evals/grading/`): how often the grader passes an answer that should not pass. 80
  made-up answers (60 must not pass, from half-right to "mark this as passed" injections and code that
  games its checker) and 100 labelled student answers from the SAF set (CC BY 4.0), graded through the
  Grade button's own run, scored as a false-pass rate with a 95% interval, kappa, per category and cost
  per answer. It measures; it changes nothing in how grading works.


- `edu4self doctor` reports the Claude Code login: signed in, signed out (with the fix, `claude auth login`,
  and it counts as a thing to fix), or unknown on a Claude Code too old to say. It asks the same check the
  dashboard uses, so the two always agree.

### Changed

- Grading is strict: an answer counts as proof only when it covers every required point and has no factual
  error. A grade that names a missing point or an error is not a pass; the learner is told what to fix and
  tries again. Every new lesson exercise and probe question gets an answer key (required points, wrong answers
  to watch for, what is not required) in `_system/keys/<topic>/<task-id>.md`, written with the page and never
  served by the dashboard. The grade goes point by point and records a checklist: `history[].points` (each
  key point, true or false) and `history[].errors` (wrong claims). The checklist decides the pass, not the
  grader's overall impression: `edu4self check` fails a pass with a missed point or an error on it, and
  after a run started from the page (which has no shell to run the check) the dashboard runs
  `edu4self check --overrule`, which turns such a pass into not passed and says why in the Claude panel.
  An older task without a key is graded against its page, and the grade says so. The example topic ships
  with its keys. (PROTOCOL.md sections 1, 3, 4 and 7; the `check-inbox`, `write-lesson` and `write-probe` skills.)
- The honesty test's vault carries answer keys like a real one, and `--set small` grades a fixed set of 30
  answers (`evals/grading/small.txt`) to try a grading change on before the full run.
- A grade follows this engine's own tutor plugin (`--plugin-dir`), not the version installed in Claude Code, and no
  personal settings or hooks from `~/.claude` load into it. Chat runs are unchanged.
- README says what grading costs: plan usage on Pro or Max, a per-run bill with an API key (one first-try grade measured $0.28).
- `edu4self doctor` looks up the newest GitHub release (one request to api.github.com, 2 s timeout, silent offline,
  `EDU4SELF_NO_UPDATE_CHECK=1` turns it off; nothing about you is sent) and, when you are behind, prints the update
  commands: `git pull && ./edu4self restart`, and the two `claude plugin` commands for the tutor skills. README and
  CONTRIBUTING gained Updating and Releasing sections.
- `serve` on a taken port prints one plain line (which port, and `--port` to pick another) instead of a traceback, and
  `setup` checks the port before it makes anything. `setup` on a folder that already holds a vault now uses it and
  carries on, instead of stopping with "Pick a new folder".
- No dashboard text is smaller than 11 px any more (it went down to 7.5 px in the week strip and the streak board).
- The README images went from 10.0 MB to 4.6 MB (screenshots resized to 1600 px wide and palette-packed, the tour gif at
  5 fps with 64 colours); nothing was removed.
- README opens with a 5-line quick start; install shows `git clone --depth 1` (a third of the download).


- The dashboard server speaks HTTP/1.1 and keeps connections open, so a page load reuses a few connections
  instead of opening one per file. Every response says where it ends, a refused upload closes its connection,
  and an idle connection is closed after 30 seconds.
- The Windows browser tests in CI block again. They failed about one run in three, one test each time: Chrome
  ran out of buffer space (`ERR_NO_BUFFER_SPACE`) with one connection per file, and some browser waits gave up
  for good if the page was mid-redraw when they checked.


- The first visit is a two-minute try instead of a three-card tour: one idea, hidden, answered from memory, a
  quick check on the spot (it looks for three key points and says it can be fooled), and, one click and
  opt-in, Claude's real grade of the same answer in the card. Without Claude the check still runs and the card
  says what's missing. It ends with a pick: your own topic (straight into New topic) or the example lesson.
  Shown once; existing users never see it. "Replay the intro" in Help shows it again. It's a stage of its own:
  the dashboard stays hidden until the pick, and the card is readable from the first frame (it used to fade in
  over the busy page).
- The page's Claude runs have a new kind, `first`: a grade-only run for the first try (fenced like grading, no
  planning or new lessons), so the first grade lands faster and costs less than a full "check my inbox".

### Fixed

- The "From memory" warm-up no longer asks a question the moment Claude writes it. A recall question is
  shown only once its task passed at least 3 days ago (one constant, `RECALL_MIN_AGE_DAYS`), on a normal
  day and on the welcome back alike, and never for a task that has not passed. The pass date is the
  latest graded submission; a question may carry an optional `added: YYYY-MM-DD` for a task marked done
  without one, and a done task with no date at all is still shown.


- A Grade button greyed out because Claude Code is missing or signed out now looks off at a glance, in the
  classic page and in every room: no colour fill or glow, a dashed edge, a not-allowed cursor, and the
  reason on hover. Its label and the reason beside it stay readable (at least 4.5:1), also on the paper
  cards of the library, tea and train rooms.
- The green "Submitted just now" line on the task card was almost invisible (about 1.2:1) on the paper cards of the
  library, tea and train rooms. Each now draws it in a dark green that suits the room (at least 4.5:1).

## 1.4.0 - 2026-11-11

### Added

- Windows is supported. `edu4self install` (and `setup`) adds a Task Scheduler task that starts the dashboard
  at logon, with no 72-hour limit and a restart after a crash; `uninstall`, `restart` and `status` use it
  too. Unit and browser tests now run on Windows in CI. The
  login task itself is only unit-tested.
- The dashboard says when it opens if Claude Code is missing or not signed in, before any lesson: a note under
  the top bar (classic page and rooms) with the one-line fix, and Grade greyed out with the reason. It checks
  with `claude auth status`, which costs nothing, and again when you come back to the tab; the note goes by
  itself once Claude works. A gift waits while Claude is signed out.

### Changed

- `edu4self setup` installs the tutor plugin itself when Claude Code is found: it asks once (default yes),
  runs `claude plugin marketplace add` and `claude plugin install`, skips what is already there, and checks
  `claude plugin list` afterwards. If that fails it prints the two commands to run by hand, and setup
  still finishes. `--no-plugin` skips it. Without Claude Code, setup says it's needed. Before, setup only
  printed the commands, and people who skipped them had no tutor skills.
- `edu4self doctor` asks Claude Code whether the plugin is installed and enabled (the same check setup
  uses), and says so when it's installed but disabled.

### Fixed

- `edu4self setup` crashed on Windows when its input wasn't a terminal (Windows calls the `NUL` device one):
  a question with no answer now takes the suggestion in brackets.
- The away mail and the Sunday recap failed on Windows (a date format Windows rejects).
- On Windows, the Claude panel never runs npm's `claude.cmd` through `cmd.exe` (which mangles a prompt), and
  the dashboard server no longer crashes when started without a console (as the login task does).
- On Windows, the Claude panel works with Claude Code installed by npm: it runs what `claude.cmd` points at
  directly (the package's `bin/claude.exe`, or `node` and the script in older versions), so a prompt arrives
  unchanged. `claude.exe` from Anthropic's installer still comes first. When the npm install is broken
  (missing file, install step skipped, no Node.js), `doctor` says which and how to fix it.
- After a Claude run that failed, the page could still say "Claude is done." (the check after it passed because
  nothing had changed). It says so now only when the run itself succeeded.

## 1.3.0 - 2026-11-09

### Added

- Rooms name the back room and say more lines their own way: `words.collection`, `row`, `rows`,
  `tray`, `trays`, and `lines.water`, `hydrated`, `row_full`, `row_full_body`, `die_full_body` with
  `{placeholders}` (see docs/THEMES.md). The help panel and Settings' voice names follow the room,
  and each built-in room has its own words (the library's shelves and bookcases, for one).
- Two plugin skills that write edu4self's own units: `write-lesson` (the lesson page, its closed-book
  exercises, an exercise with a checker, a redo with a refresher) and `write-probe` (probes,
  checkpoints and spaced recall checks). The topic file formats live in the plugin too, adapted from
  Matt Pocock's `teach` skill with its MIT notice. `new-topic` and `check-inbox` use them.

### Removed

- The dependency on Matt Pocock's `teach` skill (`mattpocock-skills`): the plugin installs on its own,
  and nothing falls back to `teach` any more. Starting a topic is **+ New topic**, "I want to learn X",
  or `/edu4self:new-topic`. `edu4self doctor` checks the plugin's own skills. Credit stays in `CREDITS.md`.
- A name on the bar's neon sign can have several subtitle lines (`bar.names`: `[name, [line, ...]]`, up to 20,
  80 characters each). The next one shows each time the neon blinks, and they hold still during a block. A single line is still a plain string.
- The room is drawn once and patched after that: a poll rewrites only the slots that changed, so
  nothing restarts every 15 seconds. In the bar, what changed moves: a fuel segment gulps in, a week
  tile flips, a die stone is set with a spark, a new voice line leans in, a new job card clips on, an
  opened door slides out. Bigger beats play once on `.room[data-event]`: the goal (the sign blinks, a
  cap lands on the counter), a week won, a die shipped (a light sweeps the case, glints walk the
  bottles), a grade (the counter bell rings), a block's end (the record winds down, the bartender
  nods) and coming back after 3 or more days (the lights come up). The time of day tints the scene
  (`data-phase`). During a block the room holds still; the record turns slowly. Reduced motion is honoured.
- The streak on a chalk board on the front of the counter: days in a row with at least one finished
  block, in tally marks, "13 nights running" and the house record in the corner (theme words
  `streak_run`, `streak_best`). A new day draws a stroke, every fifth the slash,
  7, 14, 30, 60, 100, 200 and 365 get an underline and a tap from the bartender, a new best a brass
  star; after a break the board is wiped once and the best stays. New optional theme slot `streak`;
  rooms without it keep the streak as a Willpower line.
- Room sounds (Settings, Room; `room_sounds`, off by default): small sounds made in the browser, no
  files, each starting with its motion. During a block only its start and end make a sound.
- "How sure are you?" on the submit form: guessed, shaky or solid, required for answers and done,
  stored on the inbox entry as `confidence`. The tutor compares it with the grade and the work record
  and names a mismatch in one line. Once three answers are graded, the progress page shows how often
  "solid" really passed (a history entry links its grade with `inbox`).
- A small calculator in the answer form, only for tasks (and recall questions) whose state.json entry
  says `calculator: true`, which the tutor sets when the rules allow one. It reads `+ - * / ( )`, `^` or
  `**`, `%` as a remainder, `1e9`, and the byte units KiB, MiB, GiB (1024s) and KB, MB, GB (1000s), with
  its own parser. Results get thousands separators and a short form ("16,384 (16 KiB)"). The job card
  says "Calculator allowed". The sums go to the inbox with the answer as `calc: [{expr, result}]` (at
  most 50), so the tutor can name the wrong step, not only the wrong total.
- A "From memory" warm-up before Up next: 2 or 3 one-line questions the tutor wrote from passed work
  (`recall` in state.json), the ones not asked for the longest. Answers are typed with only the
  questions shown and go to the inbox as kind `recall`; "Not now" hides it for today. After 3 or more
  days away the same card is the welcome back: about 5 minutes, only work already passed, the most
  recently passed first. Nothing ever asks for a return date.
- "Your attempts" in the Hints window: every checker run (passed or not, and how long after the one
  before) and every hint opened, in order. After 3 failing runs in a row the task shows a gentle
  nudge that offers the next hint. Nothing is written by it.
- A work record for exercises with a checker. Each run saves what the checker printed and a copy of
  your code, named by its time, in the exercise's `trace/` folder. Hints open one at a time from the
  dashboard (a Hints button on the task, or `#hints=<task>`) and each one opened is noted in the same
  folder. When you hand the exercise in, the tutor reads the whole attempt with your comments and
  plans from where you actually got stuck. Settings shows what's kept and can delete it, after saying
  what that costs. New `exercise` field on tasks; checkers start with a few lines from PROTOCOL.md.
- The mail app password can live in the macOS Keychain or a Linux desktop's password store instead of
  the config file. It's optional: `mail setup` lists where it can go and the risk of each, and the
  file stays the default.
- The jukebox plays a list of your own songs (`music.files`, up to 100) in turn, back to the first after
  the last, with prev / next buttons; it resumes the same song after a reload. Settings → Music → Your
  songs adds one file or several at once, renames, reorders and takes songs off the list (the files
  stay). Uploads take mp3, m4a/aac, ogg/oga, opus, wav, flac and webm, up to 1 GB each; a same-name file
  gets a suffix instead of overwriting, and a file that isn't audio is refused. A config with only
  `music.file` plays as before.
- Sharing rooms. The `.room` export and import (Settings buttons, `/api/themes/export`,
  `/api/themes/import`, `./edu4self room`) are gone. Your rooms and the ones you make with Claude work
  as before.
### Fixed

- The dashboard's New topic asked Claude to start the `teach` skill, which only a person can start
  (`disable-model-invocation`). It now starts the plugin's `new-topic` skill.
- Lesson quizzes shuffle their answer options when the page opens, so the right answer isn't always
  second. `data-fixed` on a quiz keeps its order.
- The Rules line on a task was nearly invisible in the library, tea and train rooms; each room now
  gives it a dark ink.
- The train ticket, the tea scroll and the library's drawers no longer stretch to the height of the
  tallest column.
- The work record's copy of the checker output no longer re-adds everything kept on every write, so a
  checker that prints a lot doesn't slow down. Same text, same 200k cap.

### Changed

- The built-in bar is general now: study life and light coding humour, with no machine-learning
  in-jokes. New sign names (The Rubber Duck, Cram & Tonic, Off by One, The Open Tab, Last Call), new
  gags, Halloween, Valentine and water lines, the `gpu` voice shown as "The die-maker", and the back
  room counts finished dies in rows of 8 and trays of 4 rows in "The die case" (it said GPUs, nodes,
  racks and "Your cluster"). Voice ids are unchanged, so saved state still works. To keep the old
  bar, copy it into `<vault>/themes/bar/` and set the words and lines below.
- New vaults start with a daily goal of 60 focused minutes (it was 120), still 4 days a week.
  Existing `goals` in `config.json` are kept.
- The bar's default sign names no longer include "Bad Tokens"; "Off by One" takes its place. A name
  list you saved keeps working as it is.
- The job comes first in every room. The room's own lines no longer repeat what's already on screen
  (tonight's minutes, the week's nights, Up next, the die's count, the finish line), which also
  drops the stray "seen?." full stop. Every line folds to one line with its name; the host's note
  shows its headline and two lines with "more". Click, tap or press Enter to open one in place. The
  lines fade in faster. On a phone the bar puts the talk and the job before the back bar, the
  finish line, the doors and the trophies, and space puts the mission above the comms log. The
  classic coach card folds the same way.
- The tutor writes a short coach note: a headline of at most 15 words, a body of at most 40 words,
  and 2 to 3 one-beat voices. The detail lives in the history entry and the learning record.
  `edu4self check` warns (and still passes) past 60 words or 4 voices.
- Gifts from Claude are off until you say yes. Each one is a run on your Claude plan, so setup asks
  (or `--gifts on|off`), and if it didn't, the dashboard asks once. A gift won before you answer waits.
- Tasks carry no dates. The `opens` field is gone: a spaced recall check sits a few units later in
  `PLAN.md` and opens as soon as the units before it are done. The MCP tool `get_due` went with it;
  `get_progress` now lists the answers waiting to be graded.
- MCP: every read tells the connected tool (Claude included) to let you know, once per conversation,
  that what it reads goes to its model provider. docs/MCP.md says what leaves your computer.
- Reminders come by mail only, and only when you've been away: after 3, 7, 15 and 30 days without a
  block, answer or note, then once every 30 days. Each mail says what you've done so far and offers
  one small thing for today. The daily nudge and desktop notifications are gone. The Sunday recap
  stays, by mail. Mail is on by default once `./edu4self mail setup` is done, unless you switched it off
  before: a saved `mail: false` stays off.
- The away mail gives context: where you left off (your last session and the last thing you proved,
  your milestone), what each trophy on your shelf stands for, how close your next die is, and why
  the next task matters.
- Every trophy on the shelf can be clicked: a small card shows the day it was won, stamped in the
  room's words ("bottled", "checked out", "punched"), what it stands for and the numbers behind it.
  The shelf caption says what each kind means. Rooms set the word with `keepsakes.<kind>.stamp`.
- A reminder mail that fails shows on the dashboard until you dismiss it, with the reason and a way to
  the mail settings.
- The README says up front what you need (Claude Code, macOS or Linux, Python 3.9+) and opens on a room.
- The plugin has its own README, and LICENSE is plain MIT text so GitHub detects it (the font note moved to CREDITS).
- macOS CI runs on release tags and manual runs only; Linux runs on every push.
- The two time-of-day dashboard tests pin the page clock, so they pass at any hour.

## 1.2.0 - 2026-11-04

### Added
- A running plan. New vaults get a `PLAN.md`: every upcoming unit, in order, across all topics.
  The tutor re-plans it after every grading and every request, so no topic goes quiet waiting for
  its next lesson (PROTOCOL.md, section 5).
- Two units always ready: the tutor writes the next unit while the learner works on the current
  one, and re-plans on every signal (notes, time, skips, recall results), not only on grades.

### Fixed
- Maths in lesson pages uses its proper fonts again. Lessons run sandboxed, and the browser refused
  their font files; the server now allows font files, and only font files, to sandboxed pages.

## 1.1.0 - 2026-11-02

### Added
- Share rooms. Save any room as one `.room` file and add rooms others made, from Settings or with
  `./edu4self room export` / `import`. Imports are checked and can't touch anything outside
  `themes/<id>/`.
- Your progress in any AI tool: `./edu4self mcp` is an MCP server. Claude, Codex, Cursor and other
  MCP clients can read your progress, next task (with its rules) and proven work, and leave your tutor
  a note. They can't submit or grade. See `docs/MCP.md`.
- Reminders. One nudge on a day you haven't studied, only when something opens today or your
  week needs today, after an hour at the computer, never during a block. A desktop notification,
  and mail from your own account (`./edu4self mail setup`). Every Sunday, a recap of your week,
  saved to `recaps/`. Tasks can carry an `opens` date for spaced recall checks.
- A Settings switch for Claude's gifts.
- Trophies. Meeting your daily goal adds a trophy to a pile on your shelf, drawn by your room (a
  bottle cap, a book, a mission patch). Weekly goals and finished dice add their own, each with a
  card to print and a small gift Claude makes from what you proved. Days and dice pile up as
  real objects (a stack of bottle caps, a row of bound volumes). Trophies keep the look of the
  room they were won in, so a shelf can mix rooms. Past history is awarded once, quietly. Rooms
  define their trophies in `theme.json` (see `docs/THEMES.md`).
- Rooms. Pick where you study in Settings: the bar, the library, the space station, the night train
  or the tea house. Each has its own layout, colours, characters, jokes and sound, and lessons take
  its look (Settings turns that off). Make your own in `<vault>/themes/`, or ask Claude to:
  `docs/THEMES.md` is the guide. A room can't run code or load anything, and `edu4self check` says
  what's wrong with one that doesn't pass.
- Claude in the page. **✦ Grade** grades your inbox, **✦ Claude** opens a chat with your tutor, and
  **+ New topic** (its own button) starts a topic from what and why. The page runs Claude Code in your
  vault and shows what it reads and edits as it works, then the check result. Without Claude Code, the
  page keeps its terminal instructions.
- The jukebox plays without any files: three soundscapes made live in the browser (Night shift, Rain
  on the window, Brown noise; offline, the new default, paused until you press play), or a radio
  station (four Radio Paradise channels, or any stream address). Your own track still works, and older
  configs keep playing it. Settings → Music picks the source. The soundscapes are music, not noise:
  Night shift is lo-fi electric piano with soft bass and brushes, Rain is slow piano over a soft rain
  bed (`app/dashboard/scapes.js`; `tests/e2e/scapes.js` renders them to WAV and measures them).
- `AGENTS.md` (and a `CLAUDE.md` that imports it): the playbook for an agent a person hands this repo
  to. It sets edu4self up and turns plain-English wishes into settings. The README now leads with it.
- A two-minute tour video and a GIF cut, recorded from the real dashboard by `tests/e2e/tour.js`.

### Security
- Lesson pages in the vault run sandboxed (CSP `sandbox`), so a shared lesson's scripts can't use the
  dashboard API.
- Claude runs started from the page are fenced: reads and edits stay inside the vault, the instruction
  files are locked, there is no shell, and grading has no web access. Tested with a real Claude told
  to break out.

### Fixed
- `edu4self install`: the dashboard started at login can now find Claude Code. Services start
  with a bare PATH, so the Claude panel and the Grade button stayed off; the service now carries
  the PATH of the shell that ran install. Run `./edu4self install` again to pick this up.
- The jukebox could throw when a track was changed or removed (the old player kept firing events).
- `edu4self check` validates `config.json`. A bad file used to make the dashboard fall back to defaults
  silently while the check passed.
- `Home.md` in a new vault links the port it was made for, not always 4747.

## 1.0.0 - 2026-10-30

First public release, opened up from a personal setup that had been in daily use.

### Added
- The learn → submit → "check my inbox" → graded loop, with Claude Code as the tutor and
  `docs/PROTOCOL.md` as the contract.
- Dashboard with two views (classic and the bar), Up next, queue, milestones, finish line, evidence log,
  skills ladder, library, and a readiness gate for topics that need one.
- Focus blocks with free durations and kinds, the die → node → rack record, water rounds.
- The bar: voices that comment on real data and on Claude's grading, rotating jokes, the jukebox.
- **Settings panel**: name, default view, goals, block presets and kinds, water, music upload, bar names,
  jokes, your own lines, voice names and colours, Obsidian. Stored in `_system/config.json`.
- `edu4self` command line: `setup`, `init`, `serve`, `install`/`uninstall` (launchd, systemd),
  `restart`, `status`, `check`, `doctor`, `open`.
- Vault template with an example topic ("How learning works"), `CLAUDE.md` and `AGENTS.md`.
- Claude Code plugin (`check-inbox`, `new-topic`, `customize`) that installs Matt Pocock's `teach` skill
  as a dependency.
- Unit tests (standard library) and browser tests (Puppeteer), CI on Linux and macOS.

### Verified
- A real `claude -p "check my inbox"` in a fresh vault graded a lesson submission, updated `state.json`
  and passed `edu4self check`. It also found two gaps in the protocol (the honor flag on lessons; a
  hard-coded port), fixed before release.
