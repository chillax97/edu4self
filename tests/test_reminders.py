"""Reminders: when a nudge goes out (and when it stays quiet), the Sunday recap, mail, and the server loop."""
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

CFG = {"goals": {"day_minutes": 60, "week_days": 4}, "reminders": {"notify": True, "mail": False}}
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


class NudgeTest(unittest.TestCase):
    def test_a_task_opening_today_nudges_once_you_have_been_around_an_hour(self):
        st = state_with(opens="2026-11-04")
        n = reminders.nudge(st, [], [], CFG, WED, 60)
        self.assertIsNotNone(n)
        self.assertIn("Recall check", n[0])
        self.assertEqual(n[2], "t-recall")
        self.assertIsNone(reminders.nudge(st, [], [], CFG, WED, 59), "not before an hour at the computer")

    def test_quiet_when_you_already_studied_or_a_block_is_running(self):
        st = state_with(opens="2026-11-04")
        self.assertIsNone(reminders.nudge(st, [blk(WED - timedelta(hours=3))], [], CFG, WED, 90), "a block today")
        self.assertIsNone(reminders.nudge(st, [], [{"ts": (WED - timedelta(hours=1)).isoformat()}], CFG, WED, 90), "an answer sent today")
        self.assertIsNone(reminders.nudge(st, [], [], CFG, WED, 90, block_until=WED + timedelta(minutes=20)), "a block running now")
        self.assertIsNotNone(reminders.nudge(st, [blk(WED - timedelta(days=1))], [], CFG, WED, 90), "yesterday's block doesn't count")

    def test_quiet_at_night_and_early_morning(self):
        st = state_with(opens="2026-11-04")
        self.assertIsNone(reminders.nudge(st, [], [], CFG, WED.replace(hour=22), 90))
        self.assertIsNone(reminders.nudge(st, [], [], CFG, WED.replace(hour=8, minute=59), 90))
        self.assertIsNotNone(reminders.nudge(st, [], [], CFG, WED.replace(hour=9), 90))

    def test_a_done_task_or_another_day_is_no_reason(self):
        easy = dict(CFG, goals={"day_minutes": 60, "week_days": 1})       # the week is already won, so only "opens" could nudge
        monday = [blk(WED - timedelta(days=2))]
        self.assertIsNotNone(reminders.nudge(state_with(opens="2026-11-04"), monday, [], easy, WED, 90))
        self.assertIsNone(reminders.nudge(state_with(opens="2026-11-04", status="done"), monday, [], easy, WED, 90))
        self.assertIsNone(reminders.nudge(state_with(opens="2026-11-05"), monday, [], easy, WED, 90))

    def test_the_week_is_at_risk_only_with_at_most_one_day_to_spare(self):
        # Wednesday: 5 days left including today. Goal 4 days.
        mon = WED - timedelta(days=2)
        st = state_with()
        self.assertIsNotNone(reminders.nudge(st, [], [], CFG, WED, 90), "0 done, 4 needed, 5 left: one day to spare")
        self.assertIsNone(reminders.nudge(st, [blk(mon)], [], CFG, WED, 90), "1 done, 3 needed, 5 left: two to spare")
        sat = WED + timedelta(days=3)       # 2 days left
        self.assertIsNotNone(reminders.nudge(st, [blk(mon), blk(mon + timedelta(days=1))], [], CFG, sat, 90), "2 needed, 2 left")
        self.assertIsNone(reminders.nudge(st, [blk(mon)], [], CFG, sat, 90), "3 needed, 2 left: already lost, no nagging")
        four = [blk(mon + timedelta(days=i)) for i in range(2)] + [blk(WED - timedelta(days=7))]
        self.assertIsNone(reminders.nudge(st, four[:2] + [blk(mon), blk(mon)], [], dict(CFG, goals={"day_minutes": 60, "week_days": 2}), sat, 90),
                          "goal already met")


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


