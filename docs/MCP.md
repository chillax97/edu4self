# Your progress in any AI tool (MCP)

edu4self speaks MCP, the protocol AI tools use to plug in outside data. Connect it once, and the AI
tool you already use (Claude, Codex, Cursor and others) can see where you are: your topics, your next
task and its rules, what you've proven, what's waiting to be graded. When you ask it to, it can leave your tutor a note.

It can't hand in answers, grade, or change anything else. Proof is something you do yourself, in the
dashboard. Each task carries your rules ("closed book", "no AI"), and the tool is told to respect them.

The dashboard has to be running (it is, if you ran `./edu4self install`). The MCP server reads it over
`http://127.0.0.1:<port>` and sends nothing anywhere itself.

**What leaves your computer.** Whatever the AI tool reads through these tools becomes part of your
chat, and the tool sends it to its own model under its own terms. That's true for every tool,
Claude included: Claude Code and Claude Desktop send it to Anthropic, Codex to OpenAI, Cursor to
whichever model you picked. It's your progress (topics, task titles and rules, what you proved, focused
time), not your answers or your files. The server asks each tool to tell you this, in one line, the
first time it reads your progress in a conversation.

## Connect it

Use the full path to your `edu4self` folder. If your dashboard isn't on port 4747, add
`"--port", "<port>"` after `"mcp"`.

**Claude Code**

```sh
claude mcp add edu4self -- /path/to/edu4self/edu4self mcp
```

**Codex CLI** (`~/.codex/config.toml`)

```toml
[mcp_servers.edu4self]
command = "/path/to/edu4self/edu4self"
args = ["mcp"]
```

Codex asks before running a tool that writes. `leave_note` is the only one.

**Cursor** (`~/.cursor/mcp.json`), **Claude Desktop** (`claude_desktop_config.json`), and other tools
that read an `mcpServers` file:

```json
{ "mcpServers": { "edu4self": { "command": "/path/to/edu4self/edu4self", "args": ["mcp"] } } }
```

Then ask your tool something like "what's my next edu4self task?".

## The tools

| tool | what it gives back |
|---|---|
| `get_progress` | each topic's milestone and next task, minutes today and days this week against your goals, total hours, trophies, the answers waiting to be graded |
| `get_next_task` | the next tasks in a topic (or all): why, rules, effort, the dashboard link |
| `get_proven` | what you've proven, newest first |
| `leave_note` | sends your tutor a note through the dashboard's inbox, marked with the tool's name |

Tested with Claude Code and Codex CLI. Cursor and Claude Desktop use the same standard setup but
haven't been tried here; if one doesn't work, open an issue.
