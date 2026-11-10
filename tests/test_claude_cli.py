"""Which command runs Claude Code (app/claude_cli.py), most of all npm's claude.cmd on Windows.

The layouts are built the way npm writes them, in a temp folder, and Windows is injected (windows=True,
a fake which), so every test runs on every OS. The round trip at the end runs a real node through the
real server path and checks a nasty prompt arrives byte for byte.
"""
import functools
import http.client
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ENGINE, "app"))
sys.path.insert(0, HERE)
import claude_cli  # noqa: E402
import server  # noqa: E402
from test_server import free_port, load_cli, make_vault  # noqa: E402  (functions only: no test classes twice)

# What npm's cmd-shim writes for a bin that is a node script (claude-code before 2.1) ...
SHIM_JS = (
    '@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n\r\n'
    'IF EXIST "%dp0%\\node.exe" (\r\n  SET "_prog=%dp0%\\node.exe"\r\n) ELSE (\r\n  SET "_prog=node"\r\n'
    '  SET PATHEXT=%PATHEXT:;.JS;=;%\r\n)\r\n\r\n'
    'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
    '"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\{entry}" %*\r\n')
# ... and for a bin that is a program (2.1 and later: bin/claude.exe, the native binary copied in at install)
SHIM_EXE = ('@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n'
            '"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\{entry}"   %*\r\n')


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as fh:
        fh.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class NpmLayout:
    """An npm global prefix: claude.cmd, node_modules/@anthropic-ai/claude-code/{package.json, entry}."""
    def __init__(self, root, entry="cli.js", shim=SHIM_JS, bin_field=None, make_entry=True, entry_bytes=None):
        self.root = root
        self.pkg = os.path.join(root, "node_modules", "@anthropic-ai", "claude-code")
        self.shim = write(os.path.join(root, "claude.cmd"), shim.replace("{entry}", entry.replace("/", "\\")))
        write(os.path.join(self.pkg, "package.json"),
              json.dumps({"name": "@anthropic-ai/claude-code", "bin": bin_field or {"claude": entry}}))
        self.entry = os.path.join(self.pkg, *entry.split("/"))
        if make_entry:
            if entry_bytes is not None:
                write(self.entry, entry_bytes, "wb")
            else:
                write(self.entry, "console.log(JSON.stringify(process.argv.slice(2)))\n")

    def which(self, **found):
        """A fake shutil.which: claude.cmd is the shim; anything else only if passed in."""
        table = {"claude.cmd": self.shim}
        table.update(found)
        calls = []

        def which(name):
            calls.append(name)
            return table.get(name)
        which.calls = calls
        return which


class NpmShimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-npm-")
        self.node = write(os.path.join(self.tmp, "nodejs", "node.exe"), "")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def find(self, layout, **found):
        return claude_cli.find(None, layout.which(**found), windows=True)

    def test_node_script_runs_with_node_not_cmd(self):
        npm = NpmLayout(self.tmp)
        cmd, why = self.find(npm, node=self.node)
        self.assertEqual(cmd, [self.node, npm.entry])
        self.assertIsNone(why)

    def test_node_next_to_the_shim_wins(self):
        npm = NpmLayout(self.tmp)
        own = write(os.path.join(self.tmp, "node.exe"), "")
        self.assertEqual(self.find(npm, node=self.node)[0], [own, npm.entry])

    def test_entry_name_comes_from_package_json(self):
        # the shim and the package agree on a name that isn't cli.js; nothing is hardcoded
        npm = NpmLayout(self.tmp, entry="dist/start.mjs")
        self.assertEqual(self.find(npm, node=self.node)[0], [self.node, npm.entry])
        # a plain-string bin field works too
        npm = NpmLayout(self.tmp, entry="main.cjs", bin_field="main.cjs")
        self.assertEqual(self.find(npm, node=self.node)[0], [self.node, npm.entry])

    def test_native_binary_in_the_package_runs_directly(self):
        npm = NpmLayout(self.tmp, entry="bin/claude.exe", shim=SHIM_EXE, entry_bytes=b"MZ\x90\x00 a real program")
        self.assertEqual(self.find(npm, node=self.node), ([npm.entry], None))

    def test_placeholder_binary_is_no_claude_and_says_why(self):
        # what npm leaves when the install step didn't run: a text file named claude.exe
        npm = NpmLayout(self.tmp, entry="bin/claude.exe", shim=SHIM_EXE, entry_bytes=b'echo "Error: claude native binary not installed."')
        cmd, why = self.find(npm)
        self.assertIsNone(cmd)
        self.assertIn("placeholder", why)
        self.assertIn("install.cjs", why)

    def test_claude_exe_is_preferred(self):
        npm = NpmLayout(self.tmp)
        exe = write(os.path.join(self.tmp, "native", "claude.exe"), "")
        which = npm.which(**{"claude.exe": exe, "node": self.node})
        self.assertEqual(claude_cli.find(None, which, windows=True), ([exe], None))
        self.assertNotIn("claude.cmd", which.calls)

    def test_missing_entry_is_no_claude_and_says_why(self):
        npm = NpmLayout(self.tmp, make_entry=False)
        cmd, why = self.find(npm, node=self.node)
        self.assertIsNone(cmd)
        self.assertIn(npm.entry, why)
        self.assertIn("doesn't exist", why)
        self.assertIn("npm i -g @anthropic-ai/claude-code", why)

    def test_no_node_is_no_claude_and_says_why(self):
        npm = NpmLayout(self.tmp)
        cmd, why = self.find(npm)
        self.assertIsNone(cmd)
        self.assertIn("Node.js", why)

    def test_shim_alone_still_resolves(self):
        # no package.json (an odd install): the path on the shim's own line is used
        npm = NpmLayout(self.tmp)
        os.remove(os.path.join(npm.pkg, "package.json"))
        self.assertEqual(self.find(npm, node=self.node)[0], [self.node, npm.entry])

    def test_package_json_alone_still_resolves(self):
        # a shim whose line we can't read: the package next to it is used
        npm = NpmLayout(self.tmp, shim="@ECHO off\r\nsomething else %*\r\n")
        self.assertEqual(self.find(npm, node=self.node)[0], [self.node, npm.entry])

    def test_bin_outside_the_package_is_refused(self):
        npm = NpmLayout(self.tmp, bin_field={"claude": "../../../evil.js"})
        write(os.path.join(self.tmp, "evil.js"), "")
        cmd, why = self.find(npm, node=self.node)
        self.assertIsNone(cmd)
        self.assertIn("outside its package", why)

    def test_nothing_on_path(self):
        self.assertEqual(claude_cli.find(None, lambda name: None, windows=True), (None, "Claude Code not found on the PATH"))

    def test_override_to_a_shim_is_resolved(self):
        npm = NpmLayout(self.tmp)
        cmd, _ = claude_cli.find(npm.shim, npm.which(node=self.node), windows=True)
        self.assertEqual(cmd, [self.node, npm.entry])

    def test_override_to_a_python_stand_in(self):
        fake = os.path.join(HERE, "fake_claude.py")
        for windows in (True, False):
            self.assertEqual(claude_cli.find(fake, lambda name: None, windows=windows), ([sys.executable, fake], None))

    def test_other_systems_are_untouched(self):
        # macOS and Linux: whatever `claude` is on the PATH, as is; claude.cmd is never looked at
        npm = NpmLayout(self.tmp)
        claude = write(os.path.join(self.tmp, "bin", "claude"), "#!/bin/sh\n")
        which = npm.which(claude=claude, node=self.node)
        self.assertEqual(claude_cli.find(None, which, windows=False), ([claude], None))
        self.assertEqual(which.calls, ["claude"])
        self.assertEqual(claude_cli.find(None, lambda name: None, windows=False)[0], None)

    def test_doctor_says_what_runs_and_why_not(self):
        cli = load_cli()
        npm = NpmLayout(self.tmp)
        with mock.patch.dict(os.environ, {"EDU4SELF_CLAUDE": ""}):
            mark, line = cli.claude_line(windows=True, which=npm.which(node=self.node))
            self.assertEqual(mark, "✓")
            self.assertIn("%s %s" % (self.node, npm.entry), line)
            os.remove(npm.entry)
            mark, line = cli.claude_line(windows=True, which=npm.which(node=self.node))
            self.assertEqual(mark, "✗")
            self.assertIn("claude.cmd found, but the dashboard's Claude panel can't use it", line)
            self.assertIn("doesn't exist", line)
            self.assertEqual(cli.claude_line(windows=True, which=lambda name: None)[0], "✗")


