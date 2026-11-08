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
| Default look | `view` | `"bar"` (your room) or `"classic"` | `"bar"` |
| Room | `theme` | `bar`, `library`, `space`, `train`, `tea`, or a room in `<vault>/themes/` | `"bar"` |
| Lessons wear the room's look | `theme_lessons` | `true` / `false` | `true` |
| Room sounds (small sounds with the room's motion) | `room_sounds` | `true` / `false` | `false` |
| Gifts from Claude for a week or a die (each is a run on your Claude plan) | `gifts` | `true` / `false` | not set: setup or the dashboard asks you once |
| Mail me when I've been away | `reminders.mail` | `true` / `false` (needs `./edu4self mail setup`) | `true` |
| Focused minutes a day | `goals.day_minutes` | 10–960 | 120 |
| Days a week | `goals.week_days` | 1–7 | 4 |
| Durations | `blocks.presets` | 1–4 numbers, each 1–240 | `[25, 50, 90]` |
| Kinds of block | `blocks.kinds` | 1–8 kinds, see below | Lessons, Practice, Reading, Free, Play |
| Water | `water.every` | 15, 30 or 0 (off) | 15 |
| Music | `music` | see below | the Night shift soundscape, paused |
| Names on the neon sign | `bar.names` | 1–20 `[name, subtitle]` pairs; the subtitle is a string, or a list of up to 20 strings (each at most 80 characters) that rotates, see below; the bar only, other rooms bring their own | five names |
| Room jokes | `bar.gags` | `true` / `false` | `true` |
| Your own lines | `bar.lines` | up to 100 `{voice, text}` | none |
| Voices | `bar.voices` | per voice: `{name?, color?}` | see below |
| Open notes in Obsidian | `obsidian.enabled`, `obsidian.vault` | `true`/`false`, vault name | off |

The look (bar or classic) and the water setting are also remembered per browser once you switch them
on the page itself. **Reset to defaults** in Settings clears both, and keeps your songs.

### Rotating subtitles on the sign

A name's subtitle may be a list. The sign shows one entry at a time and moves to the next each time
the neon blinks (twice every 7 seconds), swapping while the sign is dim. It holds still while a focus
block is running. With reduced motion the neon doesn't flicker, so the entry moves every 30 seconds.

```json
"bar": { "names": [["The Night Shift", ["line one", "line two", "line three"]], ["Cache Miss", "a plain string still works"]] }
```

In Settings, put one subtitle per line; extra lines for the same name start with `|`:

```
The Night Shift | line one
| line two
| line three
```

One line is saved as a string, several as a list.

### Rooms

A room sets the layout, colours, the names of things, the voices, the jokes and the default sound.
Your own voices and lines (below) still win over the room's. With `theme_lessons` on, lesson
pages take the room's colours too; off, they keep the plain default look.

To make a room, or change a built-in one, see [THEMES.md](THEMES.md). A room in `<vault>/themes/` with
a built-in's id replaces it. If the chosen room is broken or missing, the bar shows instead and
`./edu4self check` says why.

### Trophies

Nothing to set: they follow your goals. A day that reaches **Focused minutes a day** adds a trophy
to a pile on your shelf, a week with blocks on **Days a week** days adds a week trophy, and every 10
focused hours finishes a die. Weeks and dice have a card to print, and, if you said yes to gifts
and Claude Code is installed, a gift Claude makes for you. Until you answer, a won gift waits. They're stored in `_system/keepsakes.json`; delete that file and they
are awarded again from your blocks, in the room you're in now.

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

- **Soundscape** (the default): *Night shift* (lo-fi electric piano, soft bass, brushes), *Rain on the window* (slow piano over soft rain), or *Brown
  noise*. Made live in your browser with the Web Audio API, so there is nothing to download and it works
  offline. Switch between them with the buttons on the jukebox itself.
- **Radio**: a Radio Paradise channel (Mellow, Serenity, Main mix, Global), or any station by its stream
  address (an `http://` or `https://` URL that a browser can play, usually ending in `.mp3`, `.aac` or a
  port). This is the only part of edu4self that uses the internet: while it plays, the page connects to
  that station.
- **Your songs**: **Add songs…** copies audio files you own into `_system/music/`: mp3, m4a/aac,
  ogg/oga, opus, wav, flac or webm audio, up to 1 GB each and 100 songs in all. Pick one file or several
  at once; each upload goes to the end of the list. A file with the same name as one already in the
  folder gets `-2`, `-3`, … so nothing is overwritten, and a file that isn't audio is refused. In the
  list you can rename a song, move it with ▲ / ▼ and take it off with ✕ (its file stays in
  `_system/music/`); **Save** keeps the order. The jukebox plays the songs in order and goes back to
  the first after the last; ⏮ prev and next ⏭ skip. One song alone plays on loop. It resumes the
  same song at the same spot, per browser. The scrubber, −1m / +1m and "random" choose where it plays.

```json
"music": {"source": "scape", "scape": "rain", "autoplay": false}
"music": {"source": "radio", "stream": {"url": "https://stream.radioparadise.com/mellow-128", "name": "Radio Paradise · Mellow"}}
"music": {"source": "file", "files": [{"file": "Night-Drive.m4a", "title": "Night Drive"}, {"file": "Rain.mp3", "title": "Rain"}],
          "subtitle": "three hours, no lyrics", "autoplay": true}
```

`source` is `scape`, `radio` or `file`; `scape` is `night`, `rain` or `noise`. Radio needs
`stream.url`. `files` is a list of up to 100 `{file, title}`; each file must already be in
`_system/music/` (upload it in Settings), and a blank `title` shows the file name without its extension.
`subtitle` is shown under every song. A config that names only one `file` (and its `title`), from before
lists existed, plays that file exactly as before, as a list of one; it is written in the new shape the
next time you save Settings. Saved configs also keep `file` and `title` set to the first song.

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

### Reminders and the Sunday recap

Reminders come by mail only. If you've been away (no block saved, no answer or note sent), you get
a short mail after 3, 7, 15 and 30 days, then once every 30 days. Each one says what you've done
so far (hours, what you proved, your shelf) and offers one small thing for today: your next task,
with a link, and the shortest block you have. Your next block or answer starts the count again.
Mails go out between 09:00 and 22:00, never while a block runs. If one can't be sent (a wrong
password, a locked Keychain, no network), the dashboard says so, with the reason, until you dismiss it.

