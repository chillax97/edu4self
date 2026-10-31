#!/usr/bin/env python3
"""edu4self dashboard server.

Serves the dashboard at http://127.0.0.1:4747, exposes the learning state as JSON,
and appends the learner's submissions to an inbox that Claude reads and grades.

Python 3.9+ standard library only. Binds to 127.0.0.1, never to the network.

The code (this folder) and the learner's data (the vault) live apart, so updating the
code never touches the data. The vault is picked with --vault or EDU4SELF_VAULT.

Files it reads:   _system/state.json (written by Claude), _system/config.json, topic folders.
Files it writes:  _system/inbox.jsonl and _system/blocks.jsonl (append-only),
                  _system/config.json and _system/music/ (from the Settings panel). Nothing else.
"""
import argparse
import copy
import html
import json
import mimetypes
import os
import posixpath
import re
import sys
import threading
import urllib.parse
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(APP, "dashboard")
VERSION = "1.0.0"

HOST = "127.0.0.1"
MAX_BODY = 64 * 1024
MAX_MUSIC = 1024 * 1024 * 1024          # 1 GiB: a few hours of compressed audio
MUSIC_EXTS = {".m4a", ".mp3", ".ogg", ".opus", ".wav", ".flac", ".aac", ".webm"}
KINDS = {"answers", "done", "note"}
INBOX_LOCK = threading.Lock()
BLOCKS_LOCK = threading.Lock()
CONFIG_LOCK = threading.Lock()

# Set by configure(); module-level so the handler and the tests share them.
ROOT = SYSTEM = STATE = INBOX = BLOCKS = CONFIG = MUSIC_DIR = None
PORT = 4747
ALLOWED_HOSTS = set()
ALLOWED_ORIGINS = set()


