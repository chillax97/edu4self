"""Reminders: when an away mail goes out (and when it stays quiet), what it says, the Sunday recap, mail, the server loop."""
import json
import os
import shutil
import socket
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ENGINE, "app"))
sys.path.insert(0, HERE)
import reminders  # noqa: E402
import server  # noqa: E402
from test_server import make_vault, free_port, read_json  # noqa: E402

CFG = {"goals": {"day_minutes": 60, "week_days": 4}, "reminders": {"mail": True}, "blocks": {"presets": [25, 50]}}
WED = datetime(2026, 11, 4, 15, 0).astimezone()          # a Wednesday afternoon


def blk(when, minutes=30):
    return {"ts": when.astimezone().isoformat(), "started": (when - timedelta(minutes=minutes)).astimezone().isoformat(),
            "block": "lessons", "minutes": minutes}


def state_with(opens=None, status="todo"):
    q = {"id": "t-recall", "kind": "probe", "status": status, "label": "Recall check", "title": "How big is the cache?", "href": "/x"}
    if opens:
        q["opens"] = opens
    return {"topics": [{"id": "t", "title": "Inference", "queue": [q], "history": [
        {"date": "2026-11-03", "title": "Lesson 06: cache size", "evidence": True},
        {"date": "2026-10-20", "title": "older", "evidence": True}]}]}


class AwayTest(unittest.TestCase):
    def test_the_ladder_is_3_7_15_30_then_every_30_days(self):
        last = WED - timedelta(hours=1)
        step = lambda days: reminders.away_step(last, WED + timedelta(days=days))
        self.assertEqual([step(d) for d in (0, 2, 3, 6, 7, 14, 15, 29, 30, 59, 60, 95)],
                         [None, None, 3, 3, 7, 7, 15, 15, 30, 30, 60, 90])
        self.assertIsNone(reminders.away_step(None, WED), "nothing ever done: nothing to come back to")

    def test_each_step_once_and_your_next_action_starts_over(self):
        blocks = [blk(WED - timedelta(days=3))]
        due = reminders.away_due(blocks, [], WED, {"away": []})
        self.assertEqual(due[:2], ("2026-11-01+3", 3))
        self.assertIsNone(reminders.away_due(blocks, [], WED + timedelta(days=2), {"away": ["2026-11-01+3"]}), "day 5: 3 is sent, 7 not yet")
        self.assertEqual(reminders.away_due(blocks, [], WED + timedelta(days=4), {"away": ["2026-11-01+3"]})[1], 7)
        self.assertEqual(reminders.away_due(blocks, [], WED + timedelta(days=12), {"away": []})[1], 15,
                         "off for a while: only the step reached now goes, not a pile of old ones")
        back = blocks + [blk(WED + timedelta(days=5))]
        self.assertIsNone(reminders.away_due(back, [], WED + timedelta(days=6), {"away": ["2026-11-01+3"]}), "a block resets the clock")
        note = [{"ts": (WED - timedelta(days=1)).isoformat(), "kind": "note"}]
        self.assertIsNone(reminders.away_due(blocks, note, WED, {"away": []}), "so does an answer or a note")

    def test_quiet_at_night_and_during_a_block(self):
        blocks = [blk(WED - timedelta(days=3))]
        self.assertIsNone(reminders.away_due(blocks, [], WED.replace(hour=22), {"away": []}))
        self.assertIsNone(reminders.away_due(blocks, [], WED.replace(hour=8, minute=59), {"away": []}))
        self.assertIsNotNone(reminders.away_due(blocks, [], WED.replace(hour=9), {"away": []}))
        self.assertIsNone(reminders.away_due(blocks, [], WED, {"away": []}, block_until=WED + timedelta(minutes=20)))

    def test_the_mail_praises_what_you_did_then_offers_one_small_thing(self):
        blocks = [blk(WED - timedelta(days=8), 90), blk(WED - timedelta(days=7), 30)]
        items = [{"name": "bottle cap", "plural": "bottle caps"}] * 2
        title, body = reminders.away(state_with(), blocks, items, CFG, 7, reminders.last_activity(blocks, []), set(), 4747)
        self.assertIn("A week away", title)
        self.assertIn("2 focused hours over 2 days", body)
        self.assertIn("2 things proven, most recently: Lesson 06: cache size; older", body)
        self.assertIn("2 bottle caps", body)
        self.assertIn("Recall check: How big is the cache?, in Inference", body)
        self.assertIn("One 25-minute block", body, "the smallest block on offer")
        self.assertIn("http://127.0.0.1:4747/#submit=t-recall", body)
        self.assertNotRegex(body.lower(), r"miss|behind|fail|streak", "no guilt")

    def test_nothing_to_do_still_gives_a_small_step_and_long_absences_get_their_own_words(self):
        blocks = [blk(WED - timedelta(days=60))]
        last = reminders.last_activity(blocks, [])
        title, body = reminders.away(state_with(), blocks, [], CFG, 60, last, {"t-recall"}, 4747)
        self.assertIn("60 days away", title)
        self.assertIn("One 25-minute block of anything", body, "the only task is waiting for grading")
        self.assertNotIn("#submit=", body)


