"""Reminders, by mail only: a note when you've been away, and a recap every Sunday.

The away mail goes out after 3, 7, 15 and 30 days without a study action (a focus block saved, an
answer or a note sent), then every 30 days while you stay away. Each step goes out once; your next
study action starts the ladder again. It says what you've already done, then offers one small thing
to do today, so coming back feels cheap. It goes out between 09:00 and 22:00, never while a block runs,
and only when mail is set up (`edu4self mail setup`) and switched on in Settings.

The recap goes out once a week, on Sunday from 19:00 (or the first chance after, until Monday ends). It's
written to recaps/<year>-W<week>.md in the vault, and mailed when mail is set up.

Mail settings (server, account, app password) live outside the vault, in the edu4self config folder
(mail.json, readable only by you), so they never end up in a synced or shared vault. If you choose, the
app password goes to the system's password store instead (macOS Keychain, or the Secret Service on
Linux desktops) and mail.json only says where it is. See PASSWORD_STORES for what each one protects.
"""
import json
import os
import platform
import shutil
import smtplib
import ssl
import subprocess
from datetime import datetime, timedelta
from email.message import EmailMessage

AWAY_STEPS = (3, 7, 15, 30)    # days without a study action that send a mail; then every 30 days
AWAY_REPEAT = 30
MAIL_HOURS = (9, 22)           # local hours an away mail may go out in: from 09:00, before 22:00
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


def last_activity(blocks, inbox):
    """When you last did something: the latest saved block or sent entry (answers, notes), or None."""
    times = [local_dt(b.get("ts") or b.get("started") or "") for b in blocks]
    times += [local_dt(e.get("ts") or "") for e in inbox]
    times = [t for t in times if t]
    return max(times) if times else None


def away_step(last, now):
    """The away step reached now (3, 7, 15, 30, 60, 90...), or None before day 3."""
    if not last:
        return None
    days = (now.date() - last.date()).days
    if days < AWAY_STEPS[0]:
        return None
    if days < AWAY_REPEAT:
        return max(s for s in AWAY_STEPS if s <= days)
    return AWAY_REPEAT * (days // AWAY_REPEAT)


def away_due(blocks, inbox, now, sent, block_until=None):
    """(key, step, last) when an away mail should go out now, else None. The key marks it as sent."""
    if not MAIL_HOURS[0] <= now.hour < MAIL_HOURS[1] or (block_until and block_until > now):
        return None
    last = last_activity(blocks, inbox)
    step = away_step(last, now)
    if step is None:
        return None
    key = "%s+%d" % (last.date().isoformat(), step)
    return None if key in sent.get("away", []) else (key, step, last)


OPENERS = {
    3: ("Three days off. Your next step is waiting", "It's been three days. A short break is fine, and everything you built is still here."),
    7: ("A week away. Here's what you've built", "It's been a week. Starting again feels bigger than it is: the next step is small."),
    15: ("Two weeks away. Pick up where you left off", "It's been two weeks. You don't have to catch up on anything. Just start where you left off."),
}


def away(state, blocks, keepsake_items, cfg, step, last, pending_tasks, port):
    """(title, plain-text body) for an away mail: what you did, then one small thing for today."""
    if step in OPENERS:
        title, opener = OPENERS[step]
    else:
        title = "%d days away. Nothing is lost" % step
        opener = "It's been %d days. Your progress, your trophies and your next step are all where you left them." % step
    days = block_days(blocks)
    hours = sum(days.values()) / 60
    proven = []
    for t in state.get("topics", []):
        for h in t.get("history", []):
            if h.get("evidence"):
                proven.append((h.get("date") or "", h.get("title") or ""))
    proven.sort(reverse=True)
    done = ["%s focused hour%s over %d day%s" % (("%.1f" % hours).rstrip("0").rstrip("."), "" if round(hours, 1) == 1 else "s",
                                                 len(days), "" if len(days) == 1 else "s")] if days else []
    if proven:
        done.append("%d thing%s proven, most recently: %s" % (len(proven), "" if len(proven) == 1 else "s",
                                                             "; ".join(p[1] for p in proven[:3])))
    if keepsake_items:
        counts = {}
        for i in keepsake_items:
            k = i.get("plural") or i.get("name") or "trophy"
            counts[k] = counts.get(k, 0) + 1
        done.append("On your shelf: " + ", ".join("%d %s" % (n, k) for k, n in counts.items()))
    lines = [opener, ""]
    if done:
        lines += ["What you've done so far:"] + ["- " + d for d in done] + [""]
    lines.append("Your last session was on %s." % last.strftime("%A %-d %B"))
    lines.append("")
    minutes = min(cfg.get("blocks", {}).get("presets") or [25])
    nxt = None
    for t in state.get("topics", []):
        for q in t.get("queue", []):
            if q.get("status") == "todo" and q.get("id") not in pending_tasks:
                nxt = (t, q)
                break
        if nxt:
            break
    lines.append("Something small for today:")
    if nxt:
        t, q = nxt
        name = (q.get("label") + ": " if q.get("label") else "") + q.get("title", "")
        lines.append("%s, in %s. Open it and do only the first part. One %d-minute block is enough to pick the thread back up."
                     % (name, t.get("title", ""), minutes))
        lines.append("http://127.0.0.1:%d/#submit=%s" % (port, q.get("id")))
    else:
        lines.append("One %d-minute block of anything you like. It counts." % minutes)
        lines.append("http://127.0.0.1:%d/" % port)
    lines += ["", "(You get these after 3, 7, 15 and 30 days away, then once a month. Switch them off in Settings.)"]
    return title, "\n".join(lines)


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
    proven, nxt = [], []
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
    lines += ["", "Dashboard: http://127.0.0.1:%d/" % port, ""]
    return title, "\n".join(lines)


# ---------------------------------------------------------------- delivery

def config_dir():
    return os.environ.get("EDU4SELF_CONFIG_HOME") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "edu4self")


