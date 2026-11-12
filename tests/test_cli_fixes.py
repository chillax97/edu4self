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

    def tearDown(self):
        self.held.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, CLI, *args], env=self.env, stdin=subprocess.DEVNULL, timeout=60,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")

    def make_vault(self, name="vault"):
        vault = os.path.join(self.tmp, name)
        r = self.run_cli("init", vault, "--name", "Kim", "--port", str(self.port + 1))
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


class SetupTwiceTest(Cmd):
    def test_setup_on_an_existing_vault_carries_on_and_leaves_it_alone(self):
        vault = self.make_vault()
        note = os.path.join(vault, "my-notes.md")
        with open(note, "w", encoding="utf-8") as fh:
            fh.write("keep me")
        state = os.path.join(vault, "_system", "state.json")
        before = read(state)
        port = str(self.port + 1)
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
        r = self.run_cli("setup", "--vault", folder, "--name", "Kim", "--port", str(self.port + 1), "--no-service", "--no-open", "--no-plugin")
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
