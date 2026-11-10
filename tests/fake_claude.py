#!/usr/bin/env python3
"""A stand-in for the claude CLI in tests: prints stream-json like `claude -p --output-format stream-json`.

It records its arguments and working folder to $FAKE_CLAUDE_LOG, and acts out a tiny part of the job:
for "check my inbox" it marks every pending inbox entry as processed in state.json, the way the real
tutor would, and for a gift it writes gifts/<id>.html. FAKE_CLAUDE_SLEEP makes it slow, to test the "one run at a time" rule.
It also answers the login check (see below).
"""
import json
import os
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

if "check my inbox" in prompt:
    path = os.path.join("_system", "state.json")
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    ids = []
    with open(os.path.join("_system", "inbox.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                ids.append(json.loads(line)["id"])
    state["processed_inbox"] = sorted(set(state.get("processed_inbox", []) + ids))
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
