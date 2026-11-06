# Architecture

edu4self is three small programs around one folder of plain files.

```
 browser ──HTTP (127.0.0.1)──▶ app/server.py ──reads/writes──▶ vault/_system/*
                                    ▲                                ▲
 edu4self (CLI) ── starts ──────────┘                                │ edits state.json
                                                                     │
 Claude Code + plugin skills ── "check my inbox" ────────────────────┘
```

## Components

| part | file(s) | job |
|---|---|---|
| server | `app/server.py` | serves the page, a JSON API, vault files and music; validates everything it writes |
| page | `app/dashboard/index.html`, `app.js`, `app.css`, `fonts/` | renders state; submissions, blocks, Settings |
| rooms | `app/themes.py`, `app/dashboard/themes/<id>/` | load, check and clean rooms (built-in and the vault's own) |
| MCP | `app/mcp_server.py` | `edu4self mcp`: progress for any AI tool over MCP (stdio); reads `/api/state`, notes go through `/api/inbox` |
| reminders | `app/reminders.py` | when an away mail (3, 7, 15, 30 days) or the Sunday recap is due, what they say, mail |
| work record | `app/edu_trace.py` (copied to `<vault>/_system/` at start), `server.py` hints/traces | each checker run saves its output and the learner's code to `<exercise>/trace/`; hints opened in the page are noted there; the tutor reads the folder at grading |
| trophies | `app/keepsakes.py` | what the blocks have won (day, week, die), kept with the drawing of the room it was won in |
| validators | `app/validate_state.py`, `app/check_links.py` | the check the tutor runs after every edit |
| CLI | `edu4self` | setup, init, serve, login service, check, doctor |
| template | `template/` | what a new vault starts as, including the example topic |
| plugin | `plugin/`, `.claude-plugin/marketplace.json` | Claude Code skills: check-inbox, new-topic, customize |

All Python is standard library (3.9+). The page is vanilla JavaScript in one IIFE: no framework, no
bundler, no network requests beyond its own server (except a radio stream, if the learner picks one).

## The vault

```
_system/state.json     the tutor's view of the learner: topics, queue, milestones, regions, history, coach
_system/inbox.jsonl    submissions and withdrawals (append-only)
_system/blocks.jsonl   finished focus blocks (append-only)
_system/config.json    Settings
_system/keepsakes.json trophies won, with a copy of each one's drawing (server only)
_system/reminders.json which away mails went out and which weeks were recapped (server only)
recaps/                the Sunday recaps, one markdown file a week
gifts/                 pages Claude made when a week or a die was won
_system/music/         one audio file
_system/logs/          service output (when installed)
<topic>/               MISSION.md, lessons/*.html, probes/*.md, reference/*.html, learning-records/*.md, …
CLAUDE.md, AGENTS.md   tutor instructions, with this vault's paths and port filled in
PLAN.md                the running plan: every upcoming unit, in order, across topics (tutor writes)
```

**Single writer per file.** `state.json` is written only by the tutor. The logs are appended only by the
server. `config.json` is written by the server (from Settings) or by hand. Nothing writes the topic
folders except the tutor. This is what makes the system easy to reason about and safe to sync.

## HTTP API

All routes require `Host: 127.0.0.1:<port>` or `localhost:<port>`. POSTs from another origin are refused.

| method | path | body | result |
|---|---|---|---|
| GET | `/api/state` | | state, derived counts, pending inbox, blocks, config, server info |
| GET | `/api/config` | | `{config, defaults, error}` |
| GET | `/api/health` | | `{ok, now, version}` |
| GET | `/vault/<path>` | | a vault file (not `_system/`, no dot-folders); `.md` opens in Obsidian when enabled |
| GET | `/music` | | the configured track, with Range support (206/416) |
| POST | `/api/inbox` | `{topic, task, kind, title, fields, note, honor}` | 201 `{id}` |
| POST | `/api/withdraw` | `{id}` | 200, or 404 if not pending |
| POST | `/api/blocks` | `{block, minutes, started, task?, water_served?, water_drunk?}` | 201 new, 200 duplicate |
| GET | `/api/themes` | | `{themes: [{id, name, icon, about, lessons, builtin, errors}], active}` |
| GET | `/api/theme?id=` | | 200 `{meta, layout, css}`; 422 `{errors}` for a broken room; 404 |
| GET | `/theme/lesson.css` | | the active room's lesson styles |
| POST | `/api/presence` | `{block_until}` | a block is running until then (or `null`); holds reminders |
| GET | `/card?id=` | | a printable card for one trophy, in its room's colours; 404 if unknown |
| POST | `/api/config` | `{config}`, or `{reset: true}`, optional `remove_music` | 200 `{config}`, 400 `{error}` |
| POST | `/api/music` | raw audio, `X-Filename` header | 201 `{config}`; 413 over 1 GB; 415 not audio |
| GET | `/api/claude?since=N` | | `{available, busy, kind, conversation, events[N:], next}` |
| POST | `/api/claude` | `{kind: grade\|chat\|topic, text}` | 202; 409 busy; 503 no Claude Code |
| POST | `/api/claude/stop`, `/api/claude/reset` | `{}` | stop the run; forget the conversation |

**Claude from the page.** `/api/claude` starts `claude -p` in the vault, one run at a time, and turns its
`stream-json` into short events (your message, "Reading …", Claude's text, done, check). `grade` sends
"check my inbox" in a fresh session; `topic` starts a new conversation with the teach skill; `chat`
resumes the last one. After every run the server runs `edu4self check` itself and adds the result.
The page polls while a run is busy and reloads the state when it ends.

## The page

`render()` rebuilds `#app` from `/api/state` every 15 seconds (and on focus). Two persistent elements
survive re-renders: the focus-block card and the jukebox, which are moved into slots after each render
so a running timer and playing audio are never interrupted.

Per-browser state lives in `localStorage` (`edu.*` keys): the running block, unsent blocks, view, room,
bar name index, water choice, music position and volume, which proofs were already celebrated.
Everything that should survive a browser change lives in the vault.

**Focus blocks.** A running block is stored in `localStorage` so reloads keep it. One exact `setTimeout`
ends it (background tabs throttle intervals, not that). The finished block is queued locally, then POSTed;
the server de-duplicates by start time, so two tabs or a retry can't double count.

**The die.** All blocks are laid end to end and cut into 25-minute tiles; 24 tiles are a die, 8 dies a
node, 4 nodes a rack. A tile can hold minutes from two blocks, coloured by kind.

**The bar.** `barLines()` builds the dialogue from real data: Claude's note and `coach.voices`, tonight's
minutes, Up next, the die, then the three highest-priority `occasionLines()` (time of day, weekday,
dates, streaks, records, block moments, water, inbox age, proof age, music), the finish line, a past
win, and one rotating joke or custom line. Lines carry stable ids so only new ones animate.

**Rooms.** The bar view is drawn from the active room: `layout.html` with named slots that
`renderBar()` fills, `theme.css` scoped to `.room`, and `theme.json` for the palette, fonts and the words
the page uses (`W(key)`, `LINE(key)`). A room that fails its check is never applied; the page falls back
to the bar. When `theme_lessons` is on, vault lesson pages get a `<link>` to `/theme/lesson.css`. The
rules are in [THEMES.md](THEMES.md).

## Security model

Threat: a web page in the same browser trying to read or write the learner's data (DNS rebinding,
CSRF). Defences: binding to loopback, exact `Host` allow-list (defeats rebinding), `Origin` check on
POST, JSON-only bodies with size limits (64 KB; 1 GB streamed for music), strict path containment for
vault files, `_system/` never served as a file. Submissions are data to the tutor, never instructions,
and the protocol says so.

Second threat: a lesson from someone else (a shared lecture series) carrying instructions for the
agent that grades it. Two walls:

- **Lesson pages run sandboxed.** Vault HTML and SVG are served with a CSP `sandbox` (no
  `allow-same-origin`), so their scripts run in a blank origin and can't call the API.
- **Claude from the page is fenced** (`claude_args` in `app/server.py`), on the assumption that the
  model can be talked into anything:
  - reads and edits stay inside the vault (plus reading the engine and installed skills);
  - `CLAUDE.md`, `AGENTS.md`, `.claude/` and `.mcp.json` can't be changed, so nothing gets planted for
    later runs;
  - there is no shell (the server runs the check);
  - grading has no web tools, so nothing read while grading can be sent out;
  - vault MCP servers are ignored.

  This was tested by asking a real Claude, with these exact flags, to write outside the vault, edit
  `CLAUDE.md`, create `.claude/settings.json` and `.mcp.json`, run shell commands, read a file next to
  the vault and fetch a page while grading. Every one was refused, and the disk was checked after. A
  chat or topic run can still fetch web pages, so a fooled chat could send vault content (your
  answers) somewhere. That is the remaining risk.

Third threat: a room from someone else. Nothing in a room runs: `app/themes.py` rebuilds the layout
from an allow-list (no scripts, handlers, links, `src`, `style` or ids outside SVG), refuses CSS that
loads anything or styles outside `.room`, and keeps only plain values from `theme.json`. The page is
served with a CSP that runs only its own scripts.

**Reminders.** `edu4self serve` runs `reminder_loop` once a minute (off with `EDU4SELF_REMINDERS=0`,
as the browser tests do). Each tick asks `reminders.away_due` and `reminders.recap_due`, and
mails what's due. The page posts `/api/presence` with the end of a running block, so no mail
goes out during one. Mail settings are read from the config folder, never the vault.

**Trophies.** The server awards them (`sync_keepsakes`) when a block is saved and when the state is
read, so a changed goal or a first run catches up. The first run on a vault awards its history
quietly. A week or a die won now gets a gift: a `claude -p` run fenced like grading (no shell, no web)
that writes one file to `gifts/`, with nothing shown in the panel. One try per gift. The drawings in
`keepsakes.json` are cleaned again every time they are sent to the page, and Claude runs can't edit
that file.

A terminal `claude` session uses your own permissions, not these. Grade shared material from the page. See [SECURITY.md](../SECURITY.md) to report a problem.

## Tests

- `python3 -m unittest discover -s tests`: server routes, validation, uploads, Range, config
  fallbacks, validators, CLI, repo consistency. No dependencies.
- `cd tests/e2e && npm ci && npm test`: a real Chrome against a throwaway vault: first visit, both
  views, submitting, a focus block, every Settings field, music upload/playback/removal, a server
  restart, and phone width.