class RecapTest(unittest.TestCase):
    def test_sunday_evening_then_once(self):
        sun = datetime(2026, 11, 8, 19, 0).astimezone()
        self.assertIsNone(reminders.recap_due(sun.replace(hour=18, minute=59), {"recaps": []}))
        self.assertEqual(reminders.recap_due(sun, {"recaps": []})[0], "2026-W45")
        self.assertEqual(reminders.recap_due(sun + timedelta(hours=10), {"recaps": []})[0], "2026-W45", "Monday catches a missed Sunday")
        self.assertIsNone(reminders.recap_due(sun, {"recaps": ["2026-W45"]}))
        self.assertIsNone(reminders.recap_due(sun + timedelta(days=2), {"recaps": []}), "Tuesday is too late")

    def test_the_recap_says_what_happened_and_what_is_next(self):
        mon = datetime(2026, 11, 2).date()
        blocks = [blk(WED - timedelta(days=1), 70), blk(WED, 20), blk(WED - timedelta(days=9), 50)]
        title, body = reminders.recap(state_with(opens="2026-11-10"), blocks, [
            {"name": "book", "kind": "day", "date": "2026-11-03", "backfill": False}], CFG, mon, 4747)
        self.assertIn("2 of 4 days", title)
        self.assertIn("90 focused minutes on 2 days", body)
        self.assertIn("1 day reached the daily goal", body)
        self.assertIn("Lesson 06: cache size", body)
        self.assertNotIn("older", body)
        self.assertIn("1 book", body)
        self.assertIn("opens 2026-11-10", body)


class FakeSMTP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.mails = []
        super().__init__(("127.0.0.1", 0), self.Handler)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            w = lambda s: self.wfile.write((s + "\r\n").encode())
            w("220 fake")
            data, buf = False, []
            for raw in self.rfile:
                line = raw.decode().rstrip("\r\n")
                if data:
                    if line == ".":
                        self.server.mails.append("\n".join(buf))
                        data, buf = False, []
                        w("250 ok")
                    else:
                        buf.append(line)
                    continue
                cmd = line.upper()
                if cmd.startswith("EHLO"):
                    w("250 fake")
                elif cmd.startswith("DATA"):
                    data = True
                    w("354 go")
                elif cmd.startswith("QUIT"):
                    w("221 bye")
                    return
                else:
                    w("250 ok")


class MailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-mail-")
        os.environ["EDU4SELF_CONFIG_HOME"] = self.tmp
        self.smtp = FakeSMTP()
        threading.Thread(target=self.smtp.serve_forever, daemon=True).start()
        self.acct = {"host": "127.0.0.1", "port": self.smtp.server_address[1], "security": "none", "user": "me@example.com",
                     "password": "", "to": "me@example.com"}

    def tearDown(self):
        self.smtp.shutdown()
        self.smtp.server_close()
        os.environ.pop("EDU4SELF_CONFIG_HOME", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mail_is_sent_and_the_account_file_is_private(self):
        reminders.save_mail(self.acct)
        self.assertEqual(stat.S_IMODE(os.stat(reminders.mail_path()).st_mode), 0o600)
        reminders.send_mail(reminders.load_mail(), "edu4self: hi", "body text")
        self.assertIn("Subject: edu4self: hi", self.smtp.mails[0])
        self.assertIn("body text", self.smtp.mails[0])

    def test_unencrypted_mail_only_goes_to_this_computer(self):
        with self.assertRaises(reminders.smtplib.SMTPException):
            reminders.send_mail(dict(self.acct, host="smtp.example.com"), "x", "y")

    def test_cli_test_and_off(self):
        cli = os.path.join(ENGINE, "edu4self")
        run = lambda *a: subprocess.run([sys.executable, cli, "mail"] + list(a), stdout=subprocess.PIPE, text=True, env=dict(os.environ))
        self.assertEqual(run("test").returncode, 1, "nothing set up yet")
        reminders.save_mail(self.acct)
        r = run("test")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(len(self.smtp.mails), 1)
        self.assertEqual(run("off").returncode, 0)
        self.assertFalse(os.path.exists(reminders.mail_path()))


class ServerLoopTest(unittest.TestCase):
    """The real server: the away mail through a mail server, never during a block; the recap file on Sunday."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-rem-")
        self.vault, _ = make_vault(self.tmp)
        os.environ["EDU4SELF_CONFIG_HOME"] = os.path.join(self.tmp, "cfg")
        self.smtp = FakeSMTP()
        threading.Thread(target=self.smtp.serve_forever, daemon=True).start()
        reminders.save_mail({"host": "127.0.0.1", "port": self.smtp.server_address[1], "security": "none",
                             "user": "me@example.com", "password": "", "to": "me@example.com"})
        self.blocks(WED - timedelta(days=3))
        self.port = free_port()
        self.httpd = server.make_server(self.vault, self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        server.BLOCK_UNTIL = None

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.smtp.shutdown()
        self.smtp.server_close()
        os.environ.pop("EDU4SELF_CONFIG_HOME", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def blocks(self, *when):
        with open(os.path.join(self.vault, "_system", "blocks.jsonl"), "w") as fh:
            for w in when:
                fh.write(json.dumps(blk(w)) + "\n")

    def config(self, c):
        with open(os.path.join(self.vault, "_system", "config.json"), "w") as fh:
            json.dump(c, fh)

    def test_one_mail_per_step_with_a_link_to_the_task(self):
        self.assertEqual(server.reminder_tick(WED)[0], "away")
        self.assertIsNone(server.reminder_tick(WED + timedelta(minutes=5)), "once per step")
        self.assertEqual(len(self.smtp.mails), 1)
        self.assertIn("Subject: edu4self: Three days off", self.smtp.mails[0])
        self.assertIn("#submit=", self.smtp.mails[0])
        self.assertIn("+3", read_json(os.path.join(self.vault, "_system", "reminders.json"))["away"][0])
        self.assertEqual(server.reminder_tick(WED + timedelta(days=4))[0], "away", "day 7")
        self.assertIn("A week away", self.smtp.mails[1])

    def test_a_block_running_in_the_page_holds_the_mail(self):
        import http.client
        now = datetime.now().astimezone() + timedelta(minutes=1)    # the block's end is set from the real clock
        hours, reminders.MAIL_HOURS = reminders.MAIL_HOURS, (0, 24)   # so this runs at any hour
        self.addCleanup(setattr, reminders, "MAIL_HOURS", hours)
        self.blocks(now - timedelta(days=3))
        with open(os.path.join(self.vault, "_system", "reminders.json"), "w") as fh:   # no recap in the way
            json.dump({"recaps": [reminders.week_id(now.date()), reminders.week_id(now.date() - timedelta(days=1))]}, fh)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        until = (datetime.now().astimezone() + timedelta(minutes=30)).isoformat()
        c.request("POST", "/api/presence", json.dumps({"block_until": until}),
                  {"Content-Type": "application/json", "Host": "127.0.0.1:%d" % self.port, "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(c.getresponse().status, 200)
        self.assertIsNone(server.reminder_tick(now))
        self.assertEqual(self.smtp.mails, [])
        server.BLOCK_UNTIL = None                       # the block ends: now the mail may go
        self.assertEqual(server.reminder_tick(now)[0], "away")

    def test_switched_off_or_not_set_up_means_quiet(self):
        self.config({"reminders": {"mail": False}})
        self.assertIsNone(server.reminder_tick(WED))
        self.config({})
        os.remove(reminders.mail_path())
        self.assertIsNone(server.reminder_tick(WED))
        self.assertEqual(self.smtp.mails, [])

    def test_an_old_config_keeps_mail_on(self):
        # up to 1.2, {"notify": true, "mail": false} was the default: mail off meant "not set up", not "no thanks"
        self.config({"reminders": {"notify": True, "mail": False}})
        self.assertTrue(server.load_config()[0]["reminders"]["mail"])
        self.assertNotIn("notify", server.load_config()[0]["reminders"])
        self.assertEqual(server.reminder_tick(WED)[0], "away")

    def test_sunday_writes_the_recap_and_mails_it(self):
        sun = datetime(2026, 11, 8, 19, 30).astimezone()
        self.blocks(sun - timedelta(hours=2))
        kind, title = server.reminder_tick(sun)
        self.assertEqual(kind, "recap")
        path = os.path.join(self.vault, "recaps", "2026-W45.md")
        self.assertTrue(os.path.isfile(path))
        self.assertIn("# Your week", open(path).read())
        self.assertIn("Subject: edu4self: Your week", self.smtp.mails[0])
        self.assertIsNone(server.reminder_tick(sun + timedelta(minutes=1)))


if __name__ == "__main__":
    unittest.main()
