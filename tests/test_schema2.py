import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
CLI = os.path.join(ENGINE, "edu4self")
PINNED_NOW = "2026-06-05T12:00:00+00:00"


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


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


def snapshot_vault(root):
    snap = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            with open(full, "rb") as fh:
                snap[rel] = fh.read()
    return snap


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


def make_task(topic_id, task_id, kind="lesson", status="todo", num_fields=1, locked=False):
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
        task["submit"] = {
            "type": "answers",
            "intro": "Answer from memory.",
            "fields": [f"{i}. Prompt {i}" for i in range(1, num_fields + 1)],
        }
    return task


def write_task_page(vault, topic_id, task_id):
    write_text(os.path.join(vault, topic_id, f"{task_id}.md"), f"# {task_id}\n\nExercise content.\n")


def make_topic(topic_id, queue, regions, history):
    return {
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
        "regions": regions,
        "history": history,
    }


def make_state(topics, processed_inbox=None):
    return {
        "schema": 1,
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
        "processed_inbox": list(processed_inbox or []),
    }


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
            {
                "id": "skill-retired",
                "name": "Retired",
                "region": "A",
                "can": "Old skill.",
                "requires": [],
                "retired": True,
            },
        ],
        "changes": [{"version": 1, "date": "2026-06-01", "why": "Initial."}],
    }


def make_inbox_entry(
    entry_id,
    topic="spanish",
    task="sp-01",
    kind="answers",
    ts="2026-01-15T10:00:00+00:00",
    honor=True,
    fields=None,
    note="",
    ref=None,
    skill=None,
):
    entry = {
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
    if ref is not None:
        entry["ref"] = ref
    if skill is not None:
        entry["skill"] = skill
    return entry


def make_grader(session="run-1"):
    return {
        "agent": "claude-code",
        "model": "claude-opus-5-5",
        "session": session,
    }


def make_request(
    attempt,
    questions=None,
    title="Graded",
    detail="Checked against key.",
    session="run-1",
    record=None,
):
    req = {
        "attempt": attempt,
        "grader": make_grader(session=session),
        "title": title,
        "detail": detail,
        "questions": questions if questions is not None else [],
    }
    if record is not None:
        req["record"] = record
    return req


class Schema2TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.class_tmp = tempfile.mkdtemp(prefix="edu4self-schema2-base-")
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
        self.tmp = tempfile.mkdtemp(prefix="edu4self-schema2-")
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
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()

    def start_server(self, vault):
        port = free_port()
        proc = subprocess.Popen(
            [sys.executable, CLI, "serve", "--vault", vault, "--port", str(port)],
            env=self.env,
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
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
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

    def run_migrate(self, vault, dry_run=False, now=PINNED_NOW):
        args = ["migrate", "--vault", vault]
        if dry_run:
            args.append("--dry-run")
        if now is not None:
            args.extend(["--now", now])
        return self.run_cli(*args)

    def run_check(self, vault):
        res = self.run_cli("check", "--vault", vault)
        return res.returncode, res.stdout + res.stderr

    def run_ingest(self, vault):
        res = self.run_cli("ingest", "--vault", vault)
        try:
            payload = json.loads(res.stdout)
        except ValueError:
            self.fail(f"ingest did not print valid JSON (rc={res.returncode}): {res.stdout!r} {res.stderr!r}")
        return res.returncode, payload

    def write_request(self, vault, filename, data):
        path = os.path.join(vault, "_system", "grading", filename)
        raw = data.encode("utf-8") if isinstance(data, str) else json.dumps(data).encode("utf-8")
        write_bytes(path, raw)
        return path, raw

    def fresh_init_vault(self, name="fresh-vault"):
        vault = os.path.join(self.tmp, name)
        shutil.copytree(self.base_vault, vault)
        return vault

    def build_schema1_fixture(self, name="fixture", extra_inbox=None):
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
                    "date": "2026-06-02",
                    "kind": "note",
                    "title": "Midway review",
                    "detail": "Reviewed notes without inbox.",
                    "evidence": False,
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
        state = make_state([spanish, rust], processed_inbox=["in-1", "in-ack"])
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
                ts="2026-01-15T10:00:00+00:00",
                honor=True,
                fields={"1. Prompt 1": "Alpha", "2. Prompt 2": "Extra"},
            ),
            make_inbox_entry(
                "in-ack",
                topic="spanish",
                task="note",
                kind="note",
                ts="2026-01-15T11:00:00+00:00",
                honor=False,
                fields={},
                note="Quick question before migration.",
            ),
        ]
        if extra_inbox:
            inbox.extend(extra_inbox)
        write_jsonl(os.path.join(vault, "_system", "inbox.jsonl"), inbox)
        return vault


