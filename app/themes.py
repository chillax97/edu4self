"""Rooms (themes) for the dashboard: load, validate, and clean them.

A theme is a folder with three files:
  theme.json   the data: name, palette, fonts, the words for things, voices, jokes, default sound
  layout.html  the room, drawn around named slots (<div data-slot="job"></div>) the engine fills
  theme.css    styles, every selector inside .room
  lesson.css   optional: how lesson pages look in this room (Settings can turn it off)

Built-in themes live in app/dashboard/themes/. A learner's own live in <vault>/themes/<id>/. A theme may
come from someone else, so nothing in it runs: the layout is rebuilt from an allow-list of tags and
attributes (no scripts, no event handlers, no links, no ids, no engine actions), the CSS may only style
the room and may not load anything, and theme.json is plain values. The page's CSP backs this up.
docs/THEMES.md is the guide for people and agents making one.
"""
import html
import json
import os
import re
from html.parser import HTMLParser

LIMIT = 64 * 1024
THEME_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

# The engine draws these. Required ones must appear exactly once; optional ones at most once.
SLOTS_REQUIRED = ("name", "rooms", "voices", "job", "replies", "block", "music", "tonight", "week", "die")
SLOTS_OPTIONAL = ("timer", "finish", "doors", "clock", "sign", "water", "keys", "shelf")
SLOTS = SLOTS_REQUIRED + SLOTS_OPTIONAL

# Words a theme may rename. Core learning words (Lesson, Submit, Grade, minutes) are never renamed.
# Rule from docs/THEMES.md: fit the room, but stay understood at a glance.
WORDS = {
    "front": "The bar", "front_icon": "🍸", "back": "The back room", "back_icon": "🗝",
    "view": "Bar view", "place": "the bar", "counter": "the counter",
    "host": "The bartender", "music_box": "The jukebox",
    "tonight": "Fuel · tonight", "week": "Streak · this week", "nights": "nights",
    "die_case": "The die case", "die": "die", "dies": "dies", "tile": "tile", "tiles": "tiles", "shipped": "shipped",
    "doors": "Doors that won't open yet", "job": "The job", "note": "Leave a note for the bartender.",
    "how": "How does this place work?", "back_q": "What's in the back room?",
    "glass": "glass", "glasses": "glasses", "sign_open": "OPEN", "sign_busy": "ON AIR",
}
# Lines a room may say its own way (the defaults are the bar's, in app.js occasionLines)
LINES = ("play", "evening", "friday", "silent", "newyear", "nye", "halloween", "valentine", "music_quiet", "music_none")
VOICES = ("bartender", "logic", "volition", "gpu", "encyclopedia", "physical", "nostalgia", "critic", "regular", "jukebox", "you")
FONTS = {"sans", "serif", "mono", "head", "neon"}   # bundled families, see app.css
SCAPES = ("night", "rain", "noise")
PALETTE = ("bg", "bg2", "surface", "surface2", "ink", "ink2", "muted", "line", "line2", "accent", "accent2", "accent_ink")
COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*(,\s*[\d.]+\s*)?\))$")
# a CSS background built from colours and gradients only: no url(), no functions beyond these
BACKDROP = re.compile(r"^[\s#%(),./0-9a-zA-Z-]*$")
BACKDROP_FUNCS = {"radial-gradient", "linear-gradient", "conic-gradient", "repeating-linear-gradient",
                  "repeating-radial-gradient", "rgb", "rgba", "hsl", "hsla", "color-mix"}

HTML_TAGS = {"div", "span", "section", "article", "aside", "header", "footer", "main", "nav", "p", "h1", "h2", "h3",
             "h4", "h5", "h6", "ul", "ol", "li", "figure", "figcaption", "b", "i", "em", "strong", "small", "br",
             "hr", "kbd", "s", "u", "sup", "sub"}
SVG_TAGS = {"svg", "g", "path", "circle", "rect", "ellipse", "line", "polyline", "polygon", "defs", "lineargradient",
            "radialgradient", "stop", "text", "tspan", "title", "desc", "pattern", "clippath", "mask", "filter",
            "fegaussianblur", "feoffset", "feblend", "fecolormatrix"}