NASTY = ('grade "this" & echo pwned %PATH% %dp0% ^ | < > !x! \\"quoted\\" end\\\n'
         'line two\twith a tab\nline 3: é ü 日本 \\\\server\\share\\ \'single\' `tick` $HOME ;')


@unittest.skipUnless(shutil.which("node"), "needs Node.js on the PATH (CI runners have it)")
class NpmRoundTripTest(unittest.TestCase):
    """The real server path: POST /api/claude -> claude_start -> Popen, with npm's layout and a real node.
    The fake cli.js writes the argv node gave it, so any quoting or shell on the way would show."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-npm-rt-")
        cls.vault, _ = make_vault(cls.tmp)
        cls.npm = NpmLayout(os.path.join(cls.tmp, "npm"))
        write(cls.npm.entry,
              "const fs = require('fs');\n"
              "fs.writeFileSync(process.env.FAKE_ARGV_LOG, JSON.stringify(process.argv.slice(2)), 'utf8');\n"
              "console.log(JSON.stringify({type: 'system', subtype: 'init', session_id: 'npm-rt'}));\n"
              "console.log(JSON.stringify({type: 'result', is_error: false, result: 'ok'}));\n")
        cls.log = os.path.join(cls.tmp, "argv.json")
        cls.env = mock.patch.dict(os.environ, {"EDU4SELF_CLAUDE": cls.npm.shim, "FAKE_ARGV_LOG": cls.log})
        cls.env.start()
        # Windows is real on Windows CI; elsewhere it is injected, and the real node on the PATH runs
        cls.win = mock.patch.object(claude_cli, "find", functools.partial(claude_cli.find, windows=True))
        cls.win.start()
        cls.port = free_port()
        cls.httpd = server.make_server(cls.vault, cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.win.stop()
        cls.env.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                  headers={"Host": "127.0.0.1:%d" % self.port, "Content-Type": "application/json"})
        r = c.getresponse()
        data = json.loads(r.read())
        c.close()
        return r.status, data

    def test_prompt_arrives_byte_for_byte(self):
        self.assertTrue(self.req("GET", "/api/claude")[1]["available"])
        real_popen = subprocess.Popen
        launched = []

        def spy(args, *a, **kw):
            launched.append((args, kw))
            return real_popen(args, *a, **kw)
        with mock.patch.object(server.subprocess, "Popen", spy):
            code, d = self.req("POST", "/api/claude", {"kind": "chat", "text": NASTY})
        self.assertEqual(code, 202, d)
        end = time.time() + 30
        while self.req("GET", "/api/claude")[1]["busy"] and time.time() < end:
            time.sleep(0.05)
        args, kw = launched[0]
        self.assertIsInstance(args, list)
        self.assertFalse(kw.get("shell"))
        self.assertEqual(args[:2], [shutil.which("node"), self.npm.entry])
        self.assertNotIn("cmd", os.path.basename(args[0]).lower())
        with open(self.log, encoding="utf-8") as fh:
            argv = json.load(fh)
        self.assertEqual(argv[argv.index("-p") + 1], NASTY)
        self.assertEqual(argv, args[2:])      # every other argument too


if __name__ == "__main__":
    unittest.main()
