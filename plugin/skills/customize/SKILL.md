---
name: customize
description: Change edu4self dashboard settings for the learner (name, daily goal, focus block kinds and durations, water reminders, bar names, bar voices and their lines, music, Obsidian). Use when the learner asks to change how the dashboard looks or behaves.
argument-hint: "What do you want to change?"
---

The learner wants to change: $ARGUMENTS

Settings live in the vault's `_system/config.json`. The dashboard's Settings panel (⚙ in the top bar,
or `http://127.0.0.1:<port>/#settings`) edits the same file, so first tell the learner they can do it
there. Then, if they want you to do it:

1. Read `_system/config.json` (it may hold only some keys; missing keys use the defaults).
2. Change only what was asked. The format and limits are below; values outside them make the server
   ignore the whole file and fall back to defaults.
   - `name` (≤ 60 chars), `view`: `"bar"` or `"classic"`
   - `goals`: `day_minutes` 10–960, `week_days` 1–7
   - `blocks.presets`: 1–4 durations, 1–240 min. `blocks.kinds`: 1–8 of `{id, label, color, minutes?}`;
     `id` is lowercase `[a-z][a-z0-9_-]{0,23}` and must stay the same for existing kinds (old blocks
     refer to it); `color` is `#rrggbb` or one of lesson, probe, checkpoint, reading, project, mock,
     coral, amber, green
   - `water.every`: 15, 30 or 0
   - `obsidian`: `{enabled, vault}`
   - `bar.names`: 1–20 of `[name, tagline]`; `bar.gags`: true/false; `bar.lines`: up to 100 of
     `{voice, text}`; `bar.voices`: `{voice_id: {name?, color?}}`. Voice ids: bartender, logic,
     volition, gpu, encyclopedia, physical, nostalgia, critic, regular, jukebox
   - `music`: `{file, title, subtitle, autoplay}`. `file` must already be in `_system/music/`; to add a
     track, the learner uploads it in Settings → Music. Never download or copy music for them.
3. Run the check command from the vault's `CLAUDE.md`, then `curl -s http://127.0.0.1:<port>/api/config`
   and confirm `"error": null`. The dashboard picks the change up within 15 seconds.
