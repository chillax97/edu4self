"""The learner-facing helpers: the recall warm-up (which questions, and the welcome back after a gap)
and the stuck nudge on an exercise."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import server  # noqa: E402
from test_server import make_vault, read_json, write_json  # noqa: E402

NOW = datetime(2026, 11, 6, 20, 0).astimezone()


def iso(days_ago, hour=12):
    return (NOW - timedelta(days=days_ago)).replace(hour=hour).isoformat(timespec="seconds")


def state(*recall):
    return {"processed_inbox": ["s-a", "s-b", "s-c"], "recall": list(recall), "topics": [{"queue": [
        {"id": "a", "status": "done"}, {"id": "b", "status": "done"}, {"id": "c", "status": "done"},
        {"id": "open", "status": "todo"}]}]}


def q(qid, task):
    return {"id": qid, "q": "What does %s do?" % qid, "from": task}


class RecallPickTest(unittest.TestCase):
    def ids(self, picked):
        return [x["id"] for x in picked["questions"]]

    def test_a_normal_day_asks_the_ones_not_asked_for_the_longest(self):
        st = state(q("q1", "a"), q("q2", "b"), q("q3", "c"), q("q4", "open"))
        entries = [{"id": "r1", "ts": iso(5), "kind": "recall", "recall": ["q2"]},
                   {"id": "r2", "ts": iso(2), "kind": "recall", "recall": ["q1"]},
                   {"id": "blk", "ts": iso(1), "kind": "note"}]                    # active yesterday: a normal day
        p = server.pick_recall(st, entries, [], NOW)
        self.assertFalse(p["comeback"])
        self.assertEqual(self.ids(p), ["q3", "q4", "q2"], "never asked first (in the tutor's order), then the oldest")
        self.assertFalse(p["sent_today"])

    def test_a_withdrawn_recall_does_not_count_as_asked(self):
        st = state(q("q1", "a"), q("q2", "b"))
        entries = [{"id": "r1", "ts": iso(1), "kind": "recall", "recall": ["q1"]}, {"id": "w", "ts": iso(1), "kind": "withdraw", "ref": "r1"}]
        self.assertEqual(self.ids(server.pick_recall(st, entries, [], NOW)), ["q1", "q2"])

    def test_after_three_days_away_only_passed_work_most_recently_passed_first(self):
        st = state(q("q-open", "open"), q("q-a", "a"), q("q-b", "b"), q("q-c", "c"))
        st["recall"].append(q("q-open-2", "open"))
        entries = [{"id": "s-a", "ts": iso(20), "task": "a", "kind": "answers"},
                   {"id": "s-c", "ts": iso(9), "task": "c", "kind": "answers"},
                   {"id": "s-b", "ts": iso(4), "task": "b", "kind": "answers"},     # the last thing done: 4 days ago
                   {"id": "r", "ts": iso(30), "kind": "recall", "recall": ["q-b"]}]
        p = server.pick_recall(st, entries, [], NOW)
        self.assertTrue(p["comeback"])
        self.assertEqual(p["days_away"], 4)
        self.assertEqual(self.ids(p), ["q-b", "q-c", "q-a"], "not the unpassed one, newest pass first")
        st["recall"] = [q("q-open", "open"), q("q-a", "a")]
        self.assertEqual(self.ids(server.pick_recall(st, entries, [], NOW)), ["q-a"], "only passed work, even with room to spare")

    def test_the_gap_uses_the_away_mail_rule_and_stays_the_same_all_day(self):
        st = state(q("q1", "a"))
        blocks = [{"ts": iso(2), "minutes": 25}]
        self.assertFalse(server.pick_recall(st, [], blocks, NOW)["comeback"], "two days is not a gap")
        blocks = [{"ts": iso(3), "minutes": 25}]
        self.assertTrue(server.pick_recall(st, [], blocks, NOW)["comeback"], "three days is, like the first away mail")
        blocks.append({"ts": iso(0, hour=9), "minutes": 25})                       # a block this morning
        self.assertTrue(server.pick_recall(st, [], blocks, NOW)["comeback"], "today's study doesn't flip the card mid-day")

    def test_sent_today_and_no_questions(self):
        st = state(q("q1", "a"))
        p = server.pick_recall(st, [{"id": "r", "ts": iso(0, hour=9), "kind": "recall", "recall": ["q1"]}], [], NOW)
        self.assertTrue(p["sent_today"])
        self.assertEqual(server.pick_recall({"topics": []}, [], [], NOW)["questions"], [])

    def test_at_most_three(self):
        st = state(*[q("q%d" % i, "a") for i in range(6)])
        self.assertEqual(len(server.pick_recall(st, [], [], NOW)["questions"]), 3)


class RecallSchemaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-recall-")
        self.vault, _ = make_vault(self.tmp)
        self.path = os.path.join(self.vault, "_system", "state.json")
        self.state = read_json(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self):
        write_json(self.path, self.state)
        return subprocess.run([sys.executable, os.path.join(APP, "validate_state.py"), self.vault], stdout=subprocess.PIPE, text=True)

    def test_recall_questions_are_checked(self):
        self.state["recall"] = [{"id": "r1", "q": "What does storage strength mean?", "from": "hlw-lesson-01"}]
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("1 recall question", r.stdout)
        for bad, msg in (([{"id": "r1", "q": "x", "from": "nope"}], "from must be the id of the task"),
                         ([{"id": "r 1", "q": "x", "from": "hlw-lesson-01"}], "must be letters"),
                         ([{"id": "r1", "q": "two\nlines", "from": "hlw-lesson-01"}], "one line"),
                         ([{"id": "r1", "q": "x" * 301, "from": "hlw-lesson-01"}], "one line"),
                         ([{"id": "r1", "q": "a", "from": "hlw-lesson-01"}, {"id": "r1", "q": "b", "from": "hlw-lesson-01"}], "duplicate recall"),
                         ({"r1": "x"}, "recall must be a list")):
            self.state["recall"] = bad
            r = self.check()
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn(msg, r.stdout)

    def test_the_inbox_takes_recall_answers_for_known_questions_only(self):
        server.configure(self.vault, 4799)
        self.state["recall"] = [{"id": "r1", "q": "Q one?", "from": "hlw-lesson-01"}, {"id": "r2", "q": "Q two?", "from": "hlw-lesson-01"}]
        good = {"topic": "general", "task": "recall", "kind": "recall", "fields": {"Q one?": "an answer", "Q two?": ""}, "recall": ["r1", "r2"]}
        e = server.clean_submission(good, self.state)
        self.assertEqual((e["kind"], e["recall"], "confidence" in e), ("recall", ["r1", "r2"], False))
        self.assertNotIn("comeback", e, "a fresh vault has no gap")
        for change, msg in (({"recall": ["r9"]}, "unknown recall questions"), ({"recall": []}, "unknown recall questions"),
                            ({"recall": "r1"}, "unknown recall questions"), ({"recall": ["r1", "r1"]}, "unknown recall questions"),
                            ({"fields": {"Q one?": " "}}, "no answers")):
            with self.assertRaises(ValueError) as cm:
                server.clean_submission(dict(good, **change), self.state)
            self.assertEqual(str(cm.exception), msg)

    def test_a_recall_sent_after_a_gap_is_marked_as_the_comeback(self):
        server.configure(self.vault, 4799)
        with open(os.path.join(self.vault, "_system", "blocks.jsonl"), "w") as fh:
            fh.write(json.dumps({"ts": (datetime.now().astimezone() - timedelta(days=5)).isoformat(), "minutes": 25}) + "\n")
        self.state["recall"] = [{"id": "r1", "q": "Q one?", "from": "hlw-lesson-01"}]
        e = server.clean_submission({"topic": "general", "task": "recall", "kind": "recall", "fields": {"Q one?": "x"}, "recall": ["r1"]}, self.state)
        self.assertTrue(e["comeback"])


class StuckTest(unittest.TestCase):
    def test_three_failing_runs_in_a_row_and_a_pass_resets_it(self):
        f = server.fails_in_a_row
        self.assertEqual([f([]), f([1, 1]), f([1, 1, 1]), f([1, 1, 1, 0]), f([0, 1, 1, 1]), f([1, 1, 1, 0, 1]), f([0, 2, 1, 1, 1])],
                         [0, 2, 3, 0, 3, 1, 4])

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-stuck-")
        self.vault, _ = make_vault(self.tmp)
        server.configure(self.vault, 4798)
        self.ex = os.path.join(self.vault, "topic", "ex")
        os.makedirs(os.path.join(self.ex, "trace"))
        with open(os.path.join(self.ex, "HINTS.md"), "w") as fh:
            fh.write("# Hints\n\n## 1 · start\n- a\n\n## 2 · the loop\n- b\n\n## 3 · the end\n- c\n")
        self.task = {"id": "t-ex", "status": "todo", "exercise": "topic/ex"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name, rec):
        with open(os.path.join(self.ex, "trace", name), "w") as fh:
            json.dump(dict(rec, edu4self_trace=1), fh)

    def test_the_timeline_in_time_order_and_the_next_unopened_hint(self):
        self.put("2026-11-06T10-00-00.000-run.json", {"kind": "run", "ts": "2026-11-06T10:00:00+03:00", "exit": 1})
        self.put("2026-11-06T10-02-30.000-run.json", {"kind": "run", "ts": "2026-11-06T10:02:30+03:00", "exit": 1})
        self.assertFalse(server.attempts(self.task)["stuck"], "two failing runs: not yet")
        self.put("2026-11-06T10-03-00.000-hint-1.json", {"kind": "hint", "ts": "2026-11-06T10:03:00+03:00", "hint": 1, "title": "1 · start"})
        self.put("2026-11-06T10-10-30.000-run.json", {"kind": "run", "ts": "2026-11-06T10:10:30+03:00", "exit": 1})
        with open(os.path.join(self.ex, "trace", "notes.json"), "w") as fh:      # not the record's: ignored
            fh.write('{"kind": "run", "exit": 0}')
        before = sorted(os.listdir(os.path.join(self.ex, "trace")))
        a = server.attempts(self.task)
        self.assertEqual([(e["kind"], e.get("passed"), e.get("since")) for e in a["events"]],
                         [("run", False, None), ("run", False, 150), ("hint", None, None), ("run", False, 480)])
        self.assertTrue(a["stuck"])
        self.assertEqual(a["next_hint"], {"n": 2, "title": "2 · the loop"}, "hint 1 is already open")
        self.assertEqual(sorted(os.listdir(os.path.join(self.ex, "trace"))), before, "reading the record writes nothing")
        state = {"topics": [{"queue": [self.task, {"id": "done-one", "status": "done", "exercise": "topic/ex"}]}]}
        self.assertEqual(server.stuck_tasks(state), {"t-ex": {"fails": 3, "next_hint": {"n": 2, "title": "2 · the loop"}}})
        self.put("2026-11-06T10-20-00.000-run.json", {"kind": "run", "ts": "2026-11-06T10:20:00+03:00", "exit": 0})
        a = server.attempts(self.task)
        self.assertEqual((a["stuck"], a["fails_in_a_row"], a["events"][-1]["passed"]), (False, 0, True), "a pass resets it")
        self.assertEqual(server.stuck_tasks(state), {})

    def test_no_exercise_no_timeline(self):
        self.assertIsNone(server.attempts({"id": "x"}))
        self.assertIsNone(server.attempts({"id": "x", "exercise": "../outside"}))


if __name__ == "__main__":
    unittest.main()
