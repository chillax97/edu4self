"""A grade follows the engine's own tutor plugin, not whatever version is installed, and no personal
settings or hooks from ~/.claude load into it."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_server import APP  # noqa: E402

sys.path.insert(0, APP)
import server  # noqa: E402


def opt(args, name):
    return args[args.index(name) + 1] if name in args else None


class GradePinningTest(unittest.TestCase):
    def test_fenced_runs_use_the_engine_plugin_and_no_user_settings(self):
        plugin = os.path.join(server.ENGINE, "plugin")
        self.assertTrue(os.path.isfile(os.path.join(plugin, ".claude-plugin", "plugin.json")))
        for kind in server.FENCED:
            args = server.claude_args("check my inbox", None, kind)
            self.assertEqual(opt(args, "--plugin-dir"), plugin, kind)
            self.assertEqual(opt(args, "--setting-sources"), "project", kind)
            self.assertEqual(args.count("--setting-sources"), 1, kind)

    def test_chat_keeps_the_learners_own_setup(self):
        args = server.claude_args("hi", None, "chat")
        self.assertNotIn("--plugin-dir", args)
        self.assertEqual(opt(args, "--setting-sources"), "user,project")


if __name__ == "__main__":
    unittest.main()
