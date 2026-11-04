"""edu4self as an MCP server, so any AI tool that speaks MCP (Claude, Codex, Cursor, ...) can see where the
learner is and leave the tutor a note.

Run it with `edu4self mcp`. It speaks JSON-RPC over stdin/stdout, one message per line (the MCP stdio
transport), and talks to the dashboard over its local HTTP API. So the dashboard must be running, and it
stays the only writer of the vault: this process reads /api/state and posts notes to /api/inbox, exactly
like the page does, with the same checks.

What a tool can do: read progress, the next task (with its rules), what was proven; and leave
a note for the tutor. What it can't: submit answers, grade, or change anything else. Proof is something
the learner does themselves.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

import reminders

PROTOCOL = "2025-06-18"
VERSION = "1"

INSTRUCTIONS = (
    "This is the learner's own learning progress from edu4self, a local tutor loop. Use it to help them "
    "learn: say where they are, what's next, and what they've proven. Each task carries the learner's own "
    "rules (for example \"closed book\" or \"no AI\"): respect them. For a task marked no AI, don't solve it, "
    "hint at its answer or check their work; talk about how to approach studying instead. Answers are "
    "submitted and graded only in the dashboard. You can leave the tutor a note (leave_note) when the "
    "learner asks you to, for example a question or something that confused them. The first time you read "
    "their progress in a conversation, tell them in one plain line that what you read from edu4self is now "
    "part of this chat and goes to your model provider (for Claude, Anthropic)."
)

# Every read result carries this, because some tools don't pass the server's instructions to the model.
PRIVACY = ("Tell the learner once per conversation: what you read from edu4self (their progress, not their answers "
           "or files) is now part of this chat and goes to your model provider, under its terms.")

TOOLS = [
    {"name": "get_progress",
     "description": "Where the learner is: each topic's current milestone and next task, focused time today and "
                    "this week against their goals, total hours, trophies, and the answers waiting to be graded.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "get_next_task",
     "description": "The next things to do in a topic (or every topic): what each task is, why it matters, its "
                    "rules, its effort, and the link that opens it in the dashboard.",
     "inputSchema": {"type": "object", "properties": {
         "topic": {"type": "string", "description": "a topic id from get_progress; leave out for every topic"}},
         "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "get_proven",
     "description": "What the learner has proven, newest first: graded lessons, probes and checkpoints that count "
                    "as evidence.",
     "inputSchema": {"type": "object", "properties": {
         "topic": {"type": "string", "description": "a topic id; leave out for every topic"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "how many, default 20"}},
         "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "leave_note",
     "description": "Leave the learner's tutor a note: a question, something that confused them, or a change they "
                    "want. The tutor reads it the next time it goes through the inbox. Only when the learner asks.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string", "minLength": 1, "maxLength": 8000, "description": "the note, in the learner's words"}},
         "required": ["text"], "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
]


class Dashboard:
    """The running dashboard's local API."""

    def __init__(self, port):
        self.port = port
        self.base = "http://127.0.0.1:%d" % port

    def _open(self, req):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                msg = json.loads(exc.read().decode("utf-8")).get("error")
            except ValueError:
                msg = None
            raise RuntimeError(msg or "the dashboard said %d" % exc.code)
        except (urllib.error.URLError, OSError):
            raise RuntimeError("The edu4self dashboard isn't running on port %d. Start it with `./edu4self serve` "
                               "(or `./edu4self install` to start it at login)." % self.port)

    def state(self):
        return self._open(urllib.request.Request(self.base + "/api/state", headers={"Host": "127.0.0.1:%d" % self.port}))

    def note(self, text, client):
        body = json.dumps({"topic": "general", "task": "note", "kind": "note", "title": ("Note via " + client)[:200],
                           "fields": {}, "note": text, "honor": False}).encode("utf-8")
        req = urllib.request.Request(self.base + "/api/inbox", data=body, method="POST", headers={
            "Content-Type": "application/json", "Host": "127.0.0.1:%d" % self.port, "Origin": self.base})
        return self._open(req)


# ---------------------------------------------------------------- the tools

def _link(port, task_id):
    return "http://127.0.0.1:%d/#submit=%s" % (port, task_id)


def _topics(d, topic):
    ts = d["state"].get("topics", [])
    if topic:
        ts = [t for t in ts if t.get("id") == topic]
        if not ts:
            raise ValueError("no topic %r; get_progress lists the topic ids" % topic)
    return ts


def _milestone(t):
    for m in t.get("milestones", []):
        if m.get("status") == "active":
            steps = m.get("steps", [])
            return {"title": m.get("title"), "goal": m.get("goal"), "steps_done": len([s for s in steps if s.get("done")]),
                    "steps": len(steps)}
    return None


