"""Save each checker run for the tutor: what the checker printed and the learner's code at that moment.

An exercise's checker calls start() once, at its top. When the checker finishes (passing, failing or
crashing), one file is written next to it, in trace/, named by the time of the run:

    inference-engineering/exercises/p03b/trace/2026-11-06T14-02-11.204-run.json

Sorted by name, the folder is the learner's attempt in order. Hints opened in the dashboard land in
the same folder (...-hint-2.json), so the order shows when a hint came. When the learner hands the
task in, the tutor reads the folder as a whole with their comments, then grades and plans
(docs/PROTOCOL.md, "Grading an exercise").

The dashboard copies this file into <vault>/_system/ each time it starts, so a vault's checkers always
find it there. It is standard library only, and nothing in it may stop or change the checker: every
failure is swallowed, and the only thing added to the output is one line saying where the run was saved.
"""
import atexit
import io
import json
import os
import sys
from datetime import datetime

MARK = "edu4self_trace"          # every file we write carries this, so deleting only ever touches ours
CODE_MAX = 200_000               # characters kept per code file
OUTPUT_MAX = 200_000             # characters of checker output kept


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
                out.flush()
            except Exception:
                pass

        atexit.register(_save)
    except Exception:
        pass
