import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ENGINE, "app")
CLI = os.path.join(ENGINE, "edu4self")
sys.path.insert(0, APP)
import server


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LessonBackBarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-backbar-")
        env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg"))
        self.vault = os.path.join(self.tmp, "vault")
        subprocess.run([sys.executable, CLI, "init", self.vault, "--name", "Tester"], env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.port = free_port()
        self.httpd = server.make_server(self.vault, self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": "127.0.0.1:%d" % self.port})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body, r

    def anchors(self, html):
        out = []
        for tag in re.findall(r"<a\b[^>]*>", html, re.I):
            out.append({m.group(1).lower(): m.group(3) for m in re.finditer(r"""([\w:-]+)\s*=\s*(["'])(.*?)\2""", tag, re.S)})
        return out

    def state_path(self):
        return os.path.join(self.vault, "_system", "state.json")

    def test_A2_1_the_lesson_page_has_a_back_bar_to_its_submit_form_and_the_dashboard(self):
        code, body, _ = self.get("/vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html")
        self.assertEqual(code, 200)
        html = body.decode("utf-8")
        self.assertIn("data-edu-back", html)
        anchors = self.anchors(html)
        submit = [a for a in anchors if a.get("href") == "/#submit=hlw-lesson-01"]
        home = [a for a in anchors if a.get("href") == "/"]
        self.assertTrue(submit, "a link back to the lesson's submit form")
        self.assertTrue(home, "a link back to the dashboard")
        self.assertEqual(submit[0].get("target"), "_top")
        self.assertEqual(home[0].get("target"), "_top")

    def test_A2_2_a_probe_markdown_page_has_the_back_bar_and_its_submit_link(self):
        code, body, _ = self.get("/vault/how-learning-works/probes/0001-how-you-study-now.md")
        self.assertEqual(code, 200)
        html = body.decode("utf-8")
        self.assertIn("data-edu-back", html)
        self.assertIn("/#submit=hlw-probe-01", [a.get("href") for a in self.anchors(html)])

    def test_A2_3_the_same_markdown_as_raw_text_has_no_back_bar(self):
        code, body, _ = self.get("/vault/how-learning-works/probes/0001-how-you-study-now.md?raw=1")
        self.assertEqual(code, 200)
        self.assertNotIn("data-edu-back", body.decode("utf-8", "replace"))

    def test_A2_4_a_note_that_is_no_task_has_no_back_bar(self):
        code, body, _ = self.get("/vault/Home.md")
        self.assertEqual(code, 200)
        self.assertNotIn("data-edu-back", body.decode("utf-8", "replace"))

    def test_A2_5_a_done_task_gets_no_back_bar(self):
        with open(self.state_path(), encoding="utf-8") as fh:
            st = json.load(fh)
        task = next(t for t in st["topics"][0]["queue"] if t["id"] == "hlw-probe-01")
        task["status"] = "done"
        with open(self.state_path(), "w", encoding="utf-8") as fh:
            json.dump(st, fh)
        code, body, _ = self.get("/vault/how-learning-works/probes/0001-how-you-study-now.md")
        self.assertEqual(code, 200)
        self.assertNotIn("data-edu-back", body.decode("utf-8", "replace"))
