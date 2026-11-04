#!/usr/bin/env python3
"""Validate a vault's _system/state.json before the dashboard reads it. Exit 0 = valid.

Run after every edit to state.json:  edu4self check   (or: python3 validate_state.py VAULT)
"""
import json, os, sys

ARG = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("EDU4SELF_VAULT", ".")))
# accept the vault folder or the state.json file itself
ROOT = os.path.dirname(os.path.dirname(ARG)) if ARG.endswith(".json") else ARG
PATH = ARG if ARG.endswith(".json") else os.path.join(ROOT, "_system", "state.json")
KINDS = {"lesson", "probe", "checkpoint", "reading", "project", "mock"}
STATUSES = {"todo", "done", "locked"}
errors = []
notes = []

def err(msg):
    errors.append(msg)

try:
    s = json.load(open(PATH, encoding="utf-8"))
except (OSError, ValueError) as exc:
    print("INVALID: cannot parse state.json:", exc)
    sys.exit(1)

for key in ("schema", "updated", "topics", "processed_inbox"):
    if key not in s:
        err("missing top-level key: %s" % key)

# block kinds: from config.json if it has them, else the defaults
KIND_IDS = {"lessons", "practice", "reading", "free", "play"}
try:
    _cfg = json.load(open(os.path.join(ROOT, "_system", "config.json"), encoding="utf-8"))
    if (_cfg.get("blocks") or {}).get("kinds"):
        KIND_IDS = {k.get("id") for k in _cfg["blocks"]["kinds"]}
except (OSError, ValueError, AttributeError):
    pass

ids = set()
for t in s.get("topics", []):
    tid = t.get("id", "?")
    for key in ("id", "title", "path", "color", "milestones", "queue", "regions", "history"):
        if key not in t:
            err("topic %s missing %s" % (tid, key))
    if not os.path.isdir(os.path.join(ROOT, t.get("path", ""))):
        err("topic %s path does not exist: %s" % (tid, t.get("path")))
    if "gate" in t and (t.get("gate") or {}).get("level") not in ("RED", "AMBER", "GREEN"):
        err("topic %s gate.level must be RED/AMBER/GREEN (or leave the gate out)" % tid)
    # the learner can delete block kinds in Settings; the dashboard then falls back to the first kind,
    # so a stale reference is a note, not an error (otherwise a settings change would break Claude's check)
    if t.get("block") is not None and t["block"] not in KIND_IDS:
        notes.append("topic %s block %r isn't a block kind in Settings any more; the first kind is used" % (tid, t["block"]))
    for task in t.get("queue", []):
        k = task.get("id")
        if k in ids:
            err("duplicate task id %s" % k)
        ids.add(k)
        if task.get("kind") not in KINDS:
            err("task %s kind %r not in %s" % (k, task.get("kind"), sorted(KINDS)))
        if task.get("status") not in STATUSES:
            err("task %s status %r not in %s" % (k, task.get("status"), sorted(STATUSES)))
        href = task.get("href")
        if task.get("status") == "todo" and not href and not task.get("submit"):
            err("task %s is actionable but has neither href nor submit" % k)
        if href and href.startswith("/vault/") and not os.path.isfile(os.path.join(ROOT, href[len("/vault/"):])):
            err("task %s href points at a missing file: %s" % (k, href))
        if task.get("status") == "locked" and not task.get("unlock"):
            err("task %s is locked but says nothing about how it unlocks" % k)
        sub = task.get("submit")
        if sub and sub.get("type") == "answers" and not sub.get("fields"):
            err("task %s submit.type=answers needs fields" % k)
        for label in (sub or {}).get("fields") or []:
            if len(label) > 1000:  # must match FIELD_LABEL_MAX in server.py, or submissions are rejected
                err("task %s has a question label of %d characters; the server accepts at most 1000" % (k, len(label)))
    for r in t.get("regions", []):
        if r.get("level") not in (0, 1, 2, 3, 4):
            err("region %s level must be 0..4" % r.get("code"))
    for h in t.get("history", []):
        if h.get("record") and not os.path.isfile(os.path.join(ROOT, t.get("path", ""), h["record"])):
            err("history record missing: %s" % h["record"])
    for m in t.get("milestones", []):
        if m.get("status") not in ("active", "locked", "done"):
            err("milestone %s bad status" % m.get("id"))

# Lines Claude writes for the bar view's voices, after grading (optional)
VOICES = {"logic", "volition", "gpu", "encyclopedia", "physical", "nostalgia", "critic", "regular", "jukebox"}
voices = (s.get("coach") or {}).get("voices", [])
if not isinstance(voices, list) or len(voices) > 6:
    err("coach.voices must be a list of at most 6 lines")
else:
    for v in voices:
        if not isinstance(v, dict) or v.get("voice") not in VOICES:
            err("coach.voices: each line needs a voice in %s" % sorted(VOICES))
        elif not isinstance(v.get("text"), str) or not 0 < len(v["text"]) <= 400:
            err("coach.voices: a %s line needs text of 1-400 characters" % v["voice"])

for link in s.get("linked_topics", []):
    if not os.path.isdir(link.get("root", "")):
        err("linked topic root missing: %s" % link.get("root"))

for n in notes:
    print("  note:", n)
if errors:
    print("INVALID (%d):" % len(errors))
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("state.json valid: %d topic(s), %d task(s), %d linked" % (len(s["topics"]), len(ids), len(s.get("linked_topics", []))))
