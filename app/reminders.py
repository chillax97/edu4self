"""Reminders: one gentle nudge on a day you haven't studied, and a recap every Sunday.

The nudge goes out at most once a day, and only when all of these hold:
  - there's a reason: a task opens today (its "opens" date), or the week's goal is at risk (the days you
    still need are as many as, or one fewer than, the days left in the week);
  - nothing edu happened today: no block saved, no answer submitted, no block running in the page;
  - you've been at the computer for an hour today (macOS: keyboard or mouse used in the last 2 minutes,
    counted minute by minute; elsewhere the minutes the server has been up);
  - it's between 09:00 and 22:00.
It's a desktop notification and/or a mail, each switched on in Settings.

The recap goes out once a week, on Sunday from 19:00 (or the first chance after, until Monday ends). It's
written to recaps/<year>-W<week>.md in the vault, shown as a notification, and mailed when mail is set up.

Mail settings (server, account, app password) live outside the vault, in the edu4self config folder
(mail.json, readable only by you), so they never end up in a synced or shared vault.
"""
import json
import os
import platform
import re
import shutil
import smtplib
import ssl
import subprocess
from datetime import datetime, timedelta
from email.message import EmailMessage

ACTIVE_IDLE = 120          # seconds without input that still count as "at the computer"
NUDGE_AFTER = 60           # minutes at the computer today before a nudge may go out
NUDGE_HOURS = (9, 22)      # local hours a nudge may go out in: from 09:00, before 22:00
RECAP_HOUR = 19            # Sunday, from this hour


# ---------------------------------------------------------------- reading the vault

def local_dt(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def monday(d):
    return d - timedelta(days=d.weekday())


def week_id(d):
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def block_days(blocks):
    """{local date: minutes} over all blocks."""
    out = {}
    for b in blocks:
        t = local_dt(b.get("ts") or b.get("started") or "")
        m = b.get("minutes")
        if t and isinstance(m, int) and m > 0:
            out[t.date()] = out.get(t.date(), 0) + m
    return out


def studied_today(blocks, inbox, today, block_until, now):
    """Anything edu today: a block saved, an answer sent, or a block running right now."""
    if today in block_days(blocks):
        return True
    for e in inbox:
        t = local_dt(e.get("ts") or "")
        if t and t.date() == today:
            return True
    return bool(block_until and block_until > now)


def opening_today(state, today):
    """Tasks whose opens date is today and that are still to do: [(topic title, task)]."""
    out = []
    for t in state.get("topics", []):
        for q in t.get("queue", []):
            if q.get("opens") == today.isoformat() and q.get("status") != "done":
                out.append((t.get("title", ""), q))
    return out


def week_at_risk(blocks, today, week_days):
    """(days done this week, days still needed, days left including today) when the goal is at risk, else None.
    At risk: still reachable, and with at most one day to spare."""
    mon = monday(today)
    done = len([d for d in block_days(blocks) if mon <= d <= today])
    need = week_days - done
    left = 7 - today.weekday()
    if need > 0 and left - 1 <= need <= left:
        return done, need, left
    return None


def nudge(state, blocks, inbox, cfg, now, active_minutes, block_until=None):
    """The nudge to send now as (title, body, link task id), or None."""
    today = now.date()
    if not NUDGE_HOURS[0] <= now.hour < NUDGE_HOURS[1] or active_minutes < NUDGE_AFTER:
        return None
    if studied_today(blocks, inbox, today, block_until, now):
        return None
    opens = opening_today(state, today)
    if opens:
        topic, q = opens[0]
        name = (q.get("label") + ": " if q.get("label") else "") + q.get("title", "")
        more = " (and %d more)" % (len(opens) - 1) if len(opens) > 1 else ""
        return ("Opens today: %s" % (q.get("label") or q.get("title")),
                "%s%s, in %s. It's spaced on purpose: today is when it works best. One 25-minute block is enough." % (name, more, topic),
                q.get("id"))
    risk = week_at_risk(blocks, today, cfg["goals"]["week_days"])
    if risk:
        done, need, left = risk
        tail = "Every day left counts now." if need == left else "One day to spare."
        return ("Your week needs today",
                "%d of %d days so far, %d more to go, %d days left including today. %s A 25-minute block counts."
                % (done, cfg["goals"]["week_days"], need, left, tail), None)
    return None


def recap_due(now, sent):
    """The week to recap now, or None: from Sunday 19:00 until Monday ends, once per week."""
    d = now.date()
    if d.weekday() == 6 and now.hour >= RECAP_HOUR:
        week = d
    elif d.weekday() == 0:
        week = d - timedelta(days=1)
    else:
        return None
    wid = week_id(week)
    return None if wid in sent.get("recaps", []) else (wid, monday(week))


def recap(state, blocks, keepsake_items, cfg, mon, port):
    """(title, markdown body) for the week starting mon."""
    sun = mon + timedelta(days=6)
    days = {d: m for d, m in block_days(blocks).items() if mon <= d <= sun}
    mins = sum(days.values())
    goal_days = cfg["goals"]["week_days"]
    won = len(days) >= goal_days
    goal_hit = len([m for m in days.values() if m >= cfg["goals"]["day_minutes"]])
    proven, nxt, opens = [], [], []
    for t in state.get("topics", []):
        for h in t.get("history", []):
            try:
                hd = datetime.fromisoformat(h.get("date", "")).date()
            except ValueError:
                continue
            if h.get("evidence") and mon <= hd <= sun:
                proven.append("%s: %s" % (t.get("title", ""), h.get("title", "")))
        todo = [q for q in t.get("queue", []) if q.get("status") == "todo"]
        if todo:
            q = todo[0]
            nxt.append("%s: %s%s" % (t.get("title", ""), (q.get("label") + ", ") if q.get("label") else "", q.get("title", "")))
        for q in t.get("queue", []):
            o = q.get("opens")
            if o and q.get("status") != "done" and (sun + timedelta(days=1)).isoformat() <= o <= (sun + timedelta(days=7)).isoformat():
                opens.append("%s: %s (opens %s)" % (t.get("title", ""), q.get("label") or q.get("title", ""), o))
    trophies = [i for i in keepsake_items if not i.get("backfill") and mon.isoformat() <= str(i.get("date", ""))[:10] <= sun.isoformat()]
    title = "Your week, %s to %s: %s" % (mon.strftime("%-d %b"), sun.strftime("%-d %b"),
                                         "goal met" if won else "%d of %d days" % (len(days), goal_days))
    lines = ["# " + title, "",
             "- %d focused minutes on %d day%s (goal: %d days)" % (mins, len(days), "" if len(days) == 1 else "s", goal_days),
             "- %d day%s reached the daily goal of %d minutes" % (goal_hit, "" if goal_hit == 1 else "s", cfg["goals"]["day_minutes"])]
    if trophies:
        counts = {}
        for i in trophies:
            counts[i["name"]] = counts.get(i["name"], 0) + 1
        lines.append("- Trophies: " + ", ".join("%d %s" % (n, k) for k, n in counts.items()))
    lines += ["", "## Proven this week", ""] + (["- " + p for p in proven] or ["- Nothing graded this week. The minutes still count."])
    if nxt:
        lines += ["", "## Up next", ""] + ["- " + n for n in nxt]
    if opens:
        lines += ["", "## Opening next week", ""] + ["- " + o for o in opens]
    lines += ["", "Dashboard: http://127.0.0.1:%d/" % port, ""]
    return title, "\n".join(lines)


# ---------------------------------------------------------------- presence

def idle_seconds():
    """Seconds since the last keyboard or mouse input, or None where we can't tell (not macOS)."""
    if platform.system() != "Darwin":
        return None
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
    return int(m.group(1)) / 1e9 if m else None


class Presence:
    """Minutes at the computer today, counted once a minute."""

    def __init__(self, idle=idle_seconds):
        self.idle, self.day, self.minutes = idle, None, 0

    def tick(self, now):
        if now.date() != self.day:
            self.day, self.minutes = now.date(), 0
        s = self.idle()
        if s is None or s < ACTIVE_IDLE:
            self.minutes += 1
        return self.minutes


# ---------------------------------------------------------------- delivery

def config_dir():
    return os.environ.get("EDU4SELF_CONFIG_HOME") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "edu4self")


