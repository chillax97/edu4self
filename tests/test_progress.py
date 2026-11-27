import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
CLI = os.path.join(ENGINE, "edu4self")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


def write_jsonl(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    for entry in entries:
        if isinstance(entry, str):
            lines.append(entry)
        else:
            lines.append(json.dumps(entry))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))


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


def make_key(task_id, sections):
    parts = [f"# Answer key: {task_id}\n"]
    for idx, skill in enumerate(sections, start=1):
        parts.append(
            f"\n## {idx}. Question {idx}\n\n"
            f"Skill: {skill}\n\n"
            f"Required:\n"
            f"- {idx}a. Core point {idx}.\n"
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


def make_topic(topic_id, queue, regions=None):
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
        "regions": regions
        or [
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


def make_graph(topic_id, regions, skills):
    return {
        "schema": 1,
        "topic": topic_id,
        "version": 1,
        "regions": regions,
        "skills": skills,
        "changes": [{"version": 1, "date": "2026-06-01", "why": "Initial."}],
    }


def make_skill(skill_id, region, requires=None, retired=False):
    entry = {
        "id": skill_id,
        "name": f"Skill {skill_id}",
        "region": region,
        "can": f"Demonstrate {skill_id}.",
        "requires": list(requires or []),
    }
    if retired:
        entry["retired"] = True
    return entry


def make_grade(
    grade_id,
    attempt,
    answered,
    topic,
    task,
    questions,
    passed=True,
    ts=None,
    kind="answers",
    honor=True,
):
    return {
        "type": "grade",
        "id": grade_id,
        "ts": ts or answered,
        "attempt": attempt,
        "answered": answered,
        "topic": topic,
        "task": task,
        "kind": kind,
        "honor": honor,
        "passed": passed,
        "questions": questions,
    }


class ProgressCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.class_tmp = tempfile.mkdtemp(prefix="edu4self-progress-base-")
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
        self.tmp = tempfile.mkdtemp(prefix="edu4self-progress-")
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

    def run_progress(self, vault, now="2026-06-01T12:00:00+00:00", topic=None):
        args = ["progress", "--vault", vault]
        if topic is not None:
            args.extend(["--topic", topic])
        if now is not None:
            args.extend(["--now", now])
        res = self.run_cli(*args)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return json.loads(res.stdout)

    def new_vault(self, name="vault"):
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
        return vault

    def build_standard_vault(self, grades=None, inbox=None, name="vault"):
        vault = self.new_vault(name=name)
        topic_id = "spanish"
        queue = [
            make_task(topic_id, "sp-01", num_fields=1),
            make_task(topic_id, "sp-02", num_fields=1),
            make_task(topic_id, "sp-locked", kind="checkpoint", locked=True),
        ]
        state = make_state([make_topic(topic_id, queue)])
        write_json(os.path.join(vault, "_system", "state.json"), state)
        graph = make_graph(
            topic_id,
            regions=[
                {"code": "A", "name": "Core"},
                {"code": "B", "name": "Applied"},
            ],
            skills=[
                make_skill("skill-alpha", "A"),
                make_skill("skill-beta", "B", requires=["skill-alpha"]),
                make_skill("skill-retired", "A", retired=True),
            ],
        )
        write_json(os.path.join(vault, topic_id, "graph.json"), graph)
        write_task_page(vault, topic_id, "sp-01")
        write_task_page(vault, topic_id, "sp-02")
        write_text(
            os.path.join(vault, "_system", "keys", topic_id, "sp-01.md"),
            make_key("sp-01", ["skill-alpha"]),
        )
        write_text(
            os.path.join(vault, "_system", "keys", topic_id, "sp-02.md"),
            make_key("sp-02", ["skill-beta"]),
        )
        if grades is not None:
            write_jsonl(os.path.join(vault, "_system", "grades.jsonl"), grades)
        if inbox is not None:
            write_jsonl(os.path.join(vault, "_system", "inbox.jsonl"), inbox)
        return vault

    def test_level_zero_with_no_answers_and_top_level_schema(self):
        vault = self.build_standard_vault()
        now = "2026-06-01T12:00:00+00:00"
        data = self.run_progress(vault, now=now)

        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["computed"], now)
        self.assertEqual(
            data["model"],
            {"name": "memory-v1", "bar": 0.8, "learned_bar": 0.5},
        )
        self.assertEqual(data["recall_due"], [])
        self.assertEqual(data["unlinked"], [])

        topic = data["topics"]["spanish"]
        self.assertIn("skill-alpha", topic["skills"])
        self.assertIn("skill-beta", topic["skills"])
        self.assertNotIn("skill-retired", topic["skills"])

        alpha = topic["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 0)
        self.assertEqual(alpha["estimate"], 0.0)
        self.assertEqual(alpha["met"], 0)
        self.assertEqual(alpha["missed"], 0)
        self.assertIsNone(alpha["first_met"])
        self.assertIsNone(alpha["last_met"])
        self.assertIsNone(alpha["due"])
        self.assertIs(alpha["skipped"], False)

        self.assertEqual(topic["regions"]["A"], {"name": "Core", "level": 0, "skills": 1, "started": 0})
        self.assertEqual(topic["regions"]["B"], {"name": "Applied", "level": 0, "skills": 1, "started": 0})

        self.assertIn("sp-01", topic["tasks"])
        self.assertIn("sp-02", topic["tasks"])
        self.assertNotIn("sp-locked", topic["tasks"])
        self.assertEqual(
            topic["tasks"]["sp-01"],
            {"passed": False, "grade": None, "needs": [], "ready": True},
        )
        self.assertEqual(
            topic["tasks"]["sp-02"],
            {"passed": False, "grade": None, "needs": ["skill-alpha"], "ready": False},
        )
        self.assertNotIn("blocked", topic)

    def test_one_met_answer_worked_numbers_and_level_two(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            )
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")

        topic = data["topics"]["spanish"]
        alpha = topic["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 2)
        self.assertEqual(alpha["p_learned"], 0.58)
        self.assertEqual(alpha["stability_days"], 7.5)
        self.assertEqual(alpha["estimate"], 0.58)
        self.assertEqual(alpha["met"], 1)
        self.assertEqual(alpha["missed"], 0)
        self.assertEqual(alpha["first_met"], "2026-06-01")
        self.assertEqual(alpha["last_met"], "2026-06-01")
        self.assertEqual(alpha["due"], "2026-06-04")
        self.assertIs(alpha["skipped"], False)

        self.assertEqual(topic["tasks"]["sp-01"]["passed"], True)
        self.assertEqual(topic["tasks"]["sp-01"]["grade"], "g-0000000001")
        self.assertEqual(topic["tasks"]["sp-02"]["needs"], [])
        self.assertEqual(topic["tasks"]["sp-02"]["ready"], True)

    def test_one_missed_answer_gives_level_one_and_no_due(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "missed"}],
                passed=False,
            )
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")

        alpha = data["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 1)
        self.assertEqual(alpha["p_learned"], 0.309)
        self.assertEqual(alpha["stability_days"], 1.5)
        self.assertEqual(alpha["met"], 0)
        self.assertEqual(alpha["missed"], 1)
        self.assertIsNone(alpha["first_met"])
        self.assertIsNone(alpha["last_met"])
        self.assertIsNone(alpha["due"])

    def test_two_met_same_day_worked_numbers_and_level_two(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T10:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-01T14:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-01T14:00:00+00:00")

        alpha = data["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 2)
        self.assertEqual(alpha["p_learned"], 0.925)
        self.assertEqual(alpha["stability_days"], 18.75)
        self.assertEqual(alpha["met"], 2)
        self.assertEqual(alpha["missed"], 0)

    def test_two_met_four_days_apart_reaches_level_three(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-05T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-05T12:00:00+00:00")

        alpha = data["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 3)
        self.assertEqual(alpha["p_learned"], 0.925)
        self.assertEqual(alpha["stability_days"], 18.75)
        self.assertEqual(alpha["estimate"], 0.925)
        self.assertEqual(alpha["first_met"], "2026-06-01")
        self.assertEqual(alpha["last_met"], "2026-06-05")

    def test_sixty_days_later_drops_to_level_two_with_due_in_past(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-05T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-08-04T12:00:00+00:00")

        alpha = data["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 2)
        self.assertAlmostEqual(alpha["estimate"], 0.038, places=3)
        self.assertIsNotNone(alpha["due"])
        self.assertLess(alpha["due"], "2026-08-04")
        self.assertEqual(
            data["recall_due"],
            [{"topic": "spanish", "skill": "skill-alpha", "due": alpha["due"]}],
        )

    def test_level_four_requires_met_thirty_plus_days_after_reaching_three(self):
        base_grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-05T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
        ]

        vault_too_soon = self.build_standard_vault(
            grades=base_grades
            + [
                make_grade(
                    "g-0000000003",
                    attempt="a3",
                    answered="2026-07-04T12:00:00+00:00",
                    topic="spanish",
                    task="sp-01",
                    questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                    passed=True,
                )
            ],
            name="vault-too-soon",
        )
        data_soon = self.run_progress(vault_too_soon, now="2026-07-04T12:00:00+00:00")
        self.assertEqual(data_soon["topics"]["spanish"]["skills"]["skill-alpha"]["level"], 3)

        vault_permanent = self.build_standard_vault(
            grades=base_grades
            + [
                make_grade(
                    "g-0000000003",
                    attempt="a3",
                    answered="2026-07-06T12:00:00+00:00",
                    topic="spanish",
                    task="sp-01",
                    questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                    passed=True,
                )
            ],
            name="vault-permanent",
        )
        data_perm = self.run_progress(vault_permanent, now="2026-07-06T12:00:00+00:00")
        self.assertEqual(data_perm["topics"]["spanish"]["skills"]["skill-alpha"]["level"], 4)

    def test_missed_answer_after_level_three_drops_below_three(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-05T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
            make_grade(
                "g-0000000003",
                attempt="a3",
                answered="2026-06-06T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "missed"}],
                passed=False,
            ),
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-06T12:00:00+00:00")

        alpha = data["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertLess(alpha["level"], 3)
        self.assertEqual(alpha["level"], 2)
        self.assertEqual(alpha["met"], 2)
        self.assertEqual(alpha["missed"], 1)

    def test_needs_and_skip_clears_needs_without_changing_skill_level(self):
        vault = self.build_standard_vault()
        before = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")
        self.assertEqual(before["topics"]["spanish"]["tasks"]["sp-02"]["needs"], ["skill-alpha"])
        self.assertIs(before["topics"]["spanish"]["tasks"]["sp-02"]["ready"], False)
        self.assertEqual(before["topics"]["spanish"]["skills"]["skill-alpha"]["level"], 0)
        self.assertIs(before["topics"]["spanish"]["skills"]["skill-alpha"]["skipped"], False)

        write_jsonl(
            os.path.join(vault, "_system", "inbox.jsonl"),
            [
                {
                    "id": "s1",
                    "kind": "skip",
                    "topic": "spanish",
                    "skill": "skill-alpha",
                    "ts": "2026-06-01T11:00:00+00:00",
                    "note": "Already know this.",
                }
            ],
        )
        after = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")
        self.assertEqual(after["topics"]["spanish"]["tasks"]["sp-02"]["needs"], [])
        self.assertIs(after["topics"]["spanish"]["tasks"]["sp-02"]["ready"], True)
        self.assertEqual(after["topics"]["spanish"]["skills"]["skill-alpha"]["level"], 0)
        self.assertIs(after["topics"]["spanish"]["skills"]["skill-alpha"]["skipped"], True)

    def test_needs_excludes_task_own_skills(self):
        vault = self.new_vault()
        topic_id = "spanish"
        state = make_state([make_topic(topic_id, [make_task(topic_id, "sp-both", num_fields=2)])])
        write_json(os.path.join(vault, "_system", "state.json"), state)
        graph = make_graph(
            topic_id,
            regions=[{"code": "A", "name": "Core"}],
            skills=[
                make_skill("skill-alpha", "A"),
                make_skill("skill-beta", "A", requires=["skill-alpha"]),
            ],
        )
        write_json(os.path.join(vault, topic_id, "graph.json"), graph)
        write_task_page(vault, topic_id, "sp-both")
        write_text(
            os.path.join(vault, "_system", "keys", topic_id, "sp-both.md"),
            make_key("sp-both", ["skill-alpha", "skill-beta"]),
        )
        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")
        self.assertEqual(data["topics"]["spanish"]["tasks"]["sp-both"]["needs"], [])
        self.assertIs(data["topics"]["spanish"]["tasks"]["sp-both"]["ready"], True)

    def test_unsure_question_changes_nothing_and_multi_question_aggregation(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T10:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "unsure"}],
                passed=False,
            )
        ]
        vault = self.build_standard_vault(grades=grades, name="vault-unsure")
        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")
        alpha = data["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 0)
        self.assertEqual(alpha["met"], 0)
        self.assertEqual(alpha["missed"], 0)
        self.assertEqual(alpha["estimate"], 0.0)

        mixed_grades = [
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-01T10:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[
                    {"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"},
                    {"q": "sp-01#2", "skill": "skill-alpha", "outcome": "unsure"},
                ],
                passed=False,
            ),
            make_grade(
                "g-0000000003",
                attempt="a3",
                answered="2026-06-01T11:00:00+00:00",
                topic="spanish",
                task="sp-02",
                questions=[
                    {"q": "sp-02#1", "skill": "skill-beta", "outcome": "met"},
                    {"q": "sp-02#2", "skill": "skill-beta", "outcome": "missed"},
                ],
                passed=False,
            ),
        ]
        vault_mixed = self.build_standard_vault(grades=mixed_grades, name="vault-mixed")
        data_mixed = self.run_progress(vault_mixed, now="2026-06-01T12:00:00+00:00")
        self.assertEqual(data_mixed["topics"]["spanish"]["skills"]["skill-alpha"]["level"], 2)
        self.assertEqual(data_mixed["topics"]["spanish"]["skills"]["skill-alpha"]["met"], 1)
        self.assertEqual(data_mixed["topics"]["spanish"]["skills"]["skill-beta"]["level"], 1)
        self.assertEqual(data_mixed["topics"]["spanish"]["skills"]["skill-beta"]["missed"], 1)

    def test_regrade_replaces_earlier_grade_for_same_attempt(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T10:00:00+00:00",
                ts="2026-06-01T10:05:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "missed"}],
                passed=False,
            ),
            make_grade(
                "g-0000000002",
                attempt="a1",
                answered="2026-06-01T10:00:00+00:00",
                ts="2026-06-01T11:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")

        topic = data["topics"]["spanish"]
        alpha = topic["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 2)
        self.assertEqual(alpha["p_learned"], 0.58)
        self.assertEqual(alpha["met"], 1)
        self.assertEqual(alpha["missed"], 0)
        self.assertIs(topic["tasks"]["sp-01"]["passed"], True)
        self.assertEqual(topic["tasks"]["sp-01"]["grade"], "g-0000000002")

    def test_honor_false_first_try_future_and_non_grade_lines_change_nothing(self):
        grades = [
            "",
            {"type": "ack", "id": "ack-1", "ts": "2026-06-01T09:00:00+00:00", "attempt": "n1"},
            {"type": "legacy", "id": "leg-1", "ts": "2026-06-01T09:00:00+00:00", "topic": "spanish"},
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T10:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
                honor=False,
            ),
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-01T10:30:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
                kind="first-try",
            ),
            make_grade(
                "g-0000000003",
                attempt="a3",
                answered="2026-06-05T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")

        alpha = data["topics"]["spanish"]["skills"]["skill-alpha"]
        self.assertEqual(alpha["level"], 0)
        self.assertEqual(alpha["met"], 0)
        self.assertEqual(alpha["missed"], 0)
        self.assertEqual(alpha["estimate"], 0.0)

    def test_blocked_when_only_unpassed_task_needs_missed_skill_and_cleared_by_skip(self):
        vault = self.new_vault()
        topic_id = "spanish"
        state = make_state([make_topic(topic_id, [make_task(topic_id, "sp-02", num_fields=1)])])
        write_json(os.path.join(vault, "_system", "state.json"), state)
        graph = make_graph(
            topic_id,
            regions=[
                {"code": "A", "name": "Core"},
                {"code": "B", "name": "Applied"},
            ],
            skills=[
                make_skill("skill-alpha", "A"),
                make_skill("skill-beta", "B", requires=["skill-alpha"]),
            ],
        )
        write_json(os.path.join(vault, topic_id, "graph.json"), graph)
        write_task_page(vault, topic_id, "sp-02")
        write_text(
            os.path.join(vault, "_system", "keys", topic_id, "sp-02.md"),
            make_key("sp-02", ["skill-beta"]),
        )
        write_jsonl(
            os.path.join(vault, "_system", "grades.jsonl"),
            [
                make_grade(
                    "g-0000000001",
                    attempt="a1",
                    answered="2026-06-01T10:00:00+00:00",
                    topic=topic_id,
                    task="sp-01",
                    questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "missed"}],
                    passed=False,
                )
            ],
        )

        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")
        topic = data["topics"][topic_id]
        self.assertIn("blocked", topic)
        self.assertEqual(topic["blocked"]["skills"], ["skill-alpha"])

        write_jsonl(
            os.path.join(vault, "_system", "inbox.jsonl"),
            [
                {
                    "id": "s1",
                    "kind": "skip",
                    "topic": topic_id,
                    "skill": "skill-alpha",
                    "ts": "2026-06-01T11:00:00+00:00",
                    "note": "Skip prereq.",
                }
            ],
        )
        data_after = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")
        self.assertNotIn("blocked", data_after["topics"][topic_id])

    def test_region_level_is_lowest_started_skill(self):
        vault = self.new_vault()
        topic_id = "spanish"
        state = make_state([make_topic(topic_id, [make_task(topic_id, "sp-01", num_fields=3)])])
        write_json(os.path.join(vault, "_system", "state.json"), state)
        graph = make_graph(
            topic_id,
            regions=[
                {"code": "A", "name": "Core"},
                {"code": "B", "name": "Applied"},
            ],
            skills=[
                make_skill("skill-a1", "A"),
                make_skill("skill-a2", "A"),
                make_skill("skill-a3", "A"),
                make_skill("skill-retired", "A", retired=True),
                make_skill("skill-b1", "B"),
            ],
        )
        write_json(os.path.join(vault, topic_id, "graph.json"), graph)
        write_task_page(vault, topic_id, "sp-01")
        write_text(
            os.path.join(vault, "_system", "keys", topic_id, "sp-01.md"),
            make_key("sp-01", ["skill-a1", "skill-a2", "skill-a3"]),
        )
        write_jsonl(
            os.path.join(vault, "_system", "grades.jsonl"),
            [
                make_grade(
                    "g-0000000001",
                    attempt="a1",
                    answered="2026-06-01T12:00:00+00:00",
                    topic=topic_id,
                    task="sp-01",
                    questions=[{"q": "sp-01#1", "skill": "skill-a1", "outcome": "met"}],
                    passed=True,
                ),
                make_grade(
                    "g-0000000002",
                    attempt="a2",
                    answered="2026-06-05T12:00:00+00:00",
                    topic=topic_id,
                    task="sp-01",
                    questions=[
                        {"q": "sp-01#1", "skill": "skill-a1", "outcome": "met"},
                        {"q": "sp-01#2", "skill": "skill-a2", "outcome": "missed"},
                    ],
                    passed=False,
                ),
            ],
        )

        data = self.run_progress(vault, now="2026-06-05T12:00:00+00:00")
        regions = data["topics"][topic_id]["regions"]
        self.assertEqual(regions["A"], {"name": "Core", "level": 1, "skills": 3, "started": 2})
        self.assertEqual(regions["B"], {"name": "Applied", "level": 0, "skills": 1, "started": 0})

    def test_topic_filtering_and_unknown_topic_exit_one(self):
        vault = self.new_vault()
        state = make_state(
            [
                make_topic("spanish", [make_task("spanish", "sp-01", num_fields=1)]),
                make_topic("rust", [make_task("rust", "rs-01", num_fields=1)]),
            ]
        )
        write_json(os.path.join(vault, "_system", "state.json"), state)
        for tid, task_id, skill_id in (
            ("spanish", "sp-01", "skill-sp"),
            ("rust", "rs-01", "skill-rs"),
        ):
            write_json(
                os.path.join(vault, tid, "graph.json"),
                make_graph(tid, [{"code": "A", "name": "Core"}], [make_skill(skill_id, "A")]),
            )
            write_task_page(vault, tid, task_id)
            write_text(
                os.path.join(vault, "_system", "keys", tid, f"{task_id}.md"),
                make_key(task_id, [skill_id]),
            )

        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00", topic="rust")
        self.assertEqual(list(data["topics"].keys()), ["rust"])

        res = self.run_cli(
            "progress", "--vault", vault, "--topic", "unknown-topic", "--now", "2026-06-01T12:00:00+00:00"
        )
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertTrue((res.stdout + res.stderr).strip())

    def test_unlinked_topic_listed(self):
        vault = self.new_vault()
        state = make_state(
            [
                make_topic("spanish", [make_task("spanish", "sp-01", num_fields=1)]),
                make_topic("notes-only", [make_task("notes-only", "no-01", num_fields=1)]),
            ]
        )
        write_json(os.path.join(vault, "_system", "state.json"), state)
        write_json(
            os.path.join(vault, "spanish", "graph.json"),
            make_graph("spanish", [{"code": "A", "name": "Core"}], [make_skill("skill-sp", "A")]),
        )
        write_task_page(vault, "spanish", "sp-01")
        write_task_page(vault, "notes-only", "no-01")
        write_text(
            os.path.join(vault, "_system", "keys", "spanish", "sp-01.md"),
            make_key("sp-01", ["skill-sp"]),
        )

        data = self.run_progress(vault, now="2026-06-01T12:00:00+00:00")
        self.assertIn("spanish", data["topics"])
        self.assertNotIn("notes-only", data["topics"])
        self.assertTrue(
            any("notes-only" in str(item) for item in data["unlinked"]),
            data["unlinked"],
        )

    def test_recall_due_ordered_oldest_first(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            ),
            make_grade(
                "g-0000000002",
                attempt="a2",
                answered="2026-06-03T12:00:00+00:00",
                topic="spanish",
                task="sp-02",
                questions=[{"q": "sp-02#1", "skill": "skill-beta", "outcome": "met"}],
                passed=True,
            ),
        ]
        vault = self.build_standard_vault(grades=grades)
        data = self.run_progress(vault, now="2026-06-10T12:00:00+00:00")

        self.assertEqual(
            data["recall_due"],
            [
                {"topic": "spanish", "skill": "skill-alpha", "due": "2026-06-04"},
                {"topic": "spanish", "skill": "skill-beta", "due": "2026-06-06"},
            ],
        )

    def test_invalid_content_exits_one(self):
        vault = self.new_vault()
        topic_id = "spanish"
        state = make_state([make_topic(topic_id, [make_task(topic_id, "sp-01", num_fields=1)])])
        write_json(os.path.join(vault, "_system", "state.json"), state)
        graph = make_graph(
            topic_id,
            regions=[{"code": "A", "name": "Core"}],
            skills=[
                make_skill("cycle-a", "A", requires=["cycle-b"]),
                make_skill("cycle-b", "A", requires=["cycle-a"]),
            ],
        )
        write_json(os.path.join(vault, topic_id, "graph.json"), graph)
        write_task_page(vault, topic_id, "sp-01")
        write_text(
            os.path.join(vault, "_system", "keys", topic_id, "sp-01.md"),
            make_key("sp-01", ["cycle-a"]),
        )

        res = self.run_cli("progress", "--vault", vault, "--now", "2026-06-01T12:00:00+00:00")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        combined = res.stdout + res.stderr
        self.assertTrue("cycle-a" in combined or "cycle-b" in combined, combined)

    def test_vault_is_byte_identical_after_command(self):
        grades = [
            make_grade(
                "g-0000000001",
                attempt="a1",
                answered="2026-06-01T12:00:00+00:00",
                topic="spanish",
                task="sp-01",
                questions=[{"q": "sp-01#1", "skill": "skill-alpha", "outcome": "met"}],
                passed=True,
            )
        ]
        inbox = [
            {
                "id": "s1",
                "kind": "skip",
                "topic": "spanish",
                "skill": "skill-beta",
                "ts": "2026-06-01T11:00:00+00:00",
                "note": "Skip.",
            }
        ]
        vault = self.build_standard_vault(grades=grades, inbox=inbox)
        before = snapshot_vault(vault)
        self.run_progress(vault, now="2026-06-05T12:00:00+00:00")
        after = snapshot_vault(vault)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
