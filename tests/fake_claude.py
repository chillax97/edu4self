#!/usr/bin/env python3
"""A stand-in for the claude CLI in tests: prints stream-json like `claude -p --output-format stream-json`.

It records its arguments and working folder to $FAKE_CLAUDE_LOG, and acts out a tiny part of the job:
on a schema-2 vault it writes grade requests to _system/grading/ (an ack for the welcome card's
"Grade only my first try", a full request for each pending answer), the way the real tutor would; on a
schema-1 vault it keeps the old behavior and marks pending entries processed in state.json. For a gift it
writes gifts/<id>.html. FAKE_CLAUDE_SLEEP makes it slow, to test the "one run at a time" rule.
It also answers the login check (see below).
"""
import json
import os
import re
import sys
import time

args = sys.argv[1:]

# `claude --help` and `claude auth status`, as the real CLI answers them (the dashboard's login check).
# FAKE_CLAUDE_SIGNED_OUT plays a Claude Code nobody has signed in to: "1", or a file path (signed out while it exists).
# FAKE_CLAUDE_OLD=1 plays one too old to have `auth`: its help doesn't list it, and "auth status" becomes a prompt.
# These calls go to $FAKE_CLAUDE_CHECK_LOG, not $FAKE_CLAUDE_LOG, which is for real runs.
old = os.environ.get("FAKE_CLAUDE_OLD")
if args == ["--help"] or (args[:2] == ["auth", "status"] and not old):
    if os.environ.get("FAKE_CLAUDE_CHECK_LOG"):
        with open(os.environ["FAKE_CLAUDE_CHECK_LOG"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(args) + "\n")
    if args == ["--help"]:
        print("Usage: claude [options] [command] [prompt]\n\nCommands:\n" +
              ("" if old else "  auth                                  Manage authentication\n") +
              "  doctor                                Check the health of your Claude Code installation")
        sys.exit(0)
    flag = os.environ.get("FAKE_CLAUDE_SIGNED_OUT", "")
    out = flag == "1" or (len(flag) > 1 and os.path.exists(flag))
    print(json.dumps({"loggedIn": not out, "authMethod": "none" if out else "claude.ai", "apiProvider": "firstParty"}, indent=2))
    sys.exit(1 if out else 0)
prompt = args[args.index("-p") + 1] if "-p" in args else ""
session = args[args.index("--resume") + 1] if "--resume" in args else "fake-session-%d" % os.getpid()

log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"args": args, "cwd": os.getcwd()}) + "\n")


def say(obj):
    print(json.dumps(obj), flush=True)