VOID = {"br", "hr", "path", "circle", "rect", "ellipse", "line", "polyline", "polygon", "stop", "fegaussianblur",
        "feoffset", "feblend", "fecolormatrix"}
COMMON_ATTRS = {"class", "data-slot", "data-part", "aria-hidden", "aria-label", "role", "title"}
SVG_ATTRS = {"viewbox", "xmlns", "d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "width", "height",
             "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity",
             "fill-opacity", "stroke-opacity", "transform", "points", "offset", "stop-color", "stop-opacity",
             "gradientunits", "gradienttransform", "preserveaspectratio", "font-size", "font-weight",
             "text-anchor", "dominant-baseline", "letter-spacing", "patternunits", "stddeviation", "dx", "dy",
             "in", "in2", "mode", "values", "type", "result", "clip-path", "mask", "filter", "fx", "fy"}
ROLES = {"presentation", "img", "group", "note", "status"}
REF = re.compile(r"^url\(#t-[a-z0-9-]+\)$")   # fill="url(#t-glow)" inside the theme's own SVG is fine


class _Sanitizer(HTMLParser):
    """Rebuilds the layout from allowed parts. Anything else is an error, so authors learn what to fix."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.errors, self.stack, self.slots, self.svg = [], [], [], [], 0

    def err(self, msg):
        if len(self.errors) < 20:
            self.errors.append("line %d: %s" % (self.getpos()[0], msg))

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, closing=False)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, closing=True)

    def _open(self, tag, attrs, closing):
        in_svg = self.svg > 0 or tag == "svg"
        if tag not in HTML_TAGS and not (in_svg and tag in SVG_TAGS):
            return self.err("<%s> isn't allowed (themes have no scripts, links, forms, images or embeds)" % tag)
        kept = []
        for name, value in attrs:
            value = value or ""
            if name.startswith("on"):
                self.err("%s= isn't allowed: themes can't run code" % name)
            elif name == "id" and in_svg and re.match(r"^t-[a-z0-9-]{1,40}$", value):
                kept.append((name, value))   # SVG gradients need ids; the t- prefix keeps them off the page's own ids
            elif name in ("href", "xlink:href", "src", "style", "id") or name.startswith("data-") and name not in ("data-slot", "data-part"):
                self.err("%s= isn't allowed on <%s>%s" % (name, tag, " (put styles in theme.css)" if name == "style" else ""))
            elif name in COMMON_ATTRS or (in_svg and name in SVG_ATTRS) or name.startswith("aria-"):
                if "url(" in value.lower() and not REF.match(value.strip()):
                    self.err("%s= may only point inside the same SVG, like url(#glow)" % name)
                elif name == "role" and value not in ROLES:
                    self.err("role=%s isn't allowed" % value)
                elif name == "data-slot":
                    if value not in SLOTS:
                        self.err("unknown slot %r (slots: %s)" % (value, ", ".join(SLOTS)))
                    self.slots.append(value)
                    kept.append((name, value))
                else:
                    kept.append((name, value))
            else:
                self.err("%s= isn't allowed on <%s>" % (name, tag))
        self.out.append("<%s%s%s>" % (tag, "".join(' %s="%s"' % (n, html.escape(v, quote=True)) for n, v in kept),
                                      " /" if closing and in_svg else ""))
        if tag == "svg" and not closing:
            self.svg += 1
        if not closing and tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag not in self.stack:
            return
        while self.stack:
            t = self.stack.pop()
            self.out.append("</%s>" % t)
            if t == "svg":
                self.svg -= 1
            if t == tag:
                break

    def handle_data(self, data):
        self.out.append(html.escape(data, quote=False))

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def unknown_decl(self, data):
        self.err("<![%s ...]> isn't allowed" % data[:10])

    def handle_pi(self, data):
        self.err("<?...> isn't allowed")


# ---------------------------------------------------------------- trophies (keepsakes)
# Each room draws three trophies: one for a day that met the goal (small, made to be stacked), one for a
# week that met the goal, and one for a finished die. A trophy keeps the drawing of the room it was won
# in, so a shelf can mix rooms. The drawing is one small SVG: shapes only, no ids, no references.
KEEPSAKE_KINDS = ("day", "week", "die")
KEEPSAKE_LINES = ("day", "week", "die", "gift")
STACKS = ("pile", "fan", "heap", "row")   # how day and die trophies gather: straight up, fanned out, tossed in a
                                          # heap, or standing side by side like books on a shelf
ART_LIMIT = 4096
DEFAULT_KEEPSAKES = {
    "day": {"name": "star", "plural": "stars", "stack": "pile",
            "art": '<svg viewBox="0 0 40 14"><rect x="1" y="2" width="38" height="10" rx="5" fill="#ffd166" stroke="#a87b12"/></svg>'},
    "week": {"name": "ribbon", "plural": "ribbons", "stack": "pile",
             "art": '<svg viewBox="0 0 40 60"><path d="M12 30 L6 58 L16 52 L20 60 L24 38 Z" fill="#c0392b"/><path d="M28 30 L34 58 L24 52 L20 60 L16 38 Z" fill="#a93226"/><circle cx="20" cy="22" r="18" fill="#ffd166" stroke="#a87b12" stroke-width="3"/></svg>'},
    "die": {"name": "die", "plural": "dice", "stack": "heap",
            "art": '<svg viewBox="0 0 48 48"><rect x="4" y="4" width="40" height="40" rx="8" fill="#f4f1ea" stroke="#8a7f6a" stroke-width="2"/><circle cx="15" cy="15" r="4" fill="#333"/><circle cx="33" cy="33" r="4" fill="#333"/><circle cx="24" cy="24" r="4" fill="#333"/></svg>'},
    "lines": {},
}


class _ArtSanitizer(_Sanitizer):
    """A trophy: one <svg> of plain shapes. It's copied into the learner's vault and drawn next to other
    rooms' trophies, many times over, so ids and url(#...) references are out too (they would collide)."""

    def _open(self, tag, attrs, closing):
        if not self.out and tag != "svg":
            return self.err("a trophy drawing starts with <svg>")
        if tag not in SVG_TAGS or tag in ("text", "tspan"):
            return self.err("<%s> isn't allowed in a trophy (shapes only)" % tag)
        for name, value in attrs:
            if name == "id" or "url(" in (value or "").lower():
                return self.err("trophies can't use ids or url(#...) references (draw with plain fills)")
        super()._open(tag, attrs, closing)

    def handle_data(self, data):
        if data.strip():
            self.err("a trophy has no text, only shapes")


