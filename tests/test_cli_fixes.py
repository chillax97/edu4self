"""Plain-words failures and the update hint in the command line: a busy port, setup run twice, doctor's version check.
No real network and no Claude: sockets are local, the release lookup is faked."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
CLI = os.path.join(ENGINE, "edu4self")
loader = importlib.machinery.SourceFileLoader("edu4self_cli_fixes", CLI)
cli = importlib.util.module_from_spec(importlib.util.spec_from_loader("edu4self_cli_fixes", loader))
loader.exec_module(cli)
sys.path.insert(0, os.path.join(ENGINE, "app"))
import server  # noqa: E402


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Cmd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-cli-")
        self.env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg"), HOME=self.tmp,
                        CLAUDE_CONFIG_DIR=os.path.join(self.tmp, "claude"), EDU4SELF_NO_UPDATE_CHECK="1")
        self.env.pop("EDU4SELF_PORT", None)
        self.env.pop("EDU4SELF_VAULT", None)
        self.held = socket.socket()
        self.held.bind(("127.0.0.1", 0))
        self.held.listen(1)
        self.port = self.held.getsockname()[1]
        with socket.socket() as probe:      # a port nothing holds (port + 1 can be taken on a busy CI machine)
            probe.bind(("127.0.0.1", 0))
            self.free = probe.getsockname()[1]

    def tearDown(self):
        self.held.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, CLI, *args], env=self.env, stdin=subprocess.DEVNULL, timeout=60,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")

    def make_vault(self, name="vault"):
        vault = os.path.join(self.tmp, name)
        r = self.run_cli("init", vault, "--name", "Kim", "--port", str(self.free))
        self.assertEqual(r.returncode, 0, r.stderr)
        return vault


class BusyPortTest(Cmd):
    def test_serve_on_a_taken_port_says_so_in_one_plain_message(self):
        vault = self.make_vault()
        r = self.run_cli("serve", "--vault", vault, "--port", str(self.port))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("Port %d is already in use" % self.port, r.stderr)
        self.assertIn("--port", r.stderr)
        self.assertLessEqual(len(r.stderr.strip().splitlines()), 3)

    def test_setup_checks_the_port_before_it_makes_anything(self):
        vault = os.path.join(self.tmp, "fresh")
        r = self.run_cli("setup", "--vault", vault, "--name", "Kim", "--port", str(self.port), "--no-service", "--no-open", "--no-plugin")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Port %d is already in use" % self.port, r.stderr)
        self.assertFalse(os.path.exists(vault), "no half-made vault")


class FirstRunTest(Cmd):
    """What a stranger (or the agent setting it up for them) reads on the first run."""

    def setup_no_service(self):
        vault = os.path.join(self.tmp, "fresh")
        r = self.run_cli("setup", "--vault", vault, "--name", "Kim", "--port", str(self.free), "--no-service",
                         "--no-open", "--no-plugin", "--gifts", "off")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_serve_says_where_it_runs_even_when_its_output_goes_to_a_file(self):
        # an agent starts serve in the background with its output in a log; the URL must be in there at once
        vault = self.make_vault()
        p = subprocess.Popen([sys.executable, CLI, "serve", "--vault", vault, "--port", str(self.free)], env=self.env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
        got = []
        reader = threading.Thread(target=lambda: got.append(p.stdout.readline()), daemon=True)
        reader.start()
        reader.join(10)
        timed_out = reader.is_alive()       # read before kill: killing closes the pipe and readline returns ''
        p.kill()
        p.wait()
        p.stdout.close()
        self.assertFalse(timed_out, "serve printed nothing within 10 s")
        self.assertIn("http://127.0.0.1:%d/" % self.free, got[0])

    def test_setup_without_a_service_says_to_start_the_dashboard_before_opening_it(self):
        out = self.setup_no_service()
        steps = [l.strip() for l in out[out.index("Next:"):].splitlines() if l.strip()[:2].rstrip(".").isdigit()]
        start = [i for i, l in enumerate(steps) if "./edu4self serve" in l]
        url = [i for i, l in enumerate(steps) if "http://127.0.0.1:%d/" % self.free in l]
        self.assertTrue(start, "a numbered step says how to start it: %r" % steps)
        self.assertTrue(url, steps)
        self.assertLessEqual(start[0], url[0], "start comes before open: %r" % steps)

    def test_setup_without_a_terminal_does_not_ask_to_press_enter(self):
        self.assertNotIn("Press Enter", self.setup_no_service())


    def test_the_server_starts_without_asking_dns_for_its_own_name(self):
        # http.server looks up 127.0.0.1's name when it binds; on a Mac with slow reverse DNS (CI's macOS runners,
        # a VPN) that held serve's first line, and the start-at-login check, for about 35 s
        vault = self.make_vault()
        with mock.patch.object(socket, "getfqdn", side_effect=AssertionError("asked DNS for its own name")):
            httpd = server.make_server(vault, 0)
        httpd.server_close()

    def test_setup_asks_nothing_when_only_stdin_looks_like_a_terminal(self):
        # Windows calls NUL a terminal: an agent's setup has stdin=NUL (isatty True) and its output in a pipe
        class Nul(io.StringIO):
            def isatty(self):
                return True
        vault = os.path.join(self.tmp, "nul")
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(cli.sys, "stdin", Nul("")), \
                mock.patch("builtins.input", side_effect=AssertionError("asked a question")), \
                contextlib.redirect_stdout(out):
            cli.main(["setup", "--vault", vault, "--name", "Kim", "--port", str(self.free), "--no-service",
                      "--no-open", "--no-plugin"])
        self.assertNotIn("Press Enter", out.getvalue())
        self.assertNotIn("Turn gifts on", out.getvalue())

    def test_agents_md_quotes_what_setup_really_prints(self):
        # AGENTS.md tells the agent to run the plugin commands only when setup printed this line
        self.assertIn('"Give Claude the tutor skills"', read(os.path.join(ENGINE, "AGENTS.md")))
        self.assertIn("Give Claude the tutor skills", self.setup_no_service())


class ReadmeSetupTest(unittest.TestCase):
    """The README's setup steps work as written on every system they name."""

    def section(self, title):
        text = read(os.path.join(ENGINE, "README.md"))
        start = text.index("## " + title)
        end = text.find("\n## ", start + 3)
        return text[start:end if end > 0 else None]

    def test_every_setup_section_gives_the_windows_form_too(self):
        for title in ("Quick start", "Set it up yourself", "Everyday commands"):
            body = self.section(title)
            self.assertIn("./edu4self", body)
            self.assertIn("python edu4self", body, "%s says ./edu4self, which PowerShell can't run" % title)

    def test_a_fresh_mac_is_told_about_the_command_line_tools(self):
        self.assertIn("Command Line Tools", self.section("What you need"))

    def test_the_clone_goes_to_the_home_folder(self):
        # not Documents, Desktop or Downloads, which macOS may keep a login service out of
        for title in ("Quick start", "Set it up yourself"):
            self.assertIn("cd ~", self.section(title), title)


