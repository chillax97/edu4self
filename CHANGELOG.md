# Changelog

All notable changes. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org).

## Unreleased

### Added
- The jukebox plays without any files: three soundscapes made live in the browser (Night shift, Rain
  on the window, Brown noise; offline, the new default, paused until you press play), or a radio
  station (four Radio Paradise channels, or any stream address). Your own track still works, and older
  configs keep playing it. Settings → Music picks the source.
- `AGENTS.md` (and a `CLAUDE.md` that imports it): the playbook for an agent a person hands this repo
  to. It sets edu4self up and turns plain-English wishes into settings. The README now leads with it.
- A two-minute tour video and a GIF cut, recorded from the real dashboard by `tests/e2e/tour.js`.

### Fixed
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