def configure(vault, port):
    """Point the server at a vault folder and a port."""
    global ROOT, SYSTEM, STATE, INBOX, BLOCKS, CONFIG, MUSIC_DIR, PORT, ALLOWED_HOSTS, ALLOWED_ORIGINS
    ROOT = os.path.abspath(os.path.expanduser(vault))
    SYSTEM = os.path.join(ROOT, "_system")
    STATE = os.path.join(SYSTEM, "state.json")
    INBOX = os.path.join(SYSTEM, "inbox.jsonl")
    BLOCKS = os.path.join(SYSTEM, "blocks.jsonl")
    CONFIG = os.path.join(SYSTEM, "config.json")
    MUSIC_DIR = os.path.join(SYSTEM, "music")
    PORT = int(port)
    ALLOWED_HOSTS = {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
    ALLOWED_ORIGINS = {"http://" + h for h in ALLOWED_HOSTS}


# ---------------------------------------------------------------- settings
# Everything a learner may want to change without code. The dashboard's Settings panel edits it;
# people can also edit _system/config.json by hand. Missing keys fall back to these defaults.
DEFAULT_CONFIG = {
    "name": "",                     # what the dashboard calls you; empty = state.json "learner"
    "view": "bar",                  # default look: "bar" or "classic" (each browser can switch)
    "goals": {"day_minutes": 120, "week_days": 4},
    "blocks": {
        "presets": [25, 50, 90],
        "kinds": [
            {"id": "lessons", "label": "Lessons", "color": "lesson"},
            {"id": "practice", "label": "Practice", "color": "mock", "minutes": 60},
            {"id": "reading", "label": "Reading", "color": "reading"},
            {"id": "free", "label": "Free", "color": "probe"},
            {"id": "play", "label": "Play", "color": "checkpoint"},
        ],
    },
    "water": {"every": 15},         # minutes between glasses during a block: 15, 30 or 0 (off)
    "obsidian": {"enabled": False, "vault": ""},
    "bar": {
        "names": [
            ["Cache Miss", "nobody remembers your name"],
            ["The Last Token", "last call, every step"],
            ["Bad Tokens", "loud, wrong, and proud of it"],
            ["Exploding Gradients", "no ceiling, no mercy"],
            ["Dead Neurons", "switched off since forever"],
        ],
        "voices": {},               # per-voice overrides: {"logic": {"name": "Spock", "color": "#85b8ff"}}
        "gags": True,               # the rotating bar jokes
        "lines": [],                # your own lines: [{"voice": "regular", "text": "..."}]
    },
    # source: "scape" (built in, made in the browser, offline), "radio" (a stream URL) or "file" (an upload)
    "music": {"source": "scape", "scape": "night", "stream": {"url": "", "name": ""},
              "file": "", "title": "", "subtitle": "", "autoplay": False},
}
MUSIC_SOURCES = ("scape", "radio", "file")
SCAPES = ("night", "rain", "noise")
VOICE_IDS = {"bartender", "logic", "volition", "gpu", "encyclopedia", "physical", "nostalgia",
             "critic", "regular", "jukebox", "you"}
COLOR_TOKENS = {"lesson", "probe", "checkpoint", "reading", "project", "mock", "coral", "amber", "green"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
ID = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")


def _text(v, limit, what):
    if not isinstance(v, str) or len(v) > limit:
        raise ValueError("%s must be text of at most %d characters" % (what, limit))
    return v.strip()


def _int(v, lo, hi, what):
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise ValueError("%s must be a whole number from %d to %d" % (what, lo, hi))
    return v


def clean_config(body):
    """Validate a full config object. Raises ValueError with a message a person can act on."""
    if not isinstance(body, dict):
        raise ValueError("settings must be an object")
    c = merged_config(body)
    out = {
        "name": _text(c["name"], 60, "name"),
        "view": c["view"] if c["view"] in ("bar", "classic") else "bar",
        "goals": {"day_minutes": _int(c["goals"].get("day_minutes"), 10, 960, "daily goal"),
                  "week_days": _int(c["goals"].get("week_days"), 1, 7, "weekly goal")},
        "water": {"every": c["water"].get("every") if c["water"].get("every") in (0, 15, 30) else 15},
    }
    b = c["blocks"]
    presets = b.get("presets")
    if not isinstance(presets, list) or not 1 <= len(presets) <= 4:
        raise ValueError("block presets: give 1 to 4 durations")
    kinds = b.get("kinds")
    if not isinstance(kinds, list) or not 1 <= len(kinds) <= 8:
        raise ValueError("block kinds: give 1 to 8")
    seen, ck = set(), []
    for k in kinds:
        if not isinstance(k, dict) or not isinstance(k.get("id"), str) or not ID.match(k["id"]):
            raise ValueError("block kind ids are lowercase letters, digits, - or _ (max 24)")
        if k["id"] in seen:
            raise ValueError("block kind %s appears twice" % k["id"])
        seen.add(k["id"])
        color = k.get("color", "lesson")
        if color not in COLOR_TOKENS and not (isinstance(color, str) and HEX.match(color)):
            raise ValueError("block kind %s: color must be #rrggbb or one of %s" % (k["id"], ", ".join(sorted(COLOR_TOKENS))))
        item = {"id": k["id"], "label": _text(k.get("label") or k["id"], 24, "block label") or k["id"], "color": color}
        if k.get("minutes") not in (None, "", 0):
            item["minutes"] = _int(k["minutes"], 1, 240, "block minutes")
        ck.append(item)
    out["blocks"] = {"presets": [_int(p, 1, 240, "preset") for p in presets], "kinds": ck}
    o = c["obsidian"]
    out["obsidian"] = {"enabled": bool(o.get("enabled")), "vault": _text(o.get("vault") or "", 120, "Obsidian vault name")}
    bar = c["bar"]
    names = bar.get("names")
    if not isinstance(names, list) or not 1 <= len(names) <= 20:
        raise ValueError("bar names: give 1 to 20")
    cn = []
    for n in names:
        if not isinstance(n, list) or not 1 <= len(n) <= 2:
            raise ValueError("each bar name is [name, tagline]")
        nm = _text(n[0], 40, "bar name")
        if nm:
            cn.append([nm, _text(n[1] if len(n) > 1 else "", 80, "bar tagline")])
    if not cn:
        raise ValueError("give the bar at least one name")
    voices = bar.get("voices") or {}
    if not isinstance(voices, dict):
        raise ValueError("voices must be an object")
    cv = {}
    for vid, v in voices.items():
        if vid not in VOICE_IDS or not isinstance(v, dict):
            raise ValueError("unknown voice %s" % vid)
        e = {}
        if v.get("name"):
            e["name"] = _text(v["name"], 30, "voice name")
        if v.get("color"):
            if not HEX.match(str(v["color"])):
                raise ValueError("voice colors are #rrggbb")
            e["color"] = v["color"]
        if e:
            cv[vid] = e
    lines = bar.get("lines") or []
    if not isinstance(lines, list) or len(lines) > 100:
        raise ValueError("at most 100 custom lines")
    cl = []
    for ln in lines:
        if not isinstance(ln, dict) or ln.get("voice") not in VOICE_IDS - {"you"}:
            raise ValueError("each custom line needs a voice in %s" % ", ".join(sorted(VOICE_IDS - {"you"})))
        t = _text(ln.get("text"), 300, "custom line")
        if t:
            cl.append({"voice": ln["voice"], "text": t})
    out["bar"] = {"names": cn, "voices": cv, "gags": bool(bar.get("gags", True)), "lines": cl}
    m = c["music"]
    raw = body.get("music") if isinstance(body.get("music"), dict) else {}
    f = m.get("file") or ""
    if f and (not isinstance(f, str) or not re.match(r"^[A-Za-z0-9._-]{1,120}$", f) or os.path.splitext(f)[1].lower() not in MUSIC_EXTS):
        raise ValueError("bad music file name")
    # configs from before sources existed name only a file; they keep playing it
    source = raw.get("source") or ("file" if f else "scape")
    if source not in MUSIC_SOURCES:
        raise ValueError("music source must be one of %s" % ", ".join(MUSIC_SOURCES))
    scape = m.get("scape") or "night"
    if scape not in SCAPES:
        raise ValueError("soundscape must be one of %s" % ", ".join(SCAPES))
    st = m.get("stream") if isinstance(m.get("stream"), dict) else {}
    url = _text(st.get("url") or "", 500, "station address").strip()
    if url and not re.match(r"^https?://[^\s]+$", url):
        raise ValueError("a station address starts with http:// or https://")
    if source == "radio" and not url:
        raise ValueError("pick a station or paste its address")
    if source == "file" and not f:
        raise ValueError("upload a track first")
    out["music"] = {"source": source, "scape": scape, "stream": {"url": url, "name": _text(st.get("name") or "", 60, "station name")},
                    "file": f, "title": _text(m.get("title") or "", 80, "track title"),
                    "subtitle": _text(m.get("subtitle") or "", 80, "track subtitle"),
                    # a soundscape waits for a click; older configs and real music keep their autoplay default
                    "autoplay": bool(raw["autoplay"]) if "autoplay" in raw else source != "scape"}
    return out


def merged_config(user):
    """Defaults, overlaid one level deep with what the user set."""
    c = copy.deepcopy(DEFAULT_CONFIG)
    for k, v in (user or {}).items():
        if k in c and isinstance(c[k], dict) and isinstance(v, dict):
            c[k].update(v)
        elif k in c:
            c[k] = v
    return c


def load_config():
    """The effective config. A broken file never breaks the dashboard: it falls back to defaults."""
    raw = read_text(CONFIG)
    if not raw.strip():
        return merged_config({}), None
    try:
        return clean_config(json.loads(raw)), None
    except ValueError as exc:
        return merged_config({}), "config.json ignored: %s" % exc


def save_config(cfg):
    with CONFIG_LOCK:
        tmp = CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, CONFIG)


def block_kinds():
    return {k["id"] for k in load_config()[0]["blocks"]["kinds"]}


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_text(path, limit=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(limit) if limit else fh.read()
    except (OSError, UnicodeDecodeError):
        return ""


def frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    meta = {}
    for line in text[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            meta[key.strip()] = value.strip()
    return meta


def html_title(path):
    m = re.search(r"<title>(.*?)</title>", read_text(path, 4096), re.S | re.I)
    return html.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else os.path.basename(path)


def listing(folder, exts):
    try:
        names = sorted(n for n in os.listdir(folder) if not n.startswith(".") and n.endswith(exts))
    except OSError:
        return []
    return names


# ---------------------------------------------------------------- derived data

def local_topic(topic):
    """Facts computed from the topic folder, so counts can never drift from disk."""
    base = os.path.join(ROOT, topic["path"])
    rel = topic["path"]

    def item(sub, name):
        path = os.path.join(base, sub, name)
        return {"file": name, "title": html_title(path), "href": "/vault/%s/%s/%s" % (rel, sub, name)}

    probes = listing(os.path.join(base, "probes"), ".md")
    probes_done = 0
    for name in probes:
        status = frontmatter(read_text(os.path.join(base, "probes", name), 2048)).get("status", "open")
        if not status.startswith("open"):
            probes_done += 1
    glossary = read_text(os.path.join(base, "GLOSSARY.md"))
    return {
        "stats": {
            "lessons": len(listing(os.path.join(base, "lessons"), ".html")),
            "probes_done": probes_done,
            "probes_total": len(probes),
            "records": len(listing(os.path.join(base, "learning-records"), ".md")),
            "glossary": len(re.findall(r"^\*\*[^*\n]+\*\*:\s*$", glossary, re.M)),
        },
        "library": {
            "lessons": [item("lessons", n) for n in listing(os.path.join(base, "lessons"), ".html")],
            "reference": [item("reference", n) for n in listing(os.path.join(base, "reference"), ".html")],
        },
    }


def linked_topic(link):
    """Read-only facts about a topic that lives outside this vault (e.g. the old teach hub)."""
    root = link["root"]
    mission = read_text(os.path.join(root, "MISSION.md"))
    title = link.get("title")
    if not title:
        m = re.search(r"^#\s+(.+)$", mission, re.M)
        title = re.sub(r"^Mission:\s*", "", m.group(1)).strip() if m else os.path.basename(root)
    blurb = ""
    why = re.search(r"^##\s+Why\s*\n+(.+?)(?:\n\s*\n|\n##)", mission, re.S | re.M)
    if why:
        blurb = re.sub(r"\s+", " ", why.group(1)).strip()
        blurb = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", blurb)
        if len(blurb) > 240:
            blurb = blurb[:237].rsplit(" ", 1)[0] + "…"
    lessons = listing(os.path.join(root, "lessons"), (".html", ".md"))
    read = 0
    if link.get("read_state"):
        try:
            state = json.loads(read_text(link["read_state"]) or "{}")
            prefix = os.path.basename(root) + "/lessons/"
            read = sum(1 for k in state if k.startswith(prefix))
        except ValueError:
            pass
    return {
        "id": link["id"], "title": title, "blurb": blurb, "url": link["url"],
        "color": link.get("color"), "exists": os.path.isdir(root),
        "lessons": len(lessons), "read": min(read, len(lessons)),
        "records": len(listing(os.path.join(root, "learning-records"), ".md")),
    }


def read_jsonl(path):
    entries = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def inbox_entries():
    return read_jsonl(INBOX)


def pending_entries(state):
    entries = inbox_entries()
    processed = set(state.get("processed_inbox", []))
    withdrawn = {e.get("ref") for e in entries if e.get("kind") == "withdraw"}
    return [e for e in entries
            if e.get("kind") != "withdraw" and e.get("id") not in processed and e.get("id") not in withdrawn]


def api_state():
    raw = read_text(STATE)
    try:
        state = json.loads(raw)
    except ValueError as exc:
        return {"error": "state.json could not be parsed: %s" % exc, "config": load_config()[0],
                "server": {"now": now_iso(), "version": VERSION, "port": PORT}}
    derived = {"topics": {}, "linked": []}
    for topic in state.get("topics", []):
        derived["topics"][topic["id"]] = local_topic(topic)
    for link in state.get("linked_topics", []):
        derived["linked"].append(linked_topic(link))
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(STATE)).astimezone().isoformat(timespec="seconds")
    except OSError:
        mtime = None
    entries = inbox_entries()
    withdrawn = {e.get("ref") for e in entries if e.get("kind") == "withdraw"}
    cfg, cfg_err = load_config()
    return {
        "state": state,
        "derived": derived,
        "inbox": {"pending": pending_entries(state), "all_submissions": [
            {"id": e.get("id"), "ts": e.get("ts"), "task": e.get("task"), "kind": e.get("kind")}
            for e in entries if e.get("kind") != "withdraw" and e.get("id") not in withdrawn]},
        "blocks": [{k: e.get(k) for k in ("ts", "started", "block", "minutes", "task", "water_served", "water_drunk") if k in e}
                   for e in read_jsonl(BLOCKS)],
        "config": cfg,
        "server": {"now": now_iso(), "state_mtime": mtime, "version": VERSION, "port": PORT,
                   "vault": os.path.basename(ROOT), "config_error": cfg_err},
    }


# ---------------------------------------------------------------- validation

# Longest question label a submission may carry. validate_state.py checks state.json against the same limit.
FIELD_LABEL_MAX = 1000


def clean_submission(body, state):
    topics = {t["id"] for t in state.get("topics", [])} | {"general"}
    topic = body.get("topic")
    task = body.get("task")
    kind = body.get("kind")
    if topic not in topics:
        raise ValueError("unknown topic")
    if not isinstance(task, str) or not re.match(r"^[A-Za-z0-9._-]{1,80}$", task):
        raise ValueError("bad task id")
    if kind not in KINDS:
        raise ValueError("bad kind")
    fields = body.get("fields") or {}
    if not isinstance(fields, dict) or len(fields) > 40:
        raise ValueError("bad fields")
    clean_fields = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(key) > FIELD_LABEL_MAX or len(value) > 20000:
            raise ValueError("bad field")
        clean_fields[key] = value
    note = body.get("note") or ""
    title = body.get("title") or ""
    if not isinstance(note, str) or len(note) > 8000 or not isinstance(title, str) or len(title) > 200:
        raise ValueError("bad note or title")
    if kind == "answers" and not any(v.strip() for v in clean_fields.values()):
        raise ValueError("no answers")
    if kind == "note" and not note.strip():
        raise ValueError("empty note")
    return {
        "id": uuid.uuid4().hex[:10], "ts": now_iso(), "topic": topic, "task": task, "kind": kind,
        "title": title, "fields": clean_fields, "note": note, "honor": bool(body.get("honor")),
    }


def clean_block(body):
    block = body.get("block")
    minutes = body.get("minutes")
    started = body.get("started")
    if block not in block_kinds():
        raise ValueError("unknown block kind (see Settings)")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 240:
        raise ValueError("minutes must be 1-240")
    if not isinstance(started, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$", started):
        raise ValueError("bad start time")
    task = body.get("task")
    if task is not None and (not isinstance(task, str) or not re.match(r"^[A-Za-z0-9._-]{1,80}$", task)):
        raise ValueError("bad task id")
    entry = {"id": uuid.uuid4().hex[:10], "ts": now_iso(), "started": started, "block": block, "minutes": minutes}
    if task:
        entry["task"] = task
    # water rounds during the block: glasses served (one per interval) and glasses drunk
    served, drunk = body.get("water_served"), body.get("water_drunk")
    if served is not None or drunk is not None:
        for v in (served, drunk):
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 50:
                raise ValueError("water counts must be 0-50")
        if drunk > served:
            raise ValueError("more glasses drunk than served")
        entry["water_served"], entry["water_drunk"] = served, drunk
    return entry


def append_block(entry):
    """Append a finished block unless one with the same start is already there (two tabs, retries)."""
    with BLOCKS_LOCK:
        if any(e.get("started") == entry["started"] for e in read_jsonl(BLOCKS)):
            return False
        with open(BLOCKS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True


def append_inbox(entry):
    with INBOX_LOCK:
        with open(INBOX, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "edu4self/" + VERSION

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (now_iso(), fmt % args))

    # responses
    def send_json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path):
        """Send a file. Honors a single Range request (the audio player needs it to seek)."""
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        try:
            size = os.path.getsize(path)
            fh = open(path, "rb")
        except OSError:
            return self.send_error(404)
        with fh:
            start, end = 0, size - 1
            m = re.match(r"^bytes=(\d*)-(\d*)$", self.headers.get("Range", "").strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:   # "bytes=-N": the last N bytes
                    start = max(0, size - int(m.group(2)))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            fh.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = fh.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass   # the player moved on (seek, pause, tab closed)

    def host_ok(self):
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            self.send_error(403, "bad host")
            return False
        return True

    def within(self, base, rel):
        target = os.path.realpath(os.path.join(base, rel))
        base_real = os.path.realpath(base)
        return target if target == base_real or target.startswith(base_real + os.sep) else None

    # routes
    def do_GET(self):
        if not self.host_ok():
            return
        parsed = urllib.parse.urlsplit(self.path)
        route = posixpath.normpath(urllib.parse.unquote(parsed.path))
        if route in ("/", "/index.html"):
            return self.send_file(os.path.join(DASH, "index.html"))
        if route == "/api/state":
            return self.send_json(200, api_state())
        if route == "/favicon.ico":
            return self.send_file(os.path.join(DASH, "favicon.svg"))
        if route == "/api/health":
            return self.send_json(200, {"ok": True, "now": now_iso(), "version": VERSION})
        if route == "/api/config":
            cfg, err = load_config()
            return self.send_json(200, {"config": cfg, "defaults": DEFAULT_CONFIG, "error": err})
        if route == "/music":
            f = load_config()[0]["music"]["file"]
            target = self.within(MUSIC_DIR, f) if f else None
            if not target or not os.path.isfile(target):
                return self.send_error(404)
            return self.send_file(target)
        if route.startswith("/vault/"):
            return self.serve_vault(route[len("/vault/"):], parsed.query)
        name = route.lstrip("/")
        if re.match(r"^(fonts/)?[A-Za-z0-9._-]+$", name):
            target = self.within(DASH, name)
            if target and os.path.isfile(target):
                return self.send_file(target)
        self.send_error(404)

    def serve_vault(self, rel, query):
        parts = [p for p in rel.split("/") if p]
        if not parts or parts[0] in ("_system",) or any(p.startswith(".") for p in parts):
            return self.send_error(404)
        target = self.within(ROOT, "/".join(parts))
        if not target or not os.path.isfile(target):
            return self.send_error(404)
        obs = load_config()[0]["obsidian"]
        if target.endswith(".md") and obs["enabled"] and "raw=1" not in query:
            vault = obs["vault"] or os.path.basename(ROOT)
            file_param = urllib.parse.quote("/".join(parts)[:-3], safe="")
            self.send_response(302)
            self.send_header("Location", "obsidian://open?vault=%s&file=%s" % (urllib.parse.quote(vault), file_param))
            self.end_headers()
            return
        return self.send_file(target)

    def do_POST(self):
        if not self.host_ok():
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return self.send_json(403, {"error": "cross-origin request refused"})
        if urllib.parse.urlsplit(self.path).path == "/api/music":
            return self.upload_music()
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send_json(415, {"error": "send application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            return self.send_json(413, {"error": "body too large"})
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(body, dict):
                raise ValueError("expected an object")
        except (ValueError, UnicodeDecodeError):
            return self.send_json(400, {"error": "invalid json"})
        route = urllib.parse.urlsplit(self.path).path
        if route == "/api/config":
            return self.post_config(body)
        try:
            state = json.loads(read_text(STATE))
        except ValueError:
            return self.send_json(500, {"error": "state.json is unreadable"})

        if route == "/api/inbox":
            try:
                entry = clean_submission(body, state)
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            append_inbox(entry)
            return self.send_json(201, {"ok": True, "id": entry["id"], "ts": entry["ts"]})
        if route == "/api/withdraw":
            ref = body.get("id")
            if ref not in {e.get("id") for e in pending_entries(state)}:
                return self.send_json(404, {"error": "no pending submission with that id"})
            append_inbox({"id": uuid.uuid4().hex[:10], "ts": now_iso(), "kind": "withdraw", "ref": ref})
            return self.send_json(200, {"ok": True})
        if route == "/api/blocks":
            try:
                entry = clean_block(body)
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            added = append_block(entry)
            return self.send_json(201 if added else 200, {"ok": True, "duplicate": not added})
        return self.send_json(404, {"error": "no such endpoint"})

    def post_config(self, body):
        """Save settings. {"reset": true} goes back to the defaults; "remove_music" deletes the track."""
        try:
            if body.get("reset"):
                cfg = merged_config({})
                cfg["music"] = load_config()[0]["music"]     # resetting looks shouldn't throw away a 200 MB upload
            else:
                cfg = clean_config(body.get("config"))
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        if body.get("remove_music"):
            old = load_config()[0]["music"]["file"]
            target = self.within(MUSIC_DIR, old) if old else None
            if target and os.path.isfile(target):
                os.remove(target)
            cfg["music"]["file"] = ""
            if cfg["music"]["source"] == "file":
                cfg["music"]["source"] = "scape"
        elif cfg["music"]["file"] and not os.path.isfile(os.path.join(MUSIC_DIR, cfg["music"]["file"])):
            return self.send_json(400, {"error": "that music file isn't in _system/music/"})
        save_config(cfg)
        return self.send_json(200, {"ok": True, "config": cfg})

    def upload_music(self):
        """Raw audio body, file name in X-Filename. Streams to disk, then swaps it in."""
        ctype = self.headers.get("Content-Type", "")
        name = os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename", "")))
        ext = os.path.splitext(name)[1].lower()
        if ext not in MUSIC_EXTS or not (ctype.startswith("audio/") or ctype.startswith("video/") or ctype == "application/octet-stream"):
            return self.send_json(415, {"error": "send an audio file (%s)" % ", ".join(sorted(MUSIC_EXTS))})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_MUSIC:
            return self.send_json(413, {"error": "music files can be up to 1 GB"})
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.splitext(name)[0]).strip("-.")[:80] or "track"
        final = stem + ext
        os.makedirs(MUSIC_DIR, exist_ok=True)
        tmp = os.path.join(MUSIC_DIR, ".upload-%s" % uuid.uuid4().hex[:8])
        left = length
        try:
            with open(tmp, "wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        raise OSError("upload cut short")
                    fh.write(chunk)
                    left -= len(chunk)
        except OSError as exc:
            if os.path.exists(tmp):
                os.remove(tmp)
            return self.send_json(400, {"error": str(exc)})
        cfg = load_config()[0]
        old = cfg["music"]["file"]
        os.replace(tmp, os.path.join(MUSIC_DIR, final))
        if old and old != final and os.path.isfile(os.path.join(MUSIC_DIR, old)):
            os.remove(os.path.join(MUSIC_DIR, old))      # one track at a time
        cfg["music"]["file"] = final
        cfg["music"]["source"] = "file"
        if not cfg["music"]["title"] or old:
            cfg["music"]["title"] = re.sub(r"[-_]+", " ", stem).strip()[:80]
        save_config(cfg)
        return self.send_json(201, {"ok": True, "config": cfg})


def add_types():
    for ctype, ext in (("text/javascript", ".js"), ("text/css", ".css"), ("audio/mp4", ".m4a"), ("audio/mpeg", ".mp3"),
                       ("audio/ogg", ".ogg"), ("audio/ogg", ".opus"), ("audio/flac", ".flac"), ("audio/aac", ".aac"),
                       ("font/woff2", ".woff2"), ("image/svg+xml", ".svg"), ("text/plain", ".md")):
        mimetypes.add_type(ctype, ext)


def make_server(vault, port):
    configure(vault, port)
    add_types()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    return httpd


def main(argv=None):
    ap = argparse.ArgumentParser(description="edu4self dashboard server")
    ap.add_argument("--vault", default=os.environ.get("EDU4SELF_VAULT"), help="the learning vault folder")
    ap.add_argument("--port", type=int, default=int(os.environ.get("EDU4SELF_PORT", "4747")))
    args = ap.parse_args(argv)
    if not args.vault or not os.path.isfile(os.path.join(os.path.expanduser(args.vault), "_system", "state.json")):
        sys.stderr.write("no vault: pass --vault PATH (a folder made by `edu4self init`)\n")
        return 2
    httpd = make_server(args.vault, args.port)
    sys.stderr.write("%s edu4self %s on http://%s:%d (vault %s)\n" % (now_iso(), VERSION, HOST, PORT, ROOT))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
