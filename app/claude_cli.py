"""Find the command that runs Claude Code, as a list for subprocess (never a shell).

On macOS and Linux that is the `claude` on the PATH. On Windows it is `claude.exe` from Anthropic's
installer when there is one. npm installs only `claude.cmd`, a batch file, and a batch file always runs
through cmd.exe, which mangles a prompt (quotes, &, %, newlines) and can run text from it. So for npm we
read the package the shim points at and run its entry ourselves: `bin/claude.exe` in current versions,
`node cli.js` in older ones. If that can't be worked out, there is no Claude, and `problem` says why.
"""
import json
import os
import re
import shutil
import sys

PACKAGE = ("@anthropic-ai", "claude-code")
SHIM_PATH = re.compile(r'"%dp0%\\([^"]+)"')      # cmd-shim writes "%dp0%\node_modules\...\<entry>"
SCRIPT = (".js", ".cjs", ".mjs")


def find(env=None, which=shutil.which, windows=None):
    """(command list or None, problem or None). env is EDU4SELF_CLAUDE, an explicit override."""
    windows = os.name == "nt" if windows is None else windows
    if env:
        if windows and env.lower().endswith((".cmd", ".bat")):
            return npm_shim(env, which)
        return plain(env)
    if not windows:
        return plain(which("claude"))
    exe = which("claude.exe")
    if exe:
        return plain(exe)
    shim = which("claude.cmd")
    if shim:
        return npm_shim(shim, which)
    return None, "Claude Code not found on the PATH"


def plain(exe):
    if not exe or not os.path.isfile(exe) or not os.access(exe, os.X_OK):
        return None, "Claude Code not found%s" % (" at %s" % exe if exe else " on the PATH")
    return ([sys.executable, exe] if exe.endswith(".py") else [exe]), None


def npm_shim(shim, which=shutil.which):
    """npm's claude.cmd -> the command it would run, without cmd.exe in between."""
    fix = ("Reinstall with `npm i -g @anthropic-ai/claude-code`, or use Anthropic's native installer "
           "(it gives claude.exe, which the dashboard runs directly).")
    base = os.path.dirname(os.path.abspath(shim))
    try:
        with open(shim, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return None, "can't read %s (%s). %s" % (shim, exc, fix)
    named = [p for p in SHIM_PATH.findall(text) if not p.lower().endswith("node.exe")]
    pointed = os.path.join(base, *named[-1].split("\\")) if named else None
    # the package folder: from the shim's own line when it names one, else next to the shim (npm's layout)
    pkg = os.path.join(base, "node_modules", *PACKAGE)
    if pointed:
        parts = pointed.split(os.sep)
        for i in range(len(parts) - 1):
            if (parts[i], parts[i + 1]) == PACKAGE:
                pkg = os.sep.join(parts[:i + 2])
    entry = None
    try:
        with open(os.path.join(pkg, "package.json"), encoding="utf-8") as fh:
            bins = json.load(fh).get("bin")
        rel = bins if isinstance(bins, str) else (bins or {}).get("claude")
        if isinstance(rel, str) and rel:
            entry = os.path.normpath(os.path.join(pkg, rel))
            if not entry.startswith(os.path.normpath(pkg) + os.sep):
                return None, "%s names a bin outside its package (%s). %s" % (os.path.join(pkg, "package.json"), rel, fix)
    except (OSError, ValueError, AttributeError):
        pass
    entry = entry or pointed
    if not entry:
        return None, "%s doesn't look like npm's shim, and there is no %s next to it. %s" % (
            shim, os.path.join("node_modules", *PACKAGE, "package.json"), fix)
    if not os.path.isfile(entry):
        return None, "npm's claude.cmd points at %s, which doesn't exist. %s" % (entry, fix)
    low = entry.lower()
    if low.endswith(".exe"):
        try:
            with open(entry, "rb") as fh:
                real = fh.read(2) == b"MZ"     # every Windows program starts with these two bytes
        except OSError:
            real = False
        if not real:
            return None, ("%s is npm's placeholder, not the real program: the install step didn't run. Run "
                          "`node \"%s\"`, or reinstall without --ignore-scripts." % (entry, os.path.join(pkg, "install.cjs")))
        return [entry], None
    if low.endswith(SCRIPT):
        node = os.path.join(base, "node.exe")
        node = node if os.path.isfile(node) else which("node")
        if not node:
            return None, "npm's Claude Code needs Node.js, and `node` isn't on the PATH. Install Node.js, or %s" % (
                fix[0].lower() + fix[1:])
        return [node, entry], None
    return None, "npm's claude.cmd runs %s, which is neither a program nor a script. %s" % (entry, fix)