def clean_art(text):
    """(clean svg, [errors]) for one trophy drawing."""
    if not isinstance(text, str) or not text.strip():
        return "", ["the drawing is empty"]
    if len(text.encode("utf-8")) > ART_LIMIT:
        return "", ["a trophy drawing is over 4 KB"]
    p = _ArtSanitizer()
    p.feed(text.strip())
    p.close()
    while p.stack:
        p.out.append("</%s>" % p.stack.pop())
    out = "".join(p.out)
    if not p.errors and (not out.startswith("<svg") or out.count("<svg") != 1):
        p.errors.append("a trophy is exactly one <svg>")
    if not p.errors and "viewbox=" not in out.lower():
        p.errors.append("give the <svg> a viewBox so it scales")
    return out, p.errors


def clean_keepsakes(raw, errors):
    """The theme's trophies, defaults filled in for anything it leaves out."""
    if raw is None:
        return json.loads(json.dumps(DEFAULT_KEEPSAKES))
    if not isinstance(raw, dict):
        errors.append("keepsakes must be an object with day, week, die and lines")
        return json.loads(json.dumps(DEFAULT_KEEPSAKES))
    out = {"lines": {}}
    for k in KEEPSAKE_KINDS:
        d = raw.get(k)
        if d is None:
            out[k] = dict(DEFAULT_KEEPSAKES[k])
            continue
        if not isinstance(d, dict):
            errors.append("keepsakes.%s must be an object" % k)
            out[k] = dict(DEFAULT_KEEPSAKES[k])
            continue
        e = {"name": _text(d.get("name"), 30, "keepsakes.%s.name" % k, errors)}
        e["plural"] = _text(d.get("plural", e["name"] + "s"), 32, "keepsakes.%s.plural" % k, errors)
        stack = d.get("stack", "pile")
        if stack not in STACKS:
            errors.append("keepsakes.%s.stack must be one of %s" % (k, ", ".join(STACKS)))
            stack = "pile"
        e["stack"] = stack
        art, errs = clean_art(d.get("art"))
        errors.extend("keepsakes.%s.art: %s" % (k, x) for x in errs)
        e["art"] = art if not errs else DEFAULT_KEEPSAKES[k]["art"]
        out[k] = e
    lines = raw.get("lines") or {}
    for k, v in (lines.items() if isinstance(lines, dict) else []):
        if k not in KEEPSAKE_LINES:
            errors.append("unknown keepsakes line %r (use %s)" % (k, ", ".join(KEEPSAKE_LINES)))
        else:
            out["lines"][k] = _text(v, 200, "keepsakes line %s" % k, errors)
    return out


