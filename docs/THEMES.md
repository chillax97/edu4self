# Rooms: making your own

A **room** is where you study in edu4self: the bar, the library, the space station, the night train, the
tea house, or one you make. It sets the layout, colours, fonts, the names of things, the characters'
voices, the jokes and the sound. Your goals, blocks, lessons and grades are the same in every room.
Pick one in **⚙ Settings → Room**.

This guide is for anyone making a room, and it is written so an agent can follow it. Ask Claude
"make me a room that feels like a lighthouse" and it should be able to finish with nothing but this file.

## The one rule: themed, but recognizable

Every object the learner sees should belong to the room, and still be understood at a glance.

- In the library, finished dies are bound **volumes** in **the bindery**. On the train they are **ticket
  books** you punch. Both read instantly. A "codex of accumulated attentional resonance" does not.
- Rename a thing only when the new word is obvious in its place. If the learner would need a legend to
  decode it, keep the plain word.
- **Core learning words never change:** Lesson 01, Submit answers, Grade, 25 min, dates, numbers and
  every button that does something. The engine enforces this: those words can't be renamed.
- Give each room its own fitting object for every visible thing, including new ones (the shelf for
  keepsakes, reminders, cards). A room that leaves the bar's jukebox standing in a library feels broken.
- Keep it light. The jokes are background: one short line, about studying, kind to the learner.

How the five built-ins map the same things:

| thing | bar | library | space station | night train | tea house |
|---|---|---|---|---|---|
| host | the bartender | the librarian | Station AI | the conductor | the tea master |
| music | the jukebox | the gramophone | comms | the radio car | the kettle |
| a die / a tile | die / tile | volume / page | core / cell | ticket book / punch | tin / leaf |
| where dies live | the die case | the bindery | reactor core | punches | the tea tin |
| sound | night | rain | noise | rain | rain |
| day trophy (stacks) | bottle cap | book | mission patch | ticket stub | tea bowl |
| week trophy | neon sign | brass bookend | medal | postcard | teapot |
| die trophy (stacks) | chip | volume | core | ticket book | tin |

## Making one, step by step

Each step ends with how you know it's done.

1. **Map the place.** Write down, for this place, the object that plays each part: the host, the music
   box, the die and its tiles, where finished dies are kept, the sign on the door, the water. Use the
   table above as the pattern. *Done when every row has a word a stranger would understand.*
2. **Copy the closest built-in.** Copy `app/dashboard/themes/<id>/` from the engine to
   `<vault>/themes/<new-id>/` (lowercase letters, digits and `-`, up to 32 characters). A dark place
   starts from `library` or `train`, a light one from `tea`. *Done when the folder has `theme.json`,
   `layout.html`, `theme.css` and `lesson.css`.* To change a built-in instead, give the copy the same id:
   a room in the vault replaces the built-in with that id.
3. **Write `theme.json`** (reference below): name, icon, one-line `about`, `dark`, palette, backdrop,
   fonts, the words from step 1, voices, three sign names, five to ten gags, and the lines.
4. **Make the trophies** (`keepsakes` in `theme.json`, reference below): one for a day that met the
   goal, one for a week, one for a finished die, plus the host's line for each and for a gift. They
   follow the same rule as everything else: a stranger knows what each one is, and each is a thing
   you could hold. Day and die trophies are drawn stacked, up to ten to a pile, so make them things
   that gather well (flat and wide for `pile`, a card or a ticket for `fan`, something small and loose
   for `heap`, something tall that stands up, like a book or a jar, for `row`).
   Trophies leave the room: they stay on the learner's shelf in every room they move to afterwards,
   so each drawing should look good on any background. *Done when all three drawings pass the check
   and a pile of ten of the day trophy reads as a pile, not a smear.*
5. **Draw `layout.html`.** Arrange the slots the way this place is arranged (a desk, a dashboard, a
   carriage) and add drawing around them: plain elements and inline SVG.
6. **Style it in `theme.css`.** Every selector starts with `.room`. Set the colour tokens first, then the
   place's own parts.
7. **Dress the lessons in `lesson.css`.** Same palette, paper or glass for the quiz box. Keep text
   contrast high: lessons are read for twenty minutes at a time.
8. **Prove it works.**
   - `./edu4self check` prints `themes/<id>: OK` and exits 0. If not, it lists each rule broken; fix
     and rerun.
     (From the dashboard's Claude panel there is no shell: the server runs this check after your
     reply and shows the result. Say so, and set the room anyway; a failing room falls back to the bar.)
   - Set `"theme": "<id>"` in `_system/config.json` (or pick it in Settings), open the dashboard, and
     look at it at full width and at phone width (390 px): every slot shows, nothing scrolls sideways,
     all text is readable against its background, the replies and the timer still click, and the
     shelf shows (with history, or after one block that meets a small daily goal).
   - Open a lesson: it wears the room, and the quiz is readable.

   *Done when all three hold.* A room that fails its check is listed in Settings with the reason and
   can't be picked; the page falls back to the bar, so nothing breaks while you work.

