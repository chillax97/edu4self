#!/usr/bin/env python3
"""A stand-in for the claude CLI in tests: prints stream-json like `claude -p --output-format stream-json`.

It records its arguments and working folder to $FAKE_CLAUDE_LOG, and acts out a tiny part of the job:
for "check my inbox" it marks every pending inbox entry as processed in state.json, the way the real
tutor would. FAKE_CLAUDE_SLEEP makes it slow, to test the "one run at a time" rule.
"""
import json
import os
import sys
import time

args = sys.argv[1:]
prompt = args[args.index("-p") + 1] if "-p" in args else ""
session = args[args.index("--resume") + 1] if "--resume" in args else "fake-session-%d" % os.getpid()

log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps({"args": args, "cwd": os.getcwd()}) + "\n")


def say(obj):
    print(json.dumps(obj), flush=True)


say({"type": "system", "subtype": "init", "session_id": session})
time.sleep(float(os.environ.get("FAKE_CLAUDE_SLEEP", "0")))
say({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": os.path.join(os.getcwd(), "_system", "inbox.jsonl")}}]}})

if "check my inbox" in prompt:
    path = os.path.join("_system", "state.json")
    with open(path) as fh:
        state = json.load(fh)
    ids = []
    with open(os.path.join("_system", "inbox.jsonl")) as fh:
        for line in fh:
            if line.strip():
                ids.append(json.loads(line)["id"])
    state["processed_inbox"] = sorted(set(state.get("processed_inbox", []) + ids))
    state["coach"]["headline"] = "Graded by the fake tutor."
    with open(path, "w") as fh:
        json.dump(state, fh, indent=1)
    say({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": os.path.abspath(path)}}]}})
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Graded %d submission(s)." % len(ids)}]}})
else:
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "You said: " + prompt[-200:]}]}})

if os.environ.get("FAKE_CLAUDE_FAIL"):
    say({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "something broke", "session_id": session})
    sys.exit(1)
say({"type": "result", "subtype": "success", "is_error": False, "result": "done", "total_cost_usd": 0.01, "session_id": session})
