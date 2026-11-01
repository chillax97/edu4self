"""Trophies (keepsakes): what you won by meeting your goals, kept on a shelf in your vault.

Three kinds, from the focus blocks alone:
  day   a day whose blocks reach the daily goal (minutes)
  week  a week (Monday to Sunday) with blocks on at least the weekly goal's number of days
  die   every 24 tiles of 25 minutes, counted over all blocks ever (10 hours)

A trophy is drawn by the room it was won in, and keeps that drawing for good: the drawing is copied into
_system/keepsakes.json when it's won, so changing or deleting the room later changes nothing, and a shelf
can hold trophies from several rooms. The server is the only writer of that file.

The first time this runs on a vault with history, everything already earned is awarded at once, quietly
(no gifts, no fuss). After that, a week or die won "now" also gets a gift: a Claude run that makes the
learner something (see server.gift_*).
"""
import hashlib
import json
import os
import threading
from datetime import datetime, timedelta

TILE_MIN = 25
DIE_TILES = 24
LOCK = threading.Lock()


def local_dt(iso):
    """A block timestamp (UTC 'Z' or with an offset) in this computer's local time."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except (AttributeError, ValueError):
        return None


def monday_of(d):
    return d - timedelta(days=d.weekday())


def earned(blocks, day_minutes, week_days):
    """Every trophy these blocks earn: [{id, kind, ts, key...}], ordered by when it was earned.
    ts is the end of the block that crossed the line. Mirrors the dashboard's own counting (app.js:
    tonight(), dieNow()): a block belongs to the local day it ended on."""
    rows = []
    for b in blocks:
        end = local_dt(b.get("ts") or b.get("started") or "")
        mins = b.get("minutes")
        if end is None or not isinstance(mins, int) or mins <= 0:
            continue
        rows.append((end, mins, b.get("ts") or b.get("started")))
    rows.sort(key=lambda r: r[0])
    out, day_total, week_days_seen, total = [], {}, {}, 0
    days_won, weeks_won = set(), set()
    for end, mins, ts in rows:
        day = end.date()
        before = day_total.get(day, 0)
        day_total[day] = before + mins
        if before < day_minutes <= day_total[day] and day not in days_won:
            days_won.add(day)
            out.append({"id": "day-%s" % day.isoformat(), "kind": "day", "ts": ts, "date": day.isoformat(),
                        "minutes": day_total[day]})
        mon = monday_of(day)
        seen = week_days_seen.setdefault(mon, set())
        seen.add(day)
        if len(seen) >= week_days and mon not in weeks_won:
            weeks_won.add(mon)
            iso = mon.isocalendar()
            out.append({"id": "week-%d-W%02d" % (iso[0], iso[1]), "kind": "week", "ts": ts, "date": mon.isoformat(),
                        "days": len(seen)})
        old_dies = (total // TILE_MIN) // DIE_TILES
        total += mins
        for n in range(old_dies + 1, (total // TILE_MIN) // DIE_TILES + 1):
            out.append({"id": "die-%d" % n, "kind": "die", "ts": ts, "date": day.isoformat(), "n": n})
    return out


def is_now(item, now):
    """Was this won in the current period? Only those get a gift; anything older is backfill."""
    d = datetime.fromisoformat(item["date"]).date()
    today = now.date()
    if item["kind"] == "day":
        return d == today
    if item["kind"] == "week":
        return d == monday_of(today)
    end = local_dt(item["ts"])
    return end is not None and now - end < timedelta(days=1)


def art_key(theme_id, kind, art):
    return "%s-%s-%s" % (theme_id, kind, hashlib.sha1(art.encode("utf-8")).hexdigest()[:8])


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("items"), list) and isinstance(data.get("art"), dict):
            return data
    except (OSError, ValueError):
        pass
    return None


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sync(path, blocks, day_minutes, week_days, theme_id, theme_keepsakes, now=None):
    """Add any trophy earned but not yet on the shelf. Returns the new items.
    The first sync on a vault awards its whole history quietly (backfill: true, no gift)."""
    now = now or datetime.now().astimezone()
    with LOCK:
        data = load(path)
        first = data is None
        if first:
            data = {"version": 1, "items": [], "art": {}}
        have = {i["id"] for i in data["items"]}
        new = []
        for item in earned(blocks, day_minutes, week_days):
            if item["id"] in have:
                continue
            look = theme_keepsakes[item["kind"]]
            key = art_key(theme_id, item["kind"], look["art"])
            data["art"].setdefault(key, look["art"])
            quiet = first or not is_now(item, now)
            item.update(theme=theme_id, name=look["name"], plural=look.get("plural", look["name"] + "s"),
                        stack=look.get("stack", "pile"), art=key, won=now.isoformat(timespec="seconds"),
                        backfill=quiet, gift=None if quiet or item["kind"] == "day" else "pending")
            data["items"].append(item)
            have.add(item["id"])
            new.append(item)
        if new or first:
            save(path, data)
        return new


def set_gift(path, item_id, value):
    with LOCK:
        data = load(path)
        if not data:
            return
        for i in data["items"]:
            if i["id"] == item_id:
                i["gift"] = value
        save(path, data)


def pending_gift(path):
    data = load(path) or {"items": []}
    for i in data["items"]:
        if i.get("gift") == "pending":
            return i
    return None
