# edu4self

**A learning dashboard that runs on your computer, with Claude as your tutor. Hand it to your agent
and it sets itself up around you.**

You pick what to learn. Claude writes short lessons, tests what you know, and grades your answers.
The dashboard always shows one next step, keeps a record of what you've actually proven, and turns
your focused time into something you can see grow. Nothing leaves your machine.

[![A two-minute tour: install, first lesson, grading, Settings](docs/images/tour.gif)](docs/video/tour.mp4)

<sub>The first minute of the tour. [Watch all of it (2 min)](docs/video/tour.mp4).</sub>

## Hand it to your agent

Open Claude Code (or any coding agent) and paste:

```text
Clone https://github.com/chillax97/edu4self, read its AGENTS.md, and set it up for me.
```

Then say what you want in your own words. The agent asks what it's missing, installs everything,
turns your wishes into settings, checks its own work, and tells you how to start your first topic.
[AGENTS.md](AGENTS.md) is the playbook it follows.

A real run, word for word what was asked:

> Call me Kim. I'm learning Rust so I can contribute to a CLI tool by March. I study 45 minutes at a
> time, about 90 minutes a day, 5 days a week. No water reminders please. Call the bar 'The Borrow
> Checker' with the tagline 'nothing outlives its owner', and make the critic grumpier.

It came back with 45-minute blocks, a 90-minute goal over 5 days, water off, the new sign, and a critic
renamed "The curmudgeon" with lines of its own: *"unwrap() is not error handling. It is a confession."*
Then it ran `edu4self check` to prove the settings were valid.

Rather click than type? Everything the agent changed is also in **⚙ Settings** on the dashboard.

## How it works

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

- **One next step, always.** The Up next card says what to do. No planning, no deciding.
- **Proof, not time.** The evidence log lights up only when you demonstrate something, like an answer
  from memory or a solved problem. Reading doesn't count. This follows the research on retrieval
  practice ([why](docs/SPEC.md#principles)).
- **Focus blocks you can see.** Each focused 25 minutes etches a tile. 24 tiles make a die (10 hours),
  8 dies a node, 4 nodes a rack. A water reminder arrives every 15 minutes while a block runs, if you want one.
- **Two looks.** *Classic* is calm and plain. *The bar* is a dim room where your skills talk to you about
  tonight's work, a jukebox plays a built-in soundscape, a radio station or your own track, and the
  bartender slides you water.
- **Yours to change, no terminal needed.** Name, goals, block kinds, bar names, voices, your own jokes and
  the jukebox track are all in **⚙ Settings**.

<details>
<summary>Screenshots: the bar, classic view, the back room, Settings, phone</summary>

![The bar view: your skills talk, the jukebox plays, a focus block is running](docs/images/bar.png)

| classic | the back room |
|---|---|
| ![Classic view](docs/images/classic.png) | ![The back room: cluster, milestones, evidence, skills](docs/images/backroom.png) |
| **Settings** | **phone** |
| ![Settings panel](docs/images/settings.png) | ![The bar on a phone](docs/images/phone.png) |

</details>

## Set it up yourself

You need **Python 3.9+** (macOS and most Linux have it), **[Claude Code](https://claude.com/claude-code)**, and git.

```sh
git clone https://github.com/chillax97/edu4self.git
cd edu4self
./edu4self setup
```

`setup` asks where to put your learning vault (default `~/learn`) and what to call you. Then it starts
the dashboard at login and opens <http://127.0.0.1:4747>. After that, give Claude the tutor skills (once):

```sh
claude plugin marketplace add chillax97/edu4self
claude plugin install edu4self@edu4self     # also installs Matt Pocock's teach skill
```

Then work from your vault:

Then it's all on the dashboard: **+ New topic** starts one (say what and why, Claude asks a few
questions in the side panel), **✦ Grade** grades what you submitted, and **✦ Claude** opens a chat with
your tutor. The page runs Claude Code on your computer, with your own login. A terminal still works too:

```sh
cd ~/learn && claude
> /teach Spanish for a move to Madrid     # start a topic
> check my inbox                          # after you submit something on the dashboard
```

A small example topic ("How learning works") is ready on day one, so you can try the whole loop in
15 minutes. Delete it whenever you like: tell Claude "remove the example topic".

<details>
<summary>Windows, or you don't want a login service</summary>

Run `python3 edu4self setup --no-service`, then keep `python3 edu4self serve` running in a terminal
while you study. Starting at login is automated on macOS (launchd) and Linux (systemd user services).
</details>

## Everyday commands

| command | what it does |
|---|---|
| `./edu4self setup` | first-time setup: make a vault, start at login, open the dashboard |
| `./edu4self serve [--open]` | run the dashboard in this terminal instead of as a service |
| `./edu4self install` / `uninstall` | start at login / stop doing that (your files stay) |
| `./edu4self restart` / `status` | restart the service / show what's running |
| `./edu4self check` | validate the vault (Claude runs this after every update) |
| `./edu4self doctor` | check everything and say how to fix what's wrong |

Update with `git pull` and `./edu4self restart`. The code and your data live in different folders,
so updating never touches your vault.

## What's where

```
edu4self/               the code (this repo)            ~/learn/                your vault (yours)
  app/server.py           local web server                CLAUDE.md, AGENTS.md    instructions for the tutor
  app/dashboard/          the page (no build step)        _system/state.json      what the dashboard shows (Claude writes)
  edu4self                the command line                _system/inbox.jsonl     your submissions
  template/               what a new vault starts as      _system/blocks.jsonl    your focus blocks
  plugin/                 Claude Code skills              _system/config.json     your Settings
  docs/                   spec, protocol, customizing     _system/music/          your jukebox track
                                                          <topic>/                lessons, probes, records
```

The vault is plain files. It opens in [Obsidian](https://obsidian.md) as is (turn on "Open notes in
Obsidian" in Settings), and works with git if you want history.

## Documentation

- [AGENTS.md](AGENTS.md): what an agent does when you hand it this repo
- [Product spec](docs/SPEC.md): who it's for, what it does, why it's built this way
- [Customizing](docs/CUSTOMIZING.md): every setting, in the panel and in `config.json`
- [The Claude protocol](docs/PROTOCOL.md): the contract between the dashboard and the tutor
- [Architecture](docs/ARCHITECTURE.md): files, API, data flow, security model
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md)

## Privacy

The server binds to `127.0.0.1` only and refuses requests from other sites. The page loads nothing from
the internet (fonts are bundled), with one exception you choose: if you pick a radio station for the
jukebox, the page connects to that station while it plays. Your submissions, blocks, settings and music stay in your vault. Claude
reads your inbox only when you ask it to, through Claude Code, under Anthropic's terms.

## Credits

edu4self stands on other people's work: Matt Pocock's `teach` skill, Claude Code, four open-source
typefaces, and decades of learning research. The bar view's dialogue is inspired by *Disco Elysium*.
Full list with licenses: [CREDITS.md](CREDITS.md).

## License

[MIT](LICENSE). Bundled fonts are under the SIL Open Font License 1.1 (see [CREDITS.md](CREDITS.md)).
