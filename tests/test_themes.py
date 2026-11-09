"""Rooms: the checks a theme must pass, and how the server serves them. python3 -m unittest discover tests"""
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_server import APP, CLI, free_port, make_vault, write_json, read_json  # noqa: E402

sys.path.insert(0, APP)
import server  # noqa: E402
import themes  # noqa: E402

BUILTIN = os.path.join(APP, "dashboard", "themes")
SLOTS = "".join('<div data-slot="%s"></div>' % s for s in themes.SLOTS_REQUIRED)


def make_theme(base, tid, layout=SLOTS, css=".room .x { color: red; }", meta=None, lesson=None):
    d = os.path.join(base, "themes", tid)
    os.makedirs(d, exist_ok=True)
    write_json(os.path.join(d, "theme.json"), meta if meta is not None else {"name": tid.title()})
    for name, text in (("layout.html", layout), ("theme.css", css), ("lesson.css", lesson)):
        if text is not None:
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(text)
    return d


class BuiltinTest(unittest.TestCase):
    def test_every_built_in_room_passes_its_check(self):
        ids = sorted(os.listdir(BUILTIN))
        self.assertIn("bar", ids)
        for tid in ids:
            t = themes.load(os.path.join(BUILTIN, tid), tid)
            self.assertEqual(t["errors"], [], tid)
            self.assertTrue(t["lesson_css"], tid + " dresses lessons too")

    def test_the_defaults_carry_no_one_s_field(self):
        # the built-in rooms, the page and the server defaults are for strangers: studying and light
        # coding humour, not one person's machine-learning jokes (those go in a vault room)
        # (a "-" before a word is code: linear-gradient, bx-cluster; lowercase "gpu" is the voice's id and a class)
        ml = re.compile(r"(?<![-\w])(GPUs?|(?i:h100|kv cache|softmax|gradients?|attention is all|residual connection|mlp|"
                        r"leetcode|neural|whisperer|last token|cache miss|dead neurons|cluster|rack|in prod))\b")
        for tid in sorted(os.listdir(BUILTIN)):
            meta = themes.load(os.path.join(BUILTIN, tid), tid)["meta"]
            text = json.dumps([meta[k] for k in ("names", "gags", "lines", "words", "about")] +
                              [v.get("name", "") for v in meta["voices"].values()])   # names, not ids: the id "gpu" stays
            self.assertEqual(ml.findall(text), [], tid)
        self.assertEqual(ml.findall(json.dumps(server.DEFAULT_CONFIG["bar"])), [])
        self.assertEqual(ml.findall(json.dumps(themes.WORDS)), [])
        with open(os.path.join(APP, "dashboard", "app.js"), encoding="utf-8") as fh:
            strings = re.findall(r'"(?:[^"\\\n]|\\.)*"', fh.read())   # what the page can say; ids and classes like "gpu" aren't words
        said = [x for x in strings if " " in x and ml.search(x)]
        self.assertEqual(said, [])
        self.assertEqual(server.DEFAULT_CONFIG["goals"], {"day_minutes": 60, "week_days": 4})


class LayoutTest(unittest.TestCase):
    def errors(self, extra):
        return themes.clean_layout(SLOTS + extra)[1]

    def test_nothing_that_runs_or_loads_survives(self):
        for bad in ('<script>alert(1)</script>', '<div onclick="x()"></div>', '<img src="x">', '<a href="https://x">x</a>',
                    '<iframe></iframe>', '<div style="background:url(https://x)"></div>', '<form></form>',
                    '<svg><use href="#a"/></svg>', '<svg><a href="javascript:x"></a></svg>', '<link rel="stylesheet">',
                    '<div id="cl-send"></div>', '<button data-claude="grade">free</button>', '<div data-claude="grade"></div>'):
            self.assertTrue(self.errors(bad), bad)
        clean = themes.clean_layout(SLOTS + '<div onclick="x()"><script>x</script></div>')[0]
        self.assertNotIn("onclick", clean)
        self.assertNotIn("<script", clean)

    def test_drawing_is_allowed(self):
        ok = ('<div class="window" aria-hidden="true"><svg viewBox="0 0 10 10"><defs><linearGradient id="t-moon"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
              '<circle cx="5" cy="5" r="4" fill="url(#t-moon)"/></svg></div>')
        self.assertEqual(self.errors(ok), [])
        self.assertTrue(self.errors('<svg><circle id="cl-send"/></svg>'), "ids outside the t- prefix")
        self.assertTrue(self.errors('<div id="t-x"></div>'), "ids only inside SVG")
        self.assertEqual(self.errors('<p class="k">The jukebox <b>·</b> <kbd>1</kbd></p>'), [])

    def test_slots_are_required_once(self):
        _, errs = themes.clean_layout('<div data-slot="job"></div><div data-slot="job"></div><div data-slot="nope"></div>')
        text = " ".join(errs)
        self.assertIn("missing the 'voices' slot", text)
        self.assertIn("'job' slot appears 2 times", text)
        self.assertIn("unknown slot 'nope'", text)