Every Sunday from 19:00 (or the first time the dashboard runs before Monday ends) you get a recap of
the week: minutes, days, what you proved and what's next. It's saved to
`recaps/<year>-W<week>.md` in your vault, and mailed when mail is set up.

Mail uses your own account. Run `./edu4self mail setup`, give it an app password (not your main
password), and it sends a test mail before saving anything. The account lives in
`~/.config/edu4self/mail.json`, readable only by you and never inside the vault.

You choose where the app password is kept, and setup shows the risk of each:

| where | risk |
|---|---|
| in `mail.json` (default) | any program running as you can read it, and it's in backups of your home folder |
| the macOS Keychain | encrypted on disk, locked when you log out; any program running as you can still ask for it through `security`; mail waits while the Keychain is locked |
| your Linux desktop's password store (`secret-tool`, when installed) | encrypted on disk, locked when you log out; any program in your session can ask for it; without a desktop session mail fails |

None of them protects against a program already running as you. That's why it should be an app
password you can revoke, never your main one. `./edu4self mail off` removes it from wherever it is.
`./edu4self mail test` sends another test, `./edu4self mail off` deletes it.

### Obsidian

With **Open notes in Obsidian** on, `.md` links open in the Obsidian app (`obsidian://`), in the vault
named in Settings, or the vault folder's name by default. Off, they open as plain text in the browser.

## Changing the port

The port is chosen at `init` (default 4747) and stored in `~/.config/edu4self/settings.json`. To change
it, run `./edu4self install --port 4800` (it rewrites the login service), and update the port in your
vault's `CLAUDE.md`.

## Changing more than settings

The dashboard is three plain files in `app/dashboard/` (`index.html`, `app.js`, `app.css`) with no build
step: edit, reload. The bar's built-in lines live in `app.js` (`occasionLines`, `barLines`); each room's jokes and lines are in its `theme.json`.
See [ARCHITECTURE.md](ARCHITECTURE.md) before larger changes, and [CONTRIBUTING.md](../CONTRIBUTING.md)
if you'd like to send them upstream.
