# Changelog

All notable changes. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org).

## Unreleased

### Added
- A running plan. New vaults get a `PLAN.md`: every upcoming unit, in order, across all topics.
  The tutor re-plans it after every grading and every request, so no topic goes quiet waiting for
  its next lesson (PROTOCOL.md, section 5).
- Two units always ready: the tutor writes the next unit while the learner works on the current
  one, and re-plans on every signal (notes, time, skips, recall results), not only on grades.

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
