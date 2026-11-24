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
sys.path.insert(0, HERE)
from test_server import APP, free_port, make_vault

sys.path.insert(0, APP)
import server


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def request(port, path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Host": "127.0.0.1:%d" % port}
    h.update(headers or {})
    c.request("GET", path, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data, r


def opt(args, name):
    return args[args.index(name) + 1] if name in args else None


class AnswerKeyPointsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-backlog-key-")
        self.vault, _ = make_vault(self.tmp)
        self.state_path = os.path.join(self.vault, "_system", "state.json")
        self.state = read_json(self.state_path)
        self.key_path = os.path.join(self.vault, "_system", "keys", "how-learning-works", "hlw-lesson-01.md")
        self.inbox_id = "ab12cd34ef"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def grade(self, key_text, points, errors=None):
        with open(self.key_path, "w", encoding="utf-8") as fh:
            fh.write(key_text)
        entry = {"id": self.inbox_id, "ts": "2026-01-02T10:00:00", "topic": "how-learning-works",
                 "task": "hlw-lesson-01", "kind": "answers", "fields": {"q": "a"}}
        inbox = os.path.join(self.vault, "_system", "inbox.jsonl")
        with open(inbox, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        hist = self.state["topics"][0]["history"]
        hist[:] = [x for x in hist if x.get("inbox") != self.inbox_id]
        h = {"date": "2026-01-02", "kind": "lesson", "title": "Lesson 01", "detail": "d",
             "inbox": self.inbox_id, "evidence": True, "points": points}
        if errors is not None:
            h["errors"] = errors
        hist.append(h)
        write_json(self.state_path, self.state)
        return subprocess.run([sys.executable, os.path.join(APP, "validate_state.py"), self.vault, "--overrule"],
                              stdout=subprocess.PIPE, encoding="utf-8")

    def evidence(self):
        st = read_json(self.state_path)
        return [x for x in st["topics"][0]["history"] if x.get("inbox") == self.inbox_id][0]["evidence"]

    def test_a_missed_required_point_overrules_a_pass(self):
        key = ("# Answer key: hlw-lesson-01\n\n## 1. Section\n\nRequired:\n"
               "- 1. Claim one.\n- 2. Claim two.\n")
        r = self.grade(key, {"1": True}, errors=[])
        self.assertIn("OVERRULED", r.stdout)
        self.assertIn("2", r.stdout)
        self.assertIs(self.evidence(), False)

    def test_every_required_point_met_is_not_overruled(self):
        key = ("# Answer key: hlw-lesson-01\n\n## 1. Section\n\nRequired:\n"
               "- 1. Claim one.\n- 2. Claim two.\n")
        r = self.grade(key, {"1": True, "2": True}, errors=[])
        self.assertNotIn("OVERRULED", r.stdout)

    def test_a_bullet_under_not_required_is_not_a_required_point(self):
        key = ("# Answer key: hlw-lesson-01\n\n## 1. Section\n\nRequired:\n- 1a. A.\n\n"
               "Not required:\n- 9z. Extra.\n")
        r = self.grade(key, {"1a": True}, errors=[])
        self.assertNotIn("OVERRULED", r.stdout)

    def test_a_multi_letter_point_id_is_named_when_missed(self):
        key = "# Answer key: hlw-lesson-01\n\n## 1. Section\n\nRequired:\n- 12b. X.\n"
        r = self.grade(key, {}, errors=[])
        self.assertIn("OVERRULED", r.stdout)
        self.assertIn("12b", r.stdout)
        self.assertIs(self.evidence(), False)


class FenceTest(unittest.TestCase):
    def test_fenced_kinds_deny_writes_to_the_system_files_and_still_deny_bash(self):
        kinds = ["chat", "topic"] + list(server.FENCED)
        for kind in kinds:
            args = server.claude_args("prompt", None, kind)
            self.assertIsInstance(args, list, kind)
            denied = opt(args, "--disallowedTools")
            self.assertIsNotNone(denied, kind)
            rules = denied.split(",")
            self.assertIn("Bash", rules, kind)
            for tool in ("Edit", "Write", "MultiEdit"):
                for path in ("./_system/inbox.jsonl", "./_system/blocks.jsonl", "./_system/music/**"):
                    rule = "%s(%s)" % (tool, path)
                    self.assertIn(rule, rules, "%s: %s" % (kind, rule))


PROBE = ("---\ntags: [probe]\nstatus: open\n---\n# Probe 0001: Title\n\nSome **bold** and `code` text.\n\n"
         "1. First question\n2. Second <script>alert(1)</script>\n\n- item a\n- item b\n\n```\nx = 1 < 2\n```\n")


class MarkdownServedReadableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-backlog-md-")
        cls.vault, _ = make_vault(cls.tmp)
        cls.probe = os.path.join(cls.vault, "how-learning-works", "probes", "x.md")
        with open(cls.probe, "w", encoding="utf-8") as fh:
            fh.write(PROBE)
        cls.httpd = None
        cls.start_error = None
        try:
            cls.port = free_port()
            cls.httpd = server.make_server(cls.vault, cls.port)
            threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        except OSError as exc:
            cls.start_error = str(exc)

    @classmethod
    def tearDownClass(cls):
        if cls.httpd is not None:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def require_server(self):
        if self.start_error is not None:
            self.fail("could not start the test server: " + self.start_error)

    def test_markdown_renders_to_sandboxed_html(self):
        self.require_server()
        code, data, r = request(self.port, "/vault/how-learning-works/probes/x.md")
        self.assertEqual(code, 200)
        ctype = r.getheader("Content-Type") or ""
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("sandbox", r.getheader("Content-Security-Policy") or "")
        body = data.decode("utf-8")
        self.assertNotIn("status: open", body)
        self.assertIn("<h1>Probe 0001: Title</h1>", body)
        self.assertIn("<strong>bold</strong>", body)
        self.assertIn("<code>code</code>", body)
        self.assertIn("<ol>", body)
        self.assertIn("</ol>", body)
        ordered = body[body.index("<ol>"):body.index("</ol>")]
        self.assertEqual(ordered.count("<li>"), 2)
        self.assertIn("<ul>", body)
        self.assertIn("<pre><code>", body)
        self.assertIn("x = 1 &lt; 2", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>alert", body)

    def test_raw_serves_the_original_text(self):
        self.require_server()
        code, data, r = request(self.port, "/vault/how-learning-works/probes/x.md?raw=1")
        self.assertEqual(code, 200)
        ctype = r.getheader("Content-Type") or ""
        self.assertTrue(ctype.startswith("text/plain"), ctype)
        self.assertEqual(data.decode("utf-8"), PROBE)


if __name__ == "__main__":
    unittest.main()
