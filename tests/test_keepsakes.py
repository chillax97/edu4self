"""Trophies: what counts as won, the quiet backfill, drawings that travel between rooms, cards and gifts.
python3 -m unittest discover tests"""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_server import APP, free_port, make_vault, write_json, read_json  # noqa: E402

sys.path.insert(0, APP)
import keepsakes  # noqa: E402
import server  # noqa: E402
import themes  # noqa: E402

FAKE = os.path.join(HERE, "fake_claude.py")
LOOK = {k: dict(v) for k, v in themes.DEFAULT_KEEPSAKES.items() if k != "lines"}


def block(end, minutes):
    """A block that ended at a local datetime."""
    end = end.astimezone()
    start = end - timedelta(minutes=minutes)
    return {"ts": end.isoformat(timespec="seconds"), "started": start.isoformat(timespec="seconds"),
            "block": "lessons", "minutes": minutes}


def at(days_ago, hour):
    d = datetime.now().astimezone() - timedelta(days=days_ago)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0)


class EarnedTest(unittest.TestCase):
    def test_day_week_and_die_are_counted_like_the_dashboard(self):
        mon = at(0, 12) - timedelta(days=at(0, 12).weekday() + 14)   # a Monday two weeks back
        blocks = [block(mon.replace(hour=9), 30), block(mon.replace(hour=11), 40),      # day goal 60: met by the 2nd
                  block(mon + timedelta(days=2), 20),                                    # 2nd day of that week
                  block(mon + timedelta(days=3), 600)]                                    # crosses 10 hours: die 1
        won = keepsakes.earned(blocks, day_minutes=60, week_days=2)
        ids = [w["id"] for w in won]
        self.assertEqual(ids[0], "day-%s" % mon.date().isoformat())
        self.assertEqual(won[0]["ts"], blocks[1]["ts"], "won by the block that crossed the line")
        self.assertIn("week-%d-W%02d" % mon.isocalendar()[:2], ids)
        self.assertEqual(sum(1 for i in ids if i.startswith("day-")), 2, "the 20-minute day missed the goal")
        self.assertEqual([i for i in ids if i.startswith("die-")], ["die-1"])

    def test_a_long_block_can_finish_two_dice(self):
        won = keepsakes.earned([block(at(3, 20), 1250)], day_minutes=960, week_days=7)
        self.assertEqual([w["id"] for w in won if w["kind"] == "die"], ["die-1", "die-2"])


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-keep-")
        self.path = os.path.join(self.tmp, "keepsakes.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_history_is_awarded_once_and_quietly(self):
        old = [block(at(20 + i, 20), 60) for i in range(12)]
        first = keepsakes.sync(self.path, old, 30, 2, "bar", LOOK)
        self.assertTrue(first)
        self.assertTrue(all(i["backfill"] and i["gift"] is None for i in first), "no gifts for the past")
        self.assertEqual(keepsakes.sync(self.path, old, 30, 2, "bar", LOOK), [], "nothing twice")

    def test_a_week_or_die_won_now_waits_for_its_gift_and_a_day_never_gets_one(self):
        keepsakes.sync(self.path, [], 30, 1, "bar", LOOK)            # the shelf exists: nothing after this is backfill
        new = keepsakes.sync(self.path, [block(datetime.now().astimezone() - timedelta(minutes=1), 40)], 30, 1, "bar", LOOK)
        by = {i["kind"]: i for i in new}
        self.assertEqual(by["day"]["gift"], None)
        self.assertEqual(by["week"]["gift"], "pending")
        self.assertFalse(by["week"]["backfill"])
        self.assertEqual(keepsakes.pending_gift(self.path)["id"], by["week"]["id"])

    def test_a_trophy_keeps_the_drawing_of_the_room_it_was_won_in(self):
        library = dict(LOOK, day=dict(LOOK["day"], name="book", art='<svg viewBox="0 0 4 1"><rect width="4" height="1"/></svg>'))
        keepsakes.sync(self.path, [block(at(9, 20), 60)], 30, 7, "library", library)
        keepsakes.sync(self.path, [block(at(9, 20), 60), block(at(8, 20), 60)], 30, 7, "space", LOOK)
        data = keepsakes.load(self.path)
        rooms = [(i["theme"], i["name"]) for i in data["items"] if i["kind"] == "day"]
        self.assertEqual(rooms, [("library", "book"), ("space", "star")])
        self.assertEqual(len(data["art"]), 2, "both drawings are kept")
        self.assertIn("<rect", data["art"][data["items"][0]["art"]])


class ArtTest(unittest.TestCase):
    def test_a_trophy_is_shapes_only(self):
        self.assertEqual(themes.clean_art('<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="red"/></svg>')[1], [])
        for bad in ('<svg viewBox="0 0 1 1"><script>x</script></svg>', '<svg viewBox="0 0 1 1"><circle id="t-a"/></svg>',
                    '<svg viewBox="0 0 1 1"><rect fill="url(#t-a)"/></svg>', '<svg viewBox="0 0 1 1"><circle onclick="x()"/></svg>',
                    '<div></div>', '<svg viewBox="0 0 1 1"><text>hi</text></svg>', '<svg><circle/></svg>',
                    '<svg viewBox="0 0 1 1"></svg><svg viewBox="0 0 1 1"></svg>', '<svg viewBox="0 0 1 1"><a href="x"/></svg>'):
            self.assertTrue(themes.clean_art(bad)[1], bad)

    def test_a_room_without_trophies_gets_plain_ones_and_bad_ones_are_named(self):
        meta, errs = themes.clean_meta({"name": "Plain"}, "plain")
        self.assertEqual(errs, [])
        self.assertEqual(meta["keepsakes"]["day"]["name"], "star")
        meta, errs = themes.clean_meta({"name": "X", "keepsakes": {"day": {"name": "tooth", "art": "<script>x</script>", "stack": "tower"}}}, "x")
        self.assertTrue(any("keepsakes.day.art" in e for e in errs))
        self.assertTrue(any("stack" in e for e in errs))

    def test_every_built_in_room_brings_its_own_three_trophies(self):
        base = os.path.join(APP, "dashboard", "themes")
        for tid in os.listdir(base):
            ks = themes.load(os.path.join(base, tid), tid)["meta"]["keepsakes"]
            for k in themes.KEEPSAKE_KINDS:
                self.assertNotEqual(ks[k]["art"], themes.DEFAULT_KEEPSAKES[k]["art"], (tid, k))
            self.assertEqual(set(ks["lines"]), set(themes.KEEPSAKE_LINES), tid)


class ServerTest(unittest.TestCase):
    """The real server: a block earns trophies, the page gets them, cards print, gifts get made."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-keepsrv-")
        cls.vault, _ = make_vault(cls.tmp)
        cls.log = os.path.join(cls.tmp, "fake.log")
        os.environ["EDU4SELF_CLAUDE"] = FAKE
        os.environ["FAKE_CLAUDE_LOG"] = cls.log
        write_json(os.path.join(cls.vault, "_system", "config.json"), {"theme": "library", "goals": {"day_minutes": 30, "week_days": 1}})
        with open(os.path.join(cls.vault, "_system", "blocks.jsonl"), "w") as fh:     # history from before trophies existed
            for i in range(3):
                fh.write(json.dumps(block(at(30 + i, 20), 45)) + "\n")
        cls.port = free_port()
        cls.httpd = server.make_server(cls.vault, cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.environ.pop("EDU4SELF_CLAUDE", None)
        os.environ.pop("FAKE_CLAUDE_LOG", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": "127.0.0.1:%d" % self.port}
        if body is not None:
            headers.update({"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % self.port})
        c.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, dict(r.getheaders()), data

    def test_1_history_shows_up_quietly_then_a_new_week_gets_a_gift(self):
        code, _, data = self.req("GET", "/api/state")
        items = json.loads(data)["keepsakes"]["items"]
        self.assertEqual(len([i for i in items if i["kind"] == "day"]), 3)
        self.assertTrue(all(i["backfill"] and i["theme"] == "library" for i in items))
        now = datetime.now().astimezone() - timedelta(minutes=1)
        b = block(now, 40)
        utc = datetime.fromisoformat(b["started"]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        code, _, data = self.req("POST", "/api/blocks", {"block": "lessons", "minutes": 40, "started": utc})
        self.assertEqual(code, 201, data)
        won = json.loads(data)["keepsakes"]
        self.assertTrue(any(w.startswith("week-") for w in won), won)
        week = [w for w in won if w.startswith("week-")][0]
        for _ in range(100):   # the gift is made in the background
            item = next(i for i in keepsakes.load(os.path.join(self.vault, "_system", "keepsakes.json"))["items"] if i["id"] == week)
            if item["gift"] not in ("pending", "making"):
                break
            time.sleep(0.1)
        self.assertEqual(item["gift"], "gifts/%s.html" % week)
        self.assertTrue(os.path.isfile(os.path.join(self.vault, item["gift"])))
        run = [json.loads(l) for l in open(self.log)][-1]["args"]
        allowed, denied = run[run.index("--allowedTools") + 1], run[run.index("--disallowedTools") + 1]
        self.assertNotIn("WebFetch", allowed, "a gift run has no web")
        self.assertIn("Bash", denied)
        self.assertIn("WebFetch", denied)
        status = json.loads(self.req("GET", "/api/claude")[2])
        self.assertFalse(any("surprise" in e["text"].lower() or "gifts/" in e["text"] for e in status["events"]),
                         "the panel doesn't spoil the surprise")

    def test_2_a_card_prints_in_the_colours_of_the_room_it_was_won_in(self):
        items = json.loads(self.req("GET", "/api/state")[2])["keepsakes"]["items"]
        day = next(i for i in items if i["kind"] == "day")
        code, headers, page = self.req("GET", "/card?id=" + day["id"])
        self.assertEqual(code, 200)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertIn(b"The library", page)
        self.assertIn(b"<svg", page)
        self.assertIn(b"45 focused minutes", page)
        self.assertEqual(self.req("GET", "/card?id=nope")[0], 404)
        self.assertEqual(self.req("GET", "/card.js")[0], 200)

    def test_3_a_tampered_shelf_file_cant_put_markup_on_the_page(self):
        path = os.path.join(self.vault, "_system", "keepsakes.json")
        data = keepsakes.load(path)
        key = data["items"][0]["art"]
        data["art"][key] = '<svg viewBox="0 0 1 1" onload="alert(1)"><script>x()</script></svg>'
        keepsakes.save(path, data)
        art = json.loads(self.req("GET", "/api/state")[2])["keepsakes"]["art"][key]
        self.assertNotIn("onload", art)
        self.assertNotIn("<script", art)

    def test_5_with_gifts_off_a_new_trophy_keeps_its_place_but_no_claude_run_starts(self):
        path = os.path.join(self.vault, "_system", "keepsakes.json")
        cfg = os.path.join(self.vault, "_system", "config.json")
        write_json(cfg, {"theme": "library", "goals": {"day_minutes": 30, "week_days": 1}, "gifts": False})
        data = keepsakes.load(path)
        data["items"].append({"id": "die-99", "kind": "die", "n": 99, "date": "2026-11-01", "ts": "2026-11-01T10:00:00Z",
                              "theme": "library", "name": "volume", "plural": "volumes", "stack": "row",
                              "art": data["items"][0]["art"], "backfill": False, "gift": "pending"})
        keepsakes.save(path, data)
        runs = sum(1 for _ in open(self.log))
        try:
            self.req("GET", "/api/state")
            item = next(i for i in keepsakes.load(path)["items"] if i["id"] == "die-99")
            self.assertEqual(item["gift"], "off")
            self.assertEqual(sum(1 for _ in open(self.log)), runs, "no Claude run when gifts are off")
        finally:
            write_json(cfg, {"theme": "library", "goals": {"day_minutes": 30, "week_days": 1}})

    def test_4_claude_runs_cant_edit_the_shelf(self):
        args = server.claude_args("x", None, "chat")
        self.assertIn("Write(./_system/keepsakes.json)", args[args.index("--disallowedTools") + 1])


if __name__ == "__main__":
    unittest.main()