class Schema2BehaviorTest(Schema2TestBase):
    def test_server_migrates_schema1_fixture_preserving_view_creates_backup_and_passes_check(self):
        vault = self.build_schema1_fixture()
        state_path = os.path.join(vault, "_system", "state.json")
        old_state = read_json(state_path)
        old_state_bytes = read_bytes(state_path)
        expected = {}
        for topic in old_state["topics"]:
            expected[topic["id"]] = {
                "history_titles": sorted(h["title"] for h in topic["history"]),
                "regions": {r["code"]: r["level"] for r in topic["regions"]},
                "done_tasks": sorted(t["id"] for t in topic["queue"] if t["status"] == "done" and t.get("submit")),
            }

        port, proc = self.start_server(vault)
        code, after = self.http_req(port, "GET", "/api/state")
        self.stop_server(proc)
        self.assertEqual(code, 200, after)

        disk_state = read_json(state_path)
        self.assertEqual(disk_state["schema"], 2)
        self.assertNotIn("processed_inbox", disk_state)
        for topic in disk_state["topics"]:
            self.assertNotIn("history", topic)
            self.assertNotIn("regions", topic)
            for task in topic["queue"]:
                if task.get("submit"):
                    self.assertNotEqual(task["status"], "done")

        backup_folder = os.path.join(vault, "_system", "backup")
        backups = [os.path.join(backup_folder, n) for n in sorted(os.listdir(backup_folder))]
        self.assertTrue(any(read_bytes(path) == old_state_bytes for path in backups), backups)

        check_rc, check_out = self.run_check(vault)
        self.assertEqual(check_rc, 0, check_out)

        after_summary = {}
        for topic in after["state"]["topics"]:
            after_summary[topic["id"]] = {
                "history_titles": sorted(h["title"] for h in topic["history"]),
                "regions": {r["code"]: r["level"] for r in topic["regions"]},
                "done_tasks": sorted(t["id"] for t in topic["queue"] if t["status"] == "done"),
            }
        self.assertEqual(after_summary, expected)

    def test_dry_run_and_second_migrate_change_no_bytes(self):
        vault = self.build_schema1_fixture()
        snap_before = snapshot_vault(vault)

        dry_res = self.run_migrate(vault, dry_run=True, now=PINNED_NOW)
        self.assertEqual(dry_res.returncode, 0, dry_res.stdout + dry_res.stderr)
        dry_report = json.loads(dry_res.stdout)
        self.assertEqual(dry_report["schema"], 1)
        self.assertIs(dry_report["dry_run"], True)
        self.assertEqual(snapshot_vault(vault), snap_before)

        real_res = self.run_migrate(vault, dry_run=False, now=PINNED_NOW)
        self.assertEqual(real_res.returncode, 0, real_res.stdout + real_res.stderr)
        real_report = json.loads(real_res.stdout)
        self.assertEqual(real_report["append"], dry_report["append"])
        self.assertEqual(real_report["undone"], dry_report["undone"])

        snap_after_first = snapshot_vault(vault)
        second_res = self.run_migrate(vault, dry_run=False, now=PINNED_NOW)
        self.assertEqual(second_res.returncode, 0, second_res.stdout + second_res.stderr)
        self.assertEqual(snapshot_vault(vault), snap_after_first)
        try:
            second_report = json.loads(second_res.stdout)
        except ValueError:
            self.assertIn("2", second_res.stdout + second_res.stderr)
        else:
            self.assertEqual(second_report["schema"], 2)
            self.assertEqual(second_report["append"], {"legacy": 0, "legacy_topic": 0, "ack": 0})
            self.assertEqual(second_report["undone"], [])

    def test_pre_migration_handled_inbox_entries_are_not_pending_after_migration(self):
        unhandled = make_inbox_entry(
            "in-open",
            topic="spanish",
            task="sp-02",
            kind="answers",
            ts="2026-01-16T10:00:00+00:00",
        )
        vault = self.build_schema1_fixture(extra_inbox=[unhandled])
        res = self.run_migrate(vault, now=PINNED_NOW)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        port, proc = self.start_server(vault)
        code, data = self.http_req(port, "GET", "/api/state")
        self.stop_server(proc)
        self.assertEqual(code, 200, data)

        pending_ids = [entry["id"] for entry in data["inbox"]["pending"]]
        self.assertNotIn("in-1", pending_ids)
        self.assertNotIn("in-ack", pending_ids)
        self.assertIn("in-open", pending_ids)

    def test_migrated_fresh_init_vault_grade_request_updates_state_and_progress_json(self):
        vault = self.fresh_init_vault()
        mig = self.run_migrate(vault, now=PINNED_NOW)
        self.assertEqual(mig.returncode, 0, mig.stdout + mig.stderr)

        write_jsonl(
            os.path.join(vault, "_system", "inbox.jsonl"),
            [
                make_inbox_entry(
                    "hlw-a1",
                    topic="how-learning-works",
                    task="hlw-lesson-01",
                    kind="answers",
                    ts="2026-01-15T10:00:00+00:00",
                    honor=True,
                    fields={
                        "1. Retrieval vs storage": "Retrieval is current ease; storage is deep durability.",
                        "2. Why rereading feels good": "Familiarity raises retrieval strength, not storage.",
                        "3. Retrieval plan": "Close my Rust notes and write a summary from memory.",
                    },
                )
            ],
        )
        self.write_request(
            vault,
            "hlw-a1.json",
            make_request(
                "hlw-a1",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True, "2b": True}, "errors": []},
                    {"n": 3, "points": {"3a": True, "3b": True}, "errors": []},
                ],
                title="All three clear",
                detail="Every required point covered.",
            ),
        )

        port, proc = self.start_server(vault)
        code1, data1 = self.http_req(port, "GET", "/api/state")
        self.assertEqual(code1, 200, data1)

        hlw_topic = next(t for t in data1["state"]["topics"] if t["id"] == "how-learning-works")
        hlw_task = next(q for q in hlw_topic["queue"] if q["id"] == "hlw-lesson-01")
        self.assertEqual(hlw_task["status"], "done")

        derived_prog = data1["derived"]["progress"]
        hlw_skills = derived_prog["topics"]["how-learning-works"]["skills"]
        for skill_id in (
            "storage-vs-retrieval-strength",
            "rereading-familiarity",
            "plan-retrieval-practice",
        ):
            self.assertEqual(hlw_skills[skill_id]["level"], 2, skill_id)

        progress_path = os.path.join(vault, "_system", "progress.json")
        self.assertTrue(os.path.isfile(progress_path))
        disk_prog = read_json(progress_path)
        self.assertEqual(disk_prog["topics"], derived_prog["topics"])
        self.assertEqual(disk_prog["recall_due"], derived_prog["recall_due"])
        self.assertEqual(disk_prog["unlinked"], derived_prog["unlinked"])

        bytes_after_first = read_bytes(progress_path)
        mtime_after_first = os.stat(progress_path).st_mtime_ns

        time.sleep(0.05)
        code2, data2 = self.http_req(port, "GET", "/api/state")
        self.stop_server(proc)
        self.assertEqual(code2, 200, data2)
        self.assertEqual(read_bytes(progress_path), bytes_after_first)
        self.assertEqual(os.stat(progress_path).st_mtime_ns, mtime_after_first)

    def test_linked_topic_region_keeps_legacy_level_until_first_observation(self):
        vault = self.build_schema1_fixture(
            extra_inbox=[
                make_inbox_entry(
                    "a-obs",
                    topic="spanish",
                    task="sp-01",
                    kind="answers",
                    ts="2026-01-16T10:00:00+00:00",
                    honor=True,
                    fields={"1. Prompt 1": "Partial", "2. Prompt 2": "Ok"},
                )
            ]
        )
        res = self.run_migrate(vault, now=PINNED_NOW)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        port, proc = self.start_server(vault)
        code1, data1 = self.http_req(port, "GET", "/api/state")
        self.assertEqual(code1, 200, data1)

        spanish1 = next(t for t in data1["state"]["topics"] if t["id"] == "spanish")
        regions1 = {r["code"]: r for r in spanish1["regions"]}
        self.assertEqual(regions1["A"]["level"], 2)
        self.assertEqual(regions1["A"]["legacy_level"], 2)
        self.assertEqual(regions1["B"]["level"], 1)
        self.assertEqual(regions1["B"]["legacy_level"], 1)

        self.write_request(
            vault,
            "a-obs.json",
            make_request(
                "a-obs",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": False}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
                title="Missed 1b",
                detail="Needs second point.",
            ),
        )

        code2, data2 = self.http_req(port, "GET", "/api/state")
        self.stop_server(proc)
        self.assertEqual(code2, 200, data2)

        spanish2 = next(t for t in data2["state"]["topics"] if t["id"] == "spanish")
        regions2 = {r["code"]: r for r in spanish2["regions"]}
        self.assertEqual(regions2["A"]["level"], 1)
        self.assertNotIn("legacy_level", regions2["A"])
        self.assertEqual(regions2["B"]["level"], 1)
        self.assertEqual(regions2["B"]["legacy_level"], 1)

    def test_schema2_state_with_history_fails_check(self):
        vault = self.build_schema1_fixture()
        res = self.run_migrate(vault, now=PINNED_NOW)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        state_path = os.path.join(vault, "_system", "state.json")
        state = read_json(state_path)
        state["topics"][0]["history"] = [
            {
                "date": "2026-06-05",
                "kind": "note",
                "title": "Forbidden on schema 2",
                "detail": "Should fail check.",
                "evidence": False,
            }
        ]
        write_json(state_path, state)

        rc, out = self.run_check(vault)
        self.assertEqual(rc, 1, out)

    def test_init_makes_schema2_and_the_server_serves_it(self):
        vault = self.fresh_init_vault()
        state = read_json(os.path.join(vault, "_system", "state.json"))
        self.assertEqual(state["schema"], 2)
        self.assertNotIn("processed_inbox", state)
        for topic in state["topics"]:
            self.assertNotIn("history", topic)
            self.assertNotIn("regions", topic)

        port, proc = self.start_server(vault)
        code, data = self.http_req(port, "GET", "/api/state")
        self.stop_server(proc)
        self.assertEqual(code, 200, data)

        self.assertIn("progress", data["derived"])
        self.assertTrue(os.path.exists(os.path.join(vault, "_system", "progress.json")))
        self.assertEqual(read_json(os.path.join(vault, "_system", "state.json"))["schema"], 2)

    def test_compare_legacy_prints_old_levels_and_unlinked_without_modifying_vault(self):
        vault = self.build_schema1_fixture()
        snap_before = snapshot_vault(vault)

        res = self.run_cli("progress", "--vault", vault, "--compare-legacy", "--now", PINNED_NOW)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(snapshot_vault(vault), snap_before)

        out = res.stdout
        self.assertIn("spanish A Core: old 2 -> now 0 (0/1 skills with evidence)", out)
        self.assertIn("spanish B Applied: old 1 -> now 0 (0/1 skills with evidence)", out)
        self.assertIn("rust R1 Ownership: old 1 -> now unlinked", out)
        self.assertIn("rust: not linked to skills yet", out)

    def test_grade_request_for_pre_migration_handled_attempt_is_rejected_and_stays(self):
        vault = self.build_schema1_fixture()
        res = self.run_migrate(vault, now=PINNED_NOW)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        grades_path = os.path.join(vault, "_system", "grades.jsonl")
        grades_before = read_bytes(grades_path)

        req1_path, _ = self.write_request(
            vault,
            "in-1.json",
            make_request(
                "in-1",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
                title="Duplicate grade after migration",
                detail="Should be rejected.",
            ),
        )
        req2_path, _ = self.write_request(
            vault,
            "in-ack.json",
            {"attempt": "in-ack", "grader": make_grader("run-2"), "ack": True},
        )

        rc, report = self.run_ingest(vault)
        self.assertEqual(rc, 1, report)
        self.assertEqual(report["accepted"], [])
        self.assertIn("in-1.json", report["rejected"])
        self.assertTrue(report["rejected"]["in-1.json"])
        self.assertIn("in-ack.json", report["rejected"])
        self.assertTrue(report["rejected"]["in-ack.json"])
        self.assertTrue(os.path.isfile(req1_path))
        self.assertTrue(os.path.isfile(req2_path))
        self.assertEqual(read_bytes(grades_path), grades_before)

    def test_dispute_and_skip_entries_are_never_in_inbox_pending(self):
        extra = [
            make_inbox_entry(
                "disp-1",
                topic="spanish",
                task="sp-01",
                kind="dispute",
                ts="2026-01-16T09:00:00+00:00",
                honor=False,
                fields={},
                ref="g-0000000001",
                note="Disputing question 1.",
            ),
            make_inbox_entry(
                "skip-1",
                topic="spanish",
                task="sp-02",
                kind="skip",
                ts="2026-01-16T09:30:00+00:00",
                honor=False,
                fields={},
                skill="skill-alpha",
                note="Already know alpha.",
            ),
            make_inbox_entry(
                "open-1",
                topic="spanish",
                task="sp-02",
                kind="answers",
                ts="2026-01-16T10:00:00+00:00",
                honor=True,
            ),
        ]
        vault = self.build_schema1_fixture(extra_inbox=extra)

        port1, proc1 = self.start_server(vault)
        code1, data1 = self.http_req(port1, "GET", "/api/state")
        self.stop_server(proc1)
        self.assertEqual(code1, 200, data1)
        pending1 = [entry["id"] for entry in data1["inbox"]["pending"]]
        self.assertNotIn("disp-1", pending1)
        self.assertNotIn("skip-1", pending1)
        self.assertIn("open-1", pending1)

        mig = self.run_migrate(vault, now=PINNED_NOW)
        self.assertEqual(mig.returncode, 0, mig.stdout + mig.stderr)

        port2, proc2 = self.start_server(vault)
        code2, data2 = self.http_req(port2, "GET", "/api/state")
        self.stop_server(proc2)
        self.assertEqual(code2, 200, data2)
        pending2 = [entry["id"] for entry in data2["inbox"]["pending"]]
        self.assertNotIn("disp-1", pending2)
        self.assertNotIn("skip-1", pending2)
        self.assertIn("open-1", pending2)

    def test_two_concurrent_ingest_processes_leave_one_grade_line(self):
        vault = self.build_schema1_fixture(
            extra_inbox=[
                make_inbox_entry(
                    "a-race",
                    topic="spanish",
                    task="sp-01",
                    kind="answers",
                    ts="2026-01-16T10:00:00+00:00",
                    honor=True,
                    fields={"1. Prompt 1": "Alpha", "2. Prompt 2": "Extra"},
                )
            ]
        )
        req_path, _ = self.write_request(
            vault,
            "a-race.json",
            make_request(
                "a-race",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
            ),
        )

        cmd = [sys.executable, CLI, "ingest", "--vault", vault]
        procs = [
            subprocess.Popen(
                cmd,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
            )
            for _ in range(2)
        ]
        results = [(p.communicate(timeout=60), p.returncode) for p in procs]
        for (out, err), rc in results:
            self.assertEqual(rc, 0, f"rc={rc} out={out!r} err={err!r}")

        self.assertFalse(os.path.exists(req_path))
        events = read_jsonl(os.path.join(vault, "_system", "grades.jsonl"))
        grade_events = [e for e in events if e.get("type") == "grade" and e.get("attempt") == "a-race"]
        self.assertEqual(len(grade_events), 1)


if __name__ == "__main__":
    unittest.main()
