# Changelog

All notable changes. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org).

## Unreleased

### Added

- A name on the bar's neon sign can have several subtitle lines (`bar.names`: `[name, [line, ...]]`, up to 20,
  80 characters each). They rotate every 30 seconds and hold still during a block. A single line is still a plain string.
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

### Fixed

- The Rules line on a task was nearly invisible in the library, tea and train rooms; each room now
  gives it a dark ink.
- The train ticket, the tea scroll and the library's drawers no longer stretch to the height of the
  tallest column.
- The work record's copy of the checker output no longer re-adds everything kept on every write, so a
  checker that prints a lot doesn't slow down. Same text, same 200k cap.

### Changed

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

### Removed
- Sharing rooms. The `.room` export and import (Settings buttons, `/api/themes/export`,
  `/api/themes/import`, `./edu4self room`) are gone. Your rooms and the ones you make with Claude work
  as before.

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
