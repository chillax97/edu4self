# edu4self plugin

The tutor side of [edu4self](https://github.com/chillax97/edu4self), a local learning dashboard where
Claude Code is your tutor. You study in the dashboard; this plugin gives Claude the skills to teach you.

**It needs the edu4self dashboard.** On its own the plugin has nothing to read or grade. Set up the
dashboard first by following the [main README](https://github.com/chillax97/edu4self#readme).

## Skills

| skill | what it does |
|---|---|
| `new-topic` | starts a new topic: asks what you want to learn, writes the plan and the first lesson |
| `write-lesson` | writes one lesson in the dashboard's format |
| `write-probe` | writes a short check of what you remember |
| `check-inbox` | grades what you submitted in the dashboard and plans the next step |
| `customize` | changes dashboard settings and rooms for you |

You rarely call them by name. Say "I want to learn Spanish", press **+ New topic** in the dashboard, or
ask Claude to "check my inbox".

## Install

```
claude plugin marketplace add chillax97/edu4self
claude plugin install edu4self@edu4self
```

## Privacy

The skills read and write files only in your own edu4self folder, and talk only to the dashboard on your
computer (`127.0.0.1`). Nothing is sent to an outside service, and there is no edu4self server.
Full details: [Privacy](https://github.com/chillax97/edu4self#privacy).

MIT licensed. See [CREDITS](https://github.com/chillax97/edu4self/blob/main/CREDITS.md) for the work it builds on.
