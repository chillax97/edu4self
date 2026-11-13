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
                  "/vault/_system/keys/how-learning-works/hlw-lesson-01.md",       # answer keys stay off the page
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
        body = {"topic": "how-learning-works", "task": "hlw-lesson-01", "kind": "answers", "fields": {"Q": "A"}, "confidence": "shaky"}
        code, d, _ = self.req("POST", "/api/inbox", body)
        self.assertEqual(code, 201)
        saved = [json.loads(l) for l in open(self.sys_path("inbox.jsonl"), encoding="utf-8") if l.strip()]
        self.assertEqual([e for e in saved if e["id"] == d["id"]][0]["confidence"], "shaky")
        code, _, _ = self.req("POST", "/api/withdraw", {"id": d["id"]})
        self.assertEqual(code, 200)
        code, _, _ = self.req("POST", "/api/withdraw", {"id": d["id"]})
        self.assertEqual(code, 404)

    def test_bad_submissions(self):
        good = {"topic": "how-learning-works", "task": "t", "kind": "answers", "fields": {"Q": "A"}, "confidence": "solid"}
        sure = "say how sure you are: guessed, shaky or solid"
        for change, msg in (({"topic": "nope"}, "unknown topic"), ({"kind": "grade"}, "bad kind"),
                            ({"task": "../x"}, "bad task id"), ({"fields": {"Q": " "}}, "no answers"),
                            ({"fields": {"x" * 1001: "A"}}, "bad field"),
                            ({"confidence": None}, sure), ({"confidence": "certain"}, sure),
                            ({"kind": "done", "confidence": ""}, sure)):
            code, d, _ = self.req("POST", "/api/inbox", dict(good, **change))
            self.assertEqual((code, d["error"]), (400, msg))
        self.assertEqual(self.req("POST", "/api/inbox", dict(good, fields={"x" * 1000: "A"}))[0], 201)
        note = {"topic": "general", "task": "note", "kind": "note", "note": "a question"}
        self.assertEqual(self.req("POST", "/api/inbox", note)[0], 201, "a note isn't asked how sure")

    def test_calculator_history_rides_with_the_answer(self):
        good = {"topic": "how-learning-works", "task": "hlw-lesson-01", "kind": "answers", "fields": {"Q": "A"}, "confidence": "solid"}
        calc = [{"expr": "2*32*128*2", "result": "16384"}, {"expr": "(1+2)*3^2", "result": "27"}]
        code, d, _ = self.req("POST", "/api/inbox", dict(good, calc=calc))
        self.assertEqual(code, 201)
        saved = [json.loads(l) for l in open(self.sys_path("inbox.jsonl"), encoding="utf-8") if l.strip()]
        self.assertEqual([e for e in saved if e["id"] == d["id"]][0]["calc"], calc)
        code, d, _ = self.req("POST", "/api/inbox", dict(good, calc=[]))
        saved = [json.loads(l) for l in open(self.sys_path("inbox.jsonl"), encoding="utf-8") if l.strip()]
        self.assertNotIn("calc", [e for e in saved if e["id"] == d["id"]][0], "an empty history sends nothing")
        self.assertEqual(self.req("POST", "/api/inbox", dict(good, calc=[{"expr": "1", "result": "1"}] * 50))[0], 201)
        for bad in ([{"expr": "1", "result": "1"}] * 51, [{"expr": "x" * 201, "result": "1"}], [{"expr": "1", "result": "9" * 101}],
                    "2*3", [["2*3", "6"]], [{"expr": "1"}], [{"expr": "1", "result": 1}], [{"expr": "1", "result": "1", "more": "x"}]):
            code, d, _ = self.req("POST", "/api/inbox", dict(good, calc=bad))
            self.assertEqual((code, d["error"]), (400, "bad calculator history"), bad)

    def test_calibration_counts_only_graded_answers(self):
        state = {"topics": [{"history": [
            {"inbox": "a", "evidence": True}, {"inbox": "b", "evidence": False}, {"inbox": "c", "evidence": True},
            {"inbox": "d", "evidence": True}, {"title": "no link", "evidence": True}]}]}
        entries = [{"id": "a", "confidence": "solid"}, {"id": "b", "confidence": "solid"}, {"id": "c", "confidence": "shaky"},
                   {"id": "d"}, {"id": "e", "confidence": "solid"}]          # d: from before the question; e: not graded yet
        c = server.calibration(state, entries)
        self.assertEqual(c["rated"], 3)
        self.assertEqual(c["solid"], {"n": 2, "passed": 1})
        self.assertEqual(c["shaky"], {"n": 1, "passed": 1})
        self.assertEqual(c["guessed"], {"n": 0, "passed": 0})

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

    def test_a_sign_subtitle_is_a_string_or_a_short_list_of_strings(self):
        def names(sub):
            return server.clean_config({"bar": {"names": [["The Night Shift", sub]]}})["bar"]["names"]
        self.assertEqual(names("line one"), [["The Night Shift", "line one"]], "a string stays a string")
        self.assertEqual(names(["line one", "line two"]), [["The Night Shift", ["line one", "line two"]]])
        self.assertEqual(len(names(["x"] * 20)[0][1]), 20)
        for bad, msg in ((["x"] * 21, "1 to 20"), ([], "1 to 20"), (["x" * 81], "at most 80"),
                         (["fine", 7], "at most 80"), ("x" * 81, "at most 80")):
            with self.assertRaises(ValueError, msg=bad) as cm:
                names(bad)
            self.assertIn(msg, str(cm.exception))

    def test_room_sounds_are_off_until_turned_on(self):
        self.assertIs(server.clean_config({})["room_sounds"], False)
        self.assertIs(server.clean_config({"room_sounds": True})["room_sounds"], True)

    def test_an_update_keeps_every_setting_the_learner_saved(self):
        # what Settings in 1.2 wrote, with every choice away from the default
        saved = {"name": "Ada", "view": "classic", "theme": "library", "theme_lessons": False, "gifts": False,
                 "reminders": {"notify": True, "mail": False}, "goals": {"day_minutes": 45, "week_days": 6},
                 "blocks": {"presets": [15, 40], "kinds": [{"id": "maths", "label": "Maths", "color": "amber", "minutes": 30}]},
                 "water": {"every": 30}, "obsidian": {"enabled": True, "vault": "notes"},
                 "bar": {"names": [["Ada's", "open late"], ["The Night Shift", ["line one", "line two"]]], "voices": {}, "gags": False, "lines": []},
                 "music": {"source": "scape", "scape": "rain", "stream": {"url": "", "name": ""}, "file": "",
                           "title": "", "subtitle": "", "autoplay": True}}
        now = server.clean_config(json.loads(json.dumps(saved)))

        def kept(a, b, where=""):
            for k, v in a.items():
                if where + k == "reminders.notify":
                    continue                              # the desktop notification is gone, so is its switch
                self.assertIn(k, b, where + k)
                if isinstance(v, dict):
                    kept(v, b[k], where + k + ".")
                else:
                    self.assertEqual(b[k], v, where + k)
        kept(saved, now)
        self.assertEqual(server.clean_config({})["reminders"]["mail"], True, "never chosen: the default applies")
        self.assertIsNone(server.clean_config({})["gifts"], "never chosen: ask")

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
            r = subprocess.run([sys.executable, os.path.join(APP, "validate_state.py"), self.vault], stdout=subprocess.PIPE, encoding="utf-8")
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

    def test_an_old_single_file_config_plays_as_a_list_of_one(self):
        old = {"music": {"file": "Night-Drive.m4a", "title": "Night Drive", "subtitle": "no lyrics"}}
        m = server.clean_config(json.loads(json.dumps(old)))["music"]
        self.assertEqual(m["files"], [{"file": "Night-Drive.m4a", "title": "Night Drive"}])
        self.assertEqual((m["source"], m["file"], m["title"], m["subtitle"], m["autoplay"]),
                         ("file", "Night-Drive.m4a", "Night Drive", "no lyrics", True), "plays exactly as before")
        self.assertEqual(server.clean_config({"music": {"file": "Night_Drive-2.mp3"}})["music"]["files"][0]["title"],
                         "Night Drive 2", "no title: the file name")
        self.assertEqual(server.clean_config({})["music"]["files"], [])

    def test_loading_an_old_config_never_rewrites_it(self):
        path = self.sys_path("config.json")
        os.makedirs(self.sys_path("music"), exist_ok=True)
        with open(self.sys_path("music", "Old.mp3"), "wb") as fh:
            fh.write(b"ID3" + b"\0" * 64)
        raw = json.dumps({"music": {"file": "Old.mp3", "title": "Old one"}})
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(raw)
        try:
            d = self.req("GET", "/api/config")[1]
            self.assertEqual(d["config"]["music"]["files"], [{"file": "Old.mp3", "title": "Old one"}])
            self.assertEqual(self.req("GET", "/music")[0], 200)
            self.req("GET", "/api/state")
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), raw, "only a save in Settings writes the new shape")
        finally:
            os.remove(self.sys_path("music", "Old.mp3"))
            self.req("POST", "/api/config", {"reset": True})
            self.req("POST", "/api/config", {"config": {}})

    def test_music_files_round_trip(self):
        os.makedirs(self.sys_path("music"), exist_ok=True)
        names = ["b.mp3", "a.ogg", "c.flac"]
        for n in names:
            with open(self.sys_path("music", n), "wb") as fh:
                fh.write(b"x")
        files = [{"file": "b.mp3", "title": "Second song"}, {"file": "a.ogg", "title": ""}, {"file": "c.flac", "title": "Third"}]
        try:
            code, d, _ = self.req("POST", "/api/config", {"config": {"music": {"source": "file", "files": files, "subtitle": "mix"}}})
            self.assertEqual(code, 200, d)
            want = [{"file": "b.mp3", "title": "Second song"}, {"file": "a.ogg", "title": "a"}, {"file": "c.flac", "title": "Third"}]
            on_disk = read_json(self.sys_path("config.json"))["music"]
            self.assertEqual(on_disk["files"], want, "order and titles kept, a blank title is the file name")
            self.assertEqual((on_disk["file"], on_disk["title"]), ("b.mp3", "Second song"))
            self.assertEqual(server.clean_config({"music": on_disk})["music"], on_disk, "it reads back the same")
            self.assertEqual(self.req("GET", "/api/config")[1]["config"]["music"]["files"], want)
            # a listed song must be on disk
            code, d, _ = self.req("POST", "/api/config", {"config": {"music": {"source": "file", "files": [{"file": "gone.mp3"}]}}})
            self.assertEqual(code, 400)
            self.assertIn("gone.mp3", d["error"])
        finally:
            for n in names:
                os.remove(self.sys_path("music", n))
            self.req("POST", "/api/config", {"config": {}})

    def test_the_song_list_is_checked_and_capped(self):
        def files(fs):
            return server.clean_config({"music": {"source": "file", "files": fs}})["music"]["files"]
        self.assertEqual(len(files([{"file": "t%d.mp3" % i} for i in range(server.MAX_TRACKS)])), 100)
        for bad, msg in (([{"file": "t%d.mp3" % i} for i in range(101)], "at most 100 songs"),
                         ("a.mp3", "a list"),
                         (["a.mp3"], "each song"),
                         ([{"file": "../a.mp3"}], "bad music file name"),
                         ([{"file": "a.txt"}], "bad music file name"),
                         ([{"file": "a.mp3"}, {"file": "a.mp3"}], "twice"),
                         ([{"file": "a.mp3", "title": "x" * 81}], "song title"),
                         ([], "upload a song first")):
            with self.assertRaises(ValueError, msg=bad) as cm:
                files(bad)
            self.assertIn(msg, str(cm.exception), bad)

    def test_a_full_jukebox_refuses_one_more_upload(self):
        with open(self.sys_path("config.json"), "w", encoding="utf-8") as fh:
            json.dump({"music": {"files": [{"file": "t%d.mp3" % i} for i in range(server.MAX_TRACKS)]}}, fh)
        try:
            code, d, _ = self.upload("one-more.mp3", b"ID3" + b"\0" * 64)
            self.assertEqual(code, 409)
            self.assertIn("100 songs", d["error"])
        finally:
            self.req("POST", "/api/config", {"config": {}})

    def test_broken_config_file_falls_back_to_defaults(self):
        with open(self.sys_path("config.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        try:
            code, d, _ = self.req("GET", "/api/state")
            self.assertEqual(code, 200)
            self.assertEqual(d["config"]["goals"]["day_minutes"], 60)
            self.assertIn("config.json ignored", d["server"]["config_error"])
        finally:
            self.req("POST", "/api/config", {"reset": True})

    # ------------------------------------------------------------ music
    def upload(self, name, data, ctype="audio/mpeg"):
        return self.req("POST", "/api/music", raw=data, headers={"Content-Type": ctype, "X-Filename": name})

    def test_music_upload_seek_add_remove(self):
        data = b"ID3" + bytes(range(256)) * 40
        self.assertEqual(self.upload("notes.txt", data, "text/plain")[0], 415)
        code, d, _ = self.upload("My%20Song!.mp3", data)
        self.assertEqual(code, 201)
        self.assertEqual(d["config"]["music"]["files"], [{"file": "My-Song.mp3", "title": "My Song"}])
        self.assertEqual(d["config"]["music"]["file"], "My-Song.mp3", "the first song, for older readers")
        self.assertEqual(d["config"]["music"]["source"], "file", "an upload switches the jukebox to it")
        code, body, r = self.req("GET", "/music", headers={"Range": "bytes=100-199"})
        self.assertEqual((code, body), (206, data[100:200]))
        self.assertEqual(r.getheader("Content-Range"), "bytes 100-199/%d" % len(data))
        self.assertEqual(self.req("GET", "/music", headers={"Range": "bytes=999999-"})[0], 416)
        # a second upload is added to the list; the first stays
        m4a = b"\0\0\0\x20ftypM4A " + data
        self.assertEqual(self.upload("other.m4a", m4a, "audio/mp4")[0], 201)
        self.assertEqual(sorted(os.listdir(self.sys_path("music"))), ["My-Song.mp3", "other.m4a"])
        self.assertEqual(self.req("GET", "/music?f=other.m4a")[1], m4a)
        self.assertEqual(self.req("GET", "/music?f=nope.mp3")[0], 404, "only listed songs are served")
        # reset keeps the songs; remove_music deletes them
        code, d, _ = self.req("POST", "/api/config", {"reset": True})
        self.assertEqual([t["file"] for t in d["config"]["music"]["files"]], ["My-Song.mp3", "other.m4a"])
        code, d, _ = self.req("POST", "/api/config", {"config": d["config"], "remove_music": True})
        self.assertEqual((code, d["config"]["music"]["files"], d["config"]["music"]["file"]), (200, [], ""))
        self.assertEqual(d["config"]["music"]["source"], "scape", "no file left: back to the soundscape")
        self.assertEqual(os.listdir(self.sys_path("music")), [])
        self.assertEqual(self.req("GET", "/music")[0], 404)

    def test_a_same_name_upload_gets_a_suffix_and_overwrites_nothing(self):
        try:
            one, two = b"RIFF\0\0\0\0WAVE" + b"1" * 100, b"RIFF\0\0\0\0WAVE" + b"2" * 100
            self.assertEqual(self.upload("Tone.wav", one, "audio/wav")[0], 201)
            code, d, _ = self.upload("Tone.wav", two, "audio/wav")
            self.assertEqual(code, 201)
            self.assertEqual(d["track"], {"file": "Tone-2.wav", "title": "Tone"})
            self.assertEqual([t["file"] for t in d["config"]["music"]["files"]], ["Tone.wav", "Tone-2.wav"])
            with open(self.sys_path("music", "Tone.wav"), "rb") as fh:
                self.assertEqual(fh.read(), one, "the first file is untouched")
            with open(self.sys_path("music", "Tone-2.wav"), "rb") as fh:
                self.assertEqual(fh.read(), two)
            self.assertEqual(self.upload("Tone.wav", one, "audio/wav")[1]["track"]["file"], "Tone-3.wav")
        finally:
            self.req("POST", "/api/config", {"config": {}, "remove_music": True})

    def test_a_non_audio_upload_is_refused(self):
        # an audio name and type, but the bytes are a text file: refused, and nothing is kept
        code, d, _ = self.upload("song.mp3", b"just some notes, not music\n" * 50)
        self.assertEqual(code, 415)
        self.assertIn("isn't an audio file", d["error"])
        self.assertEqual(self.upload("song.exe", b"ID3" + b"x" * 100, "application/octet-stream")[0], 415)
        self.assertEqual(self.upload("song.mp3", b"ID3" + b"x" * 100, "text/html")[0], 415)
        music = self.sys_path("music")
        self.assertEqual(os.listdir(music) if os.path.isdir(music) else [], [])
        for head in (b"ID3", b"\xff\xfb\x90", b"\xff\xf1\x50", b"\0\0\0\x18ftypM4A ", b"OggS", b"fLaC",
                     b"\x1a\x45\xdf\xa3", b"RIFF\0\0\0\0WAVE"):
            self.assertTrue(server.looks_like_audio(head + b"\0" * 16), head)
        for head in (b"<html>", b"PK\3\4", b"%PDF-1.4", b"RIFF\0\0\0\0AVI ", b"\0" * 16):
            self.assertFalse(server.looks_like_audio(head), head)

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

    # ------------------------------------------------------------ keep-alive (HTTP/1.1)
    def keepalive(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def on(self, c, method, path, raw=None, headers=None):
        """One request on an open connection; the body is read to its end, as a browser would."""
        h = {"Host": "127.0.0.1:%d" % self.port}
        h.update(headers or {})
        c.request(method, path, body=raw, headers=h)
        r = c.getresponse()
        return r, r.read()

    def test_one_connection_carries_many_requests(self):
        data = b"ID3" + bytes(range(256)) * 40
        try:
            c = self.keepalive()
            r, _ = self.on(c, "GET", "/api/health")
            self.assertEqual((r.status, r.version), (200, 11))
            sock = c.sock
            self.assertIsNotNone(sock)
            steps = [
                ("GET", "/", None, None, 200),
                ("GET", "/fonts/monoton.woff2", None, None, 200),
                ("GET", "/theme/lesson.css", None, None, 200),
                ("GET", "/api/state", None, None, 200),
                ("GET", "/api/hints?task=nope", None, None, 404),        # an error, still on this connection
                ("POST", "/api/inbox", b"{}", {"Content-Type": "application/json"}, 400),
                ("POST", "/api/music", data, {"Content-Type": "audio/mpeg", "X-Filename": "keep.mp3"}, 201),
                ("GET", "/music", None, {"Range": "bytes=100-199"}, 206),
                ("GET", "/music", None, {"Range": "bytes=999999-"}, 416),
                ("GET", "/music", None, None, 200),
                ("GET", "/api/health", None, None, 200),
            ]
            for method, path, raw, headers, want in steps:
                r, body = self.on(c, method, path, raw, headers)
                self.assertEqual(r.status, want, path)
                self.assertFalse(r.will_close, "%s %s closed the connection" % (method, path))
                self.assertIs(c.sock, sock, "%s %s: a new connection was opened" % (method, path))
                if want == 206:
                    self.assertEqual(body, data[100:200])
                if path == "/music" and want == 200:
                    self.assertEqual(body, data)
            c.close()
        finally:
            self.req("POST", "/api/config", {"config": {}, "remove_music": True})

    def test_a_redirect_says_it_has_no_body(self):
        cfg = server.load_config()[0]
        cfg["obsidian"] = {"enabled": True, "vault": "My Vault"}
        server.save_config(cfg)
        try:
            c = self.keepalive()
            r, body = self.on(c, "GET", "/vault/how-learning-works/MISSION.md")
            self.assertEqual((r.status, r.getheader("Content-Length"), body), (302, "0", b""))
            self.assertFalse(r.will_close)
            self.assertEqual(self.on(c, "GET", "/api/health")[0].status, 200)
            c.close()
        finally:
            cfg["obsidian"] = {"enabled": False, "vault": ""}
            server.save_config(cfg)

    def test_a_plain_404_closes_and_the_next_request_still_works(self):
        c = self.keepalive()
        r, _ = self.on(c, "GET", "/no-such-page")
        self.assertEqual(r.status, 404)
        self.assertIsNotNone(r.getheader("Content-Length"))
        self.assertTrue(r.will_close, "send_error says Connection: close")
        self.assertEqual(self.on(c, "GET", "/api/health")[0].status, 200, "http.client reconnects")
        c.close()

    def test_a_refusal_before_reading_the_body_closes_the_connection(self):
        # the unread body is still on the line; reading it as the next request would be wrong
        c = self.keepalive()
        r, _ = self.on(c, "POST", "/api/inbox", b'{"x": 1}', {"Content-Type": "text/plain"})
        self.assertEqual(r.status, 415)
        self.assertTrue(r.will_close)
        r, _ = self.on(c, "POST", "/api/music", b"ID3" + b"x" * 100, {"Content-Type": "text/html", "X-Filename": "a.mp3"})
        self.assertEqual(r.status, 415)
        self.assertTrue(r.will_close)
        self.assertEqual(self.on(c, "GET", "/api/health")[0].status, 200)
        c.close()

    def test_an_idle_connection_is_closed_by_the_server(self):
        old = server.Handler.timeout
        server.Handler.timeout = 0.3
        try:
            c = self.keepalive()
            self.assertEqual(self.on(c, "GET", "/api/health")[0].status, 200)
            c.sock.settimeout(5)
            self.assertEqual(c.sock.recv(1), b"", "the server hung up on the idle connection")
            c.close()
        finally:
            server.Handler.timeout = old


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
        return subprocess.run([sys.executable, os.path.join(APP, "validate_state.py"), self.vault], stdout=subprocess.PIPE, encoding="utf-8")

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
        self.state["coach"]["voices"] = [{"voice": "narrator", "text": "x"}]
        out = self.check(self.state).stdout
        for msg in ("duplicate task id", "missing file", "says nothing about how it unlocks", "level must be 0..4", "coach.voices"):
            self.assertIn(msg, out)

    def test_a_long_coach_note_warns_but_passes(self):
        self.state["coach"]["body"] = "word " * 61
        self.state["coach"]["voices"] = [{"voice": "logic", "text": "One beat."}] * 5
        r = self.check(self.state)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("coach.body is 61 words", r.stdout)
        self.assertIn("coach.voices has 5 lines", r.stdout)
        self.state["coach"]["body"] = "One change per run. Up next: recall check 06."
        self.state["coach"]["voices"] = self.state["coach"]["voices"][:3]
        self.assertNotIn("note:", self.check(self.state).stdout)

    def test_history_may_name_the_inbox_entry_it_grades(self):
        h = self.state["topics"][0]["history"][0]
        h["inbox"] = "7e6286b84a"
        self.assertEqual(self.check(self.state).returncode, 0)
        h["inbox"] = 12
        r = self.check(self.state)
        self.assertEqual(r.returncode, 1)
        self.assertIn("inbox must be the id", r.stdout)

    def test_history_may_record_a_checklist(self):
        h = self.state["topics"][0]["history"][0]
        h["points"] = {"1a": True, "2a": False}
        h["errors"] = ["says rereading builds storage strength"]
        self.assertEqual(self.check(self.state).returncode, 0)
        h["points"] = {"1": True, "2": False}          # a key that lists no point ids: one per question
        self.assertEqual(self.check(self.state).returncode, 0)
        for bad in (["1a"], {"met": ["1a"]}, {"1a": "yes"}, {"1a": 1}, {}):
            h["points"], h["errors"] = bad, []
            r = self.check(self.state)
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("points", r.stdout)
        h["points"] = {"1a": True}
        for bad in ("none", [1], {"x": "y"}):
            h["errors"] = bad
            r = self.check(self.state)
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn("errors must be a list", r.stdout)

    def keyed_grade(self, **fields):
        """A graded answer to the example's lesson (which ships with an answer key: points 1a to 3b)."""
        entry = {"id": "ab12cd34ef", "ts": "2026-01-02T10:00:00", "topic": "how-learning-works", "task": "hlw-lesson-01",
                 "kind": "answers", "fields": {"q": "a"}}
        inbox = os.path.join(self.vault, "_system", "inbox.jsonl")
        with open(inbox, encoding="utf-8") as fh:
            seen = entry["id"] in fh.read()
        if not seen:
            with open(inbox, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        hist = self.state["topics"][0]["history"]
        hist[:] = [x for x in hist if x.get("inbox") != entry["id"]]      # one grade per call: the last one
        h = {"date": "2026-01-02", "kind": "lesson", "title": "Lesson 01", "detail": "d", "inbox": entry["id"]}
        h.update(fields)
        hist.append(h)
        return self.check(self.state)

    def test_a_pass_on_a_keyed_answer_needs_a_full_checklist(self):
        all_met = {"1a": True, "1b": True, "2a": True, "2b": True, "3a": True, "3b": True}
        r = self.keyed_grade(evidence=True, points=all_met, errors=[])
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_keyed_pass_without_a_checklist_fails_the_check(self):
        r = self.keyed_grade(evidence=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("'Lesson 01'", r.stdout)
        self.assertIn("checklist", r.stdout)
        r = self.keyed_grade(evidence=True, points={"1a": True, "1b": True, "2a": True, "2b": True, "3a": True, "3b": True})   # no errors list
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_a_keyed_pass_with_a_missed_point_fails_the_check(self):
        r = self.keyed_grade(evidence=True, points={"1a": True, "1b": False, "2a": True, "2b": True, "3a": True, "3b": True}, errors=[])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("1b", r.stdout)

    def test_a_keyed_pass_with_an_error_fails_the_check(self):
        r = self.keyed_grade(evidence=True, points={"1a": True, "1b": True, "2a": True, "2b": True, "3a": True, "3b": True},
                             errors=["says rereading builds storage strength"])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("rereading", r.stdout)

    def test_a_keyed_checklist_names_every_point_of_the_key(self):
        r = self.keyed_grade(evidence=True, points={"1a": True, "1b": True}, errors=[])     # 2a to 3b left out
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("2a", r.stdout)
        r = self.keyed_grade(evidence=False, points={"1a": True, "9z": False}, errors=[])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("9z", r.stdout)

    def test_a_keyed_answer_that_is_not_a_pass_may_skip_the_checklist(self):
        self.assertEqual(self.keyed_grade(evidence=False).returncode, 0)
        r = self.keyed_grade(evidence=False, points={"1a": True, "1b": False, "2a": True, "2b": True, "3a": True, "3b": True}, errors=["x"])
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_pass_without_a_key_validates_as_before(self):
        self.state["topics"][0]["history"].append({"date": "2026-01-02", "kind": "lesson", "title": "Old", "detail": "d",
                                                   "evidence": True, "inbox": "0000000000"})      # no such inbox entry
        self.assertEqual(self.check(self.state).returncode, 0)
        os.remove(os.path.join(self.vault, "_system", "keys", "how-learning-works", "hlw-lesson-01.md"))
        r = self.keyed_grade(evidence=True)                                                  # the task has no key
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_answer_keys_ship_with_the_example_and_a_stray_key_is_a_note(self):
        keys = os.path.join(self.vault, "_system", "keys", "how-learning-works")
        for task in ("hlw-lesson-01", "hlw-probe-01"):
            with open(os.path.join(keys, task + ".md"), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("Required", text)
            self.assertIn("Not required", text)
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("answer key", r.stdout)
        with open(os.path.join(keys, "no-such-task.md"), "w", encoding="utf-8") as fh:
            fh.write("# Answer key: no-such-task\n")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)             # a note, never an error
        self.assertIn("answer key for a task that isn't in the queue", r.stdout)
        links = subprocess.run([sys.executable, os.path.join(APP, "check_links.py"), self.vault], stdout=subprocess.PIPE,
                               encoding="utf-8")
        self.assertEqual(links.returncode, 0, links.stdout)

    def test_a_task_may_allow_the_calculator(self):
        t = self.state["topics"][0]["queue"][0]
        t["calculator"] = True
        self.assertEqual(self.check(self.state).returncode, 0)
        t["calculator"] = "yes"
        r = self.check(self.state)
        self.assertEqual(r.returncode, 1)
        self.assertIn("calculator must be true or false", r.stdout)

    def test_link_checker_finds_a_broken_link(self):
        with open(os.path.join(self.vault, "Home.md"), "a", encoding="utf-8") as fh:
            fh.write("\n[[how-learning-works/NOPE]]\n")
        r = subprocess.run([sys.executable, os.path.join(APP, "check_links.py"), self.vault], stdout=subprocess.PIPE, encoding="utf-8")
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
        with open(self.log, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_grade_runs_claude_in_the_vault_and_checks_after(self):
        sub = {"topic": "how-learning-works", "task": "hlw-lesson-01", "kind": "answers", "fields": {"1": "x"}, "confidence": "solid"}
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
        for f in ("CLAUDE.md", ".claude/**", ".mcp.json", "_system/edu_trace.py", "**/trace/**"):   # the record and its helper too
            self.assertIn("Write(./%s)" % f, denied)
            self.assertIn("Edit(./%s)" % f, denied)
        self.assertNotIn("WebFetch", allowed)      # grading: nothing it reads can leave
        self.assertIn("WebFetch", denied)
        self.assertIn("--strict-mcp-config", args)

    def test_first_try_grade_is_grade_only_and_fenced(self):
        # nothing to grade yet: refused, nothing runs
        before = len(self.calls()) if os.path.exists(self.log) else 0
        code, d, _ = self.req("POST", "/api/claude", {"kind": "first"})
        self.assertEqual(code, 409, d)
        self.assertEqual(len(self.calls()) if os.path.exists(self.log) else 0, before)
        other = {"topic": "how-learning-works", "task": "hlw-lesson-01", "kind": "answers", "fields": {"1": "x"}, "confidence": "solid"}
        first = {"topic": "how-learning-works", "task": "first-try", "kind": "answers", "fields": {"Why?": "recall sticks"}, "confidence": "shaky"}
        _, o, _ = self.req("POST", "/api/inbox", other)
        _, f, _ = self.req("POST", "/api/inbox", first)
        code, d, _ = self.req("POST", "/api/claude", {"kind": "first"})
        self.assertEqual(code, 202, d)
        d = self.wait_idle()
        self.assertEqual(d["events"][-1]["kind"], "check")
        self.assertIn("OK", d["events"][-1]["text"])
        args = self.calls()[-1]["args"]
        prompt = args[args.index("-p") + 1]
        self.assertIn("first-try", prompt)
        self.assertIn("don't change PLAN.md", prompt)
        self.assertNotIn("check my inbox\"", prompt.split("Leave")[0])   # it isn't the full grading run
        self.assertIn("WebFetch", args[args.index("--disallowedTools") + 1].split(","))   # fenced like grading
        self.assertNotIn("WebFetch", args[args.index("--allowedTools") + 1].split(","))
        self.assertNotIn("--resume", args)   # never joins the chat's conversation
        # only the first try was graded; the other answer still waits for check my inbox
        _, st, _ = self.req("GET", "/api/state")
        self.assertEqual([e["id"] for e in st["inbox"]["pending"]], [o["id"]])
        self.assertTrue(any(h.get("inbox") == f["id"] for h in st["state"]["topics"][0]["history"]))
        self.req("POST", "/api/claude", {"kind": "grade"}); self.wait_idle()   # leave the inbox empty for the other tests

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

    def test_a_new_topic_starts_a_fresh_conversation_with_the_new_topic_skill(self):
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "warm up"})[0], 202)
        self.wait_idle()
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "topic", "text": "Spanish for a move to Madrid"})[0], 202)
        self.wait_idle()
        call = self.calls()[-1]
        prompt = call["args"][call["args"].index("-p") + 1]
        self.assertIn("new-topic skill", prompt)   # edu4self's own skill, which Claude can start by itself
        self.assertNotIn("teach", prompt)          # no outside skill to fall back on
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
        self.login_env()
        os.environ["FAKE_CLAUDE_FAIL"] = "1"
        try:
            self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "break"})[0], 202)
            d = self.wait_idle()
        finally:
            os.environ.pop("FAKE_CLAUDE_FAIL")
        self.assertTrue(any(e["kind"] == "error" for e in d["events"]), d["events"])
        self.assertEqual(self.check_calls().count(["auth", "status"]), 2, "a failed run asks about the login again (it may have run out)")

    def test_no_claude_installed(self):
        old = os.environ["EDU4SELF_CLAUDE"]
        os.environ["EDU4SELF_CLAUDE"] = os.path.join(self.tmp, "nope")
        try:
            self.assertFalse(self.req("GET", "/api/claude")[1]["available"])
            self.assertEqual(self.req("POST", "/api/claude", {"kind": "grade"})[0], 503)
        finally:
            os.environ["EDU4SELF_CLAUDE"] = old

    def check_calls(self):
        if not os.path.exists(self.check_log):
            return []
        with open(self.check_log, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def login_env(self, **env):
        """Run the login check against the fake with these settings, from a clean cache."""
        self.check_log = os.path.join(self.tmp, "check-calls-%s.jsonl" % self.id().rsplit(".", 1)[-1])
        env["FAKE_CLAUDE_CHECK_LOG"] = self.check_log
        for k, v in env.items():
            os.environ[k] = v
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in env])
        server.LOGIN.update(cmd=None, at=0.0, logged_in=None)
        self.addCleanup(server.LOGIN.update, cmd=None, at=0.0, logged_in=None)

    def test_signed_in_claude_is_ready_and_polls_share_one_check(self):
        self.login_env()
        d = self.req("GET", "/api/claude")[1]
        self.assertEqual((d["available"], d["logged_in"], d["problem"]), (True, True, None))
        for _ in range(5):
            self.req("GET", "/api/claude")
        self.assertEqual(self.check_calls(), [["--help"], ["auth", "status"]], "one check for six polls")
        # a forced re-check (the page got focus) runs again, but not more than once every few seconds
        server.LOGIN["at"] -= server.LOGIN_RECHECK + 1
        self.req("GET", "/api/claude?recheck=1")
        self.req("GET", "/api/claude?recheck=1")
        self.assertEqual(len(self.check_calls()), 4)

    def test_signed_out_claude_says_so_and_wont_start(self):
        self.login_env(FAKE_CLAUDE_SIGNED_OUT="1")
        d = self.req("GET", "/api/claude")[1]
        self.assertEqual((d["available"], d["logged_in"], d["problem"]), (True, False, "signed_out"))
        code, d, _ = self.req("POST", "/api/claude", {"kind": "chat", "text": "hi"})
        self.assertEqual(code, 503)
        self.assertIn("claude auth login", d["error"])
        self.assertFalse(os.path.exists(self.log) and any("hi" in c["args"] for c in self.calls()), "no run was started")
        # signing in is picked up by the next start, without waiting for the cache
        os.environ.pop("FAKE_CLAUDE_SIGNED_OUT")
        server.LOGIN["at"] -= server.LOGIN_RECHECK + 1
        self.assertEqual(self.req("POST", "/api/claude", {"kind": "chat", "text": "signed in now"})[0], 202)
        self.wait_idle()
        self.assertIsNone(self.req("GET", "/api/claude")[1]["problem"])

    def test_a_claude_without_auth_status_is_never_handed_it_as_a_prompt(self):
        self.login_env(FAKE_CLAUDE_OLD="1")
        before = len(self.calls()) if os.path.exists(self.log) else 0
        d = self.req("GET", "/api/claude")[1]
        self.assertEqual((d["available"], d["logged_in"], d["problem"]), (True, None, None), "unknown counts as usable")
        self.assertEqual(self.check_calls(), [["--help"]])
        self.assertEqual(len(self.calls()) if os.path.exists(self.log) else 0, before, "no run was started")

    def test_missing_claude_is_reported_without_starting_anything(self):
        self.login_env()
        old = os.environ["EDU4SELF_CLAUDE"]
        os.environ["EDU4SELF_CLAUDE"] = os.path.join(self.tmp, "nope")
        try:
            d = self.req("GET", "/api/claude")[1]
        finally:
            os.environ["EDU4SELF_CLAUDE"] = old
        self.assertEqual((d["available"], d["problem"]), (False, "missing"))
        self.assertIn("not found", d["detail"])          # claude_cli's own words, for the page's note
        self.assertEqual(self.check_calls(), [])

    def test_vault_pages_are_sandboxed(self):
        # a lesson (maybe one someone shared) can't act as the dashboard: no API calls, no agent
        code, _, r = self.req("GET", "/vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html")
        self.assertEqual(code, 200)
        self.assertIn("sandbox", r.getheader("Content-Security-Policy") or "")

    def test_sandboxed_pages_can_load_their_own_fonts_and_nothing_else_cross_origin(self):
        # a sandboxed lesson's origin is "null"; browsers fetch fonts with CORS, so without this the
        # maths in a lesson falls back to plain fonts
        assets = os.path.join(self.vault, "how-learning-works", "assets")
        with open(os.path.join(assets, "Math.woff2"), "wb") as fh:
            fh.write(b"wOF2 not really a font")
        acao = lambda path, origin: self.req("GET", path, headers={"Origin": origin})[2].getheader("Access-Control-Allow-Origin")
        self.assertEqual(acao("/vault/how-learning-works/assets/Math.woff2", "null"), "null")
        self.assertIsNone(acao("/vault/how-learning-works/assets/Math.woff2", "https://example.com"), "other sites: no")
        self.assertIsNone(acao("/vault/how-learning-works/assets/quiz.js", "null"), "fonts only")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-cli-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_doctor_finds_the_plugins_own_skills(self):
        cli, home = load_cli(), os.path.join(self.tmp, "claude")
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = home
        try:
            self.assertFalse(cli.lesson_skill_found())
            for skill in ("skills/write-lesson", "skills/check-inbox"):   # a lone skill is not the plugin
                os.makedirs(os.path.join(home, "plugins/cache/edu4self/edu4self/1.3.0", skill))
                open(os.path.join(home, "plugins/cache/edu4self/edu4self/1.3.0", skill, "SKILL.md"), "w", encoding="utf-8").close()
                self.assertEqual(cli.lesson_skill_found(), skill.endswith("check-inbox"))
        finally:
            if old is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_init_writes_a_working_vault_and_remembers_it(self):
        vault, env = make_vault(self.tmp)
        self.assertEqual(read_json(os.path.join(self.tmp, "cfg", "settings.json"))["vault"], vault)
        with open(os.path.join(vault, "CLAUDE.md"), encoding="utf-8") as fh:
            claude = fh.read()
        with open(os.path.join(vault, "AGENTS.md"), encoding="utf-8") as fh:
            agents = fh.read()
        self.assertNotIn("{{", claude)
        self.assertIn("docs/PROTOCOL.md", claude)
        self.assertEqual(claude, agents)
        r = subprocess.run([sys.executable, CLI, "check"], env=env, stdout=subprocess.PIPE, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_home_note_links_the_port_the_vault_was_made_for(self):
        vault, env = make_vault(self.tmp, "--port", "4801")
        with open(os.path.join(vault, "Home.md"), encoding="utf-8") as fh:
            home = fh.read()
        self.assertIn("http://127.0.0.1:4801", home)
        self.assertNotIn("{{", home)

    def test_check_catches_a_bad_config(self):
        # an agent that hand-edits config.json must hear about a mistake; the dashboard would
        # otherwise fall back to defaults without a word
        vault, env = make_vault(self.tmp)
        cfg_path = os.path.join(vault, "_system", "config.json")
        check = lambda: subprocess.run([sys.executable, CLI, "check"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({"name": "Kim", "goals": {"day_minutes": 5}}, fh)
        r = check()
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("daily goal", r.stdout)
        with open(cfg_path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertNotEqual(check().returncode, 0)
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({"music": {"file": "missing.mp3"}}, fh)
        r = check()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("missing.mp3", r.stdout)
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({"name": "Kim", "goals": {"day_minutes": 90}, "bar": {"names": [["The Night Shift", ""]]}}, fh)
        r = check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_new_vault_starts_with_a_running_plan(self):
        vault, _ = make_vault(self.tmp)
        with open(os.path.join(vault, "PLAN.md"), encoding="utf-8") as fh:
            plan = fh.read()
        self.assertNotIn("{{", plan)
        self.assertIn("Retrieval beats rereading", plan, "the plan lists the example topic's units")
        with open(os.path.join(vault, "CLAUDE.md"), encoding="utf-8") as fh:
            claude = fh.read()
        self.assertIn("PLAN.md", claude, "the tutor is told to keep it")
        self.assertIn("two units fully written", claude, "and to stay two units ahead")
        empty, _ = make_vault(os.path.join(self.tmp, "b"), "--no-example")
        with open(os.path.join(empty, "PLAN.md"), encoding="utf-8") as fh:
            plan = fh.read()
        self.assertNotIn("How learning works", plan, "no units from a topic that isn't there")
        self.assertNotIn("{{", plan)
        self.assertIn("## Changes", plan)

    def test_init_refuses_a_folder_with_files_in_it(self):
        vault, env = make_vault(self.tmp)
        r = subprocess.run([sys.executable, CLI, "init", vault], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("isn't empty", r.stderr)

    def test_gifts_start_undecided_unless_setup_was_told(self):
        vault, _ = make_vault(os.path.join(self.tmp, "g1"))
        self.assertNotIn("gifts", read_json(os.path.join(vault, "_system", "config.json")), "left for the dashboard to ask")
        on, _ = make_vault(os.path.join(self.tmp, "g2"), "--gifts", "on")
        self.assertIs(read_json(os.path.join(on, "_system", "config.json"))["gifts"], True)
        env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg3"), HOME=self.tmp)
        v3 = os.path.join(self.tmp, "g3", "vault")
        r = subprocess.run([sys.executable, CLI, "setup", "--vault", v3, "--name", "T", "--no-service", "--no-open", "--gifts", "off",
                            "--no-plugin"],
                           env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIs(read_json(os.path.join(v3, "_system", "config.json"))["gifts"], False)
        self.assertNotIn("Turn gifts on", r.stdout, "no question without a terminal")

    def test_no_example(self):
        vault, env = make_vault(self.tmp, "--no-example")
        self.assertFalse(os.path.exists(os.path.join(vault, "how-learning-works")))
        self.assertFalse(os.path.exists(os.path.join(vault, "_system", "keys", "how-learning-works")), "nor its answer keys")
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
        with open(fake, "w", encoding="utf-8") as fh:
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
        self.assertIn('Environment="PATH=%s' % bin_dir.replace("\\", "\\\\"), unit)    # systemd wants backslashes doubled
        plistlib.loads(plist.encode())   # still a valid plist


class SetupPluginTest(unittest.TestCase):
    """setup installs the tutor plugin itself, and doctor asks claude whether it's there. A fake claude stands in."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-plugin-")
        self.log = os.path.join(self.tmp, "calls.jsonl")
        self.state = os.path.join(self.tmp, "plugins.json")
        self.env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg"), HOME=self.tmp,
                        CLAUDE_CONFIG_DIR=os.path.join(self.tmp, "claude"), FAKE_CLAUDE_LOG=self.log, FAKE_PLUGIN_STATE=self.state,
                        EDU4SELF_CLAUDE=os.path.join(ENGINE, "tests", "fake_claude_plugin.py"),
                        EDU4SELF_NO_UPDATE_CHECK="1")
        self.env.pop("FAKE_PLUGIN_FAIL", None)
        self.runs = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def setup(self, *extra):
        self.runs += 1
        vault = os.path.join(self.tmp, "vault%d" % self.runs)
        r = subprocess.run([sys.executable, CLI, "setup", "--vault", vault, "--name", "T", "--no-service", "--no-open",
                            "--gifts", "off", *extra], env=self.env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def doctor(self):
        r = subprocess.run([sys.executable, CLI, "doctor", "--port", str(free_port())], env=self.env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        return [l for l in r.stdout.splitlines() if "tutor skills" in l or "edu4self plugin" in l]

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            return [json.loads(l)["args"] for l in fh if l.strip()]

    def changes(self):
        return [a for a in self.calls() if "--json" not in a]

    def test_fresh_install_runs_both_commands_in_order_then_checks(self):
        out = self.setup()
        self.assertEqual(self.changes(), [["plugin", "marketplace", "add", "chillax97/edu4self"], ["plugin", "install", "edu4self@edu4self"]])
        self.assertEqual(self.calls()[-1], ["plugin", "list", "--json"], "checked after installing")
        self.assertIn("Successfully installed plugin", out, "claude's own output is shown")
        self.assertIn("the tutor plugin is installed and enabled", out)
        self.assertNotIn("Give Claude the tutor skills", out, "no step left to do by hand")
        self.assertIn("1. Open the dashboard", out)
        self.assertEqual(len(self.doctor()), 1)
        self.assertIn("✓", self.doctor()[0])

    def test_setup_twice_says_it_is_already_there(self):
        self.setup()
        n = len(self.changes())
        out = self.setup()
        self.assertEqual(len(self.changes()), n, "nothing installed twice")
        self.assertIn("already installed", out)

    def test_marketplace_already_added_only_installs(self):
        write_json(self.state, {"marketplaces": ["edu4self"], "plugins": []})
        out = self.setup()
        self.assertEqual(self.changes(), [["plugin", "install", "edu4self@edu4self"]])
        self.assertIn("marketplace is already added", out)

    def test_disabled_plugin_is_enabled_and_doctor_tells_the_truth(self):
        write_json(self.state, {"marketplaces": ["edu4self"], "plugins": [{"id": "edu4self@edu4self", "enabled": False}]})
        self.assertIn("✗", self.doctor()[0])
        self.assertIn("disabled", self.doctor()[0])
        self.setup()
        self.assertEqual(self.changes(), [["plugin", "enable", "edu4self@edu4self"]])
        self.assertIn("✓", self.doctor()[0])

    def test_failed_install_prints_the_commands_and_setup_still_succeeds(self):
        self.env["FAKE_PLUGIN_FAIL"] = "install"
        out = self.setup()
        self.assertIn("network error", out)
        self.assertIn("didn't install", out)
        self.assertIn("claude plugin marketplace add chillax97/edu4self", out)
        self.assertIn("claude plugin install edu4self@edu4self", out)
        self.assertIn("1. Give Claude the tutor skills", out)
        line = self.doctor()[0]
        self.assertIn("✗", line)
        self.assertIn("claude plugin install edu4self@edu4self", line)

    def test_no_claude_prints_the_steps_and_says_claude_is_needed(self):
        self.env["EDU4SELF_CLAUDE"] = os.path.join(self.tmp, "no-such-claude")
        out = self.setup()
        self.assertEqual(self.calls(), [])
        self.assertIn("Claude Code is needed", out)
        self.assertIn("claude plugin install edu4self@edu4self", out)
        self.assertNotIn("Install the tutor plugin now", out)

    def test_a_question_with_no_input_takes_the_default(self):
        # Windows calls the NUL device a terminal, so isatty() says yes and input() then meets end of file
        import builtins, io
        from unittest import mock
        cli = load_cli()
        tty = mock.Mock(isatty=lambda: True)
        with mock.patch.object(sys, "stdin", tty), mock.patch.object(builtins, "input", side_effect=EOFError), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(cli.ask("Install the tutor plugin now? (y/n)", "y"), "y")

    def test_no_plugin_flag_runs_nothing(self):
        out = self.setup("--no-plugin")
        self.assertEqual(self.calls(), [])
        self.assertIn("1. Give Claude the tutor skills", out)
        self.assertIn("✗", self.doctor()[0])


class DoctorLoginTest(unittest.TestCase):
    """doctor reports the Claude Code login with the dashboard's own check (server.claude_ready). The fake plays
    a Claude Code that's signed in, signed out, too old to say, or missing; no account or network is used."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-doctor-")
        self.env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg"), HOME=self.tmp,
                        CLAUDE_CONFIG_DIR=os.path.join(self.tmp, "claude"), FAKE_CLAUDE_LOG=os.path.join(self.tmp, "runs.jsonl"),
                        EDU4SELF_CLAUDE=os.path.join(ENGINE, "tests", "fake_claude.py"),
                        EDU4SELF_NO_UPDATE_CHECK="1")
        for k in ("FAKE_CLAUDE_SIGNED_OUT", "FAKE_CLAUDE_OLD"):
            self.env.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def doctor(self, **env):
        r = subprocess.run([sys.executable, CLI, "doctor", "--port", str(free_port())], env=dict(self.env, **env),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        login = [l.strip() for l in r.stdout.splitlines() if "signed in" in l or "login" in l.lower() and "service" not in l]
        return login, r.stdout

    def test_signed_in(self):
        login, _ = self.doctor()
        self.assertEqual(login, ["✓ Claude Code is signed in"])

    def test_signed_out_names_the_fix_and_counts_as_a_problem(self):
        login, out = self.doctor(FAKE_CLAUDE_SIGNED_OUT="1")
        self.assertEqual(len(login), 1)
        self.assertTrue(login[0].startswith("✗"), login)
        self.assertIn("claude auth login", login[0])
        problems = int(re.search(r"(\d+) things? to fix", out).group(1))
        self.assertGreater(problems, int(re.search(r"(\d+) things? to fix", self.doctor()[1]).group(1)), "one more thing to fix than signed in")

    def test_too_old_to_say_is_unknown_and_never_asked_auth_status(self):
        login, _ = self.doctor(FAKE_CLAUDE_OLD="1")
        self.assertEqual(len(login), 1)
        self.assertTrue(login[0].startswith("–"), login)
        self.assertIn("unknown", login[0])
        runs = []
        if os.path.exists(self.env["FAKE_CLAUDE_LOG"]):
            with open(self.env["FAKE_CLAUDE_LOG"], encoding="utf-8") as fh:
                runs = [json.loads(l)["args"] for l in fh if l.strip()]
        self.assertNotIn(["auth", "status"], runs, "an old Claude Code would read it as a prompt")

    def test_missing_claude_has_no_login_line(self):
        login, out = self.doctor(EDU4SELF_CLAUDE=os.path.join(self.tmp, "no-such-claude"))
        self.assertEqual(login, [])
        self.assertIn("Claude Code not found", out)

    def test_doctor_uses_the_servers_check(self):
        cli = load_cli()
        import server
        from unittest import mock
        for logged_in, mark in ((True, "✓"), (False, "✗"), (None, "–")):
            with mock.patch.object(server, "claude_ready", return_value={"installed": True, "logged_in": logged_in}) as ready:
                self.assertEqual(cli.login_line()[0], mark)
                ready.assert_called_once()


class RepoTest(unittest.TestCase):
    """Copies and version numbers that must agree across the repo."""

    def test_plugin_protocol_matches_docs(self):
        with open(os.path.join(ENGINE, "docs", "PROTOCOL.md"), encoding="utf-8") as a, open(os.path.join(ENGINE, "plugin", "skills", "check-inbox", "PROTOCOL.md"), encoding="utf-8") as b:
            self.assertEqual(a.read(), b.read(), "run: cp docs/PROTOCOL.md plugin/skills/check-inbox/PROTOCOL.md")

    def test_versions_agree(self):
        plugin = read_json(os.path.join(ENGINE, "plugin", ".claude-plugin", "plugin.json"))
        self.assertEqual(plugin["version"], server.VERSION)
        with open(os.path.join(ENGINE, "CHANGELOG.md"), encoding="utf-8") as fh:
            self.assertIn("## %s" % server.VERSION, fh.read())

    def test_marketplace_points_at_the_plugin(self):
        m = read_json(os.path.join(ENGINE, ".claude-plugin", "marketplace.json"))
        entry = m["plugins"][0]
        self.assertEqual(entry["name"], read_json(os.path.join(ENGINE, entry["source"], ".claude-plugin", "plugin.json"))["name"])


if __name__ == "__main__":
    unittest.main()
