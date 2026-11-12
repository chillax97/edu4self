# Contributing

Thanks for wanting to help. edu4self is deliberately small. Good contributions keep it that way.

## Ground rules

- **No new runtime dependencies.** Python standard library on the server, plain JavaScript and CSS on
  the page, no build step. Development-only tools (the browser tests) are fine.
- **Local-first.** Nothing may call the network at runtime or load third-party assets. The one exception is
  `./edu4self doctor` asking `api.github.com` for the newest release number (no data about the user is sent,
  2 s timeout, silent offline, off with `EDU4SELF_NO_UPDATE_CHECK=1`).
- **One writer per file.** `state.json` belongs to the tutor, the logs to the server, `config.json` to
  Settings. New data gets a clear owner.
- **Proof stays proof.** Nothing may let time spent, clicks or self-reports count as evidence.
- **An update never changes a saved setting.** Whatever is in a learner's `config.json` keeps its
  meaning after `git pull`: a new key gets its default only where nothing was saved, and a setting
  for a removed feature is dropped, never reinterpreted. `test_an_update_keeps_every_setting_the_learner_saved`
  guards this; extend it when you add a setting.
- **Product first.** A change to the engine is for everyone who uses edu4self, not for one person's
  setup. Personal taste (names, jokes, topics, goals) belongs in that person's vault config; engine
  defaults suit a stranger. See [AGENTS.md](AGENTS.md#product-first).
- **Keep both views.** A feature that shows data should work in classic and in the bar.

## Setup

```sh
git clone --depth 1 https://github.com/chillax97/edu4self.git && cd edu4self   # drop --depth 1 for the full history
./edu4self init /tmp/edu4self-dev --name Dev --port 4800
./edu4self serve --vault /tmp/edu4self-dev --port 4800 --open
```

Edit files in `app/`, reload the browser. The server needs a restart only for `server.py` changes.

## Tests

Run both suites before opening a pull request:

```sh
python3 -m unittest discover -s tests            # server, validators, CLI (no dependencies)
cd tests/e2e && npm ci && npm test               # a real Chrome; set CHROME_PATH if it isn't found
```

New behaviour needs a test that would fail without it. Bug fixes start with a test that reproduces the
bug. CI runs the unit tests on Python 3.10 and 3.13 on Linux and 3.9 and 3.13 on Windows, and the browser tests on Linux and Windows, for every push and pull request; the macOS unit tests (Python 3.9 and 3.13) run only for `v*` tags and manual runs.
While working, run only the changed test file; run the full suite before a push.

If you change how grading works (PROTOCOL.md section 1, the grade command in `app/server.py`, the
model), run the honesty test before and after and put both false-pass rates in the pull request:
[evals/grading/README.md](evals/grading/README.md).

If you change `docs/PROTOCOL.md`, copy it to `plugin/skills/check-inbox/PROTOCOL.md` (a test checks they
match). If you bump the version, change it in `app/server.py`, `plugin/.claude-plugin/plugin.json` and
`CHANGELOG.md` together (also checked).

## Releasing

1. Move the `## Unreleased` entries of `CHANGELOG.md` under a new `## X.Y.Z` heading with the date.
2. Set the same version in `app/server.py` (`VERSION`) and `plugin/.claude-plugin/plugin.json` (a test checks all three).
3. Run both test suites, then merge to `main` and wait for CI to pass on all jobs (the macOS jobs run for tags).
4. Tag `vX.Y.Z` and push the tag, then `gh release create vX.Y.Z --notes-file <the changelog section>`.
   `doctor` tells users about the newest *release*, so the release is what makes the update hint appear.

## Updating (for users)

`git pull && ./edu4self restart`, then `claude plugin marketplace update edu4self && claude plugin update edu4self@edu4self`
for the tutor skills. The README's [Updating](README.md#updating) section is the user-facing version; keep both in step.

## Style

Match the code around you: short functions, a comment where the *why* isn't obvious, no clever tricks.
User-facing text is plain and friendly, written for someone who isn't a programmer. Avoid trademarks in
the product (see the decisions in [docs/SPEC.md](docs/SPEC.md#10-decisions)).

## Pull requests

Small and focused. Describe what changed, why, and how you verified it (commands and what they printed;
screenshots for anything visual). Note anything you couldn't test.

## Reporting bugs and ideas

Use the issue templates. For a bug, `./edu4self doctor` output and your OS and browser help a lot.
Security problems go to [SECURITY.md](SECURITY.md), not to a public issue.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
