import hashlib
import http.client
import json
import os
import re
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
GRADE_ID_RE = re.compile(r"^g-[0-9a-f]{10}$")


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


def make_topic(topic_id, queue, recall=None):
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
        "regions": [
            {"code": "A", "name": "Core", "level": 0, "note": "Not tested."},
            {"code": "B", "name": "Applied", "level": 0, "note": "Not tested."},
        ],
        "history": [
            {
                "date": "2026-01-01",
                "kind": "setup",
                "title": "Created",
                "detail": "Ready",
                "evidence": False,
            }
        ],
    }
    if recall is not None:
        topic["recall"] = recall
    return topic


def make_state(topics):
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
        "processed_inbox": [],
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
    ts="2026-06-01T10:00:00+00:00",
    honor=True,
    fields=None,
    note="",
    ref=None,
    recall=None,
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
    if recall is not None:
        entry["recall"] = recall
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
    follow_up=None,
    regrade_of=None,
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
    if follow_up is not None:
        req["follow_up"] = follow_up
    if regrade_of is not None:
        req["regrade_of"] = regrade_of
    return req


class VaultTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.class_tmp = tempfile.mkdtemp(prefix="edu4self-grading-base-")
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
        self.tmp = tempfile.mkdtemp(prefix="edu4self-grading-")
        self.env = dict(
            os.environ,
            EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg"),
            HOME=self.tmp,
            CLAUDE_CONFIG_DIR=os.path.join(self.tmp, "claude"),
            EDU4SELF_NO_UPDATE_CHECK="1",
        )
        self.env.pop("EDU4SELF_PORT", None)
        self.env.pop("EDU4SELF_VAULT", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

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

    def run_ingest(self, vault):
        res = self.run_cli("ingest", "--vault", vault)
        try:
            payload = json.loads(res.stdout)
        except ValueError:
            self.fail(f"ingest did not print valid JSON (rc={res.returncode}): {res.stdout!r} {res.stderr!r}")
        return res.returncode, payload

    def run_check(self, vault):
        res = self.run_cli("check", "--vault", vault)
        return res.returncode, res.stdout + res.stderr

    def run_progress(self, vault, now="2026-06-01T12:00:00+00:00"):
        res = self.run_cli("progress", "--vault", vault, "--now", now)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return json.loads(res.stdout)

    def build_vault(
        self,
        name="vault",
        inbox=None,
        recall=None,
        with_graph=True,
        with_sp01_key=True,
        with_nokey_task=False,
    ):
        vault = os.path.join(self.tmp, name)
        shutil.copytree(self.base_vault, vault)
        for rel in ("how-learning-works", os.path.join("_system", "keys", "how-learning-works")):
            target = os.path.join(vault, rel)
            if os.path.exists(target):
                shutil.rmtree(target)
        for fn in ("inbox.jsonl", "grades.jsonl"):
            path = os.path.join(vault, "_system", fn)
            if os.path.exists(path):
                os.remove(path)
        grading_dir = os.path.join(vault, "_system", "grading")
        if os.path.exists(grading_dir):
            shutil.rmtree(grading_dir)

        topic_id = "spanish"
        queue = [
            make_task(topic_id, "sp-01", num_fields=2),
            make_task(topic_id, "sp-02", num_fields=1),
        ]
        if with_nokey_task:
            queue.append(make_task(topic_id, "sp-nokey", num_fields=1))
        state = make_state([make_topic(topic_id, queue, recall=recall)])
        write_json(os.path.join(vault, "_system", "state.json"), state)
        if with_graph:
            write_json(os.path.join(vault, topic_id, "graph.json"), make_graph(topic_id))
        write_task_page(vault, topic_id, "sp-01")
        write_task_page(vault, topic_id, "sp-02")
        if with_nokey_task:
            write_task_page(vault, topic_id, "sp-nokey")
        if with_sp01_key:
            write_text(
                os.path.join(vault, "_system", "keys", topic_id, "sp-01.md"),
                make_key("sp-01", [("skill-alpha", ["1a", "1b"]), ("none", ["2a"])]),
            )
        write_text(
            os.path.join(vault, "_system", "keys", topic_id, "sp-02.md"),
            make_key("sp-02", [("skill-beta", ["1a"])]),
        )
        if inbox is not None:
            write_jsonl(os.path.join(vault, "_system", "inbox.jsonl"), inbox)
        return vault

    def write_request(self, vault, filename, data, age_seconds=None):
        path = os.path.join(vault, "_system", "grading", filename)
        raw = data.encode("utf-8") if isinstance(data, str) else json.dumps(data).encode("utf-8")
        write_bytes(path, raw)
        if age_seconds is not None:
            ts = time.time() - age_seconds
            os.utime(path, (ts, ts))
        return path, raw


class GradingCliTest(VaultTestBase):
    def test_all_points_true_and_no_errors_is_met_and_passed(self):
        attempt = make_inbox_entry("a1", task="sp-01", ts="2026-06-01T10:00:00+00:00", honor=True)
        vault = self.build_vault(inbox=[attempt])
        req = make_request(
            "a1",
            questions=[
                {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                {"n": 2, "points": {"2a": True}, "errors": []},
            ],
            title="All clear",
            detail="Both answers cover every point.",
            record="learning-records/0001.md",
        )
        req_path, raw = self.write_request(vault, "a1.json", req)

        rc, report = self.run_ingest(vault)
        self.assertEqual(rc, 0, report)
        self.assertEqual(report, {"accepted": ["a1.json"], "rejected": {}, "waiting": []})
        self.assertFalse(os.path.exists(req_path))

        grades_path = os.path.join(vault, "_system", "grades.jsonl")
        self.assertTrue(os.path.isfile(grades_path))
        grades_raw = read_bytes(grades_path)
        self.assertTrue(grades_raw.endswith(b"\n"))
        events = read_jsonl(grades_path)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["type"], "grade")
        self.assertRegex(ev["id"], GRADE_ID_RE)
        self.assertTrue(ev["ts"])
        self.assertEqual(ev["request"], "a1.json")
        self.assertEqual(ev["request_sha"], hashlib.sha1(raw).hexdigest())
        self.assertEqual(ev["attempt"], "a1")
        self.assertEqual(ev["answered"], "2026-06-01T10:00:00+00:00")
        self.assertEqual(ev["topic"], "spanish")
        self.assertEqual(ev["task"], "sp-01")
        self.assertEqual(ev["kind"], "answers")
        self.assertIs(ev["honor"], True)
        self.assertEqual(ev["grader"], make_grader("run-1"))
        self.assertEqual(ev["title"], "All clear")
        self.assertEqual(ev["detail"], "Both answers cover every point.")
        self.assertEqual(ev["record"], "learning-records/0001.md")
        self.assertIs(ev["passed"], True)
        self.assertEqual(
            ev["questions"],
            [
                {
                    "q": "sp-01#1",
                    "skill": "skill-alpha",
                    "points": {"1a": True, "1b": True},
                    "errors": [],
                    "outcome": "met",
                },
                {
                    "q": "sp-01#2",
                    "skill": None,
                    "points": {"2a": True},
                    "errors": [],
                    "outcome": "met",
                },
            ],
        )

        prog = self.run_progress(vault)
        self.assertEqual(prog["topics"]["spanish"]["skills"]["skill-alpha"]["level"], 2)
        self.assertIs(prog["topics"]["spanish"]["tasks"]["sp-01"]["passed"], True)

        rc2, report2 = self.run_ingest(vault)
        self.assertEqual(rc2, 0, report2)
        self.assertEqual(report2, {"accepted": [], "rejected": {}, "waiting": []})
        self.assertEqual(read_bytes(grades_path), grades_raw)

    def test_false_point_or_error_is_missed_and_not_passed(self):
        cases = [
            (
                "false-point",
                [
                    {"n": 1, "points": {"1a": True, "1b": False}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
                ["missed", "met"],
            ),
            (
                "has-error",
                [
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": ["reverses cause"]},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
                ["missed", "met"],
            ),
        ]
        for label, questions, expected_outcomes in cases:
            with self.subTest(case=label):
                vault = self.build_vault(name=f"v-{label}", inbox=[make_inbox_entry("a1", task="sp-01")])
                self.write_request(vault, "a1.json", make_request("a1", questions=questions))
                rc, report = self.run_ingest(vault)
                self.assertEqual(rc, 0, report)
                self.assertEqual(report["accepted"], ["a1.json"])
                ev = read_jsonl(os.path.join(vault, "_system", "grades.jsonl"))[0]
                self.assertIs(ev["passed"], False)
                self.assertEqual([q["outcome"] for q in ev["questions"]], expected_outcomes)

    def test_unsure_question_makes_passed_false_and_gives_no_evidence(self):
        vault = self.build_vault(inbox=[make_inbox_entry("a1", task="sp-01")])
        req = make_request(
            "a1",
            questions=[
                {"n": 1, "points": {"1a": True, "1b": True}, "errors": [], "unsure": True},
                {"n": 2, "points": {"2a": True}, "errors": []},
            ],
            follow_up={"n": 1, "point": "1a", "q": "Can you explain why 1a holds?"},
        )
        self.write_request(vault, "a1.json", req)

        rc, report = self.run_ingest(vault)
        self.assertEqual(rc, 0, report)
        ev = read_jsonl(os.path.join(vault, "_system", "grades.jsonl"))[0]
        self.assertIs(ev["passed"], False)
        self.assertEqual(ev["questions"][0]["outcome"], "unsure")
        self.assertEqual(ev["questions"][1]["outcome"], "met")
        self.assertEqual(
            ev["follow_up"],
            {"q": "sp-01#1", "point": "1a", "text": "Can you explain why 1a holds?"},
        )

        prog = self.run_progress(vault)
        alpha = prog["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 0)
        self.assertEqual(alpha["met"], 0)
        self.assertEqual(alpha["missed"], 0)

    def test_rejects_unknown_withdrawn_and_already_graded_attempts(self):
        inbox = [
            make_inbox_entry("a-withdrawn", task="sp-01"),
            make_inbox_entry("w1", task="sp-01", kind="withdraw", ref="a-withdrawn"),
            make_inbox_entry("a-done", task="sp-01"),
        ]
        vault = self.build_vault(inbox=inbox)
        good_q = [
            {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
            {"n": 2, "points": {"2a": True}, "errors": []},
        ]
        self.write_request(vault, "a-done.json", make_request("a-done", questions=good_q))
        rc0, _ = self.run_ingest(vault)
        self.assertEqual(rc0, 0)

        self.write_request(vault, "a-unknown.json", make_request("a-unknown", questions=good_q))
        self.write_request(vault, "a-withdrawn.json", make_request("a-withdrawn", questions=good_q))
        self.write_request(
            vault,
            "a-done.json",
            make_request("a-done", questions=good_q, title="Second grade without regrade_of"),
        )

        grades_before = read_bytes(os.path.join(vault, "_system", "grades.jsonl"))
        check_rc, check_out = self.run_check(vault)
        self.assertEqual(check_rc, 1, check_out)
        for fn in ("a-unknown.json", "a-withdrawn.json", "a-done.json"):
            self.assertIn(f"grading: {fn}:", check_out)
            self.assertTrue(os.path.isfile(os.path.join(vault, "_system", "grading", fn)))
        self.assertEqual(read_bytes(os.path.join(vault, "_system", "grades.jsonl")), grades_before)

        ingest_rc, report = self.run_ingest(vault)
        self.assertEqual(ingest_rc, 1, report)
        self.assertEqual(report["accepted"], [])
        for fn in ("a-unknown.json", "a-withdrawn.json", "a-done.json"):
            self.assertIn(fn, report["rejected"])
            self.assertTrue(report["rejected"][fn])
            self.assertTrue(os.path.isfile(os.path.join(vault, "_system", "grading", fn)))
        self.assertEqual(read_bytes(os.path.join(vault, "_system", "grades.jsonl")), grades_before)

    def test_rejects_bad_points_missing_section_forbidden_fields_and_missing_key(self):
        valid_q = [
            {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
            {"n": 2, "points": {"2a": True}, "errors": []},
        ]
        cases = [
            (
                "wrong-point-id",
                make_request(
                    "a1",
                    questions=[
                        {"n": 1, "points": {"1a": True, "1z": True}, "errors": []},
                        {"n": 2, "points": {"2a": True}, "errors": []},
                    ],
                ),
            ),
            (
                "missing-point-id",
                make_request(
                    "a1",
                    questions=[
                        {"n": 1, "points": {"1a": True}, "errors": []},
                        {"n": 2, "points": {"2a": True}, "errors": []},
                    ],
                ),
            ),
            (
                "missing-section",
                make_request(
                    "a1",
                    questions=[{"n": 1, "points": {"1a": True, "1b": True}, "errors": []}],
                ),
            ),
            (
                "forbidden-passed",
                dict(make_request("a1", questions=valid_q), passed=True),
            ),
            (
                "forbidden-outcome",
                make_request(
                    "a1",
                    questions=[
                        {"n": 1, "points": {"1a": True, "1b": True}, "errors": [], "outcome": "met"},
                        {"n": 2, "points": {"2a": True}, "errors": []},
                    ],
                ),
            ),
            (
                "forbidden-skill",
                make_request(
                    "a1",
                    questions=[
                        {"n": 1, "points": {"1a": True, "1b": True}, "errors": [], "skill": "skill-alpha"},
                        {"n": 2, "points": {"2a": True}, "errors": []},
                    ],
                ),
            ),
        ]
        for label, payload in cases:
            with self.subTest(case=label):
                vault = self.build_vault(name=f"v-{label}", inbox=[make_inbox_entry("a1", task="sp-01")])
                req_path, _ = self.write_request(vault, "a1.json", payload)
                check_rc, check_out = self.run_check(vault)
                self.assertEqual(check_rc, 1, check_out)
                self.assertIn("grading: a1.json:", check_out)
                ingest_rc, report = self.run_ingest(vault)
                self.assertEqual(ingest_rc, 1, report)
                self.assertIn("a1.json", report["rejected"])
                self.assertTrue(os.path.isfile(req_path))
                self.assertFalse(os.path.exists(os.path.join(vault, "_system", "grades.jsonl")))

        vault_nokey = self.build_vault(
            name="v-nokey",
            inbox=[make_inbox_entry("a-nk", task="sp-nokey")],
            with_nokey_task=True,
        )
        req_path, _ = self.write_request(
            vault_nokey,
            "a-nk.json",
            make_request("a-nk", questions=[{"n": 1, "points": {"1a": True}, "errors": []}]),
        )
        ingest_rc, report = self.run_ingest(vault_nokey)
        self.assertEqual(ingest_rc, 1, report)
        self.assertIn("a-nk.json", report["rejected"])
        self.assertTrue(os.path.isfile(req_path))

        vault_nograph = self.build_vault(
            name="v-nograph",
            inbox=[make_inbox_entry("a1", task="sp-01")],
            with_graph=False,
        )
        req_path2, _ = self.write_request(vault_nograph, "a1.json", make_request("a1", questions=valid_q))
        ingest_rc2, report2 = self.run_ingest(vault_nograph)
        self.assertEqual(ingest_rc2, 1, report2)
        self.assertIn("a1.json", report2["rejected"])
        self.assertTrue(os.path.isfile(req_path2))

    def test_filename_rules_invalid_json_and_waiting_for_fresh_partial_file(self):
        vault = self.build_vault(inbox=[make_inbox_entry("a1", task="sp-01")])
        valid_q = [
            {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
            {"n": 2, "points": {"2a": True}, "errors": []},
        ]
        self.write_request(vault, "wrong-name.json", make_request("a1", questions=valid_q))
        self.write_request(vault, "a1.regrade.json", make_request("a1", questions=valid_q))
        self.write_request(vault, "broken-old.json", "{not valid json", age_seconds=30)

        rc, report = self.run_ingest(vault)
        self.assertEqual(rc, 1, report)
        for fn in ("wrong-name.json", "a1.regrade.json", "broken-old.json"):
            self.assertIn(fn, report["rejected"])
            self.assertTrue(os.path.isfile(os.path.join(vault, "_system", "grading", fn)))

        vault_wait = self.build_vault(name="v-wait", inbox=[make_inbox_entry("a1", task="sp-01")])
        fresh_path, _ = self.write_request(vault_wait, "a1.json", '{"attempt": "a1"')
        rc_wait, rep_wait = self.run_ingest(vault_wait)
        self.assertEqual(rc_wait, 0, rep_wait)
        self.assertEqual(rep_wait, {"accepted": [], "rejected": {}, "waiting": ["a1.json"]})
        self.assertTrue(os.path.isfile(fresh_path))
        self.assertFalse(os.path.exists(os.path.join(vault_wait, "_system", "grades.jsonl")))

    def test_copying_accepted_request_back_adds_no_line_and_removes_copy(self):
        vault = self.build_vault(inbox=[make_inbox_entry("a1", task="sp-01")])
        req = make_request(
            "a1",
            questions=[
                {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                {"n": 2, "points": {"2a": True}, "errors": []},
            ],
        )
        req_path, raw = self.write_request(vault, "a1.json", req)
        rc1, rep1 = self.run_ingest(vault)
        self.assertEqual(rc1, 0, rep1)
        self.assertEqual(rep1["accepted"], ["a1.json"])

        grades_path = os.path.join(vault, "_system", "grades.jsonl")
        grades_before = read_bytes(grades_path)

        write_bytes(req_path, raw)
        rc2, rep2 = self.run_ingest(vault)
        self.assertEqual(rc2, 0, rep2)
        self.assertFalse(os.path.exists(req_path))
        self.assertEqual(read_bytes(grades_path), grades_before)
        self.assertEqual(len(read_jsonl(grades_path)), 1)

    def test_regrade_requires_open_dispute_and_new_session_and_progress_counts_regrade(self):
        inbox = [make_inbox_entry("a1", task="sp-01", ts="2026-06-01T10:00:00+00:00", honor=True)]
        vault = self.build_vault(inbox=inbox)
        missed_q = [
            {"n": 1, "points": {"1a": True, "1b": False}, "errors": []},
            {"n": 2, "points": {"2a": True}, "errors": []},
        ]
        met_q = [
            {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
            {"n": 2, "points": {"2a": True}, "errors": []},
        ]
        self.write_request(vault, "a1.json", make_request("a1", questions=missed_q, session="run-1"))
        rc0, _ = self.run_ingest(vault)
        self.assertEqual(rc0, 0)
        grades_path = os.path.join(vault, "_system", "grades.jsonl")
        g1 = read_jsonl(grades_path)[0]["id"]

        self.write_request(
            vault,
            "a1.regrade.json",
            make_request("a1", questions=met_q, session="run-2", regrade_of=g1),
        )
        rc_nodisp, rep_nodisp = self.run_ingest(vault)
        self.assertEqual(rc_nodisp, 1, rep_nodisp)
        self.assertIn("a1.regrade.json", rep_nodisp["rejected"])

        inbox.append(
            {
                "id": "d1",
                "ts": "2026-06-01T10:30:00+00:00",
                "topic": "spanish",
                "task": "sp-01",
                "kind": "dispute",
                "ref": g1,
                "note": "Point 1b was in my second sentence.",
                "fields": {},
                "title": "",
                "honor": False,
            }
        )
        write_jsonl(os.path.join(vault, "_system", "inbox.jsonl"), inbox)

        self.write_request(
            vault,
            "a1.regrade.json",
            make_request("a1", questions=met_q, session="run-1", regrade_of=g1),
        )
        rc_samesess, rep_samesess = self.run_ingest(vault)
        self.assertEqual(rc_samesess, 1, rep_samesess)
        self.assertIn("a1.regrade.json", rep_samesess["rejected"])

        self.write_request(
            vault,
            "a1.regrade.json",
            make_request("a1", questions=met_q, session="run-2", regrade_of=g1),
        )
        rc_ok, rep_ok = self.run_ingest(vault)
        self.assertEqual(rc_ok, 0, rep_ok)
        self.assertEqual(rep_ok["accepted"], ["a1.regrade.json"])
        self.assertFalse(os.path.exists(os.path.join(vault, "_system", "grading", "a1.regrade.json")))

        events = read_jsonl(grades_path)
        self.assertEqual(len(events), 2)
        g2 = events[1]
        self.assertEqual(g2["regrade_of"], g1)
        self.assertIs(g2["passed"], True)

        prog = self.run_progress(vault)
        alpha = prog["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 2)
        self.assertEqual(alpha["met"], 1)
        self.assertEqual(alpha["missed"], 0)
        self.assertIs(prog["topics"]["spanish"]["tasks"]["sp-01"]["passed"], True)
        self.assertEqual(prog["topics"]["spanish"]["tasks"]["sp-01"]["grade"], g2["id"])

        self.write_request(
            vault,
            "a1.regrade.json",
            make_request("a1", questions=missed_q, session="run-3", regrade_of=g1),
        )
        rc_again, rep_again = self.run_ingest(vault)
        self.assertEqual(rc_again, 1, rep_again)
        self.assertIn("a1.regrade.json", rep_again["rejected"])

    def test_follow_up_reply_pass_requires_original_other_questions_met(self):
        inbox_pass = [
            make_inbox_entry("a1", task="sp-01", ts="2026-06-01T10:00:00+00:00"),
            make_inbox_entry(
                "f1",
                task="sp-01",
                kind="follow-up",
                ref="a1",
                ts="2026-06-01T10:30:00+00:00",
                fields={"Explain 2a": "Clear explanation"},
            ),
        ]
        vault_pass = self.build_vault(name="v-fu-pass", inbox=inbox_pass)
        self.write_request(
            vault_pass,
            "a1.json",
            make_request(
                "a1",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": [], "unsure": True},
                ],
                follow_up={"n": 2, "point": "2a", "q": "Explain 2a"},
            ),
        )
        rc0, _ = self.run_ingest(vault_pass)
        self.assertEqual(rc0, 0)
        orig_id = read_jsonl(os.path.join(vault_pass, "_system", "grades.jsonl"))[0]["id"]

        self.write_request(
            vault_pass,
            "f1.json",
            make_request(
                "f1",
                questions=[{"n": 2, "points": {"2a": True}, "errors": []}],
            ),
        )
        rc1, rep1 = self.run_ingest(vault_pass)
        self.assertEqual(rc1, 0, rep1)
        fu_ev = read_jsonl(os.path.join(vault_pass, "_system", "grades.jsonl"))[1]
        self.assertEqual(fu_ev["follows"], orig_id)
        self.assertEqual(fu_ev["questions"][0]["outcome"], "met")
        self.assertIs(fu_ev["passed"], True)

        inbox_fail = [
            make_inbox_entry("a2", task="sp-01", ts="2026-06-01T10:00:00+00:00"),
            make_inbox_entry(
                "f2",
                task="sp-01",
                kind="follow-up",
                ref="a2",
                ts="2026-06-01T10:30:00+00:00",
                fields={"Explain 2a": "Clear explanation"},
            ),
        ]
        vault_fail = self.build_vault(name="v-fu-fail", inbox=inbox_fail)
        self.write_request(
            vault_fail,
            "a2.json",
            make_request(
                "a2",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": False}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": [], "unsure": True},
                ],
                follow_up={"n": 2, "point": "2a", "q": "Explain 2a"},
            ),
        )
        rc2, _ = self.run_ingest(vault_fail)
        self.assertEqual(rc2, 0)
        orig_id2 = read_jsonl(os.path.join(vault_fail, "_system", "grades.jsonl"))[0]["id"]

        self.write_request(
            vault_fail,
            "f2.json",
            make_request(
                "f2",
                questions=[{"n": 2, "points": {"2a": True}, "errors": []}],
            ),
        )
        rc3, rep3 = self.run_ingest(vault_fail)
        self.assertEqual(rc3, 0, rep3)
        fu_ev2 = read_jsonl(os.path.join(vault_fail, "_system", "grades.jsonl"))[1]
        self.assertEqual(fu_ev2["follows"], orig_id2)
        self.assertEqual(fu_ev2["questions"][0]["outcome"], "met")
        self.assertIs(fu_ev2["passed"], False)

        vault_chain = self.build_vault(name="v-fu-chain", inbox=inbox_pass)
        self.write_request(
            vault_chain,
            "a1.json",
            make_request(
                "a1",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": [], "unsure": True},
                ],
                follow_up={"n": 2, "point": "2a", "q": "Explain 2a"},
            ),
        )
        self.assertEqual(self.run_ingest(vault_chain)[0], 0)
        self.write_request(
            vault_chain,
            "f1.json",
            make_request(
                "f1",
                questions=[{"n": 2, "points": {"2a": True}, "errors": [], "unsure": True}],
                follow_up={"n": 2, "point": "2a", "q": "One more question?"},
            ),
        )
        rc_chain, rep_chain = self.run_ingest(vault_chain)
        self.assertEqual(rc_chain, 1, rep_chain)
        self.assertIn("f1.json", rep_chain["rejected"])

    def test_recall_attempt_graded_per_recall_question(self):
        recall = [
            {"id": "r1", "q": "Recall alpha.", "from": "sp-01", "key": "sp-01#1"},
            {"id": "r2", "q": "Recall beta.", "from": "sp-02", "key": "sp-02#1"},
        ]
        inbox = [
            make_inbox_entry(
                "rec1",
                task="recall",
                kind="recall",
                ts="2026-06-01T10:00:00+00:00",
                honor=True,
                recall=["r1", "r2"],
                fields={"Recall alpha.": "Both points", "Recall beta.": "Forgot"},
            )
        ]
        vault = self.build_vault(inbox=inbox, recall=recall)
        self.write_request(
            vault,
            "rec1.json",
            make_request(
                "rec1",
                questions=[
                    {"recall": "r1", "points": {"1a": True, "1b": True}, "errors": []},
                    {"recall": "r2", "points": {"1a": False}, "errors": []},
                ],
            ),
        )
        rc, report = self.run_ingest(vault)
        self.assertEqual(rc, 0, report)
        ev = read_jsonl(os.path.join(vault, "_system", "grades.jsonl"))[0]
        self.assertEqual(ev["kind"], "recall")
        self.assertIs(ev["passed"], False)
        self.assertEqual(
            ev["questions"],
            [
                {
                    "q": "sp-01#1",
                    "recall": "r1",
                    "skill": "skill-alpha",
                    "points": {"1a": True, "1b": True},
                    "errors": [],
                    "outcome": "met",
                },
                {
                    "q": "sp-02#1",
                    "recall": "r2",
                    "skill": "skill-beta",
                    "points": {"1a": False},
                    "errors": [],
                    "outcome": "missed",
                },
            ],
        )

    def test_note_and_first_try_get_ack_and_non_gradable_kinds_rejected(self):
        inbox = [
            make_inbox_entry("n1", task="note", kind="note", fields={}, note="Quick question"),
            make_inbox_entry("ft1", task="first-try", kind="answers", fields={"Why?": "Recall"}),
            make_inbox_entry("a1", task="sp-01", kind="answers"),
            make_inbox_entry("s1", task="sp-02", kind="skip", fields={}, note="Know it"),
        ]
        vault = self.build_vault(inbox=inbox)
        ack_n1 = {"attempt": "n1", "grader": make_grader("run-1"), "ack": True}
        ack_ft1 = {"attempt": "ft1", "grader": make_grader("run-1"), "ack": True}
        _, raw_n1 = self.write_request(vault, "n1.json", ack_n1)
        _, raw_ft1 = self.write_request(vault, "ft1.json", ack_ft1)

        rc, report = self.run_ingest(vault)
        self.assertEqual(rc, 0, report)
        self.assertEqual(sorted(report["accepted"]), ["ft1.json", "n1.json"])

        events = read_jsonl(os.path.join(vault, "_system", "grades.jsonl"))
        by_attempt = {ev["attempt"]: ev for ev in events}
        self.assertEqual(set(by_attempt), {"n1", "ft1"})
        for att, raw in (("n1", raw_n1), ("ft1", raw_ft1)):
            ev = by_attempt[att]
            self.assertEqual(ev["type"], "ack")
            self.assertTrue(isinstance(ev["id"], str) and ev["id"])
            self.assertTrue(ev["ts"])
            self.assertEqual(ev["request"], f"{att}.json")
            self.assertEqual(ev["request_sha"], hashlib.sha1(raw).hexdigest())
            self.assertEqual(ev["grader"], make_grader("run-1"))

        self.write_request(vault, "a1.json", {"attempt": "a1", "grader": make_grader("run-2"), "ack": True})
        self.write_request(vault, "s1.json", {"attempt": "s1", "grader": make_grader("run-2"), "ack": True})
        rc_bad, rep_bad = self.run_ingest(vault)
        self.assertEqual(rc_bad, 1, rep_bad)
        self.assertIn("a1.json", rep_bad["rejected"])
        self.assertIn("s1.json", rep_bad["rejected"])

    def test_check_without_grading_folder_passes_and_check_is_read_only(self):
        vault = self.build_vault(inbox=[make_inbox_entry("a1", task="sp-01")])
        self.assertFalse(os.path.exists(os.path.join(vault, "_system", "grading")))
        rc, out = self.run_check(vault)
        self.assertEqual(rc, 0, out)

        req_path, _ = self.write_request(
            vault,
            "a1.json",
            make_request(
                "a1",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
            ),
        )
        rc2, out2 = self.run_check(vault)
        self.assertEqual(rc2, 0, out2)
        self.assertTrue(os.path.isfile(req_path))
        self.assertFalse(os.path.exists(os.path.join(vault, "_system", "grades.jsonl")))

        bad_path, _ = self.write_request(vault, "bad.json", make_request("no-such-attempt", questions=[]))
        rc3, out3 = self.run_check(vault)
        self.assertEqual(rc3, 1, out3)
        self.assertIn("grading: bad.json:", out3)
        self.assertTrue(os.path.isfile(req_path))
        self.assertTrue(os.path.isfile(bad_path))
        self.assertFalse(os.path.exists(os.path.join(vault, "_system", "grades.jsonl")))


class GradingServerTest(VaultTestBase):
    def setUp(self):
        super().setUp()
        self.servers = []

    def tearDown(self):
        for proc in self.servers:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        super().tearDown()

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
                    return port
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

    def test_vault_without_grading_folder_serves_and_checks_as_before(self):
        vault = self.build_vault()
        self.assertFalse(os.path.exists(os.path.join(vault, "_system", "grading")))
        rc, out = self.run_check(vault)
        self.assertEqual(rc, 0, out)

        port = self.start_server(vault)
        code, data = self.http_req(port, "GET", "/api/state")
        self.assertEqual(code, 200, data)
        self.assertIn("state", data)
        self.assertIn("grading", data)
        self.assertEqual(data["grading"], {"rejected": {}, "waiting": []})

    def test_get_state_ingests_once_and_second_get_changes_nothing(self):
        vault = self.build_vault(inbox=[make_inbox_entry("a1", task="sp-01")])
        req_path, _ = self.write_request(
            vault,
            "a1.json",
            make_request(
                "a1",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": True}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
            ),
        )
        bad_path, _ = self.write_request(
            vault,
            "bad.json",
            make_request("unknown-attempt", questions=[]),
            age_seconds=30,
        )

        port = self.start_server(vault)
        code1, data1 = self.http_req(port, "GET", "/api/state")
        self.assertEqual(code1, 200, data1)
        self.assertFalse(os.path.exists(req_path))
        self.assertTrue(os.path.isfile(bad_path))
        self.assertIn("bad.json", data1["grading"]["rejected"])

        grades_path = os.path.join(vault, "_system", "grades.jsonl")
        self.assertTrue(os.path.isfile(grades_path))
        grades_after_first = read_bytes(grades_path)
        self.assertEqual(len([e for e in read_jsonl(grades_path)
                              if e.get("type") == "grade" and e.get("attempt") == "a1"]), 1)

        code2, data2 = self.http_req(port, "GET", "/api/state")
        self.assertEqual(code2, 200, data2)
        self.assertEqual(read_bytes(grades_path), grades_after_first)
        self.assertIn("bad.json", data2["grading"]["rejected"])

    def test_inbox_dispute_validation_storage_and_keeps_grade_until_regrade(self):
        vault = self.build_vault(inbox=[make_inbox_entry("a1", task="sp-01", honor=True)])
        self.write_request(
            vault,
            "a1.json",
            make_request(
                "a1",
                questions=[
                    {"n": 1, "points": {"1a": True, "1b": False}, "errors": []},
                    {"n": 2, "points": {"2a": True}, "errors": []},
                ],
                session="run-1",
            ),
        )
        self.assertEqual(self.run_ingest(vault)[0], 0)
        g1 = read_jsonl(os.path.join(vault, "_system", "grades.jsonl"))[0]["id"]

        port = self.start_server(vault)

        for bad in (
            {"kind": "dispute", "topic": "spanish", "task": "sp-01", "ref": "g-0000000000", "note": ""},
            {"kind": "dispute", "topic": "spanish", "task": "sp-02", "ref": g1, "note": ""},
        ):
            code, err = self.http_req(port, "POST", "/api/inbox", bad)
            self.assertEqual(code, 400, (bad, err))
            self.assertTrue(err.get("error"))

        code_ok, created = self.http_req(
            port,
            "POST",
            "/api/inbox",
            {"kind": "dispute", "topic": "spanish", "task": "sp-01", "ref": g1, "note": ""},
        )
        self.assertEqual(code_ok, 201, created)

        saved = [
            e
            for e in read_jsonl(os.path.join(vault, "_system", "inbox.jsonl"))
            if e.get("kind") == "dispute"
        ]
        self.assertEqual(len(saved), 1)
        disp = saved[0]
        self.assertEqual(
            set(disp),
            {"id", "ts", "topic", "task", "kind", "ref", "note", "fields", "title", "honor"},
        )
        self.assertEqual(disp["topic"], "spanish")
        self.assertEqual(disp["task"], "sp-01")
        self.assertEqual(disp["ref"], g1)
        self.assertEqual(disp["note"], "")
        self.assertEqual(disp["fields"], {})
        self.assertEqual(disp["title"], "")
        self.assertIs(disp["honor"], False)

        code_dup, err_dup = self.http_req(
            port,
            "POST",
            "/api/inbox",
            {"kind": "dispute", "topic": "spanish", "task": "sp-01", "ref": g1, "note": "Again"},
        )
        self.assertEqual(code_dup, 400, err_dup)
        self.assertTrue(err_dup.get("error"))

        prog = self.run_progress(vault)
        alpha = prog["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 1)
        self.assertEqual(alpha["missed"], 1)

    def test_inbox_skip_validation_and_makes_task_ready(self):
        vault = self.build_vault()
        port = self.start_server(vault)

        for bad_skill in ("skill-beta", "skill-retired", "no-such-skill"):
            code, err = self.http_req(
                port,
                "POST",
                "/api/inbox",
                {
                    "kind": "skip",
                    "topic": "spanish",
                    "task": "sp-02",
                    "skill": bad_skill,
                    "note": "Skip attempt",
                },
            )
            self.assertEqual(code, 400, (bad_skill, err))
            self.assertTrue(err.get("error"))

        code_ok, created = self.http_req(
            port,
            "POST",
            "/api/inbox",
            {
                "kind": "skip",
                "topic": "spanish",
                "task": "sp-02",
                "skill": "skill-alpha",
                "note": "Already know alpha.",
            },
        )
        self.assertEqual(code_ok, 201, created)

        saved = [
            e
            for e in read_jsonl(os.path.join(vault, "_system", "inbox.jsonl"))
            if e.get("kind") == "skip"
        ]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["skill"], "skill-alpha")
        self.assertEqual(saved[0]["topic"], "spanish")

        code_dup, err_dup = self.http_req(
            port,
            "POST",
            "/api/inbox",
            {
                "kind": "skip",
                "topic": "spanish",
                "task": "sp-02",
                "skill": "skill-alpha",
                "note": "Second skip",
            },
        )
        self.assertEqual(code_dup, 400, err_dup)
        self.assertTrue(err_dup.get("error"))

        prog = self.run_progress(vault)
        self.assertIs(prog["topics"]["spanish"]["tasks"]["sp-02"]["ready"], True)
        self.assertEqual(prog["topics"]["spanish"]["tasks"]["sp-02"]["needs"], [])
        self.assertEqual(prog["topics"]["spanish"]["skills"]["skill-alpha"]["level"], 0)
        self.assertIs(prog["topics"]["spanish"]["skills"]["skill-alpha"]["skipped"], True)


if __name__ == "__main__":
    unittest.main()