def clean_layout(text):
    """(clean html, [errors]). The page only ever receives the clean version."""
    if len(text.encode("utf-8")) > LIMIT:
        return "", ["layout.html is over 64 KB"]
    p = _Sanitizer()
    p.feed(text)
    p.close()
    while p.stack:
        p.out.append("</%s>" % p.stack.pop())
    errors = p.errors
    for s in SLOTS_REQUIRED:
        if s not in p.slots:
            errors.append("missing the %r slot (every room needs: %s)" % (s, ", ".join(SLOTS_REQUIRED)))
    for s in set(p.slots):
        if p.slots.count(s) > 1:
            errors.append("the %r slot appears %d times; once only" % (s, p.slots.count(s)))
    return "".join(p.out), errors


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _blocks(css):
    """Split CSS into (prelude, body) pairs at the top level, respecting nested braces and strings."""
    out, i, n, start, depth, prelude, q = [], 0, len(css), 0, 0, "", None
    while i < n:
        ch = css[i]
        if q:
            if ch == "\\":
                i += 1
            elif ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "{":
            if depth == 0:
                prelude, start = css[start:i].strip(), i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("an extra } in theme.css")
            if depth == 0:
                out.append((prelude, css[start:i]))
                start = i + 1
        elif ch == ";" and depth == 0:
            stmt = css[start:i].strip()
            if stmt:
                out.append((stmt, None))
            start = i + 1
        i += 1
    if depth or q:
        raise ValueError("theme.css has an unclosed { or quote")
    if css[start:].strip():
        raise ValueError("theme.css ends with something that isn't a rule: %r" % css[start:].strip()[:40])
    return out


SCOPED = re.compile(r"^\.room(?=$|[\s.:\[>+~#(])")


def check_css(css, scoped=True):
    """[errors]. Nothing may be loaded; no @import or @font-face. In theme.css every selector must start
    with .room; lesson.css styles a whole lesson page (which runs sandboxed), so it may use any selector."""
    if len(css.encode("utf-8")) > LIMIT:
        return ["theme.css is over 64 KB"]
    css = _strip_comments(css)
    low = css.lower()
    errors = []
    for bad, why in (("@import", "@import isn't allowed: everything must be in the theme"),
                     ("@font-face", "@font-face isn't allowed: use the bundled fonts (see theme.json fonts)"),
                     ("expression(", "expression() isn't allowed"), ("javascript:", "javascript: isn't allowed"),
                     ("</", "</ isn't allowed in CSS"), ("@namespace", "@namespace isn't allowed")):
        if bad in low:
            errors.append(why)
    for m in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", css, flags=re.I | re.S):
        if not re.match(r"^data:image/(svg\+xml|png|webp|gif|jpeg)[;,]", m.group(2).strip(), flags=re.I):
            errors.append("url(%s) loads a file; only data:image URLs are allowed" % m.group(2)[:40])
    try:
        rules = _blocks(css)
        if scoped:
            _check_rules(rules, errors)
    except ValueError as exc:
        errors.append(str(exc))
    return errors[:20]