def mail_path():
    return os.path.join(config_dir(), "mail.json")


MAIL_KEYS = ("host", "port", "security", "user", "password", "to")


def load_mail():
    """The mail account, or None when it isn't set up (or the file is broken)."""
    try:
        with open(mail_path(), encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(m, dict) or any(k not in m for k in MAIL_KEYS):
        return None
    return m


def save_mail(m):
    os.makedirs(config_dir(), exist_ok=True)
    path = mail_path()
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1)
    os.chmod(path + ".tmp", 0o600)
    os.replace(path + ".tmp", path)


def send_mail(m, subject, body):
    """Send one plain-text mail. Raises on failure (OSError or smtplib.SMTPException)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = m.get("from") or m["user"]
    msg["To"] = m["to"]
    msg.set_content(body)
    sec, host, port = m["security"], m["host"], int(m["port"])
    if sec == "none" and host not in ("127.0.0.1", "localhost"):
        raise smtplib.SMTPException("mail without encryption is only allowed to this computer")
    if sec == "ssl":
        s = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20)
    else:
        s = smtplib.SMTP(host, port, timeout=20)
    try:
        if sec == "starttls":
            s.starttls(context=ssl.create_default_context())
        if sec != "none" or m.get("password"):
            s.login(m["user"], m["password"])
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except (OSError, smtplib.SMTPException):
            pass


def notify(title, body):
    """A desktop notification. False when this computer has no way to show one."""
    cmd = os.environ.get("EDU4SELF_NOTIFY")   # tests (and anyone) can swap in their own command
    try:
        if cmd:
            subprocess.run([cmd, title, body], timeout=10, check=False)
            return True
        if platform.system() == "Darwin":
            q = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
            subprocess.run(["osascript", "-e", "display notification %s with title %s" % (q(body[:240]), q("edu4self: " + title))],
                           timeout=10, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "edu4self: " + title, body[:240]], timeout=10, check=False)
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    return False


# ---------------------------------------------------------------- the sent log

def load_sent(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return {"nudged": list(d.get("nudged", []))[-60:], "recaps": list(d.get("recaps", []))[-60:],
                    "errors": list(d.get("errors", []))[-20:]}
    except (OSError, ValueError):
        pass
    return {"nudged": [], "recaps": [], "errors": []}


def save_sent(path, d):
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    os.replace(path + ".tmp", path)
