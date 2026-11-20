"""Save each checker run for the tutor: what the checker printed and the learner's code at that moment.

An exercise's checker calls start() once, at its top. When the checker finishes (passing, failing or
crashing), one file is written next to it, in trace/, named by the time of the run:

    python/exercises/p03b/trace/2026-11-06T14-02-11.204-run.json

Sorted by name, the folder is the learner's attempt in order. Hints opened in the dashboard land in
the same folder (...-hint-2.json), so the order shows when a hint came. When the learner hands the
task in, the tutor reads the folder as a whole with their comments, then grades and plans
(docs/PROTOCOL.md, "Grading an exercise").

The dashboard copies this file into <vault>/_system/ each time it starts, so a vault's checkers always
find it there. It is standard library only, and nothing in it may stop or change the checker: every
failure is swallowed, and the only thing added to the output is one line saying where the run was saved,
plus a hint offer when the learner is stuck (3 failing runs in a row and a hint still unopened).
"""
import atexit
import io
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime

MARK = "edu4self_trace"          # every file we write carries this, so deleting only ever touches ours
CODE_MAX = 200_000               # characters kept per code file
OUTPUT_MAX = 200_000             # characters of checker output kept
STUCK_RUNS = 3                   # failing checker runs in a row (no pass since) before we offer the next hint
HINT_FILE = re.compile(r"^.+-hint-(\d+)(?:-\d+)?\.json$")


class _Tee(io.TextIOBase):
    """Writes through to the real stream and keeps a copy."""

    def __init__(self, real, keep, size=None):
        # size: [characters in keep so far], shared by the stdout and stderr tees, so a write never re-counts
        self.real, self.keep, self.size = real, keep, size if size is not None else [sum(len(x) for x in keep)]

    def write(self, s):
        try:
            if self.size[0] < OUTPUT_MAX:
                n = len(s)
                self.keep.append(s)
                self.size[0] += n
        except Exception:
            pass
        return self.real.write(s)

    def flush(self):
        return self.real.flush()

    def isatty(self):
        return self.real.isatty()

    @property
    def encoding(self):
        return getattr(self.real, "encoding", "utf-8")


def free_name(folder, stamp, kind):
    """trace/<stamp>-<kind>.json, or -2, -3... if a run in the same second already took it."""
    name, n = "%s-%s.json" % (stamp, kind), 1
    while os.path.exists(os.path.join(folder, name)):
        n += 1
        name = "%s-%s-%d.json" % (stamp, kind, n)
    return os.path.join(folder, name)


