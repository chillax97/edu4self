---
tags: [home, index]
---

# Your learning vault

**Dashboard → <http://127.0.0.1:{{PORT}}>**

## How the loop works
1. The dashboard's **Up next** card says what to do.
2. Do it, then press **Submit answers** on the card.
3. Press **✦ Grade** at the top of the dashboard. (Or, in Claude Code from this folder, say **"check my inbox"**.)
4. Claude grades it and updates the dashboard.

## Topics
Each topic is a folder here with a `MISSION.md`, `lessons/`, `probes/`, `reference/`,
`learning-records/` and a `Dashboard.md` log. Start a new one with `/teach <what you want to learn>`.

## Your data
Everything in `_system/` is yours and stays on this computer: `state.json` (written by Claude),
`inbox.jsonl` and `blocks.jsonl` (written by the dashboard), `config.json` (your Settings) and
`music/` (your jukebox track).
