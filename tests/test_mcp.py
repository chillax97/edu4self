"""The MCP server, driven the way an AI tool drives it: a subprocess speaking JSON-RPC over stdin/stdout."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ENGINE, "app"))
sys.path.insert(0, HERE)
import server  # noqa: E402
from test_server import make_vault, free_port, read_json  # noqa: E402

CLI = os.path.join(ENGINE, "edu4self")


def talk(port, *calls, client="test-client"):
    """Run one MCP session: initialize, then each (method, params). Returns the replies by id."""
    msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": client, "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    for i, (method, params) in enumerate(calls, 1):
        msgs.append({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
    p = subprocess.run([sys.executable, CLI, "mcp", "--port", str(port)], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=30)
    replies = [json.loads(l) for l in p.stdout.splitlines()]
    assert all(r.get("jsonrpc") == "2.0" for r in replies), p.stdout   # nothing but protocol on stdout
    return {r["id"]: r for r in replies}


def tool(port, name, **args):
    r = talk(port, ("tools/call", {"name": name, "arguments": args}))[1]["result"]
    return r, r.get("structuredContent")


class McpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edu4self-mcp-")
        cls.vault, _ = make_vault(cls.tmp)
        st = read_json(os.path.join(cls.vault, "_system", "state.json"))
        t = st["topics"][0]
        t["queue"][0]["rules"] = "Closed book. No AI."
        t["history"].append({"date": "2026-11-01", "kind": "lesson", "title": "Lesson 01: proved it", "evidence": True})
        with open(os.path.join(cls.vault, "_system", "state.json"), "w", encoding="utf-8") as fh:
            json.dump(st, fh)
        cls.topic = t["id"]
        cls.port = free_port()
        cls.httpd = server.make_server(cls.vault, cls.port)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_handshake_and_the_tools_on_offer(self):
        r = talk(self.port, ("tools/list", {}), ("ping", {}))
        init = r[0]["result"]
        self.assertEqual(init["serverInfo"]["name"], "edu4self")
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        self.assertIn("no AI", init["instructions"])
        names = {t["name"] for t in r[1]["result"]["tools"]}
        self.assertEqual(names, {"get_progress", "get_next_task", "get_proven", "leave_note"})
        self.assertFalse(any("submit" in n or "grade" in n for n in names), "tools can't hand in or grade work")
        self.assertEqual(r[2]["result"], {})

    def test_progress_next_and_proven(self):
        _, p = tool(self.port, "get_progress")
        self.assertEqual(p["topics"][0]["id"], self.topic)
        self.assertIn("goal_minutes", p["today"])
        _, n = tool(self.port, "get_next_task", topic=self.topic)
        task = n["topics"][0]["todo"][0]
        self.assertEqual(task["rules"], "Closed book. No AI.", "the learner's rules travel with the task")
        self.assertIn("#submit=", task["open_in_dashboard"])
        _, pr = tool(self.port, "get_proven")
        self.assertEqual(pr["proven"][0]["title"], "Lesson 01: proved it")
        for out in (p, n, pr):
            self.assertIn("model provider", out["privacy"], "every read says where the data goes")
        self.assertIn("model provider", talk(self.port)[0]["result"]["instructions"])
        self.assertEqual(len(p["waiting_for_grading"]), p["answers_waiting_for_grading"])
        self.assertTrue(all(set(w) == {"task", "sent"} for w in p["waiting_for_grading"]))

    def test_a_note_lands_in_the_inbox_through_the_dashboard(self):
        res, out = tool(self.port, "leave_note", text="Why does rereading feel like learning?")
        self.assertFalse(res["isError"], res)
        inbox = [json.loads(l) for l in open(os.path.join(self.vault, "_system", "inbox.jsonl"), encoding="utf-8") if l.strip()]
        note = inbox[-1]
        self.assertEqual((note["kind"], note["topic"], note["note"]), ("note", "general", "Why does rereading feel like learning?"))
        self.assertIn("test-client", note["title"], "the tutor can see which tool it came from")

    def test_mistakes_come_back_as_readable_errors(self):
        res, _ = tool(self.port, "get_next_task", topic="nope")
        self.assertTrue(res["isError"])
        self.assertIn("no topic", res["content"][0]["text"])
        res, _ = tool(self.port, "leave_note", text="   ")
        self.assertTrue(res["isError"])
        r = talk(self.port, ("tools/call", {"name": "submit_answers", "arguments": {}}), ("bogus/method", {}))
        self.assertEqual(r[1]["error"]["code"], -32602)
        self.assertEqual(r[2]["error"]["code"], -32601)

    def test_says_how_to_start_the_dashboard_when_it_is_off(self):
        res = talk(free_port(), ("tools/call", {"name": "get_progress", "arguments": {}}))[1]["result"]
        self.assertTrue(res["isError"])
        self.assertIn("isn't running", res["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