class CssTest(unittest.TestCase):
    def test_room_css_stays_in_the_room_and_loads_nothing(self):
        self.assertEqual(themes.check_css(".room .a, .room:hover b { color: red } @media (max-width: 9px) { .room p { x: y } } "
                                          "@keyframes k { from { opacity: 0 } } .room i { background: url('data:image/svg+xml;utf8,<svg/>') }"), [])
        for bad in ("body { color: red }", ".roomy { x: y }", "@media (x) { .topbar { display: none } }",
                    "@import url(x.css);", "@font-face { font-family: x; src: url(x.woff) }",
                    ".room i { background: url(https://example.com/x.png) }", ".room i { background: url(/api/state) }",
                    ".room { color: red", "#cl-send { display: none }"):
            self.assertTrue(themes.check_css(bad), bad)

    def test_lesson_css_may_style_the_page_but_load_nothing(self):
        self.assertEqual(themes.check_css("body { background: #000 } h1 { color: gold }", scoped=False), [])
        self.assertTrue(themes.check_css("body { background: url(https://x/y.png) }", scoped=False))


class MetaTest(unittest.TestCase):
    def test_plain_values_only(self):
        good = {"name": "Night train", "icon": "🚂", "palette": {"bg": "#0b0d1a", "line": "rgba(255,255,255,.1)"},
                "backdrop": "radial-gradient(circle at 80% 20%, #fff6d8 0 9px, transparent 10px), #0b0d1f",
                "fonts": {"head": "head"}, "words": {"host": "The conductor"}, "voices": {"bartender": {"name": "The conductor", "color": "#ffcf6b"}},
                "names": [["The Night Express", "next stop: understanding"]], "gags": [["regular", "A man sleeps on his textbook."]],
                "lines": {"evening": "Evening. The dining car fills up."}, "scape": "rain"}
        meta, errs = themes.clean_meta(good, "train")
        self.assertEqual(errs, [])
        self.assertEqual(meta["words"]["host"], "The conductor")
        for k, v in (("backdrop", "url(https://x/y.png)"), ("backdrop", "red; } body { x"), ("palette", {"bg": "red; color: x"}),
                     ("palette", {"nope": "#000"}), ("words", {"lesson": "Chapter"}), ("fonts", {"head": "Comic Sans"}),
                     ("voices", {"stranger": {"name": "x"}}), ("lines", {"nope": "x"}), ("scape", "techno")):
            self.assertTrue(themes.clean_meta(dict(good, **{k: v}), "train")[1], (k, v))

    def test_a_room_can_name_the_back_room_and_say_its_own_lines(self):
        meta, errors = themes.clean_meta({"name": "Mine", "words": {"collection": "Your shelf", "row": "stack", "rows": "stacks",
                                                                    "tray": "crate", "trays": "crates"},
                                          "voices": {"gpu": {"name": "The printer"}},
                                          "lines": {k: "said {n}" for k in ("water", "hydrated", "row_full", "row_full_body", "die_full_body")}}, "mine")
        self.assertEqual(errors, [])
        self.assertEqual(meta["words"]["row"], "stack")
        self.assertEqual(meta["voices"]["gpu"]["name"], "The printer")
        self.assertEqual(meta["lines"]["row_full"], "said {n}")

    def test_core_learning_words_cannot_be_renamed(self):
        for word in ("lesson", "submit", "grade", "minutes"):
            self.assertNotIn(word, themes.WORDS)


class RouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-themes-")
        cls.vault, _ = make_vault(cls.tmp)
        make_theme(cls.vault, "mine", meta={"name": "Mine", "words": {"host": "The keeper"}},
                   lesson="body { background: #111 } h1 { color: gold }")
        make_theme(cls.vault, "broken", layout='<div data-slot="job"></div><script>x</script>', css="body { color: red }")
        cls.port = free_port()
        cls.httpd = server.make_server(cls.vault, cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": "127.0.0.1:%d" % self.port})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, dict(r.getheaders()), data

    def set_config(self, **kw):
        path = os.path.join(self.vault, "_system", "config.json")
        c = read_json(path) if os.path.exists(path) else {}
        c.update(kw)
        write_json(path, c)

    def test_catalog_lists_built_ins_and_the_vaults_with_problems(self):
        code, _, data = self.get("/api/themes")
        self.assertEqual(code, 200)
        by = {t["id"]: t for t in json.loads(data)["themes"]}
        self.assertTrue(by["bar"]["builtin"])
        self.assertFalse(by["mine"]["builtin"])
        self.assertTrue(by["mine"]["lessons"])
        self.assertEqual(by["mine"]["errors"], [])
        self.assertTrue(by["broken"]["errors"])

    def test_a_theme_comes_with_every_word_and_a_broken_one_never_comes(self):
        code, _, data = self.get("/api/theme?id=mine")
        self.assertEqual(code, 200)
        meta = json.loads(data)["meta"]
        self.assertEqual(meta["words"]["host"], "The keeper")
        self.assertEqual(meta["words"]["back"], themes.WORDS["back"])
        code, _, data = self.get("/api/theme?id=broken")
        self.assertEqual(code, 422)
        body = json.loads(data)
        self.assertNotIn("layout", body)
        self.assertTrue(any("<script>" in e for e in body["errors"]))
        self.assertEqual(self.get("/api/theme?id=nope")[0], 404)
        self.assertEqual(self.get("/api/theme?id=../../etc")[0], 404)

    def test_the_page_runs_only_its_own_scripts(self):
        _, headers, _ = self.get("/")
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)

    def test_lessons_wear_the_room_unless_turned_off(self):
        lesson = "/vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html"
        self.set_config(theme="mine", theme_lessons=True)
        _, headers, page = self.get(lesson)
        self.assertIn(b'href="/theme/lesson.css"', page)
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertEqual(self.get("/theme/lesson.css")[2], b"body { background: #111 } h1 { color: gold }")
        self.set_config(theme="mine", theme_lessons=False)
        self.assertNotIn(b"/theme/lesson.css", self.get(lesson)[2])
        self.set_config(theme="bar", theme_lessons=True)
        self.assertIn(b"/theme/lesson.css", self.get(lesson)[2])
        self.set_config(theme="broken", theme_lessons=True)   # a broken room never dresses a lesson
        self.assertNotIn(b"/theme/lesson.css", self.get(lesson)[2])

    def test_every_lesson_shuffles_its_answer_options_in_any_room(self):
        # lessons written by hand put the right answer second most of the time; the page shuffles it away
        lesson = "/vault/how-learning-works/lessons/0001-retrieval-beats-rereading.html"
        for theme_lessons in (True, False):
            self.set_config(theme="bar", theme_lessons=theme_lessons)
            page = self.get(lesson)[2]
            self.assertEqual(page.count(b"data-edu-shuffle"), 1)
            self.assertLess(page.index(b"data-edu-shuffle"), page.lower().index(b"</head>"))
        self.assertNotIn(b"data-edu-shuffle", self.get("/vault/how-learning-works/MISSION.md?raw=1")[2])

    def test_config_keeps_a_bad_theme_id_out(self):
        self.assertEqual(server.clean_config({"theme": "../x"})["theme"], "bar")
        self.assertEqual(server.clean_config({"theme": "night-train"})["theme"], "night-train")


class CheckTest(unittest.TestCase):
    """edu4self check is where an agent hears that the room it made is broken; the page only falls back."""

    def test_check_names_a_broken_room_and_a_missing_one(self):
        tmp = tempfile.mkdtemp(prefix="edu4self-themecheck-")
        try:
            vault, env = make_vault(tmp)
            check = lambda: subprocess.run([sys.executable, CLI, "check"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
            make_theme(vault, "cosy", meta={"name": "Cosy"})
            write_json(os.path.join(vault, "_system", "config.json"), {"theme": "cosy"})
            r = check()
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("themes/cosy: OK", r.stdout)
            make_theme(vault, "cosy", css="body { color: red }")
            r = check()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("themes/cosy: FAILED", r.stdout)
            self.assertIn("has problems", r.stdout)
            write_json(os.path.join(vault, "_system", "config.json"), {"theme": "nowhere"})
            r = check()
            self.assertIn("'nowhere' doesn't exist", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TrophyStackTest(unittest.TestCase):
    def test_dice_can_stand_in_a_row_and_a_made_up_stack_is_named(self):
        raw = {"die": {"name": "volume", "stack": "row", "art": '<svg viewBox="0 0 30 64"><rect width="30" height="64"/></svg>'}}
        errors = []
        self.assertEqual(themes.clean_keepsakes(raw, errors)["die"]["stack"], "row")
        self.assertEqual(errors, [])
        raw["die"]["stack"] = "tower"
        themes.clean_keepsakes(raw, errors)
        self.assertTrue(any("stack" in e for e in errors), errors)

class NoRoomSharingTest(unittest.TestCase):
    """Rooms aren't traded: no .room export or import from the page or the CLI (dropped 2026-11-06)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-noshare-")
        self.vault, self.env = make_vault(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_page_and_the_cli_offer_no_way_to_trade_rooms(self):
        port = free_port()
        httpd = server.make_server(self.vault, port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            def req(method, path, body=None):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                h = {"Host": "127.0.0.1:%d" % port}
                if body is not None:
                    h.update({"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % port})
                c.request(method, path, json.dumps(body) if body is not None else None, h)
                r = c.getresponse()
                r.read()
                return r.status
            self.assertEqual(req("GET", "/api/themes/export?id=library"), 404)
            room = {"format": "edu4self-room", "id": "x", "files": {"theme.json": "{}"}}
            self.assertEqual(req("POST", "/api/themes/import", {"room": room}), 404)
            self.assertFalse(os.path.exists(os.path.join(self.vault, "themes", "x")))
            self.assertEqual(req("GET", "/api/themes"), 200, "picking a room still works")
        finally:
            httpd.shutdown()
            httpd.server_close()
        r = subprocess.run([sys.executable, CLI, "room", "export", "library", "--vault", self.vault],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", env=self.env)
        self.assertEqual(r.returncode, 2, "argparse refuses an unknown command")
        self.assertFalse(hasattr(themes, "unpack"))

if __name__ == "__main__":
    unittest.main()