def _check_rules(rules, errors):
    for prelude, body in rules:
        if body is None:
            errors.append("%r isn't allowed at the top of theme.css" % prelude[:40])
            continue
        if prelude.startswith("@"):
            at = prelude.split()[0].lower()
            if at in ("@media", "@supports", "@container"):
                _check_rules(_blocks(body), errors)
            elif at in ("@keyframes", "@-webkit-keyframes"):
                pass
            else:
                errors.append("%s isn't allowed in theme.css" % at)
            continue
        for sel in prelude.split(","):
            sel = sel.strip()
            if not SCOPED.match(sel):
                errors.append("selector %r must start with .room (a theme styles only its room)" % sel[:60])


def _text(v, limit, what, errors):
    if not isinstance(v, str) or not v.strip() or len(v) > limit:
        errors.append("%s must be text of 1 to %d characters" % (what, limit))
        return ""
    return v.strip()


def clean_meta(raw, tid):
    """(clean theme.json, [errors])."""
    errors = []
    if not isinstance(raw, dict):
        return {}, ["theme.json must be an object"]
    meta = {"id": tid, "name": _text(raw.get("name"), 40, "name", errors),
            "icon": _text(raw.get("icon", "◆"), 4, "icon", errors), "dark": bool(raw.get("dark", True)),
            "about": raw.get("about", "") if isinstance(raw.get("about", ""), str) else ""}
    meta["about"] = meta["about"][:200]
    pal = raw.get("palette") or {}
    if not isinstance(pal, dict):
        errors.append("palette must be an object")
        pal = {}
    meta["palette"] = {}
    for k, v in pal.items():
        if k not in PALETTE:
            errors.append("unknown palette colour %r (use %s)" % (k, ", ".join(PALETTE)))
        elif not isinstance(v, str) or not COLOR.match(v.strip()):
            errors.append("palette %s must be #rrggbb or rgb()/rgba()" % k)
        else:
            meta["palette"][k] = v.strip()
    bd = raw.get("backdrop", "")
    if bd:
        funcs = set(re.findall(r"([a-z-]+)\(", bd.lower()))
        if not isinstance(bd, str) or len(bd) > 1200 or not BACKDROP.match(bd) or funcs - BACKDROP_FUNCS:
            errors.append("backdrop is a CSS background made of colours and gradients only")
        else:
            meta["backdrop"] = bd
    fonts = raw.get("fonts") or {}
    meta["fonts"] = {}
    for k in ("head", "body", "sign"):
        if k in fonts:
            if fonts[k] not in FONTS:
                errors.append("fonts.%s must be one of %s" % (k, ", ".join(sorted(FONTS))))
            else:
                meta["fonts"][k] = fonts[k]
    words = raw.get("words") or {}
    meta["words"] = {}
    for k, v in (words.items() if isinstance(words, dict) else []):
        if k not in WORDS:
            errors.append("unknown word %r (words you can rename: %s)" % (k, ", ".join(sorted(WORDS))))
        else:
            t = _text(v, 60, "word %s" % k, errors)
            if t:
                meta["words"][k] = t
    voices = raw.get("voices") or {}
    meta["voices"] = {}
    for vid, v in (voices.items() if isinstance(voices, dict) else []):
        if vid not in VOICES or not isinstance(v, dict):
            errors.append("unknown voice %r" % vid)
            continue
        e = {}
        if "name" in v:
            e["name"] = _text(v["name"], 30, "voice %s name" % vid, errors)
        if "color" in v:
            if not isinstance(v["color"], str) or not re.match(r"^#[0-9a-fA-F]{6}$", v["color"]):
                errors.append("voice %s color must be #rrggbb" % vid)
            else:
                e["color"] = v["color"]
        meta["voices"][vid] = e
    names = raw.get("names") or []
    meta["names"] = []
    for n in names if isinstance(names, list) else []:
        if isinstance(n, list) and 1 <= len(n) <= 2:
            meta["names"].append([_text(n[0], 40, "room name", errors), _text(n[1], 80, "tagline", errors) if len(n) > 1 else ""])
        else:
            errors.append("each name is [name, tagline]")
    meta["names"] = meta["names"][:20]
    gags = raw.get("gags") or []
    meta["gags"] = []
    for g in gags if isinstance(gags, list) else []:
        if isinstance(g, list) and len(g) == 2 and g[0] in VOICES:
            meta["gags"].append([g[0], _text(g[1], 300, "gag", errors)])
        else:
            errors.append("each gag is [voice, text]")
    meta["gags"] = meta["gags"][:60]
    lines = raw.get("lines") or {}
    meta["lines"] = {}
    for k, v in (lines.items() if isinstance(lines, dict) else []):
        if k not in LINES:
            errors.append("unknown line %r (lines you can rewrite: %s)" % (k, ", ".join(LINES)))
        else:
            meta["lines"][k] = _text(v, 300, "line %s" % k, errors)
    if raw.get("scape", "night") not in SCAPES:
        errors.append("scape must be one of %s" % ", ".join(SCAPES))
    meta["scape"] = raw.get("scape", "night") if raw.get("scape", "night") in SCAPES else "night"
    meta["keepsakes"] = clean_keepsakes(raw.get("keepsakes"), errors)
    return meta, errors


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def load(folder, tid):
    """{id, meta, layout, css, errors}. A theme with errors is listed but never applied."""
    out = {"id": tid, "meta": {"id": tid, "name": tid}, "layout": "", "css": "", "lesson_css": "", "errors": []}
    if not THEME_ID.match(tid):
        out["errors"].append("theme folder names are lowercase letters, digits and - (max 32)")
        return out
    for f in ("theme.json", "layout.html", "theme.css"):
        if not os.path.isfile(os.path.join(folder, f)):
            out["errors"].append("missing %s" % f)
    if out["errors"]:
        return out
    try:
        raw = json.loads(_read(os.path.join(folder, "theme.json")))
    except ValueError as exc:
        out["errors"].append("theme.json isn't valid JSON: %s" % exc)
        raw = {}
    out["meta"], e1 = clean_meta(raw, tid)
    out["layout"], e2 = clean_layout(_read(os.path.join(folder, "layout.html")))
    css = _read(os.path.join(folder, "theme.css"))
    e3 = check_css(css)
    out["css"] = css if not e3 else ""
    e4 = []
    lp = os.path.join(folder, "lesson.css")
    if os.path.isfile(lp):
        lcss = _read(lp)
        e4 = check_css(lcss, scoped=False)
        out["lesson_css"] = lcss if not e4 else ""
    out["errors"] = (["theme.json: " + e for e in e1] + ["layout.html: " + e for e in e2] +
                     ["theme.css: " + e for e in e3] + ["lesson.css: " + e for e in e4])
    return out


def folders(builtin_dir, vault):
    """{id: folder}. A vault theme with a built-in's id replaces it (that's how you edit a built-in)."""
    found = {}
    for base in (builtin_dir, os.path.join(vault, "themes") if vault else None):
        if base and os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                path = os.path.join(base, name)
                if os.path.isdir(path) and not name.startswith("."):
                    found[name] = path
    return found


def catalog(builtin_dir, vault):
    """What Settings lists: every theme, with its errors."""
    out = []
    for tid, path in folders(builtin_dir, vault).items():
        t = load(path, tid)
        out.append({"id": tid, "name": t["meta"].get("name") or tid, "icon": t["meta"].get("icon", "◆"),
                    "about": t["meta"].get("about", ""), "lessons": bool(t["lesson_css"]), "builtin": not path.startswith(os.path.join(vault, "")) if vault else True,
                    "errors": t["errors"]})
    return out