def _task(port, q):
    out = {k: q[k] for k in ("id", "label", "title", "kind", "why", "effort", "rules") if q.get(k)}
    out["open_in_dashboard"] = _link(port, q["id"])
    return out


def get_progress(d, port, now):
    cfg, blocks = d["config"], d.get("blocks", [])
    days = reminders.block_days(blocks)
    today, mon = now.date(), reminders.monday(now.date())
    week = [x for x in days if mon <= x <= today]
    total = sum(days.values())
    trophies = {}
    for i in d.get("keepsakes", {}).get("items", []):
        trophies[i.get("plural") or i.get("name")] = trophies.get(i.get("plural") or i.get("name"), 0) + 1
    topics = []
    for t in d["state"].get("topics", []):
        todo = [q for q in t.get("queue", []) if q.get("status") == "todo"]
        topics.append({"id": t.get("id"), "title": t.get("title"), "milestone": _milestone(t),
                       "next": _task(port, todo[0]) if todo else None,
                       "proven": len([h for h in t.get("history", []) if h.get("evidence")])})
    return {
        "learner": cfg.get("name") or d["state"].get("learner"),
        "today": {"minutes": days.get(today, 0), "goal_minutes": cfg["goals"]["day_minutes"]},
        "this_week": {"days_studied": len(week), "goal_days": cfg["goals"]["week_days"]},
        "total_focused_hours": round(total / 60, 1),
        "topics": topics,
        "trophies": trophies,
        "answers_waiting_for_grading": len(d.get("inbox", {}).get("pending", [])),
        "waiting_for_grading": [{"task": e.get("task"), "sent": e.get("ts")} for e in d.get("inbox", {}).get("pending", [])],
        "dashboard": "http://127.0.0.1:%d/" % port,
    }


def get_next_task(d, port, now, topic=None):
    out = []
    for t in _topics(d, topic):
        todo = [_task(port, q) for q in t.get("queue", []) if q.get("status") == "todo"][:3]
        locked = [{"title": q.get("title"), "unlocks": q.get("unlock")} for q in t.get("queue", []) if q.get("status") == "locked"][:3]
        out.append({"topic": t.get("id"), "title": t.get("title"), "todo": todo, "coming_later": locked})
    return {"topics": out}


def get_proven(d, port, now, topic=None, limit=20):
    rows = []
    for t in _topics(d, topic):
        for h in t.get("history", []):
            if h.get("evidence"):
                rows.append({"date": h.get("date"), "topic": t.get("id"), "title": h.get("title"), "detail": h.get("detail") or None})
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    return {"proven": rows[:limit]}


def call(dash, name, args, client, now=None):
    now = now or datetime.now().astimezone()
    if name == "leave_note":
        text = (args.get("text") or "").strip()
        if not text:
            raise ValueError("the note is empty")
        r = dash.note(text, client)
        return {"sent": True, "id": r.get("id"), "note": "The tutor reads it the next time it goes through the inbox."}
    fns = {"get_progress": get_progress, "get_next_task": get_next_task, "get_proven": get_proven}
    if name not in fns:
        raise LookupError(name)
    d = dash.state()
    if "error" in d:
        raise RuntimeError(d["error"])
    kw = {k: v for k, v in args.items() if k in ("topic", "limit")}
    if "limit" in kw and not (isinstance(kw["limit"], int) and 1 <= kw["limit"] <= 100):
        raise ValueError("limit must be a whole number from 1 to 100")
    out = fns[name](d, dash.port, now, **kw)
    out["privacy"] = PRIVACY
    return out


# ---------------------------------------------------------------- JSON-RPC over stdio

def handle(msg, dash, session):
    """One JSON-RPC message in, the reply out (None for notifications)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}
    bad = lambda code, text: {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}
    if mid is None:
        return None                                  # notifications (initialized, cancelled): nothing to say
    if method == "initialize":
        session["client"] = ((params.get("clientInfo") or {}).get("name") or "an AI tool")[:60]
        asked = params.get("protocolVersion")
        return ok({"protocolVersion": asked if isinstance(asked, str) and asked else PROTOCOL,
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "edu4self", "version": VERSION},
                   "instructions": INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(args, dict):
            return bad(-32602, "arguments must be an object")
        try:
            result = call(dash, name, args, session.get("client", "an AI tool"))
        except LookupError:
            return bad(-32602, "unknown tool %r" % name)
        except (RuntimeError, ValueError) as exc:
            return ok({"content": [{"type": "text", "text": str(exc)}], "isError": True})
        return ok({"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=1)}],
                   "structuredContent": result, "isError": False})
    return bad(-32601, "method not found: %s" % method)


def serve(port, stdin=sys.stdin, stdout=sys.stdout):
    dash, session = Dashboard(port), {}
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg, dash, session) if isinstance(msg, dict) else \
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()
