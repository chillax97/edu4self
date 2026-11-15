"""The login service: what `edu4self install` would hand to each platform's scheduler. Nothing is run here."""
import importlib.machinery
import contextlib
import importlib.util
import io
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
loader = importlib.machinery.SourceFileLoader("edu4self_cli", os.path.join(ENGINE, "edu4self"))
cli = importlib.util.module_from_spec(importlib.util.spec_from_loader("edu4self_cli", loader))
loader.exec_module(cli)

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


class WindowsTaskTest(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring(cli.windows_task_xml("C:\\Users\\Ann & Bo\\vault", 4747, user="PC\\Ann").split("\n", 1)[1])

    def text(self, path):
        return self.root.find(path, NS).text

    def test_it_runs_the_server_for_this_vault_and_port(self):
        args = self.text("t:Actions/t:Exec/t:Arguments")
        self.assertIn("server.py", args)
        self.assertIn('"C:\\Users\\Ann & Bo\\vault"', args)      # quoted: the path has spaces and an ampersand
        self.assertTrue(args.endswith("--port 4747"))
        self.assertEqual(self.text("t:Actions/t:Exec/t:WorkingDirectory"), "C:\\Users\\Ann & Bo\\vault")

    def test_it_starts_at_this_users_logon_without_admin(self):
        self.assertEqual(self.text("t:Triggers/t:LogonTrigger/t:UserId"), "PC\\Ann")
        self.assertEqual(self.text("t:Principals/t:Principal/t:RunLevel"), "LeastPrivilege")

    def test_it_is_not_killed_after_72_hours_and_comes_back_after_a_crash(self):
        self.assertEqual(self.text("t:Settings/t:ExecutionTimeLimit"), "PT0S")
        self.assertEqual(self.text("t:Settings/t:RestartOnFailure/t:Count"), "99")
        self.assertEqual(self.text("t:Settings/t:DisallowStartIfOnBatteries"), "false")

    def test_schtasks_commands(self):
        self.assertEqual(cli.schtasks("/End", "/TN", cli.TASK_NAME), ["schtasks", "/End", "/TN", "edu4self"])


class WindowsFlowTest(unittest.TestCase):
    """install, restart, uninstall, status on 'Windows': the exact schtasks calls, in order."""

    def run_flow(self, fn, *args):
        calls = []

        def fake_run(cmd, check=False):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="")
        import tempfile
        vault = tempfile.mkdtemp()
        os.makedirs(os.path.join(vault, "_system"))
        with mock.patch.object(cli.platform, "system", return_value="Windows"), mock.patch.object(cli, "run", fake_run), \
                mock.patch.object(cli, "health", return_value={"version": "x"}), \
                mock.patch.object(cli, "resolve", return_value=(vault, 4747)), mock.patch.object(cli, "need_vault"), \
                mock.patch.object(cli, "write_settings"):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = fn(mock.Mock())
        return rc, [c[:3] for c in calls], vault

    def test_install(self):
        rc, calls, vault = self.run_flow(cli.cmd_install)
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0][:2], ["schtasks", "/Create"])
        self.assertIn(["schtasks", "/Run", "/TN"], calls)
        with open(os.path.join(vault, "_system", "logs", "edu4self-task.xml"), "rb") as fh:
            self.assertEqual(fh.read(2) in (b"\xff\xfe", b"\xfe\xff"), True)     # UTF-16 with a BOM, as schtasks needs

    def test_restart_and_uninstall(self):
        _, calls, _ = self.run_flow(cli.cmd_restart)
        self.assertEqual(calls, [["schtasks", "/Query", "/TN"], ["schtasks", "/End", "/TN"], ["schtasks", "/Run", "/TN"]])
        _, calls, _ = self.run_flow(cli.cmd_uninstall)
        self.assertEqual(calls, [["schtasks", "/End", "/TN"], ["schtasks", "/Delete", "/F"]])


class MacPrivateFolderTest(unittest.TestCase):
    """macOS may keep a program started at login out of Documents, Desktop and Downloads. install warns before it
    hands the dashboard to launchd from there, and says how to move it."""

    def setUp(self):
        import tempfile
        self.home = tempfile.mkdtemp()

    def warn(self, engine, vault, system="Darwin"):
        return cli.private_folder_warning(engine, vault, home=self.home, system=system)

    def test_an_engine_or_vault_in_a_private_folder_gets_a_warning_with_the_fix(self):
        for folder in ("Documents", "Desktop", "Downloads"):
            engine = os.path.join(self.home, folder, "code", "edu4self")
            text = self.warn(engine, os.path.join(self.home, "learn"))
            self.assertIn("~/%s" % folder, text)
            self.assertIn("~/edu4self", text, "says where to move it")
        text = self.warn(os.path.join(self.home, "edu4self"), os.path.join(self.home, "Documents", "learn"))
        self.assertIn("vault", text)
        self.assertIn("--vault", text)

    def test_anywhere_else_or_another_system_is_quiet(self):
        self.assertIsNone(self.warn(os.path.join(self.home, "edu4self"), os.path.join(self.home, "learn")))
        self.assertIsNone(self.warn(os.path.join(self.home, "DocumentsArchive", "edu4self"), os.path.join(self.home, "learn")))
        self.assertIsNone(self.warn(os.path.join(self.home, "Documents", "edu4self"), os.path.join(self.home, "learn"), "Linux"))

    def test_install_on_a_mac_prints_it_before_handing_over_to_launchd(self):
        import tempfile
        vault = tempfile.mkdtemp()
        os.makedirs(os.path.join(vault, "_system"))
        engine = os.path.join(self.home, "Desktop", "edu4self")
        out, calls = io.StringIO(), []

        def fake_run(cmd, check=False):
            calls.append((cmd[:2], len(out.getvalue())))
            return mock.Mock(returncode=0, stdout="")
        with mock.patch.object(cli.platform, "system", return_value="Darwin"), mock.patch.object(cli, "run", fake_run), \
                mock.patch.object(cli, "health", return_value={"version": "x"}), \
                mock.patch.object(cli, "resolve", return_value=(vault, 4747)), mock.patch.object(cli, "need_vault"), \
                mock.patch.object(cli, "write_settings"), mock.patch.object(cli, "ENGINE", engine), \
                mock.patch.object(cli, "plist_path", return_value=os.path.join(vault, "x.plist")), \
                mock.patch.object(cli.os.path, "expanduser", lambda p: p.replace("~", self.home, 1)), \
                mock.patch.object(cli.os, "getuid", return_value=501, create=True):
            with contextlib.redirect_stdout(out):
                rc = cli.cmd_install(mock.Mock())
        self.assertEqual(rc, 0)
        at = out.getvalue().find("~/Desktop")
        self.assertGreaterEqual(at, 0, out.getvalue())
        bootstrap = [n for cmd, n in calls if cmd == ["launchctl", "bootstrap"]]
        self.assertTrue(bootstrap and at < bootstrap[0], "warned before launchd got it")


if __name__ == "__main__":
    unittest.main()
