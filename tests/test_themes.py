"""Rooms: the checks a theme must pass, and how the server serves them. python3 -m unittest discover tests"""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_server import APP, free_port, make_vault, write_json, read_json  # noqa: E402

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
        self.set_config(theme="bar", theme_lessons=True)   # the bar has no lesson.css: lessons stay plain
        self.assertNotIn(b"/theme/lesson.css", self.get(lesson)[2])

    def test_config_keeps_a_bad_theme_id_out(self):
        self.assertEqual(server.clean_config({"theme": "../x"})["theme"], "bar")
        self.assertEqual(server.clean_config({"theme": "night-train"})["theme"], "night-train")


if __name__ == "__main__":
    unittest.main()