## Reference

### The files

| file | required | what it is |
|---|---|---|
| `theme.json` | yes | the data: names, colours, words, voices, jokes, sound |
| `layout.html` | yes | the room's markup, built around slots |
| `theme.css` | yes | the room's styles, scoped to `.room` |
| `lesson.css` | no | how lesson pages look in this room; Settings → "Lessons wear the room's look" turns it off |

Each file is at most 64 KB.

### Slots

A slot is an empty element with `data-slot="<name>"`. The engine fills it; anything you put inside is
replaced. Required slots appear exactly once; optional ones at most once. An empty slot is hidden.

| slot | required | what the engine puts there |
|---|---|---|
| `name` | yes | the sign: the room's name and tagline; clicking it cycles the names |
| `rooms` | yes | the tabs between the front room and the back room |
| `voices` | yes | the conversation: the host and the characters talking |
| `job` | yes | what to do now (the next task) |
| `replies` | yes | the numbered replies: start a block, open a lesson, submit |
| `block` | yes | the focus block controls |
| `music` | yes | the player |
| `tonight` | yes | today's minutes against the goal |
| `week` | yes | this week's days against the goal |
| `die` | yes | the die being filled and the finished ones |
| `timer` | no | the running block's countdown |
| `finish` | no | how far the topic is and when it ends |
| `doors` | no | tasks that are still locked |
| `clock` | no | the time, or the block's time left |
| `sign` | no | the open / busy sign |
| `water` | no | the water glass |
| `keys` | no | the keyboard hint |
| `shelf` | no | the learner's trophies; without it they are only in the back room |

The engine's own markup inside slots uses `bx-*` classes (`.bx-neon` for the sign, `.bx-replies`,
`.bx-log`, `.bx-k` for small labels, `.bx-cab` for the die). Restyle them under `.room`.

### theme.json

```json
{
  "name": "The library", "icon": "📚", "dark": true, "scape": "rain",
  "about": "A reading room after hours. Finished dies stand on the shelf.",
  "palette": { "bg": "#0d140f", "surface": "#14201a", "ink": "#f3e6c4", "muted": "#b8a888", "line": "#2f4536", "accent": "#d8b26a" },
  "backdrop": "radial-gradient(ellipse 40% 45% at 50% 30%, rgba(255,214,140,.12), transparent 70%), #0b120d",
  "fonts": { "head": "serif", "body": "serif", "sign": "serif" },
  "words": { "host": "The librarian", "music_box": "The gramophone", "die": "volume", "dies": "volumes" },
  "voices": { "bartender": { "name": "The librarian", "color": "#f3e6c4" } },
  "names": [["The Reading Room", "silence is a study method"]],
  "gags": [["regular", "A card in the catalogue reads: SEE ALSO: sleep."]],
  "lines": { "evening": "Evening. The library fills up around now." }
}
```

- **palette** keys: `bg`, `bg2`, `surface`, `surface2`, `ink`, `ink2`, `muted`, `line`, `line2`,
  `accent`, `accent2`, `accent_ink`. Values are `#hex` or `rgb()`/`rgba()`. They colour the whole page,
  top bar included. Set `"dark": false` for a light room.
- **backdrop**: a CSS background made of colours and gradients only.
- **fonts** (`head`, `body`, `sign`): one of `sans`, `serif`, `mono`, `head` (condensed), `neon`. Only
  the bundled fonts can be used.
- **scape**: the default soundscape, `night`, `rain` or `noise`.
- **words** a room may rename, with the bar's defaults: `front` "The bar", `front_icon`, `back` "The
  back room", `back_icon`, `view` "Bar view", `place`, `counter`, `host`, `music_box`, `tonight`, `week`,
  `nights`, `die_case`, `die`, `dies`, `tile`, `tiles`, `shipped`, `doors`, `job`, `note`, `how`,
  `back_q`, `glass`, `glasses`, `sign_open`, `sign_busy`. Anything else is refused.
- **voices**: rename or recolour a character by id: `bartender` (the host), `logic`, `volition`, `gpu`,
  `encyclopedia`, `physical`, `nostalgia`, `critic`, `regular`, `jukebox` (the music box), `you`. The
  learner's own voice settings still win.
- **names**: `[name, tagline]` pairs for the sign.
- **gags**: `[voice, text]` jokes, one every 40 minutes when jokes are on.
- **lines**: the room's own words for `play`, `evening`, `friday`, `silent` (`{days}` is replaced with
  the number), `newyear`, `nye`, `halloween`, `valentine`, `music_quiet`, `music_none`.

