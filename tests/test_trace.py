"""The work record: each checker run saves its output and the learner's code, hints opened in the dashboard
are noted next to them, and the learner can delete all of it."""
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
sys.path.insert(0, HERE)
import server  # noqa: E402
from test_server import make_vault, free_port, read_json  # noqa: E402

# the lines docs/PROTOCOL.md tells the tutor to put at the top of every checker
SNIPPET = '''# edu4self: save this run for your tutor (see _system/edu_trace.py). It never stops the checker.
try:
    import os as _os, sys as _sys
    _d = _os.path.dirname(_os.path.abspath(__file__))
    while not _os.path.isfile(_os.path.join(_d, "_system", "edu_trace.py")) and _os.path.dirname(_d) != _d:
        _d = _os.path.dirname(_d)
    _sys.path.insert(0, _os.path.join(_d, "_system"))
    import edu_trace
    edu_trace.start(__file__, ["sol.py"])
except Exception:
    pass
'''

CHECKER = SNIPPET + '''
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sol
ok = sol.double(2) == 4
print("double: " + ("pass" if ok else "FAIL, got %r" % sol.double(2)))
sys.exit(0 if ok else 1)
'''

HINTS = """# Hints

Only open the one you need.

## 1 · double
- Multiply by two.

## 2 · edge cases
- What about zero?
"""


def snippet_matches_protocol(test):
    with open(os.path.join(os.path.dirname(HERE), "docs", "PROTOCOL.md"), encoding="utf-8") as fh:
        doc = fh.read()
    test.assertIn(SNIPPET.replace('["sol.py"]', '["solution.py"]'), doc, "the test runs the snippet the protocol hands out")


class TraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-trace-")
        cls.vault, _ = make_vault(cls.tmp)
        cls.port = free_port()
        cls.httpd = server.make_server(cls.vault, cls.port)      # installs _system/edu_trace.py
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.ex = os.path.join(cls.vault, "topic", "exercises", "e1")
        os.makedirs(cls.ex)
        with open(os.path.join(cls.ex, "check.py"), "w", encoding="utf-8") as fh:
            fh.write(CHECKER)
        with open(os.path.join(cls.ex, "HINTS.md"), "w", encoding="utf-8") as fh:
            fh.write(HINTS)
        st = read_json(os.path.join(cls.vault, "_system", "state.json"))
        cls.task = st["topics"][0]["queue"][0]
        cls.task["exercise"] = "topic/exercises/e1"
        with open(os.path.join(cls.vault, "_system", "state.json"), "w", encoding="utf-8") as fh:
            json.dump(st, fh)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(os.path.join(self.ex, "trace"), ignore_errors=True)

    def solve(self, body):
        with open(os.path.join(self.ex, "sol.py"), "w", encoding="utf-8") as fh:
            fh.write(body)

    def check(self):
        return subprocess.run([sys.executable, os.path.join(self.ex, "check.py")], capture_output=True, encoding="utf-8", timeout=30)

    def runs(self):
        d = os.path.join(self.ex, "trace")
        return [(n, read_json(os.path.join(d, n))) for n in sorted(os.listdir(d))] if os.path.isdir(d) else []

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": "127.0.0.1:%d" % self.port}
        data = None
        if body is not None:
            data = json.dumps(body)
            h.update({"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        c.request(method, path, data, h)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def test_the_protocol_hands_out_the_snippet_tested_here(self):
        snippet_matches_protocol(self)

    def test_every_run_is_saved_in_order_with_its_output_and_the_code(self):
        self.solve("def double(x):\n    return x + 1  # first try\n")
        first = self.check()
        self.solve("def double(x):\n    return x * 2\n")
        second = self.check()
        self.assertEqual((first.returncode, second.returncode), (1, 0), "the checker's own result is untouched")
        self.assertIn("double: FAIL", first.stdout)
        self.assertIn("run saved for your tutor: trace/", second.stdout)
        runs = self.runs()
        self.assertEqual(len(runs), 2)
        self.assertEqual([n for n, _ in runs], sorted(n for n, _ in runs))
        (n1, r1), (n2, r2) = runs
        self.assertRegex(n1, r"^\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d\.\d{3}-run(-\d+)?\.json$", "named by the time of the run")
        self.assertEqual((r1["exit"], r2["exit"]), (1, 0))
        self.assertIn("FAIL, got 3", r1["output"])
        self.assertIn("# first try", r1["code"]["sol.py"], "the code as it was then, comments included")
        self.assertIn("x * 2", r2["code"]["sol.py"])
        self.assertLessEqual(r1["ts"], r2["ts"])

    def test_a_crash_in_the_learners_code_is_saved_too(self):
        self.solve("def double(x)\n    return x * 2\n")          # a syntax error
        res = self.check()
        self.assertNotEqual(res.returncode, 0)
        (_, rec), = self.runs()
        self.assertEqual(rec["exit"], 1)
        self.assertIn("SyntaxError", rec["output"])

    def test_saving_can_fail_without_touching_the_checker(self):
        self.solve("def double(x):\n    return x * 2\n")
        with open(os.path.join(self.ex, "trace"), "w", encoding="utf-8") as fh:   # a file where the folder should be
            fh.write("in the way")
        try:
            res = self.check()
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "double: pass", "nothing added, nothing lost")
            self.assertEqual(res.stderr, "")
        finally:
            os.remove(os.path.join(self.ex, "trace"))
        # and without the helper at all (a vault the dashboard never started on), the checker just runs
        helper = os.path.join(self.vault, "_system", "edu_trace.py")
        os.rename(helper, helper + ".off")
        try:
            res = self.check()
            self.assertEqual((res.returncode, res.stdout.strip()), (0, "double: pass"))
        finally:
            os.rename(helper + ".off", helper)

    def test_hints_open_one_at_a_time_and_each_one_is_noted_in_the_record(self):
        tid = self.task["id"]
        code, d = self.req("GET", "/api/hints?task=" + tid)
        self.assertEqual(code, 200)
        self.assertEqual([h["title"] for h in d["hints"]], ["1 · double", "2 · edge cases"])
        self.assertTrue(all("body" not in h for h in d["hints"]), "nothing is sent before it's opened")
        self.solve("def double(x):\n    return x\n")
        self.check()
        code, d = self.req("POST", "/api/hints", {"task": tid, "n": 2})
        self.assertEqual(code, 200)
        self.assertIn("What about zero?", d["hint"]["body"])
        self.req("POST", "/api/hints", {"task": tid, "n": 2})          # opening it again isn't a second event
        _, d = self.req("GET", "/api/hints?task=" + tid)
        self.assertTrue(d["hints"][1]["opened"])
        self.assertNotIn("body", d["hints"][0])
        kinds = [r["kind"] for _, r in self.runs()]
        self.assertEqual(kinds, ["run", "hint"], "the hint sits after the run it followed")
        self.assertEqual(self.runs()[1][1]["hint"], 2)
        self.assertEqual(self.req("POST", "/api/hints", {"task": tid, "n": 9})[0], 404)
        self.assertEqual(self.req("POST", "/api/hints", {"task": "nope", "n": 1})[0], 404)

    def test_an_exercise_folder_must_stay_inside_the_vault(self):
        for bad in ("../outside", "/etc", "_system", ".hidden", "", None, 3, "no/such/folder"):
            self.assertIsNone(server.exercise_dir({"exercise": bad}), bad)
        self.assertEqual(server.exercise_dir({"exercise": "topic/exercises/e1"}), os.path.realpath(self.ex))
        validator = os.path.join(os.path.dirname(HERE), "app", "validate_state.py")
        path = os.path.join(self.vault, "_system", "state.json")
        good = read_json(path)
        bad = json.loads(json.dumps(good))
        bad["topics"][0]["queue"][0]["exercise"] = "../outside"
        alt = os.path.join(self.tmp, "bad-vault", "_system")
        shutil.copytree(os.path.join(self.vault, "_system"), alt, dirs_exist_ok=True)
        with open(os.path.join(alt, "state.json"), "w", encoding="utf-8") as fh:
            json.dump(bad, fh)
        res = subprocess.run([sys.executable, validator, os.path.dirname(alt)], capture_output=True, encoding="utf-8")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("exercise must be a folder in the vault", res.stdout)
        self.assertEqual(subprocess.run([sys.executable, validator, self.vault], capture_output=True, encoding="utf-8").returncode, 0,
                         "a real exercise folder is fine")

    def test_the_learner_sees_what_is_kept_and_deleting_removes_only_the_record(self):
        self.solve("def double(x):\n    return x * 2\n")
        self.check()
        self.req("POST", "/api/hints", {"task": self.task["id"], "n": 1})
        other = os.path.join(self.ex, "notes.json")                  # the learner's own files are never touched
        with open(other, "w", encoding="utf-8") as fh:
            fh.write("{}")
        mine = os.path.join(self.ex, "trace", "my-own.json")          # not even one they put inside trace/
        with open(mine, "w", encoding="utf-8") as fh:
            fh.write('{"kind": "run"}')
        code, s = self.req("GET", "/api/traces")
        self.assertEqual((code, s["runs"], s["hints"], s["exercises"]), (200, 1, 1, 1))
        self.assertGreater(s["bytes"], 0)
        self.assertEqual(self.req("POST", "/api/traces/delete", {})[0], 400, "deleting needs an explicit yes")
        code, d = self.req("POST", "/api/traces/delete", {"confirm": True})
        self.assertEqual((code, d["deleted"]), (200, 2))
        self.assertEqual(os.listdir(os.path.join(self.ex, "trace")), ["my-own.json"], "only files the record wrote go")
        os.remove(mine)
        for keep in ("check.py", "HINTS.md", "sol.py", "notes.json"):
            self.assertTrue(os.path.exists(os.path.join(self.ex, keep)), keep)
        _, d = self.req("GET", "/api/hints?task=" + self.task["id"])
        self.assertFalse(any(h["opened"] for h in d["hints"]), "the record of opened hints goes with it")


class TeeTest(unittest.TestCase):
    """The copy of the checker's output: same text as before, same cap, and no re-counting on every write."""

    def setUp(self):
        import edu_trace
        self.t = edu_trace

    def reference(self, chunks):
        keep = []                      # the old rule: add a chunk while what's kept is under the cap
        for c in chunks:
            if sum(len(x) for x in keep) < self.t.OUTPUT_MAX:
                keep.append(c)
        return keep

    def tee_pair(self):
        import io as _io
        keep, size = [], [0]
        out, err = _io.StringIO(), _io.StringIO()
        return keep, out, err, self.t._Tee(out, keep, size), self.t._Tee(err, keep, size)

    def test_keeps_exactly_what_the_old_code_kept_and_passes_everything_through(self):
        chunks = [("x" * (i % 997)) + "\n" for i in range(700)]       # about 350k characters, well past the cap
        keep, out, err, to, te = self.tee_pair()
        for i, c in enumerate(chunks):
            (to if i % 3 else te).write(c)                              # stdout and stderr share one copy and one cap
        self.assertEqual(keep, self.reference(chunks))
        self.assertGreaterEqual(sum(map(len, keep)), self.t.OUTPUT_MAX)
        self.assertLess(sum(map(len, keep)) - len(keep[-1]), self.t.OUTPUT_MAX, "stops right after the write that crossed the cap")
        self.assertEqual(len(out.getvalue()) + len(err.getvalue()), sum(map(len, chunks)), "the real streams get every character")

    def test_many_small_writes_stay_fast(self):
        import time as _time
        keep, out, err, to, te = self.tee_pair()
        began = _time.monotonic()
        for _ in range(40000):                                         # re-summing would take tens of seconds here
            to.write("ab")
        self.assertLess(_time.monotonic() - began, 2.0)
        self.assertEqual("".join(keep), "ab" * 40000)


if __name__ == "__main__":
    unittest.main()
