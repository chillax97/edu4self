#!/usr/bin/env python3
"""Check every internal link in an edu4self vault.

Covers Obsidian wikilinks ([[path]], [[path#Heading]], [[path|alias]]) and relative
markdown links in .md files, plus relative href/src attributes in .html files.
Exit code 0 means no broken links. Run: edu4self check   (or: python3 check_links.py VAULT)
"""
import os, re, sys
from urllib.parse import unquote

if os.name == "nt":      # a pipe or file on Windows defaults to the legacy code page, which can't print ✓ or ·
    for _s in (sys.stdout, sys.stderr):
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("EDU4SELF_VAULT", ".")))
SKIP_DIRS = {".obsidian", ".git", "logs", "music", "node_modules"}
EXTERNAL = re.compile(r"^(https?:|mailto:|obsidian:|data:|javascript:|#|/api/)", re.I)

def all_files():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            yield os.path.join(d, f)

FILES = [p for p in all_files()]
REL = {os.path.relpath(p, ROOT): p for p in FILES}

def strip_code(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)

def headings(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return {re.sub(r"^#+\s*", "", l).strip() for l in fh if l.startswith("#")}
    except OSError:
        return set()

def resolve_wiki(target):
    """Obsidian-style: vault-root path first, then unique path-suffix match."""
    cand = target if os.path.splitext(target)[1] else target + ".md"
    if cand in REL:
        return "exact", REL[cand]
    hits = [r for r in REL if r == cand or r.endswith("/" + cand)]
    if len(hits) == 1:
        return "suffix", REL[hits[0]]
    return ("ambiguous" if hits else "missing"), None

broken, suffix_links, checked = [], [], 0
for path in FILES:
    rel = os.path.relpath(path, ROOT)
    if path.endswith(".md"):
        text = strip_code(open(path, encoding="utf-8").read())
        for m in re.finditer(r"\[\[([^\]]+?)\]\]", text):
            raw = m.group(1).replace("\\|", "|")
            target = raw.split("|", 1)[0]
            target, _, heading = target.partition("#")
            checked += 1
            how, hit = resolve_wiki(target.strip())
            if not hit:
                broken.append((rel, f"[[{raw}]]", how))
                continue
            if how == "suffix":
                suffix_links.append((rel, f"[[{raw}]]"))
            if heading and hit.endswith(".md") and heading.strip() not in headings(hit):
                broken.append((rel, f"[[{raw}]]", "heading not found"))
        for m in re.finditer(r"\]\(([^)\s]+)\)", text):
            href = m.group(1)
            if EXTERNAL.match(href):
                continue
            checked += 1
            dest = os.path.normpath(os.path.join(os.path.dirname(path), unquote(href.split("#")[0])))
            if not os.path.exists(dest):
                broken.append((rel, href, "missing"))
    elif path.endswith(".html"):
        text = open(path, encoding="utf-8").read()
        for m in re.finditer(r'(?:href|src)="([^"]+)"', text):
            href = m.group(1)
            if EXTERNAL.match(href) or "${" in href:
                continue
            checked += 1
            clean = unquote(href.split("#")[0].split("?")[0])
            base = ROOT if clean.startswith("/") else os.path.dirname(path)
            dest = os.path.normpath(os.path.join(base, clean.lstrip("/")))
            if clean and not os.path.exists(dest):
                broken.append((rel, href, "missing"))

print(f"checked {checked} links across {len(FILES)} files under {ROOT}")
for rel, link in suffix_links:
    print(f"  note  {rel}: {link} resolves only by path-suffix (ambiguous once a second topic exists)")
for rel, link, why in broken:
    print(f"  BROKEN {rel}: {link} ({why})")
print(f"{len(broken)} broken, {len(suffix_links)} suffix-only")
sys.exit(1 if broken else 0)
