"""Server, validators and CLI. Standard library only: python3 -m unittest discover tests"""
import http.client
import importlib.machinery
import importlib.util
import json
import plistlib
import re
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ENGINE, "app")
CLI = os.path.join(ENGINE, "edu4self")
sys.path.insert(0, APP)
import server  # noqa: E402


def load_cli():
    loader = importlib.machinery.SourceFileLoader("edu4self_cli", CLI)
    spec = importlib.util.spec_from_loader("edu4self_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_vault(tmp, *extra):
    env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(tmp, "cfg"))
    vault = os.path.join(tmp, "vault")
    subprocess.run([sys.executable, CLI, "init", vault, "--name", "Tester", *extra], env=env, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return vault, env


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-test-")
        cls.vault, cls.env = make_vault(cls.tmp)
        cls.port = free_port()
        cls.httpd = server.make_server(cls.vault, cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, method, path, body=None, headers=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": "127.0.0.1:%d" % self.port}
        if body is not None:
            raw = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        c.request(method, path, body=raw, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data), r
        except ValueError:
            return r.status, data, r

    def sys_path(self, *p):
        return os.path.join(self.vault, "_system", *p)

    # ------------------------------------------------------------ reading
    def test_state_has_everything_the_page_needs(self):
        code, d, _ = self.req("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(set(d), {"state", "derived", "inbox", "blocks", "config", "keepsakes", "reminders", "server"})
        self.assertEqual(d["state"]["learner"], "Tester")   # config.json's name may have been reset by another test
        self.assertEqual(d["server"]["port"], self.port)
        self.assertEqual(d["derived"]["topics"]["how-learning-works"]["stats"]["lessons"], 1)

    def test_wrong_host_header_is_refused(self):
        code, _, _ = self.req("GET", "/api/state", headers={"Host": "evil.example:%d" % self.port})
        self.assertEqual(code, 403)

    def test_private_and_traversal_paths_are_404(self):
        for p in ("/vault/_system/state.json", "/vault/_system/config.json", "/vault/../etc/passwd",
                  "/vault/.obsidian/app.json", "/fonts/../server.py", "/../app/server.py"):
            self.assertEqual(self.req("GET", p)[0], 404, p)

    def test_markdown_is_plain_text_until_obsidian_is_on(self):
        code, _, r = self.req("GET", "/vault/how-learning-works/MISSION.md")
        self.assertEqual(code, 200)
        self.assertTrue(r.getheader("Content-Type").startswith("text/plain"))
        cfg = server.load_config()[0]
        cfg["obsidian"] = {"enabled": True, "vault": "My Vault"}
        server.save_config(cfg)
        try:
            code, _, r = self.req("GET", "/vault/how-learning-works/MISSION.md")
            self.assertEqual(code, 302)
            self.assertEqual(r.getheader("Location"), "obsidian://open?vault=My%20Vault&file=how-learning-works%2FMISSION")
        finally:
            cfg["obsidian"] = {"enabled": False, "vault": ""}
            server.save_config(cfg)

    def test_fonts_are_served(self):
        code, _, r = self.req("GET", "/fonts/oswald.woff2")
        self.assertEqual(code, 200)
        self.assertEqual(r.getheader("Content-Type"), "font/woff2")

    # ------------------------------------------------------------ writing
    def test_submission_and_withdraw(self):
        body = {"topic": "how-learning-works", "task": "hlw-lesson-01", "kind": "answers", "fields": {"Q": "A"}}
        code, d, _ = self.req("POST", "/api/inbox", body)
        self.assertEqual(code, 201)
        code, _, _ = self.req("POST", "/api/withdraw", {"id": d["id"]})
        self.assertEqual(code, 200)
        code, _, _ = self.req("POST", "/api/withdraw", {"id": d["id"]})
        self.assertEqual(code, 404)

    def test_bad_submissions(self):
        good = {"topic": "how-learning-works", "task": "t", "kind": "answers", "fields": {"Q": "A"}}
        for change, msg in (({"topic": "nope"}, "unknown topic"), ({"kind": "grade"}, "bad kind"),
                            ({"task": "../x"}, "bad task id"), ({"fields": {"Q": " "}}, "no answers"),
                            ({"fields": {"x" * 1001: "A"}}, "bad field")):
            code, d, _ = self.req("POST", "/api/inbox", dict(good, **change))
            self.assertEqual((code, d["error"]), (400, msg))
        self.assertEqual(self.req("POST", "/api/inbox", dict(good, fields={"x" * 1000: "A"}))[0], 201)

    def test_cross_origin_post_is_refused(self):
        code, d, _ = self.req("POST", "/api/blocks", {"block": "lessons"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(code, 403)

    def test_blocks(self):
        b = {"block": "lessons", "minutes": 25, "started": "2026-01-02T10:00:00Z", "water_served": 1, "water_drunk": 1}
        self.assertEqual(self.req("POST", "/api/blocks", b)[0], 201)
        code, d, _ = self.req("POST", "/api/blocks", b)
        self.assertEqual((code, d["duplicate"]), (200, True))
        for change in ({"block": "dsa"}, {"minutes": 0}, {"minutes": 241}, {"started": "yesterday"},
                       {"water_served": 1, "water_drunk": 2}):
            self.assertEqual(self.req("POST", "/api/blocks", {**b, "started": "2026-01-02T11:00:00Z", **change})[0], 400, change)

    # ------------------------------------------------------------ settings
    def test_config_defaults_and_validation(self):
        code, d, _ = self.req("GET", "/api/config")
        self.assertEqual(code, 200)
        self.assertEqual(d["config"]["blocks"]["kinds"][0]["id"], "lessons")
        for bad, msg in (({"goals": {"day_minutes": 5}}, "daily goal"),
                         ({"blocks": {"presets": [], "kinds": [{"id": "a"}]}}, "presets"),
                         ({"blocks": {"presets": [25], "kinds": [{"id": "Bad Id"}]}}, "ids"),
                         ({"blocks": {"presets": [25], "kinds": [{"id": "a"}, {"id": "a"}]}}, "twice"),
                         ({"blocks": {"presets": [25], "kinds": [{"id": "a", "color": "red"}]}}, "color"),
                         ({"bar": {"names": []}}, "bar names"),
                         ({"bar": {"voices": {"narrator": {"name": "x"}}}}, "unknown voice"),
                         ({"bar": {"lines": [{"voice": "you", "text": "x"}]}}, "voice"),
                         ({"music": {"file": "../x.mp3"}}, "music file"),
                         ({"name": "x" * 61}, "name")):
            code, d, _ = self.req("POST", "/api/config", {"config": bad})
            self.assertEqual(code, 400, bad)
            self.assertIn(msg, d["error"])

    def test_config_round_trip_and_new_block_kind(self):
        cfg = {"name": "Ada", "blocks": {"presets": [30], "kinds": [{"id": "deep", "label": "Deep", "color": "#123456", "minutes": 45}]}}
        try:
            code, d, _ = self.req("POST", "/api/config", {"config": cfg})
            self.assertEqual(code, 200)
            on_disk = read_json(self.sys_path("config.json"))
            self.assertEqual(on_disk["name"], "Ada")
            self.assertEqual(self.req("POST", "/api/blocks", {"block": "deep", "minutes": 45, "started": "2026-01-03T10:00:00Z"})[0], 201)
            self.assertEqual(self.req("POST", "/api/blocks", {"block": "lessons", "minutes": 45, "started": "2026-01-03T11:00:00Z"})[0], 400)
            # Claude's check still passes with the topic's block kind gone (it's only a note)
            r = subprocess.run([sys.executable, os.path.join(APP, "validate_state.py"), self.vault], stdout=subprocess.PIPE, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("note:", r.stdout)
        finally:
            self.req("POST", "/api/config", {"reset": True})

    def test_music_sources(self):
        # a fresh install has a built-in soundscape, paused until a click
        m = server.clean_config({})["music"]
        self.assertEqual((m["source"], m["scape"], m["autoplay"]), ("scape", "night", False))
        # a config from before sources existed keeps playing its file, on autoplay as before
        m = server.clean_config({"music": {"file": "x.mp3", "title": "X"}})["music"]
        self.assertEqual((m["source"], m["file"], m["autoplay"]), ("file", "x.mp3", True))
        m = server.clean_config({"music": {"source": "radio", "stream": {"url": "https://example.org/live.mp3", "name": "Live"}}})["music"]
        self.assertEqual((m["source"], m["stream"]), ("radio", {"url": "https://example.org/live.mp3", "name": "Live"}))
        for bad, msg in (({"source": "tape"}, "music source"),
                         ({"source": "scape", "scape": "jazz"}, "soundscape"),
                         ({"source": "radio"}, "station"),
                         ({"source": "radio", "stream": {"url": "javascript:alert(1)"}}, "http"),
                         ({"source": "radio", "stream": {"url": "ftp://example.org/x"}}, "http"),
                         ({"source": "file"}, "upload")):
            with self.assertRaises(ValueError) as cm:
                server.clean_config({"music": bad})
            self.assertIn(msg, str(cm.exception), bad)

    def test_broken_config_file_falls_back_to_defaults(self):
        with open(self.sys_path("config.json"), "w") as fh:
            fh.write("{not json")
        try:
            code, d, _ = self.req("GET", "/api/state")
            self.assertEqual(code, 200)
            self.assertEqual(d["config"]["goals"]["day_minutes"], 120)
            self.assertIn("config.json ignored", d["server"]["config_error"])
        finally:
            self.req("POST", "/api/config", {"reset": True})

    # ------------------------------------------------------------ music
    def upload(self, name, data, ctype="audio/mpeg"):
        return self.req("POST", "/api/music", raw=data, headers={"Content-Type": ctype, "X-Filename": name})

    def test_music_upload_seek_replace_remove(self):
        data = bytes(range(256)) * 40
        self.assertEqual(self.upload("notes.txt", data, "text/plain")[0], 415)
        code, d, _ = self.upload("My%20Song!.mp3", data)
        self.assertEqual(code, 201)
        self.assertEqual(d["config"]["music"]["file"], "My-Song.mp3")
        self.assertEqual(d["config"]["music"]["source"], "file", "an upload switches the jukebox to it")
        code, body, r = self.req("GET", "/music", headers={"Range": "bytes=100-199"})
        self.assertEqual((code, body), (206, data[100:200]))
        self.assertEqual(r.getheader("Content-Range"), "bytes 100-199/%d" % len(data))
        self.assertEqual(self.req("GET", "/music", headers={"Range": "bytes=999999-"})[0], 416)
        # a new upload replaces the old file, one track at a time
        self.assertEqual(self.upload("other.m4a", data, "audio/mp4")[0], 201)
        self.assertEqual(sorted(os.listdir(self.sys_path("music"))), ["other.m4a"])
        # reset keeps the track; remove deletes it
        code, d, _ = self.req("POST", "/api/config", {"reset": True})
        self.assertEqual(d["config"]["music"]["file"], "other.m4a")
        code, d, _ = self.req("POST", "/api/config", {"config": d["config"], "remove_music": True})
        self.assertEqual((code, d["config"]["music"]["file"]), (200, ""))
        self.assertEqual(d["config"]["music"]["source"], "scape", "no file left: back to the soundscape")
        self.assertEqual(os.listdir(self.sys_path("music")), [])
        self.assertEqual(self.req("GET", "/music")[0], 404)

    def test_music_too_big_is_refused_before_reading(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.putrequest("POST", "/api/music", skip_host=True)
        c.putheader("Host", "127.0.0.1:%d" % self.port)
        c.putheader("Content-Type", "audio/mpeg")
        c.putheader("X-Filename", "big.mp3")
        c.putheader("Content-Length", str(server.MAX_MUSIC + 1))
        c.endheaders()
        self.assertEqual(c.getresponse().status, 413)
        c.close()


class ValidatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-val-")
        self.vault, _ = make_vault(self.tmp)
        self.state_path = os.path.join(self.vault, "_system", "state.json")
        self.state = read_json(self.state_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, state=None):
        if state is not None:
            write_json(self.state_path, state)
        return subprocess.run([sys.executable, os.path.join(APP, "validate_state.py"), self.vault], stdout=subprocess.PIPE, text=True)

    def test_template_is_valid_and_gate_is_optional(self):
        self.assertEqual(self.check().returncode, 0)
        self.state["topics"][0]["gate"] = {"level": "PURPLE"}
        r = self.check(self.state)
        self.assertEqual(r.returncode, 1)
        self.assertIn("gate.level", r.stdout)

    def test_catches_common_mistakes(self):
        t = self.state["topics"][0]
        t["queue"].append(dict(t["queue"][0]))                    # duplicate id
        t["queue"][1]["href"] = "/vault/how-learning-works/nope.md"  # missing file
        t["queue"][2].pop("unlock")                               # locked without unlock
        t["regions"][0]["level"] = 7
        t["queue"][0]["opens"] = "next tuesday"                   # opens must be a date
        self.state["coach"]["voices"] = [{"voice": "narrator", "text": "x"}]
        out = self.check(self.state).stdout
        for msg in ("duplicate task id", "missing file", "says nothing about how it unlocks", "level must be 0..4", "coach.voices",
                    "opens must be a date"):
            self.assertIn(msg, out)

    def test_link_checker_finds_a_broken_link(self):
        with open(os.path.join(self.vault, "Home.md"), "a") as fh:
            fh.write("\n[[how-learning-works/NOPE]]\n")
        r = subprocess.run([sys.executable, os.path.join(APP, "check_links.py"), self.vault], stdout=subprocess.PIPE, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BROKEN", r.stdout)


class ClaudeTest(unittest.TestCase):
    """The page runs Claude Code in the vault. A fake claude stands in, so nothing is spent."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-claude-")
        cls.vault, cls.env = make_vault(cls.tmp)
        cls.log = os.path.join(cls.tmp, "claude-calls.jsonl")
        os.environ["EDU4SELF_CLAUDE"] = os.path.join(ENGINE, "tests", "fake_claude.py")
        os.environ["FAKE_CLAUDE_LOG"] = cls.log
        cls.port = free_port()
        cls.httpd = server.make_server(cls.vault, cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for k in ("EDU4SELF_CLAUDE", "FAKE_CLAUDE_LOG", "FAKE_CLAUDE_SLEEP", "FAKE_CLAUDE_FAIL"):
            os.environ.pop(k, None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    req = ServerTest.req

    def wait_idle(self, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            code, d, _ = self.req("GET", "/api/claude")
            if not d["busy"]:
                return d
            time.sleep(0.05)
        self.fail("claude run never finished")

    def calls(self):
        with open(self.log) as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_grade_runs_claude_in_the_vault_and_checks_after(self):
        sub = {"topic": "how-learning-works", "task": "hlw-lesson-01", "kind": "answers", "fields": {"1": "x"}}
        self.assertEqual(self.req("POST", "/api/inbox", sub)[0], 201)
        code, d, _ = self.req("GET", "/api/claude")
        self.assertTrue(d["available"])
        code, d, _ = self.req("POST", "/api/claude", {"kind": "grade"})
        self.assertEqual(code, 202, d)
        d = self.wait_idle()
        kinds = [e["kind"] for e in d["events"]]
        self.assertIn("tool", kinds)
        self.assertIn("text", kinds)
        self.assertEqual(kinds[-1], "check", kinds)
        self.assertIn("OK", d["events"][-1]["text"])
        self.assertTrue(any(e["kind"] == "done" for e in d["events"]))
        # what Claude wrote is what the dashboard shows
        code, st, _ = self.req("GET", "/api/state")
        self.assertEqual(st["inbox"]["pending"], [])
        call = self.calls()[-1]
        self.assertEqual(os.path.realpath(call["cwd"]), os.path.realpath(self.vault))
        self.assertIn("check my inbox", call["args"][call["args"].index("-p") + 1])
        # locked down, because a lesson Claude grades may come from a stranger (see claude_args)
        args = call["args"]
        flag = lambda f: args[args.index(f) + 1].split(",")
        self.assertEqual(args[args.index("--permission-mode") + 1], "acceptEdits")
        self.assertNotIn("--dangerously-skip-permissions", args)
        allowed, denied = flag("--allowedTools"), flag("--disallowedTools")
        # no bare file tools: a bare "Write" or "Read" rule means any path on the computer
        for bare in ("Read", "Edit", "Write", "MultiEdit", "Glob", "Grep", "Bash"):
            self.assertNotIn(bare, allowed)
        self.assertFalse(any(a.startswith("Bash") for a in allowed), allowed)
        self.assertIn("Bash", denied)
        for f in ("CLAUDE.md", ".claude/**", ".mcp.json"):
            self.assertIn("Write(./%s)" % f, denied)
            self.assertIn("Edit(./%s)" % f, denied)
        self.assertNotIn("WebFetch", allowed)      # grading: nothing it reads can leave
        self.assertIn("WebFetch", denied)
        self.assertIn("--strict-mcp-config", args)

    def test_chat_keeps_one_conversation_until_reset(self):
        self.assertEqual(self.req("POST", "/api/claude/reset", {})[0], 200)
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "hello"})[0], 202)
        first = self.wait_idle()
        self.assertTrue(any(e["kind"] == "you" and e["text"] == "hello" for e in first["events"]))
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "and again"})[0], 202)
        self.wait_idle()
        a, b = self.calls()[-2:]
        self.assertNotIn("--resume", a["args"])
        self.assertIn("WebFetch", a["args"][a["args"].index("--allowedTools") + 1].split(","))   # chat may look things up
        self.assertIn("--resume", b["args"])
        self.assertEqual(self.req("POST", "/api/claude/reset", {})[0], 200)
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "fresh"})[0], 202)
        self.wait_idle()
        self.assertNotIn("--resume", self.calls()[-1]["args"])

    def test_a_new_topic_starts_a_fresh_conversation_with_the_teach_skill(self):
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "warm up"})[0], 202)
        self.wait_idle()
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "topic", "text": "Spanish for a move to Madrid"})[0], 202)
        self.wait_idle()
        call = self.calls()[-1]
        prompt = call["args"][call["args"].index("-p") + 1]
        self.assertIn("teach", prompt)
        self.assertIn("Spanish for a move to Madrid", prompt)
        self.assertNotIn("--resume", call["args"])

    def test_one_run_at_a_time_and_bad_requests(self):
        os.environ["FAKE_CLAUDE_SLEEP"] = "0.6"
        try:
            self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "slow"})[0], 202)
            code, d, _ = self.req("POST", "/api/claude", {"kind": "grade"})
            self.assertEqual(code, 409)
            self.assertIn("busy", d["error"])
            self.wait_idle()
        finally:
            os.environ.pop("FAKE_CLAUDE_SLEEP")
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "dance"})[0], 400)
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": ""})[0], 400)
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "x" * 5001})[0], 400)
        # another site, or a sandboxed page, can't start the agent
        code, _, _ = self.req("POST", "/api/claude", {"kind": "grade"}, headers={"Origin": "null"})
        self.assertEqual(code, 403)
        code, _, _ = self.req("GET", "/api/claude", headers={"Origin": "null"})
        self.assertEqual(code, 403)

    def test_a_failed_run_says_so(self):
        os.environ["FAKE_CLAUDE_FAIL"] = "1"
        try:
            self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "break"})[0], 202)
            d = self.wait_idle()
        finally:
            os.environ.pop("FAKE_CLAUDE_FAIL")
        self.assertTrue(any(e["kind"] == "error" for e in d["events"]), d["events"])

    def test_no_claude_installed(self):
        old = os.environ["EDU4SELF_CLAUDE"]
        os.environ["EDU4SELF_CLAUDE"] = os.path.join(self.tmp, "nope")
        try:
            self.assertFalse(self.req("GET", "/api/claude")[1]["available"])
            self.assertEqual(self.req("POST", "/api/claude", {"kind": "grade"})[0], 503)
        finally:
            os.environ["EDU4SELF_CLAUDE"] = old

    def test_vault_pages_are_sandboxed(self):
        # a lesson (maybe one someone shared) can't act as the dashboard: no API calls, no agent
        code, _, r = self.req("GET", "/vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html")
        self.assertEqual(code, 200)
        self.assertIn("sandbox", r.getheader("Content-Security-Policy") or "")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-cli-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_writes_a_working_vault_and_remembers_it(self):
        vault, env = make_vault(self.tmp)
        self.assertEqual(read_json(os.path.join(self.tmp, "cfg", "settings.json"))["vault"], vault)
        with open(os.path.join(vault, "CLAUDE.md")) as fh:
            claude = fh.read()
        with open(os.path.join(vault, "AGENTS.md")) as fh:
            agents = fh.read()
        self.assertNotIn("{{", claude)
        self.assertIn("docs/PROTOCOL.md", claude)
        self.assertEqual(claude, agents)
        r = subprocess.run([sys.executable, CLI, "check"], env=env, stdout=subprocess.PIPE, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_home_note_links_the_port_the_vault_was_made_for(self):
        vault, env = make_vault(self.tmp, "--port", "4801")
        with open(os.path.join(vault, "Home.md")) as fh:
            home = fh.read()
        self.assertIn("http://127.0.0.1:4801", home)
        self.assertNotIn("{{", home)

    def test_check_catches_a_bad_config(self):
        # an agent that hand-edits config.json must hear about a mistake; the dashboard would
        # otherwise fall back to defaults without a word
        vault, env = make_vault(self.tmp)
        cfg_path = os.path.join(vault, "_system", "config.json")
        check = lambda: subprocess.run([sys.executable, CLI, "check"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with open(cfg_path, "w") as fh:
            json.dump({"name": "Kim", "goals": {"day_minutes": 5}}, fh)
        r = check()
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("daily goal", r.stdout)
        with open(cfg_path, "w") as fh:
            fh.write("{not json")
        self.assertNotEqual(check().returncode, 0)
        with open(cfg_path, "w") as fh:
            json.dump({"music": {"file": "missing.mp3"}}, fh)
        r = check()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("missing.mp3", r.stdout)
        with open(cfg_path, "w") as fh:
            json.dump({"name": "Kim", "goals": {"day_minutes": 90}, "bar": {"names": [["The Night Shift", ""]]}}, fh)
        r = check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_new_vault_starts_with_a_running_plan(self):
        vault, _ = make_vault(self.tmp)
        with open(os.path.join(vault, "PLAN.md")) as fh:
            plan = fh.read()
        self.assertNotIn("{{", plan)
        self.assertIn("Retrieval beats rereading", plan, "the plan lists the example topic's units")
        with open(os.path.join(vault, "CLAUDE.md")) as fh:
            claude = fh.read()
        self.assertIn("PLAN.md", claude, "the tutor is told to keep it")
        self.assertIn("two units fully written", claude, "and to stay two units ahead")
        empty, _ = make_vault(os.path.join(self.tmp, "b"), "--no-example")
        with open(os.path.join(empty, "PLAN.md")) as fh:
            plan = fh.read()
        self.assertNotIn("How learning works", plan, "no units from a topic that isn't there")
        self.assertNotIn("{{", plan)
        self.assertIn("## Changes", plan)

    def test_init_refuses_a_folder_with_files_in_it(self):
        vault, env = make_vault(self.tmp)
        r = subprocess.run([sys.executable, CLI, "init", vault], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("isn't empty", r.stderr)

    def test_no_example(self):
        vault, env = make_vault(self.tmp, "--no-example")
        self.assertFalse(os.path.exists(os.path.join(vault, "how-learning-works")))
        self.assertEqual(read_json(os.path.join(vault, "_system", "state.json"))["topics"], [])
        self.assertEqual(subprocess.run([sys.executable, CLI, "check"], env=env, stdout=subprocess.PIPE).returncode, 0)

    def test_service_files_point_at_this_engine_and_vault(self):
        cli = load_cli()
        plist = cli.launchd_plist("/tmp/my vault & co", 4800)
        self.assertIn("<string>/tmp/my vault &amp; co</string>", plist)
        self.assertIn(os.path.join(APP, "server.py"), plist)
        self.assertIn("<string>4800</string>", plist)
        unit = cli.systemd_unit("/tmp/my vault", 4800)
        self.assertIn('--vault "/tmp/my vault" --port 4800', unit)

    def test_service_can_find_claude(self):
        # a service starts with a bare PATH; the files must carry the folder claude lives in
        bin_dir = os.path.join(self.tmp, "my bin")
        os.makedirs(bin_dir)
        fake = os.path.join(bin_dir, "claude")
        with open(fake, "w") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(fake, 0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = bin_dir + os.pathsep + old
        try:
            cli = load_cli()
            plist = cli.launchd_plist("/tmp/v", 4800)
            unit = cli.systemd_unit("/tmp/v", 4800)
        finally:
            os.environ["PATH"] = old
        m = re.search(r"<key>PATH</key>\s*<string>([^<]*)</string>", plist)
        self.assertTrue(m, plist)
        self.assertEqual(m.group(1).split(os.pathsep)[0], bin_dir)
        self.assertIn('Environment="PATH=%s' % bin_dir, unit)
        plistlib.loads(plist.encode())   # still a valid plist


class RepoTest(unittest.TestCase):
    """Copies and version numbers that must agree across the repo."""

    def test_plugin_protocol_matches_docs(self):
        with open(os.path.join(ENGINE, "docs", "PROTOCOL.md")) as a, open(os.path.join(ENGINE, "plugin", "skills", "check-inbox", "PROTOCOL.md")) as b:
            self.assertEqual(a.read(), b.read(), "run: cp docs/PROTOCOL.md plugin/skills/check-inbox/PROTOCOL.md")

    def test_versions_agree(self):
        plugin = read_json(os.path.join(ENGINE, "plugin", ".claude-plugin", "plugin.json"))
        self.assertEqual(plugin["version"], server.VERSION)
        with open(os.path.join(ENGINE, "CHANGELOG.md")) as fh:
            self.assertIn("## %s" % server.VERSION, fh.read())

    def test_marketplace_points_at_the_plugin(self):
        m = read_json(os.path.join(ENGINE, ".claude-plugin", "marketplace.json"))
        entry = m["plugins"][0]
        self.assertEqual(entry["name"], read_json(os.path.join(ENGINE, entry["source"], ".claude-plugin", "plugin.json"))["name"])


if __name__ == "__main__":
    unittest.main()
