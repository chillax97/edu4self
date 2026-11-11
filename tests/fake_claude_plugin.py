#!/usr/bin/env python3
"""A stand-in for `claude plugin ...` in tests, so setup and doctor never touch a real Claude config.

It records its arguments to $FAKE_CLAUDE_LOG and keeps the installed marketplaces and plugins in the
JSON file $FAKE_PLUGIN_STATE, printing the same --json shapes as the real CLI (Claude Code 2.1).
FAKE_PLUGIN_FAIL=install makes `plugin install` fail the way a network error would. The login check
(`--help`, `auth status`) is answered by tests/fake_claude.py, with the same FAKE_CLAUDE_SIGNED_OUT switch.
"""
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):      # the real CLI writes UTF-8; Windows would default a pipe to its code page
    _s.reconfigure(encoding="utf-8")

args = sys.argv[1:]
if args == ["--help"] or args[:2] == ["auth", "status"]:   # the login check: answered as tests/fake_claude.py does
    import runpy
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_claude.py"), run_name="__main__")
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"args": args}) + "\n")

path = os.environ["FAKE_PLUGIN_STATE"]
state = {"marketplaces": [], "plugins": []}
if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)


def save():
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


if args[:3] == ["plugin", "list", "--json"]:
    print(json.dumps(state["plugins"], indent=2))
elif args[:4] == ["plugin", "marketplace", "list", "--json"]:
    print(json.dumps([{"name": n, "source": "github", "repo": "chillax97/" + n} for n in state["marketplaces"]], indent=2))
elif args[:3] == ["plugin", "marketplace", "add"]:
    name = args[3].split("/")[-1]
    if name in state["marketplaces"]:
        print("Marketplace '%s' is already installed" % name, file=sys.stderr)
        sys.exit(1)
    state["marketplaces"].append(name)
    save()
    print("Adding marketplace...\n✔ Successfully added marketplace: %s" % name)
elif args[:2] == ["plugin", "install"]:
    pid = args[2]
    if os.environ.get("FAKE_PLUGIN_FAIL") == "install" or pid.split("@")[1] not in state["marketplaces"]:
        print("✘ Failed to install plugin \"%s\": network error" % pid, file=sys.stderr)
        sys.exit(1)
    state["plugins"] = [p for p in state["plugins"] if p["id"] != pid] + [{"id": pid, "version": "1.3.0", "scope": "user", "enabled": True}]
    save()
    print("Installing plugin \"%s\"...\n✔ Successfully installed plugin: %s (scope: user)" % (pid, pid))
elif args[:2] == ["plugin", "enable"]:
    for p in state["plugins"]:
        if p["id"] == args[2]:
            p["enabled"] = True
    save()
    print("✔ Successfully enabled plugin: %s" % args[2])
else:
    print("fake claude: unknown command %r" % args, file=sys.stderr)
    sys.exit(2)