class SetupTwiceTest(Cmd):
    def test_setup_on_an_existing_vault_carries_on_and_leaves_it_alone(self):
        vault = self.make_vault()
        note = os.path.join(vault, "my-notes.md")
        with open(note, "w", encoding="utf-8") as fh:
            fh.write("keep me")
        state = os.path.join(vault, "_system", "state.json")
        before = read(state)
        port = str(self.free)
        r = self.run_cli("setup", "--vault", vault, "--name", "Other", "--port", port, "--no-service", "--no-open", "--no-plugin")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Pick a new folder", r.stdout + r.stderr)
        self.assertIn("already holds a vault", r.stdout)
        self.assertIn("http://127.0.0.1:%s/" % port, r.stdout, "it still ends with where to open the dashboard")
        self.assertEqual(read(state), before)
        self.assertEqual(read(note), "keep me")
        with open(os.path.join(self.tmp, "cfg", "settings.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["vault"], vault)

    def test_a_folder_with_other_files_is_still_refused(self):
        folder = os.path.join(self.tmp, "stuff")
        os.makedirs(folder)
        with open(os.path.join(folder, "a.txt"), "w"):
            pass
        r = self.run_cli("setup", "--vault", folder, "--name", "Kim", "--port", str(self.free), "--no-service", "--no-open", "--no-plugin")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("isn't empty", r.stderr)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def release(tag):
    return FakeResponse(json.dumps({"tag_name": tag}).encode())


class UpdateHintTest(unittest.TestCase):
    def setUp(self):
        self.had = os.environ.pop("EDU4SELF_NO_UPDATE_CHECK", None)

    def tearDown(self):
        if self.had is not None:
            os.environ["EDU4SELF_NO_UPDATE_CHECK"] = self.had

    def test_newer_release_is_found_and_same_or_older_is_not(self):
        with mock.patch.object(cli.urllib.request, "urlopen", return_value=release("v99.0.0")) as call:
            self.assertEqual(cli.newer_release(), "v99.0.0")
            req = call.call_args[0][0]
            self.assertEqual(req.full_url, "https://api.github.com/repos/chillax97/edu4self/releases/latest")
            self.assertLessEqual(call.call_args[1]["timeout"], 3, "short timeout")
        with mock.patch.object(cli.urllib.request, "urlopen", return_value=release("v" + server.VERSION)):
            self.assertIsNone(cli.newer_release())
        with mock.patch.object(cli.urllib.request, "urlopen", return_value=release("v0.0.1")):
            self.assertIsNone(cli.newer_release())

    def test_offline_or_garbage_is_silent(self):
        with mock.patch.object(cli.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertIsNone(cli.newer_release())
        with mock.patch.object(cli.urllib.request, "urlopen", return_value=FakeResponse(b"<html>")):
            self.assertIsNone(cli.newer_release())
        with mock.patch.object(cli.urllib.request, "urlopen", return_value=release("nightly")):
            self.assertIsNone(cli.newer_release())

    def test_the_opt_out_makes_no_request(self):
        with mock.patch.dict(os.environ, {"EDU4SELF_NO_UPDATE_CHECK": "1"}), mock.patch.object(cli.urllib.request, "urlopen") as call:
            self.assertIsNone(cli.latest_release())
            call.assert_not_called()

    def doctor(self, newer):
        out = io.StringIO()
        with mock.patch.object(cli, "newer_release", return_value=newer), mock.patch.object(cli, "find_claude", return_value=None), \
                mock.patch.object(cli, "lesson_skill_found", return_value=True), mock.patch.object(cli, "health", return_value=None), \
                mock.patch.object(cli, "resolve", return_value=(None, 4747)), contextlib.redirect_stdout(out):
            rc = cli.cmd_doctor(mock.Mock())
        return rc, out.getvalue()

    def test_doctor_names_the_update_commands_including_the_skills(self):
        _, text = self.doctor("v99.0.0")
        self.assertIn("edu4self 99.0.0 is out", text)
        self.assertIn("git pull", text)
        self.assertIn("./edu4self restart", text)
        self.assertIn("claude plugin marketplace update edu4self && claude plugin update edu4self@edu4self", text)

    def test_doctor_says_nothing_when_up_to_date_and_it_is_not_a_problem(self):
        rc, text = self.doctor(None)
        self.assertNotIn("is out", text)
        _, with_update = self.doctor("v99.0.0")
        self.assertEqual(with_update.count("to fix"), text.count("to fix"))
        self.assertEqual([l for l in with_update.splitlines() if "to fix" in l], [l for l in text.splitlines() if "to fix" in l])


if __name__ == "__main__":
    unittest.main()