### keepsakes (trophies)

```json
"keepsakes": {
  "day":  { "name": "bottle cap", "plural": "bottle caps", "stack": "pile", "stamp": "bottled",
            "art": "<svg viewBox='0 0 40 12'><path d='M3 3 H37 L35 10 H5 Z' fill='#c0392b'/></svg>" },
  "week": { "name": "neon sign", "art": "<svg viewBox='0 0 56 44'>…</svg>" },
  "die":  { "name": "die", "plural": "dice", "art": "<svg viewBox='0 0 48 48'>…</svg>" },
  "lines": { "day": "Another cap for the jar.", "week": "…", "die": "…", "gift": "The bartender slid something across the counter." }
}
```

- **art**: one `<svg>` with a `viewBox`, shapes only (`path`, `rect`, `circle`, `ellipse`, `line`,
  `polygon`, `polyline`, `g`), up to 4 KB. No text, no `id`, no `url(#…)`: the drawing is copied into
  the learner's vault and drawn many times next to other rooms' trophies, so it must stand alone.
  Plain fills and strokes only.
- **stack** (day and die; weeks stand alone): `pile` straight up, `fan` fanned out like cards, `heap`
  tossed in a mound, `row` standing side by side like books on a shelf. Drawn 40 px wide in a pile,
  34 px in a fan, 26 px in a heap, 50 px tall in a row. A tall drawing set to `pile` stands in a row.
- **stamp**: the word printed with the date on a trophy's card when the learner clicks it, like the
  date stamped on a bottle cap: "bottled 3 Nov 2026", "checked out", "punched". Up to 18 characters;
  leave it out for "earned". It's kept with the trophy, so a cap from the bar keeps its word in the library.
- **lines**: what the host says when a trophy is won today, and when Claude's gift is ready.
- Leave `keepsakes` out and the room gets plain ones (a star, a ribbon, a die). A drawing that fails
  the check is named by `edu4self check` and replaced by the plain one until fixed.
- Restyle the shelf in `theme.css`: set `--ks-wood` on `.room` for the plank colour, and style
  `.room .ks-sum` for the count line.

What happens to them: the server awards trophies as blocks are saved (`_system/keepsakes.json`); a
week or a die won now also gets a gift, a page Claude makes from what the learner proved; every week
and die has a printable card at `/card?id=…`, in the colours of the room it was won in, and the card
links the gift. Clicking any trophy on the shelf, days too, opens a small card: the drawing, its
stamped date, what it stands for, the numbers behind it, arrows to the others of its kind (piles
overlap, so not every one can be clicked), and for weeks and dice the printable card.

### layout.html

Allowed: `div span section article aside header footer main nav p h1–h6 ul ol li figure figcaption b i
em strong small br hr kbd s u sup sub`, and inline SVG (shapes, `g`, `text`, gradients, patterns,
masks, simple filters). Attributes: `class`, `data-slot`, `data-part`, `aria-hidden`, `aria-label`, `role`, `title`, and
SVG's drawing attributes. Inside SVG, `id` is allowed when it starts with `t-`, and `url(#t-…)` may
refer to it.

### theme.css

Every selector starts with `.room`; `@media`, `@supports`, `@container` and `@keyframes` are fine. The
room sets these colour tokens on `.room`, and the engine's markup uses them:

`--bx-line`, `--bx-line2` (borders), `--bx-k` (small labels), `--bx-text`, `--bx-dim`, `--bx-faint`,
`--bx-bright`, `--bx-soft`, `--bx-label` (text, strongest to softest), `--bx-edge`, `--bx-panel`,
`--bx-frame`, `--bx-music-bg` (surfaces), `--bx-sign` (the sign's font).

### lesson.css

Styles the whole lesson page (no `.room` needed). Lessons read these variables, so setting them on
`:root` does most of the work: `--ink`, `--ink-soft`, `--faint`, `--rule`, `--bg`, `--panel`,
`--accent`, `--good`, `--bad`, `--code`. The quiz is `.quiz` with `.prompt`, `button.opt`,
`textarea`, `.verdict.ok`, `.verdict.no` and `.explain`.

## What a room can't do

A room may be written by an AI or copied in from anywhere, so nothing in it runs or reaches outside.
The server rebuilds the layout from the allow-list above and refuses:

- scripts, event handlers (`on…`), links, `src`, `style` attributes, `id` outside SVG, other `data-*`
  attributes, forms, frames;
- CSS that loads anything (`@import`, `@font-face`, `url()` other than `data:image`), or styles outside
  `.room` in `theme.css`;
- anything in `theme.json` but plain values from the lists above.

The page's Content-Security-Policy runs only the engine's own scripts, as a second wall. If your room
needs something these rules don't allow, keep the plain version; don't work around them.
