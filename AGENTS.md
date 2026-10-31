# edu4self, for agents

edu4self is a local learning dashboard where a coding agent is the tutor. It's built to be handed to
you: a person clones this repo, opens you in it, and says what they want. Your job is one of two
branches. Pick it from the request:

- **Set it up and make it theirs** (most requests: "set this up for me", "I'm learning X", "make the
  bar called Y", "shorter blocks"). Follow *Setting up for a person*. You change files in their
  **vault**, never in this repo.
- **Change how edu4self works** (a bug, a feature, a new setting). Follow *Changing the engine*.

Two folders, never mixed: this repo is the **engine** (code, shared by everyone, updated with
`git pull`); the **vault** is the person's own data (default `~/learn`). Personal changes live in the
vault, so updates never overwrite them.

## Setting up for a person

1. **Gather their wishes.** Ask, in one short round, only what they haven't said: what to call them;
   what they want to learn and why (a goal with a date beats a subject); how they like to work (session
   length, minutes a day, days a week); the look (`bar`, a dim room with talking skills and a jukebox,
   or `classic`, calm and plain); whether the dashboard should start at login. Offer a sensible default
   for each so they can just say yes. Done when every wish is either answered or defaulted out loud.
2. **Install.** From this repo:

       ./edu4self setup --vault ~/learn --name "<name>"          # add --no-service to skip start-at-login

   It makes the vault (with a small example topic), starts the dashboard, and prints the port. Then
   give the tutor its skills (Claude Code; other agents read the vault's `AGENTS.md` instead):

       claude plugin marketplace add chillax97/edu4self
       claude plugin install edu4self@edu4self

   Done when `./edu4self status` shows the server running. (With `--no-service`, start it yourself
   in the background: `./edu4self serve --vault <vault>`.)
3. **Apply the wishes** to `<vault>/_system/config.json`. Every key, range and default is in
   [docs/CUSTOMIZING.md](docs/CUSTOMIZING.md); read it before writing. Translate each wish into keys,
   for example "45-minute sessions" → `blocks.presets` and the kinds' `minutes`; "no water
   reminders" → `water.every: 0`; "name the bar after my cat" → `bar.names`; "a grumpier critic" →
   `bar.voices.critic.name` plus a few `bar.lines` in that voice.
   - **Write the whole config.** Missing top-level sections fall back to *defaults*, not to what's in
     the file now. Read the current file (or `GET /api/config` → `.config`), change it, write it all
     back. `POST /api/config` with `{"config": {...}}` does the same and answers 400 with the reason
     when a value is out of range.
   - **Music**: the person uploads a file they own in Settings → Music. Point them there; leave
     finding or downloading tracks to them.
4. **Verify.** Run `./edu4self check --vault <vault>`. Done when it ends with `config.json: OK` and
   exits 0, and `curl -s http://127.0.0.1:<port>/api/config` shows `"error": null` and their
   values.
5. **Hand over.** Tell them: the dashboard URL; that **⚙ Settings** changes all of this later without
   you; and the next move, which happens in the vault, where the tutor instructions live:

       cd <vault> && claude
       > /teach <what they want to learn>

   If they want to remove the example topic, that's a vault change too (its `AGENTS.md` says how).

## Changing the engine

Read [CONTRIBUTING.md](CONTRIBUTING.md) first (ground rules: no runtime dependencies, local only, one
writer per file), then [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the map. The contract with
the tutor is [docs/PROTOCOL.md](docs/PROTOCOL.md); keep `plugin/skills/check-inbox/PROTOCOL.md` an
exact copy.

Work test-first in a throwaway vault (`./edu4self init /tmp/x --name Dev --port 4800`), never in a
real one. Done when both suites pass:

    python3 -m unittest discover -s tests
    cd tests/e2e && npm ci && npm test

Commit each self-contained step on its own, subject tagged `[ADD]`, `[IMP]`, `[FIX]`, `[DOC]` or
`[TEST]`.