def mail_path():
    return os.path.join(config_dir(), "mail.json")


MAIL_KEYS = ("host", "port", "security", "user", "password", "to")


# Where the app password can live. Each entry: what it is, and the risks, shown before the learner picks.
PASSWORD_STORES = {
    "file": ("a file only you can read (%s)",
             "Any program running as you can read it, and it's copied into backups of your home folder."),
    "keychain": ("the macOS Keychain",
                 "Encrypted on disk and locked when you log out. Any program running as you can still ask for "
                 "it through the `security` tool once it's stored this way. If the Keychain is locked, mail "
                 "waits until you log in."),
    "secret-service": ("your desktop's password store (Secret Service, through secret-tool)",
                       "Encrypted on disk and locked when you log out. Any program in your session can ask for "
                       "it. Without a desktop session (a server, plain SSH) it can't be read and mail fails."),
}
SECRET_SERVICE = "edu4self-mail"


def password_stores():
    """The stores this computer has, the plain file first."""
    out = ["file"]
    if platform.system() == "Darwin" and shutil.which("security"):
        out.append("keychain")
    if shutil.which("secret-tool"):
        out.append("secret-service")
    return out


def _run(cmd, stdin=""):
    """Run a password-store command; the password only ever travels on stdin or stdout, never in argv."""
    try:
        p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return p.returncode, p.stdout, p.stderr


def store_password(store, user, pw):
    """Put the password in the store. Raises OSError when the store refuses."""
    if store == "keychain":
        q = lambda v: '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        rc, _, err = _run(["security", "-i"], "add-generic-password -U -a %s -s %s -w %s\n" % (q(user), q(SECRET_SERVICE), q(pw)))
    elif store == "secret-service":
        rc, _, err = _run(["secret-tool", "store", "--label=edu4self mail", "service", SECRET_SERVICE, "account", user], pw)
    else:
        raise OSError("unknown password store %r" % store)
    if rc != 0 or read_password(store, user) != pw:
        raise OSError("the %s didn't keep the password: %s" % (store, (err or "").strip()[:200] or "no reason given"))


def read_password(store, user):
    """The password from the store, or None."""
    if store == "keychain":
        rc, out, _ = _run(["security", "find-generic-password", "-a", user, "-s", SECRET_SERVICE, "-w"])
    elif store == "secret-service":
        rc, out, _ = _run(["secret-tool", "lookup", "service", SECRET_SERVICE, "account", user])
    else:
        return None
    return out.rstrip("\n") if rc == 0 and out else None


def forget_password(store, user):
    if store == "keychain":
        _run(["security", "delete-generic-password", "-a", user, "-s", SECRET_SERVICE])
    elif store == "secret-service":
        _run(["secret-tool", "clear", "service", SECRET_SERVICE, "account", user])


def load_mail():
    """The mail account, or None when it isn't set up (or the file is broken). With the password in a
    system store, "password" is filled in from there, or None when the store won't give it."""
    try:
        with open(mail_path(), encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(m, dict) or any(k not in m for k in MAIL_KEYS):
        return None
    store = m.get("password_store", "file")
    if store != "file":
        m["password"] = read_password(store, m["user"])
    return m


def save_mail(m):
    """Save the account. With password_store set to a system store, the password goes there, not the file."""
    store = m.get("password_store", "file")
    out = dict(m)
    if store != "file":
        store_password(store, m["user"], m["password"])
        out["password"] = ""
    os.makedirs(config_dir(), exist_ok=True)
    path = mail_path()
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    os.chmod(path + ".tmp", 0o600)
    os.replace(path + ".tmp", path)


def send_mail(m, subject, body):
    """Send one plain-text mail. Raises on failure (OSError or smtplib.SMTPException)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = m.get("from") or m["user"]
    msg["To"] = m["to"]
    msg.set_content(body)
    if m.get("password") is None:
        raise smtplib.SMTPException("couldn't read the mail password from the %s (locked, or removed?)"
                                    % PASSWORD_STORES.get(m.get("password_store"), ("password store",))[0])
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


# ---------------------------------------------------------------- the sent log

def load_sent(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return {"away": list(d.get("away", []))[-60:], "recaps": list(d.get("recaps", []))[-60:],
                    "errors": list(d.get("errors", []))[-20:]}
    except (OSError, ValueError):
        pass
    return {"away": [], "recaps": [], "errors": []}


def save_sent(path, d):
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    os.replace(path + ".tmp", path)