class PresenceTest(unittest.TestCase):
    def test_counts_minutes_at_the_computer_and_resets_each_day(self):
        idle = [10]
        p = reminders.Presence(idle=lambda: idle[0])
        for i in range(3):
            p.tick(WED + timedelta(minutes=i))
        idle[0] = 600
        self.assertEqual(p.tick(WED + timedelta(minutes=3)), 3, "away from the keyboard doesn't count")
        idle[0] = 10
        self.assertEqual(p.tick(WED + timedelta(days=1)), 1, "a new day starts from zero")
        self.assertEqual(reminders.Presence(idle=lambda: None).tick(WED), 1, "where idle time is unknown, being up counts")


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
    """The real server: one nudge a day through the notifier, never during a block; the recap file on Sunday."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-rem-")
        self.vault, _ = make_vault(self.tmp)
        os.environ["EDU4SELF_CONFIG_HOME"] = os.path.join(self.tmp, "cfg")
        self.out = os.path.join(self.tmp, "notified.txt")
        note = os.path.join(self.tmp, "notify.sh")
        with open(note, "w") as fh:
            fh.write('#!/bin/sh\nprintf "%%s|%%s\\n" "$1" "$2" >> %s\n' % self.out)
        os.chmod(note, 0o755)
        os.environ["EDU4SELF_NOTIFY"] = note
        st = read_json(os.path.join(self.vault, "_system", "state.json"))
        q = st["topics"][0]["queue"][0]
        q["opens"] = WED.date().isoformat()
        q["status"] = "todo"
        with open(os.path.join(self.vault, "_system", "state.json"), "w") as fh:
            json.dump(st, fh)
        open(os.path.join(self.vault, "_system", "blocks.jsonl"), "w").close()
        self.port = free_port()
        self.httpd = server.make_server(self.vault, self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        server.PRESENCE = reminders.Presence(idle=lambda: 0)
        server.BLOCK_UNTIL = None

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        for k in ("EDU4SELF_CONFIG_HOME", "EDU4SELF_NOTIFY"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def notified(self):
        return open(self.out).read().splitlines() if os.path.exists(self.out) else []

    def warm_up(self, start):
        for i in range(59):
            server.reminder_tick(start + timedelta(minutes=i - 59))   # 59 minutes at the computer; the next tick is the 60th

    def test_one_nudge_a_day_with_a_link_to_the_task(self):
        self.warm_up(WED)
        self.assertEqual(server.reminder_tick(WED)[0], "nudge")
        self.assertIsNone(server.reminder_tick(WED + timedelta(minutes=5)), "once a day")
        lines = [l for l in self.notified() if "|" in l]   # one line per notification (the body runs on)
        self.assertEqual(len(lines), 1)
        self.assertIn("#submit=", lines[0] + open(self.out).read())
        self.assertIn(WED.date().isoformat(), read_json(os.path.join(self.vault, "_system", "reminders.json"))["nudged"])

    def test_a_block_running_in_the_page_holds_the_nudge(self):
        import http.client
        now = datetime.now().astimezone() + timedelta(minutes=1)    # the block's end is set from the real clock
        hours, reminders.NUDGE_HOURS = reminders.NUDGE_HOURS, (0, 24)   # so this runs at any hour
        self.addCleanup(setattr, reminders, "NUDGE_HOURS", hours)
        st = read_json(os.path.join(self.vault, "_system", "state.json"))
        st["topics"][0]["queue"][0]["opens"] = now.date().isoformat()
        with open(os.path.join(self.vault, "_system", "state.json"), "w") as fh:
            json.dump(st, fh)
        with open(os.path.join(self.vault, "_system", "reminders.json"), "w") as fh:   # no recap in the way
            json.dump({"recaps": [reminders.week_id(now.date()), reminders.week_id(now.date() - timedelta(days=1))]}, fh)
        self.warm_up(now)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        until = (datetime.now().astimezone() + timedelta(minutes=30)).isoformat()
        c.request("POST", "/api/presence", json.dumps({"block_until": until}),
                  {"Content-Type": "application/json", "Host": "127.0.0.1:%d" % self.port, "Origin": "http://127.0.0.1:%d" % self.port})
        self.assertEqual(c.getresponse().status, 200)
        self.assertIsNone(server.reminder_tick(now))
        self.assertEqual(self.notified(), [])
        server.BLOCK_UNTIL = None                       # the block ends: now the nudge may go
        self.assertEqual(server.reminder_tick(now)[0], "nudge")

    def test_switched_off_means_quiet(self):
        with open(os.path.join(self.vault, "_system", "config.json"), "w") as fh:
            json.dump({"reminders": {"notify": False, "mail": False}}, fh)
        self.warm_up(WED)
        self.assertIsNone(server.reminder_tick(WED))
        self.assertEqual(self.notified(), [])

    def test_sunday_writes_the_recap_and_says_so(self):
        sun = datetime(2026, 11, 8, 19, 30).astimezone()
        kind, title = server.reminder_tick(sun)
        self.assertEqual(kind, "recap")
        path = os.path.join(self.vault, "recaps", "2026-W45.md")
        self.assertTrue(os.path.isfile(path))
        self.assertIn("# Your week", open(path).read())
        self.assertTrue(any(l.startswith("Your week") for l in self.notified()))
        self.assertIsNone(server.reminder_tick(sun + timedelta(minutes=1)))


if __name__ == "__main__":
    unittest.main()
