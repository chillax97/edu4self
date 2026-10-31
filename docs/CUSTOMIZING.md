# Customizing edu4self

Everything here can be changed in the dashboard: press **⚙ Settings** in the top bar, change what you
like, press **Save**. You never need a terminal for it. Settings are stored in your vault at
`_system/config.json`. You can also edit that file by hand, or ask Claude ("make my daily goal 90
minutes"; the `customize` skill knows the format).

If the file has a mistake, the dashboard keeps working with the defaults and Settings shows what's wrong.
Saving from Settings writes a fresh, valid file.

## What you can change

| in Settings | in `config.json` | values | default |
|---|---|---|---|
| Your name | `name` | up to 60 characters; empty = the name Claude has | `""` |
| Default look | `view` | `"bar"` or `"classic"` | `"bar"` |
| Focused minutes a day | `goals.day_minutes` | 10–960 | 120 |
| Days a week | `goals.week_days` | 1–7 | 4 |
| Durations | `blocks.presets` | 1–4 numbers, each 1–240 | `[25, 50, 90]` |
| Kinds of block | `blocks.kinds` | 1–8 kinds, see below | Lessons, Practice, Reading, Free, Play |
| Water | `water.every` | 15, 30 or 0 (off) | 15 |
| Music | `music` | see below | the Night shift soundscape, paused |
| Names on the neon sign | `bar.names` | 1–20 `[name, tagline]` pairs | five names |
| Bar jokes | `bar.gags` | `true` / `false` | `true` |
| Your own lines | `bar.lines` | up to 100 `{voice, text}` | none |
| Voices | `bar.voices` | per voice: `{name?, color?}` | see below |
| Open notes in Obsidian | `obsidian.enabled`, `obsidian.vault` | `true`/`false`, vault name | off |

The look (bar or classic) and the water setting are also remembered per browser once you switch them
on the page itself. **Reset to defaults** in Settings clears both, and keeps your music file.

### Kinds of block

Each kind is `{"id": "practice", "label": "Practice", "color": "mock", "minutes": 60}`.

- `id` is how your past blocks refer to the kind: lowercase letters, digits, `-` or `_`, up to 24
  characters. Settings makes one from the label for new kinds and never changes existing ones.
- `label` is what you see.
- `color` is `#rrggbb`, or a theme colour: `lesson`, `probe`, `checkpoint`, `reading`, `project`, `mock`,
  `coral`, `amber`, `green`. Theme colours adapt to dark mode.
- `minutes` (optional) is the duration picked when you choose this kind.

A topic in `state.json` can name the kind its "Start N min on this" button uses (`"block": "practice"`).
If you delete a kind, its old blocks stay on your die in a neutral colour, and topics that used it fall
back to the first kind.

### Music

The jukebox in the bar plays one of three things. Pick it in Settings → Music. Only one browser tab plays
at a time, and the classic view is silent.

- **Soundscape** (the default): *Night shift* (slow chords, tape hiss), *Rain on the window*, or *Brown
  noise*. Made live in your browser with the Web Audio API, so there is nothing to download and it works
  offline. Switch between them with the buttons on the jukebox itself.
- **Radio**: a Radio Paradise channel (Mellow, Serenity, Main mix, Global), or any station by its stream
  address (an `http://` or `https://` URL that a browser can play, usually ending in `.mp3`, `.aac` or a
  port). This is the only part of edu4self that uses the internet: while it plays, the page connects to
  that station.
- **Your own track**: **Choose an audio file…** copies a file you own (m4a, mp3, ogg, opus, wav, flac,
  aac, webm; up to 1 GB) into `_system/music/`. It plays on loop and resumes where it stopped, per
  browser. The scrubber, −1m / +1m and "random" choose where it plays.

```json
"music": {"source": "scape", "scape": "rain", "autoplay": false}
"music": {"source": "radio", "stream": {"url": "https://stream.radioparadise.com/mellow-128", "name": "Radio Paradise · Mellow"}}
"music": {"source": "file", "file": "Night-Drive.m4a", "title": "Night Drive", "subtitle": "three hours, no lyrics", "autoplay": true}
```

`source` is `scape`, `radio` or `file`; `scape` is `night`, `rain` or `noise`. Radio needs
`stream.url`; a file must already be in `_system/music/` (upload it in Settings). A config that names
only a `file`, from before sources existed, keeps playing that file.

Browsers block sound until you click on the page once; with `autoplay` on, the first click anywhere
starts it. A soundscape starts paused unless you turn `autoplay` on. edu4self ships no recorded music.
Please only upload files you have the right to play.

### Voices

The bar's characters, with their ids (used by Claude in `coach.voices` and by you in `bar.lines`):

| id | default name | talks about |
|---|---|---|
| `bartender` | The bartender | Claude's latest note, water, the inbox |
| `logic` | Logic | what's next, the plan |
| `volition` | Willpower | tonight's minutes, streaks, records |
| `gpu` | GPU whisperer | your die and cluster |
| `encyclopedia` | The archivist | the finish line, dates, totals |
| `physical` | The body | water, breaks, sleep |
| `nostalgia` | Nostalgia | a past win |
| `critic` | The critic | what's slipping |
| `regular` | The regular | bar gossip |
| `jukebox` | The jukebox | the music |

Rename any of them or change a colour:

```json
"bar": {"voices": {"volition": {"name": "Grit", "color": "#ff7ab6"}}}
```

### Your own lines

One per line in Settings, as `voice: text`. They join the bar jokes in the rotation (a new one every
40 minutes):

```
regular: The coffee machine has been broken since the last exam.
critic: Flashcards you never review are just stationery.
```

### Obsidian

With **Open notes in Obsidian** on, `.md` links open in the Obsidian app (`obsidian://`), in the vault
named in Settings, or the vault folder's name by default. Off, they open as plain text in the browser.

## Changing the port

The port is chosen at `init` (default 4747) and stored in `~/.config/edu4self/settings.json`. To change
it, run `./edu4self install --port 4800` (it rewrites the login service), and update the port in your
vault's `CLAUDE.md`.

## Changing more than settings

The dashboard is three plain files in `app/dashboard/` (`index.html`, `app.js`, `app.css`) with no build
step: edit, reload. The bar's built-in lines live in `app.js` (`occasionLines`, `FLAVOR`, `barLines`).
See [ARCHITECTURE.md](ARCHITECTURE.md) before larger changes, and [CONTRIBUTING.md](../CONTRIBUTING.md)
if you'd like to send them upstream.
