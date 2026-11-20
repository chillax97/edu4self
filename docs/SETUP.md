# Setting up edu4self

The [README](../README.md) has the short version. This page has the rest: what you need, every setup
option, Windows, the everyday commands and where your files live.

## What you need

- **Claude Code**, signed in with a Claude plan that includes it. Claude is the tutor, so nothing works
  without it.
- **macOS, Linux or Windows.** All three can start the dashboard for you at login (launchd, systemd, Task
  Scheduler). Windows notes are [below](#windows).
- **Python 3.9 or newer**, and git. macOS and most Linux systems already have Python; on Windows install it
  from python.org. On a Mac that has never used them, the first `git` or `python3` offers to install Apple's
  Command Line Tools: say yes, it takes a few minutes.

**What it costs.** edu4self is free. Grading runs Claude Code, so it uses your Claude usage. On a Pro or Max
plan that counts against your plan's limits, with no extra bill. With an API key, each grading run is billed
by Anthropic.

## Let your agent set it up

Open Claude Code (or any coding agent) and paste:

```text
Clone https://github.com/chillax97/edu4self (git clone --depth 1), read its AGENTS.md, and set it up for me.
```

Then say what you want in your own words, for example:

> Call me Kim. I'm learning Rust so I can contribute to a CLI tool by March. I study 45 minutes at a time,
> about 90 minutes a day, 5 days a week. No water reminders please.

The agent asks what it's missing, installs everything, turns your wishes into settings, checks its own work,
and tells you how to start your first topic. [AGENTS.md](../AGENTS.md) is the playbook it follows.

## Set it up yourself

```sh
cd ~                     # your home folder: macOS may keep the login service out of Documents, Desktop and Downloads
git clone --depth 1 https://github.com/chillax97/edu4self.git
cd edu4self
./edu4self setup         # on Windows: python edu4self setup
```

`setup` asks where to put your learning vault (default `~/learn`) and what to call you, and offers to give
Claude the tutor skills (the edu4self plugin). Then it starts the dashboard at login and opens
<http://127.0.0.1:4747>. It installs the plugin by running these two commands for you, and checks that it
worked. If it couldn't (or you said no, or passed `--no-plugin`), run them yourself once:

```sh
claude plugin marketplace add chillax97/edu4self
claude plugin install edu4self@edu4self
```

`./edu4self doctor` tells you whether the plugin is installed and enabled, and whether Claude Code is signed
in. `./edu4self setup --help` lists every option (port, vault folder, name, no example topic, no login
service, no browser, no plugin).

### Your first topic

The first time you open the dashboard it asks you to try the method once, in about two minutes: one idea,
hidden, answered from memory, checked, and graded by Claude if you like. Then you pick your own topic or the
example one ("How learning works"), which runs the whole loop in 15 minutes. To remove the example later,
tell Claude "remove the example topic".

On the dashboard, **+ New topic** starts a topic (say what and why; Claude asks a few questions in the side
panel), **✦ Grade** grades what you submitted, and **✦ Claude** opens a chat with your tutor. The page runs
Claude Code on your computer, with your own login. A terminal works too:

```sh
cd ~/learn && claude
> I want to learn Spanish for a move to Madrid   # start a topic (or /edu4self:new-topic)
> check my inbox                                 # after you submit something on the dashboard
```

### Without a login service

Run `./edu4self setup --no-service`, then keep `./edu4self serve` running in a terminal while you study.

## Windows

Use `python edu4self ...` wherever these pages say `./edu4self` (for example `python edu4self setup`), in
PowerShell or Command Prompt. `setup` and `install` add a Task Scheduler task named `edu4self` that starts
the dashboard when you log on; `uninstall` removes it.

- The Claude panel works with Claude Code from Anthropic's installer (`claude.exe`) or from npm
  (`npm i -g @anthropic-ai/claude-code`). If the dashboard can't find it, `python edu4self doctor` says why
  and what to do.
- A mail app password is kept in a file in your user folder. Use an app password, not your real one.
- The test suites run on Windows in CI. The logon task is the newest part: if the dashboard doesn't start
  when you log on, run `python edu4self doctor` and open an issue.

## Everyday commands

On Windows, write `python edu4self` for `./edu4self`.

| command | what it does |
|---|---|
| `./edu4self setup` | first-time setup: make a vault, start at login, open the dashboard |
| `./edu4self open` | open the dashboard in your browser |
| `./edu4self serve [--open]` | run the dashboard in this terminal instead of as a service |
| `./edu4self install` / `uninstall` | start at login / stop doing that (your files stay) |
| `./edu4self restart` / `status` | restart the service / show what's running |
| `./edu4self check` | validate the vault (Claude runs this after every update) |
| `./edu4self doctor` | check everything and say how to fix what's wrong |
| `./edu4self mail setup` | a mail when you've been away, and the Sunday recap, from your own account |
| `./edu4self mcp` | your progress for any AI tool that speaks MCP ([how](MCP.md)) |

## How the loop works

```
   ┌──────────────┐  1. Up next: open the lesson,     ┌──────────────┐
   │  dashboard   │     do it, press Submit           │   inbox      │
   │  (browser)   │ ────────────────────────────────▶ │ (a file in   │
   │              │                                   │  your vault) │
   │              │  3. the page updates itself       └──────┬───────┘
   │              │ ◀──────────────┐                         │ 2. press ✦ Grade
   └──────────────┘                │                         │    (Claude Code runs it)
                            ┌──────┴───────┐                 │
                            │  state.json  │ ◀───────────────┘
                            │ (written by  │   Claude grades it, writes down what
                            │  Claude only)│   you proved, and lines up what's next
                            └──────────────┘
```

The dashboard never grades. Claude Code reads the inbox, grades each answer against the key it wrote with
the lesson, and writes the result. The contract between the two is [PROTOCOL.md](PROTOCOL.md).

## What's where

```
edu4self/               the code (this repo)            ~/learn/                your vault (yours)
  app/server.py           local web server                CLAUDE.md, AGENTS.md    instructions for the tutor
                                                          PLAN.md                 what comes next, in order (Claude keeps it)
  app/dashboard/          the page (no build step)        _system/state.json      what the dashboard shows (Claude writes)
  edu4self                the command line                _system/inbox.jsonl     your submissions
  template/               what a new vault starts as      _system/blocks.jsonl    your focus blocks
  plugin/                 Claude Code skills              _system/config.json     your Settings
  docs/                   protocol, customizing, rooms    _system/music/          your jukebox track
                                                          themes/                 rooms you made
                                                          gifts/                  what Claude made you
                                                          _system/keepsakes.json  your trophies
                                                          _system/keys/           answer keys (Claude writes)
                                                          <topic>/                lessons, probes, records
```

The vault is plain files. It opens in [Obsidian](https://obsidian.md) as is (turn on "Open notes in
Obsidian" in Settings), and works with git if you want history.

## Updating

See [Updating](../README.md#updating) in the README. `./edu4self doctor` tells you when you are behind and
prints the two commands to run.