def stamp(now=None):
    now = now or datetime.now().astimezone()       # milliseconds too, so a run and a hint in one second keep their order
    return now.strftime("%Y-%m-%dT%H-%M-%S") + ".%03d" % (now.microsecond // 1000)


def parse_hints(text):
    """HINTS.md: one hint per '## ' heading, in order. Whatever comes before the first heading is the intro."""
    out, cur = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = {"title": line[3:].strip(), "lines": []}
            out.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    return [{"n": i + 1, "title": h["title"][:120], "body": "\n".join(h["lines"]).strip()[:4000]} for i, h in enumerate(out)]


def hints_opened(folder):
    """{hint number: when it was opened}, from the hint files in trace/."""
    opened, tdir = {}, os.path.join(folder, "trace")
    for name in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        m = HINT_FILE.match(name)
        if not m:
            continue
        try:
            with open(os.path.join(tdir, name), encoding="utf-8", errors="replace") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get(MARK):
            opened.setdefault(int(m.group(1)), rec.get("ts"))
    return opened


def fails_in_a_row(exits):
    """How many runs at the end failed, counting back to the last pass."""
    n = 0
    for code in reversed(exits):
        if code == 0:
            break
        n += 1
    return n


def next_hint(folder):
    """The first hint in HINTS.md not opened yet, as {"n", "title"}, or None."""
    try:
        with open(os.path.join(folder, "HINTS.md"), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    opened = hints_opened(folder)
    for h in parse_hints(text):
        if h["n"] not in opened:
            return {"n": h["n"], "title": h["title"]}
    return None


def run_exits(folder):
    """The exit code of every run in <folder>/trace/, in name order (a non-int exit counts as 1)."""
    tdir, exits = os.path.join(folder, "trace"), []
    for name in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(tdir, name), encoding="utf-8", errors="replace") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or not rec.get(MARK) or rec.get("kind") != "run":
            continue
        code = rec.get("exit")
        exits.append(code if isinstance(code, int) else 1)
    return exits


def dashboard_link(folder):
    """Where to open the task's hints: the dashboard's address plus #hints=<task id>, or None without a URL."""
    folder = os.path.realpath(folder)
    root, d = None, folder
    while True:
        if os.path.isfile(os.path.join(d, "_system", "state.json")):
            root = d
            break
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    url = None
    try:
        with open(os.path.join(root, "_system", "dashboard.json"), encoding="utf-8", errors="replace") as fh:
            rec = json.load(fh)
        if isinstance(rec, dict) and isinstance(rec.get("url"), str) and rec["url"]:
            url = rec["url"]
    except (OSError, ValueError):
        url = None
    if not url:
        return None
    task_id = None
    try:
        with open(os.path.join(root, "_system", "state.json"), encoding="utf-8", errors="replace") as fh:
            state = json.load(fh)
        for topic in state.get("topics", []) if isinstance(state, dict) else []:
            for task in topic.get("queue", []) if isinstance(topic, dict) else []:
                if not isinstance(task, dict) or task.get("status") != "todo":
                    continue
                rel = task.get("exercise")
                if not isinstance(rel, str) or not rel:
                    continue
                here = os.path.join(root, *[p for p in rel.split("/") if p])
                if os.path.realpath(here) == folder:
                    task_id = task.get("id")
                    break
            if task_id is not None:
                break
    except (OSError, ValueError, TypeError):
        task_id = None
    if task_id is None:
        return url
    return url + "#hints=" + urllib.parse.quote(str(task_id))


def nudge_line(folder):
    """The offer printed after a stuck run, or None when it wouldn't help."""
    fails = fails_in_a_row(run_exits(folder))
    if fails < STUCK_RUNS:
        return None
    h = next_hint(folder)
    if not h:
        return None
    link = dashboard_link(folder) or "(open it on the dashboard)"
    return "Stuck? %d runs in a row haven't passed. Hint %d is ready: %s  %s" % (fails, h["n"], h["title"], link)


def start(checker_file, code_files):
    """Call once at the top of a checker. code_files: the learner's files, relative to the checker."""
    try:
        here = os.path.dirname(os.path.abspath(checker_file))
        began = datetime.now().astimezone()
        keep, state = [], {"exit": 0}
        out, err = sys.stdout, sys.stderr
        size = [0]
        sys.stdout, sys.stderr = _Tee(out, keep, size), _Tee(err, keep, size)

        real_exit, real_hook = sys.exit, sys.excepthook

        def _exit(code=0):
            state["exit"] = code if isinstance(code, int) else (0 if code is None else 1)
            real_exit(code)

        def _hook(kind, value, tb):
            state["exit"] = 1
            real_hook(kind, value, tb)

        sys.exit, sys.excepthook = _exit, _hook

        def _save():
            try:
                code = {}
                for rel in code_files:
                    path = os.path.join(here, rel)
                    try:
                        with open(path, encoding="utf-8", errors="replace") as fh:
                            code[rel] = fh.read(CODE_MAX)
                    except OSError:
                        code[rel] = None          # missing file: worth knowing too
                folder = os.path.join(here, "trace")
                os.makedirs(folder, exist_ok=True)
                path = free_name(folder, stamp(began), "run")
                record = {MARK: 1, "kind": "run", "ts": began.isoformat(timespec="seconds"),
                          "seconds": round((datetime.now().astimezone() - began).total_seconds(), 1),
                          "args": sys.argv[1:], "exit": state["exit"], "output": "".join(keep), "code": code}
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(record, fh, ensure_ascii=False, indent=1)
                out.write("\n(run saved for your tutor: trace/%s)\n" % os.path.basename(path))
                try:
                    line = nudge_line(here)
                except Exception:
                    line = None
                if line:
                    out.write(line + "\n")
                out.flush()
            except Exception:
                pass

        atexit.register(_save)
    except Exception:
        pass
