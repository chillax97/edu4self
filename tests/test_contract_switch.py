import http.client
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
CLI = os.path.join(ENGINE, "edu4self")

STANDIN_CLAUDE_SOURCE = """#!/usr/bin/env python3
import json
import os
import sys


def main():
    args = sys.argv[1:]
    if "--help" in args:
        print("Usage: claude [options]\\n  auth  Manage authentication")
        return 0
    if args[:2] == ["auth", "status"]:
        print(json.dumps({"loggedIn": True}))
        return 0

    log_path = os.environ.get("STANDIN_CLAUDE_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cwd": os.getcwd(), "args": args}) + "\\n")

    mode = os.environ.get("STANDIN_CLAUDE_MODE", "grade")
    vault = os.getcwd()
    sys_dir = os.path.join(vault, "_system")
    inbox_path = os.path.join(sys_dir, "inbox.jsonl")
    entries = []
    if os.path.isfile(inbox_path):
        with open(inbox_path, encoding="utf-8") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]

    if mode == "grade":
        target = next(
            (e for e in reversed(entries) if e.get("kind") == "answers" and e.get("task") == "hlw-lesson-01"),
            None,
        )
        if target is not None:
            grading_dir = os.path.join(sys_dir, "grading")
            os.makedirs(grading_dir, exist_ok=True)
            req = {
                "attempt": target["id"],
                "grader": {"agent": "claude-code", "model": "standin-model", "session": "standin-grade-1"},
                "title": os.environ.get("STANDIN_GRADE_TITLE", "Stand-in grade: all points met"),
                "detail": "Every required point covered by the stand-in grader.",
                "questions": [
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True, "2b": True}, "errors": []},
                    {"n": 3, "points": {"3a": True, "3b": True}, "errors": []},
                ],
            }
            with open(os.path.join(grading_dir, f"{target['id']}.json"), "w", encoding="utf-8") as fh:
                json.dump(req, fh, indent=1)
    elif mode == "write_history":
        state_path = os.path.join(sys_dir, "state.json")
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["topics"][0]["history"] = [
            {
                "date": "2026-06-05",
                "kind": "lesson",
                "title": "Direct history write",
                "detail": "Wrote history into schema 2 state.",
                "evidence": True,
            }
        ]
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
    elif mode == "ack_first":
        target = next(
            (e for e in reversed(entries) if e.get("task") == "first-try"),
            None,
        )
        if target is not None:
            grading_dir = os.path.join(sys_dir, "grading")
            os.makedirs(grading_dir, exist_ok=True)
            req = {
                "attempt": target["id"],
                "grader": {"agent": "claude-code", "model": "standin-model", "session": "standin-first-1"},
                "ack": True,
            }
            with open(os.path.join(grading_dir, f"{target['id']}.json"), "w", encoding="utf-8") as fh:
                json.dump(req, fh, indent=1)
            state_path = os.path.join(sys_dir, "state.json")
            with open(state_path, encoding="utf-8") as fh:
                state = json.load(fh)
            state["coach"] = {
                "date": "2026-06-05",
                "headline": "Good start on the first try.",
                "body": "Next up: open Lesson 01 and answer from memory.",
                "voices": [{"voice": "logic", "text": "You recalled the main point."}],
            }
            state["updated"] = "2026-06-05T12:05:00+00:00"
            with open(state_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=1)

    print(json.dumps({"type": "system", "subtype": "init", "session_id": "standin-session"}), flush=True)
    print(json.dumps({"type": "result", "is_error": False, "result": "done"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_jsonl(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [entry if isinstance(entry, str) else json.dumps(entry) for entry in entries]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def make_key(task_id, sections):
    parts = [f"# Answer key: {task_id}\n"]
    for idx, (skill, point_ids) in enumerate(sections, start=1):
        pts = "".join(f"- {pid}. Required point {pid}.\n" for pid in point_ids)
        parts.append(
            f"\n## {idx}. Question {idx}\n\n"
            f"Skill: {skill}\n\n"
            f"Required:\n"
            f"{pts}"
        )
    return "".join(parts)


def make_task(topic_id, task_id, kind="lesson", status="todo", num_fields=1, locked=False, with_submit=True):
    task = {
        "id": task_id,
        "kind": kind,
        "status": "locked" if locked else status,
        "label": task_id,
        "title": f"Title {task_id}",
        "why": f"Why {task_id}",
    }
    if locked:
        task["unlock"] = "Locked until ready."
    else:
        task["href"] = f"/vault/{topic_id}/{task_id}.md"
        task["effort"] = "10 min"
        if with_submit:
            task["submit"] = {
                "type": "answers",
                "intro": "Answer from memory.",
                "fields": [f"{i}. Prompt {i}" for i in range(1, num_fields + 1)],
            }
    return task


def write_task_page(vault, topic_id, task_id):
    write_text(os.path.join(vault, topic_id, f"{task_id}.md"), f"# {task_id}\n\nExercise content.\n")


def make_graph(topic_id):
    return {
        "schema": 1,
        "topic": topic_id,
        "version": 1,
        "regions": [
            {"code": "A", "name": "Core"},
            {"code": "B", "name": "Applied"},
        ],
        "skills": [
            {
                "id": "skill-alpha",
                "name": "Alpha",
                "region": "A",
                "can": "Demonstrate alpha.",
                "requires": [],
            },
            {
                "id": "skill-beta",
                "name": "Beta",
                "region": "B",
                "can": "Demonstrate beta.",
                "requires": ["skill-alpha"],
            },
        ],
        "changes": [{"version": 1, "date": "2026-06-01", "why": "Initial."}],
    }


def make_topic(topic_id, queue, regions=None, history=None):
    topic = {
        "id": topic_id,
        "title": f"Topic {topic_id}",
        "tagline": f"Tagline for {topic_id}",
        "path": topic_id,
        "color": "#13a38b",
        "phase": "Core",
        "block": "lessons",
        "milestones": [
            {
                "id": "M1",
                "title": "Milestone 1",
                "goal": "Reach the goal",
                "estimate": "1 lesson",
                "status": "active",
                "steps": [{"title": "Step 1", "done": False, "current": True}],
            }
        ],
        "queue": queue,
    }
    if regions is not None:
        topic["regions"] = regions
    if history is not None:
        topic["history"] = history
    return topic


def make_state(topics, schema=2, processed_inbox=None):
    state = {
        "schema": schema,
        "updated": "2026-06-01T09:00:00+00:00",
        "learner": "Kim",
        "pace": {"hours_per_step": 2},
        "coach": {
            "date": "2026-06-01",
            "headline": "Welcome.",
            "body": "Start with the first task.",
            "voices": [{"voice": "logic", "text": "Begin."}],
        },
        "topics": topics,
        "linked_topics": [],
    }
    if processed_inbox is not None:
        state["processed_inbox"] = list(processed_inbox)
    return state


def make_inbox_entry(
    entry_id,
    topic="spanish",
    task="sp-01",
    kind="answers",
    ts="2026-06-01T10:00:00+00:00",
    honor=True,
    fields=None,
    note="",
):
    return {
        "id": entry_id,
        "ts": ts,
        "topic": topic,
        "task": task,
        "kind": kind,
        "honor": honor,
        "fields": fields if fields is not None else {"1. Prompt 1": "My answer"},
        "note": note,
        "title": "",
    }


PROHIBITION_RE = re.compile(
    r"\b(never|don't|do not|cannot|can't|must not|no longer|not write|not add|remove|removed|forbid|forbidden)\b",
    re.IGNORECASE,
)
JSON_KEY_RE = re.compile(r'"(history|processed_inbox|levels|evidence)"\s*:')
BACKTICK_ASSIGN_RE = re.compile(
    r"`(history(?:\[\])?|processed_inbox|levels\??|evidence)\s*:\s*(true|false|bool|\[|\{)"
)
PLAIN_ASSIGN_RE = re.compile(r"\b(history|processed_inbox|levels|evidence)\s*:\s*(true|false|bool)\b")
BACKTICK_STRUCTURAL_RE = re.compile(r"`(history\[\]|processed_inbox)`")
WRITE_VERB_RE = re.compile(
    r"\b(write|add|append|update|set|put|include|record|register|keep|fill)\b",
    re.IGNORECASE,
)
WRITE_TARGET_RE = re.compile(
    r"(`(history|processed_inbox|levels|evidence)`|\b(history\s+entr(?:y|ies)|processed_inbox)\b)"
)
REQUIRED_LIST_RE = re.compile(r"\brequired\b.*\b(history|processed_inbox|levels|evidence)\b", re.IGNORECASE)
BACKTICK_FIELD_RE = re.compile(r"`(history|processed_inbox|levels|evidence)`")


def find_forbidden_doc_instructions(text):
    hits = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        if PROHIBITION_RE.search(line):
            continue
        prev = lines[idx - 2] if idx >= 2 else ""
        window = prev + " " + line
        if JSON_KEY_RE.search(line):
            hits.append((idx, line.strip()))
            continue
        if BACKTICK_ASSIGN_RE.search(line) or PLAIN_ASSIGN_RE.search(line):
            hits.append((idx, line.strip()))
            continue
        if BACKTICK_STRUCTURAL_RE.search(line):
            hits.append((idx, line.strip()))
            continue
        if REQUIRED_LIST_RE.search(line):
            hits.append((idx, line.strip()))
            continue
        m_verb = WRITE_VERB_RE.search(line)
        if m_verb and WRITE_TARGET_RE.search(line[m_verb.start():]):
            hits.append((idx, line.strip()))
            continue
        m_bt = BACKTICK_FIELD_RE.search(line)
        if m_bt:
            field = m_bt.group(1)
            if field == "levels" and "progress.json" in window:
                continue
            hits.append((idx, line.strip()))
    return hits


class ContractSwitchTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.class_tmp = tempfile.mkdtemp(prefix="edu4self-step6-base-")
        cls.base_env = dict(
            os.environ,
            EDU4SELF_CONFIG_HOME=os.path.join(cls.class_tmp, "cfg"),
            HOME=cls.class_tmp,
            CLAUDE_CONFIG_DIR=os.path.join(cls.class_tmp, "claude"),
            EDU4SELF_NO_UPDATE_CHECK="1",
        )
        cls.base_env.pop("EDU4SELF_PORT", None)
        cls.base_env.pop("EDU4SELF_VAULT", None)
        cls.base_vault = os.path.join(cls.class_tmp, "base-vault")
        res = subprocess.run(
            [sys.executable, CLI, "init", cls.base_vault, "--name", "Kim", "--port", "4800"],
            env=cls.base_env,
            stdin=subprocess.DEVNULL,
            timeout=60,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        if res.returncode != 0:
            shutil.rmtree(cls.class_tmp, ignore_errors=True)
            raise RuntimeError(res.stdout + res.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.class_tmp, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-step6-")
        self.env = dict(
            os.environ,
            EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg"),
            HOME=self.tmp,
            CLAUDE_CONFIG_DIR=os.path.join(self.tmp, "claude"),
            EDU4SELF_NO_UPDATE_CHECK="1",
        )
        self.env.pop("EDU4SELF_PORT", None)
        self.env.pop("EDU4SELF_VAULT", None)
        self.servers = []

    def tearDown(self):
        for proc in self.servers:
            self.stop_server(proc)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stop_server(self, proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        out = proc.stdout.read() if proc.stdout is not None and not proc.stdout.closed else ""
        err = proc.stderr.read() if proc.stderr is not None and not proc.stderr.closed else ""
        for stream in (proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        return out, err

    def start_server(self, vault, extra_env=None):
        port = free_port()
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        proc = subprocess.Popen(
            [sys.executable, CLI, "serve", "--vault", vault, "--port", str(port)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        self.servers.append(proc)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if proc.poll() is not None:
                out, err = proc.communicate()
                self.fail(f"server exited early ({proc.returncode}): {out} {err}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return port, proc
            except OSError:
                time.sleep(0.05)
        self.fail("server did not start listening in time")

    def http_req(self, port, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        raw = None
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=raw, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        try:
            parsed = json.loads(data)
        except ValueError:
            parsed = data
        return resp.status, parsed

    def wait_claude_idle(self, port, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            code, data = self.http_req(port, "GET", "/api/claude")
            self.assertEqual(code, 200, data)
            if not data["busy"]:
                return data
            time.sleep(0.05)
        self.fail("claude run did not finish in time")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, CLI, *args],
            env=self.env,
            stdin=subprocess.DEVNULL,
            timeout=60,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )

    def run_check(self, vault):
        res = self.run_cli("check", "--vault", vault)
        return res.returncode, res.stdout + res.stderr

    def fresh_init_vault(self, name="fresh-vault"):
        vault = os.path.join(self.tmp, name)
        shutil.copytree(self.base_vault, vault)
        return vault

    def write_standin_claude(self, name="standin_claude.py"):
        path = os.path.join(self.tmp, name)
        write_text(path, STANDIN_CLAUDE_SOURCE)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def build_schema1_fixture(self, name="schema1-fixture"):
        vault = os.path.join(self.tmp, name)
        shutil.copytree(self.base_vault, vault)
        for rel in ("how-learning-works", os.path.join("_system", "keys", "how-learning-works")):
            target = os.path.join(vault, rel)
            if os.path.exists(target):
                shutil.rmtree(target)
        for fn in ("inbox.jsonl", "grades.jsonl", "progress.json"):
            path = os.path.join(vault, "_system", fn)
            if os.path.exists(path):
                os.remove(path)
        for folder in ("grading", "backup"):
            target = os.path.join(vault, "_system", folder)
            if os.path.exists(target):
                shutil.rmtree(target)

        spanish = make_topic(
            "spanish",
            queue=[
                make_task("spanish", "sp-01", status="done", num_fields=2),
                make_task("spanish", "sp-02", status="todo", num_fields=1),
                make_task("spanish", "sp-locked", kind="checkpoint", locked=True),
            ],
            regions=[
                {"code": "A", "name": "Core", "level": 2, "note": "Solid basics."},
                {"code": "B", "name": "Applied", "level": 1, "note": "Started."},
            ],
            history=[
                {
                    "date": "2026-06-02",
                    "kind": "lesson",
                    "title": "Completed sp-01",
                    "detail": "Answered both prompts.",
                    "evidence": True,
                    "inbox": "in-1",
                },
                {
                    "date": "2026-06-01",
                    "kind": "setup",
                    "title": "Spanish created",
                    "detail": "Ready to start.",
                    "evidence": False,
                },
            ],
        )
        rust = make_topic(
            "rust",
            queue=[
                make_task("rust", "rs-01", status="done", num_fields=1),
                make_task("rust", "rs-02", status="todo", num_fields=1),
            ],
            regions=[
                {"code": "R1", "name": "Ownership", "level": 1, "note": "Intro done."},
            ],
            history=[
                {
                    "date": "2026-06-01",
                    "kind": "setup",
                    "title": "Rust created",
                    "detail": "Initial plan.",
                    "evidence": False,
                },
            ],
        )
        state = make_state([spanish, rust], schema=1, processed_inbox=["in-1", "in-ack"])
        write_json(os.path.join(vault, "_system", "state.json"), state)

        write_json(os.path.join(vault, "spanish", "graph.json"), make_graph("spanish"))
        write_task_page(vault, "spanish", "sp-01")
        write_task_page(vault, "spanish", "sp-02")
        write_text(
            os.path.join(vault, "_system", "keys", "spanish", "sp-01.md"),
            make_key("sp-01", [("skill-alpha", ["1a", "1b"]), ("none", ["2a"])]),
        )
        write_text(
            os.path.join(vault, "_system", "keys", "spanish", "sp-02.md"),
            make_key("sp-02", [("skill-beta", ["1a"])]),
        )
        write_task_page(vault, "rust", "rs-01")
        write_task_page(vault, "rust", "rs-02")

        inbox = [
            make_inbox_entry(
                "in-1",
                topic="spanish",
                task="sp-01",
                kind="answers",
                ts="2026-06-02T10:00:00+00:00",
                honor=True,
                fields={"1. Prompt 1": "Alpha", "2. Prompt 2": "Extra"},
            ),
            make_inbox_entry(
                "in-ack",
                topic="spanish",
                task="note",
                kind="note",
                ts="2026-06-02T11:00:00+00:00",
                honor=False,
                fields={},
                note="Quick question before migration.",
            ),
        ]
        write_jsonl(os.path.join(vault, "_system", "inbox.jsonl"), inbox)
        return vault

    def build_schema2_vault(self, name="schema2-vault"):
        vault = os.path.join(self.tmp, name)
        shutil.copytree(self.base_vault, vault)
        for rel in ("how-learning-works", os.path.join("_system", "keys", "how-learning-works")):
            target = os.path.join(vault, rel)
            if os.path.exists(target):
                shutil.rmtree(target)
        for fn in ("inbox.jsonl", "grades.jsonl", "progress.json"):
            path = os.path.join(vault, "_system", fn)
            if os.path.exists(path):
                os.remove(path)
        for folder in ("grading", "backup"):
            target = os.path.join(vault, "_system", folder)
            if os.path.exists(target):
                shutil.rmtree(target)

        spanish = make_topic(
            "spanish",
            queue=[
                make_task("spanish", "sp-01", status="todo", num_fields=2, with_submit=True),
                make_task("spanish", "sp-read", kind="reading", status="todo", with_submit=False),
            ],
        )
        write_json(os.path.join(vault, "_system", "state.json"), make_state([spanish], schema=2))
        write_json(os.path.join(vault, "spanish", "graph.json"), make_graph("spanish"))
        write_task_page(vault, "spanish", "sp-01")
        write_task_page(vault, "spanish", "sp-read")
        write_text(
            os.path.join(vault, "_system", "keys", "spanish", "sp-01.md"),
            make_key("sp-01", [("skill-alpha", ["1a", "1b"]), ("none", ["2a"])]),
        )
        return vault


class FreshInitSchema2Test(ContractSwitchTestBase):
    def test_fresh_init_vault_is_schema2_passes_check_and_serves_graph_regions_without_history(self):
        vault = self.fresh_init_vault()
        disk_state = read_json(os.path.join(vault, "_system", "state.json"))
        self.assertEqual(disk_state["schema"], 2)
        self.assertNotIn("processed_inbox", disk_state)

        hlw_disk = next(t for t in disk_state["topics"] if t["id"] == "how-learning-works")
        self.assertNotIn("history", hlw_disk)
        self.assertNotIn("regions", hlw_disk)

        rc, out = self.run_check(vault)
        self.assertEqual(rc, 0, out)

        graph = read_json(os.path.join(vault, "how-learning-works", "graph.json"))
        expected_regions = [(r["code"], r["name"]) for r in graph["regions"]]

        port, proc = self.start_server(vault)
        code, data = self.http_req(port, "GET", "/api/state")
        self.stop_server(proc)
        self.assertEqual(code, 200, data)

        hlw_view = next(t for t in data["state"]["topics"] if t["id"] == "how-learning-works")
        self.assertEqual(hlw_view["history"], [])
        self.assertEqual([(r["code"], r["name"]) for r in hlw_view["regions"]], expected_regions)
        for region in hlw_view["regions"]:
            self.assertEqual(region["level"], 0, region)
            self.assertNotIn("legacy_level", region)
        self.assertIn("progress", data["derived"])


class ServerAutoMigrateTest(ContractSwitchTestBase):
    def test_server_migrates_schema1_vault_before_first_state_and_preserves_view(self):
        vault = self.build_schema1_fixture()
        state_path = os.path.join(vault, "_system", "state.json")
        old_state_bytes = read_bytes(state_path)
        old_state = read_json(state_path)

        expected_summary = {}
        for topic in old_state["topics"]:
            expected_summary[topic["id"]] = {
                "history_titles": [h["title"] for h in topic["history"]],
                "regions": [(r["code"], r["level"]) for r in topic["regions"]],
                "done_tasks": [t["id"] for t in topic["queue"] if t["status"] == "done"],
            }

        port, proc = self.start_server(vault)

        disk_state = read_json(state_path)
        self.assertEqual(disk_state["schema"], 2)
        self.assertNotIn("processed_inbox", disk_state)
        for topic in disk_state["topics"]:
            self.assertNotIn("history", topic)
            self.assertNotIn("regions", topic)

        backup_dir = os.path.join(vault, "_system", "backup")
        self.assertTrue(os.path.isdir(backup_dir))
        backups = [os.path.join(backup_dir, fn) for fn in sorted(os.listdir(backup_dir)) if fn.endswith(".json")]
        self.assertTrue(any(read_bytes(p) == old_state_bytes for p in backups), backups)

        code, data = self.http_req(port, "GET", "/api/state")
        self.stop_server(proc)
        self.assertEqual(code, 200, data)

        actual_summary = {}
        for topic in data["state"]["topics"]:
            actual_summary[topic["id"]] = {
                "history_titles": [h["title"] for h in topic["history"]],
                "regions": [(r["code"], r["level"]) for r in topic["regions"]],
                "done_tasks": [t["id"] for t in topic["queue"] if t["status"] == "done"],
            }
        self.assertEqual(actual_summary, expected_summary)
        self.assertIn("progress", data["derived"])

        grades_path = os.path.join(vault, "_system", "grades.jsonl")
        grades_after_first = read_bytes(grades_path)
        backups_after_first = sorted(os.listdir(backup_dir))

        port2, proc2 = self.start_server(vault)
        code2, data2 = self.http_req(port2, "GET", "/api/state")
        self.stop_server(proc2)
        self.assertEqual(code2, 200, data2)
        self.assertEqual(read_bytes(grades_path), grades_after_first)
        self.assertEqual(sorted(os.listdir(backup_dir)), backups_after_first)

    def test_server_still_starts_on_schema1_when_migration_fails(self):
        vault = self.build_schema1_fixture(name="s1-blocked")
        state_path = os.path.join(vault, "_system", "state.json")
        old_state_bytes = read_bytes(state_path)
        write_text(os.path.join(vault, "_system", "backup"), "block backup directory creation")

        port, proc = self.start_server(vault)
        code, data = self.http_req(port, "GET", "/api/state")
        out, err = self.stop_server(proc)

        self.assertEqual(code, 200, data)
        self.assertEqual(read_bytes(state_path), old_state_bytes)
        self.assertEqual(data["state"]["schema"], 1)
        combined = (out + err).lower()
        self.assertTrue(
            any(word in combined for word in ("migrat", "error", "fail")),
            out + err,
        )


class Schema2CheckRulesTest(ContractSwitchTestBase):
    def test_schema2_forbidden_fields_fail_check_naming_grading_dir(self):
        cases = (
            ("history", lambda st: st["topics"][0].__setitem__("history", [])),
            ("regions", lambda st: st["topics"][0].__setitem__("regions", [])),
            ("processed_inbox", lambda st: st.__setitem__("processed_inbox", [])),
        )
        for label, mutate in cases:
            with self.subTest(field=label):
                vault = self.build_schema2_vault(name=f"check-{label}")
                rc_ok, out_ok = self.run_check(vault)
                self.assertEqual(rc_ok, 0, out_ok)

                state_path = os.path.join(vault, "_system", "state.json")
                state = read_json(state_path)
                mutate(state)
                write_json(state_path, state)

                rc, out = self.run_check(vault)
                self.assertEqual(rc, 1, out)
                self.assertIn("_system/grading/", out)

    def test_schema2_done_status_fails_with_submit_and_passes_without_submit(self):
        vault = self.build_schema2_vault(name="check-done")
        state_path = os.path.join(vault, "_system", "state.json")

        state = read_json(state_path)
        next(t for t in state["topics"][0]["queue"] if t["id"] == "sp-read")["status"] = "done"
        write_json(state_path, state)
        rc_reading, out_reading = self.run_check(vault)
        self.assertEqual(rc_reading, 0, out_reading)

        next(t for t in state["topics"][0]["queue"] if t["id"] == "sp-01")["status"] = "done"
        write_json(state_path, state)
        rc_submit, out_submit = self.run_check(vault)
        self.assertEqual(rc_submit, 1, out_submit)
        self.assertIn("done is computed from a passing grade", out_submit)


class PageRunContractTest(ContractSwitchTestBase):
    def test_standin_grade_request_marks_task_done_and_adds_history_without_editing_state(self):
        vault = self.fresh_init_vault(name="run-grade")
        state_path = os.path.join(vault, "_system", "state.json")
        self.assertEqual(read_json(state_path)["schema"], 2)
        state_bytes_before = read_bytes(state_path)

        standin = self.write_standin_claude()
        grade_title = "All three retrieval points clear"
        port, proc = self.start_server(
            vault,
            extra_env={
                "EDU4SELF_CLAUDE": standin,
                "STANDIN_CLAUDE_MODE": "grade",
                "STANDIN_GRADE_TITLE": grade_title,
            },
        )
        try:
            sub = {
                "topic": "how-learning-works",
                "task": "hlw-lesson-01",
                "kind": "answers",
                "fields": {
                    "1. Retrieval vs storage": "Retrieval is current ease; storage is durability.",
                    "2. Why rereading feels good": "Familiarity raises retrieval strength, not storage.",
                    "3. Retrieval plan": "Close notes and write a summary from memory.",
                },
                "confidence": "solid",
            }
            code_sub, sub_data = self.http_req(port, "POST", "/api/inbox", sub)
            self.assertEqual(code_sub, 201, sub_data)

            code_run, run_start = self.http_req(port, "POST", "/api/claude", {"kind": "grade"})
            self.assertEqual(code_run, 202, run_start)
            run_done = self.wait_claude_idle(port)

            check_events = [e["text"] for e in run_done["events"] if e["kind"] == "check"]
            self.assertTrue(check_events, run_done["events"])
            self.assertIn("OK", check_events[-1])
            self.assertFalse(any("Check FAILED" in t for t in check_events), check_events)

            self.assertEqual(read_bytes(state_path), state_bytes_before)

            code_st, st = self.http_req(port, "GET", "/api/state")
            self.assertEqual(code_st, 200, st)
            self.assertEqual(st["inbox"]["pending"], [])

            hlw = next(t for t in st["state"]["topics"] if t["id"] == "how-learning-works")
            task = next(q for q in hlw["queue"] if q["id"] == "hlw-lesson-01")
            self.assertEqual(task["status"], "done")
            matched = [h for h in hlw["history"] if h.get("title") == grade_title]
            self.assertEqual(len(matched), 1, hlw["history"])
            self.assertEqual(matched[0]["inbox"], sub_data["id"])
            self.assertIs(matched[0]["evidence"], True)
        finally:
            self.stop_server(proc)

    def test_standin_writing_history_into_schema2_state_gets_check_failed(self):
        vault = self.fresh_init_vault(name="run-history-fail")
        state_path = os.path.join(vault, "_system", "state.json")
        self.assertEqual(read_json(state_path)["schema"], 2)

        standin = self.write_standin_claude()
        port, proc = self.start_server(
            vault,
            extra_env={
                "EDU4SELF_CLAUDE": standin,
                "STANDIN_CLAUDE_MODE": "write_history",
            },
        )
        try:
            sub = {
                "topic": "how-learning-works",
                "task": "hlw-lesson-01",
                "kind": "answers",
                "fields": {"1": "Answer"},
                "confidence": "solid",
            }
            self.assertEqual(self.http_req(port, "POST", "/api/inbox", sub)[0], 201)
            code_run, run_start = self.http_req(port, "POST", "/api/claude", {"kind": "grade"})
            self.assertEqual(code_run, 202, run_start)
            run_done = self.wait_claude_idle(port)

            event_texts = [e.get("text", "") for e in run_done["events"]]
            self.assertTrue(any("Check FAILED" in text for text in event_texts), run_done["events"])
        finally:
            self.stop_server(proc)

    def test_first_try_ack_request_clears_pending_and_prompt_asks_for_ack(self):
        vault = self.fresh_init_vault(name="run-first-try")
        state_path = os.path.join(vault, "_system", "state.json")
        self.assertEqual(read_json(state_path)["schema"], 2)

        standin = self.write_standin_claude()
        log_path = os.path.join(self.tmp, "first-try-calls.jsonl")
        port, proc = self.start_server(
            vault,
            extra_env={
                "EDU4SELF_CLAUDE": standin,
                "STANDIN_CLAUDE_MODE": "ack_first",
                "STANDIN_CLAUDE_LOG": log_path,
            },
        )
        try:
            first_sub = {
                "topic": "how-learning-works",
                "task": "first-try",
                "kind": "answers",
                "fields": {"Why?": "Pulling an idea out of memory strengthens it."},
                "confidence": "shaky",
            }
            code_sub, first_data = self.http_req(port, "POST", "/api/inbox", first_sub)
            self.assertEqual(code_sub, 201, first_data)

            code_run, run_start = self.http_req(port, "POST", "/api/claude", {"kind": "first"})
            self.assertEqual(code_run, 202, run_start)
            run_done = self.wait_claude_idle(port)

            check_events = [e["text"] for e in run_done["events"] if e["kind"] == "check"]
            self.assertTrue(check_events, run_done["events"])
            self.assertIn("OK", check_events[-1])
            self.assertFalse(any("Check FAILED" in t for t in check_events), check_events)

            code_st, st = self.http_req(port, "GET", "/api/state")
            self.assertEqual(code_st, 200, st)
            pending_ids = [entry["id"] for entry in st["inbox"]["pending"]]
            self.assertNotIn(first_data["id"], pending_ids)

            grades = read_jsonl(os.path.join(vault, "_system", "grades.jsonl"))
            self.assertTrue(
                any(ev.get("type") == "ack" and ev.get("attempt") == first_data["id"] for ev in grades),
                grades,
            )

            calls = read_jsonl(log_path)
            self.assertTrue(calls)
            args = calls[-1]["args"]
            prompt = args[args.index("-p") + 1]
            self.assertIn("ack", prompt)
            self.assertIn("_system/grading/", prompt)
        finally:
            self.stop_server(proc)


class TutorDocsContractTest(unittest.TestCase):
    def test_protocol_copies_are_byte_identical(self):
        docs_protocol = os.path.join(ENGINE, "docs", "PROTOCOL.md")
        plugin_protocol = os.path.join(ENGINE, "plugin", "skills", "check-inbox", "PROTOCOL.md")
        self.assertEqual(read_bytes(docs_protocol), read_bytes(plugin_protocol))

    def test_tutor_docs_do_not_instruct_writing_schema1_fields(self):
        targets = [
            os.path.join(ENGINE, "docs", "PROTOCOL.md"),
            os.path.join(ENGINE, "plugin", "skills", "check-inbox", "PROTOCOL.md"),
            os.path.join(ENGINE, "template", "CLAUDE.md.tmpl"),
        ]
        skills_root = os.path.join(ENGINE, "plugin", "skills")
        for dirpath, dirnames, filenames in os.walk(skills_root):
            dirnames.sort()
            for fn in sorted(filenames):
                if fn.endswith(".md"):
                    full = os.path.join(dirpath, fn)
                    if full not in targets:
                        targets.append(full)

        violations = []
        for path in targets:
            rel = os.path.relpath(path, ENGINE)
            for lineno, line in find_forbidden_doc_instructions(read_text(path)):
                violations.append(f"{rel}:{lineno}: {line}")

        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