say({"type": "system", "subtype": "init", "session_id": session})
time.sleep(float(os.environ.get("FAKE_CLAUDE_SLEEP", "0")))
say({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": os.path.join(os.getcwd(), "_system", "inbox.jsonl")}}]}})

def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def read_jsonl(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError):
        return []


def grader():
    return {"agent": "claude-code", "model": "fake-model", "session": session}


def handled_attempts(grades):
    done = set()
    for g in grades:
        if not isinstance(g, dict):
            continue
        kind = g.get("type")
        if kind in ("grade", "ack") and isinstance(g.get("attempt"), str):
            done.add(g["attempt"])
        elif kind == "legacy":
            entry = g.get("entry")
            if isinstance(entry, dict) and isinstance(entry.get("inbox"), str):
                done.add(entry["inbox"])
    return done


def pending(state, inbox, grades):
    done = set(state.get("processed_inbox", [])) | handled_attempts(grades)
    return [e for e in inbox if isinstance(e, dict) and isinstance(e.get("id"), str)
            and e.get("kind") not in ("withdraw", "dispute", "skip") and e["id"] not in done]


def key_sections(state, entry):
    topic = next((t for t in state.get("topics") or [] if t.get("id") == entry.get("topic")), None)
    path = topic.get("path") if isinstance(topic, dict) else None
    task = entry.get("task")
    if not isinstance(path, str) or not isinstance(task, str):
        return None
    text = ""
    try:
        with open(os.path.join("_system", "keys", path, task + ".md"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    sections, in_required = [], False
    for line in text.splitlines():
        t = line.strip()
        m = re.match(r"^##\s+(\d+)\.\s*", t)
        if m:
            sections.append({"n": int(m.group(1)), "points": []})
            in_required = False
            continue
        if t.startswith("Required"):
            in_required = True
            continue
        if t.startswith(("Wrong answers", "Not required", "## ")):
            in_required = False
            continue
        if in_required and sections:
            pm = re.match(r"^[-*]\s+(\d+[a-z]*)\.\s", t)
            if pm and pm.group(1) not in sections[-1]["points"]:
                sections[-1]["points"].append(pm.group(1))
    return sections or None


def write_request(entry_id, request):
    folder = os.path.join("_system", "grading")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, entry_id + ".json"), "w", encoding="utf-8") as fh:
        json.dump(request, fh, indent=1)


if "Grade only my first try" in prompt:
    path = os.path.join("_system", "state.json")
    state = read_json(path, {})
    inbox = read_jsonl(os.path.join("_system", "inbox.jsonl"))
    grades = read_jsonl(os.path.join("_system", "grades.jsonl"))
    firsts = [e for e in pending(state, inbox, grades) if e.get("task") == "first-try"]
    if state.get("schema") == 2:
        for e in firsts:
            write_request(e["id"], {"attempt": e["id"], "grader": grader(), "ack": True})
        state["coach"]["headline"] = "First try graded by the fake tutor."
        state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
    else:
        for e in firsts:
            state["topics"][0]["history"].append({"date": time.strftime("%Y-%m-%d"), "kind": "lesson", "title": "First try graded by the fake tutor.",
                                                  "detail": "All three points.", "evidence": False, "inbox": e["id"]})
        state["processed_inbox"] = sorted(set(state.get("processed_inbox", [])) | {e["id"] for e in firsts})
        state["coach"]["headline"] = "First try graded by the fake tutor."
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Graded your first try."}]}})
elif "check my inbox" in prompt:
    path = os.path.join("_system", "state.json")
    state = read_json(path, {})
    inbox = read_jsonl(os.path.join("_system", "inbox.jsonl"))
    grades = read_jsonl(os.path.join("_system", "grades.jsonl"))
    ids = [e.get("id") for e in inbox]
    # FAKE_CLAUDE_PASS_IF: a pass when the answer's text holds that marker, else "Not yet."
    # FAKE_CLAUDE_LENIENT=1 plays the grader we guard against: it passes every answer, whatever its checklist says.
    marker = os.environ.get("FAKE_CLAUDE_PASS_IF")
    lenient = bool(os.environ.get("FAKE_CLAUDE_LENIENT"))
    if state.get("schema") == 2:
        for e in pending(state, inbox, grades):
            if e.get("kind") == "note" or e.get("task") == "first-try":
                write_request(e["id"], {"attempt": e["id"], "grader": grader(), "ack": True})
                continue
            if e.get("kind") not in ("answers", "done"):
                continue
            sections = key_sections(state, e)
            if sections is None:
                continue
            passed = (marker in json.dumps(e.get("fields")) if marker else False) or lenient
            questions = []
            for s in sections:
                pts = {p: True for p in s["points"]}
                if not passed and s["points"]:
                    pts[s["points"][0]] = False
                questions.append({"n": s["n"], "points": pts, "errors": []})
            write_request(e["id"], {"attempt": e["id"], "grader": grader(),
                                    "title": "Passed." if passed else "Not yet.",
                                    "detail": "Graded by the fake tutor.", "questions": questions})
        state["coach"]["headline"] = "Graded by the fake tutor."
        state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
    else:
        if marker:
            for e in inbox:
                if e["id"] in state.get("processed_inbox", []) or e.get("kind") == "withdraw":
                    continue
                text = json.dumps(e.get("fields"))
                topic = next(t for t in state["topics"] if t["id"] == e.get("topic"))
                passed = marker in text
                h = {"date": time.strftime("%Y-%m-%d"), "kind": "lesson", "inbox": e["id"],
                     "title": "Passed." if passed else "Not yet.",
                     "detail": "Graded by the fake tutor.", "evidence": passed or lenient}
                key = os.path.join("_system", "keys", topic["path"], "%s.md" % e.get("task"))
                if os.path.isfile(key):
                    with open(key, encoding="utf-8") as fh:
                        pts = re.findall(r"(?m)^\s*[-*]\s+(\d+[a-z]+)\.\s", fh.read()) or ["1a"]
                    h["points"] = {p: passed or i > 0 for i, p in enumerate(pts)}
                    h["errors"] = []
                topic["history"].append(h)
        state["processed_inbox"] = sorted(set(state.get("processed_inbox", []) + [i for i in ids if i]))
        state["coach"]["headline"] = "Graded by the fake tutor."
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
    say({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": os.path.abspath(path)}}]}})
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Graded %d submission(s)." % len(ids)}]}})
elif "A surprise for the learner" in prompt:
    import re
    gid = re.search(r"gifts/([A-Za-z0-9-]+)\.html", prompt).group(1)
    os.makedirs("gifts", exist_ok=True)
    with open(os.path.join("gifts", gid + ".html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><title>A gift</title><p>A map of what you know.</p>")
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "I made you a map."}]}})
else:
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "You said: " + prompt[-200:]}]}})

if os.environ.get("FAKE_CLAUDE_FAIL"):
    say({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "something broke", "session_id": session})
    sys.exit(1)
say({"type": "result", "subtype": "success", "is_error": False, "result": "done", "total_cost_usd": 0.01, "session_id": session})
