"""The honesty runner saves each answer as it is graded and can resume (evals/grading/run.py).
Claude is replaced by a fake grade function: nothing here starts the real `claude`."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.join(os.path.dirname(HERE), "evals", "grading")
sys.path.insert(0, EVAL)
import run  # noqa: E402
import score  # noqa: E402


class Boom(Exception):
    pass


class RunnerSaves(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "out")
        self.items = run.order(run.load_items("made-up"))[:5]
        self.calls = []          # one entry per fake grade call

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_grade(self, fail_on_call=None, time_out_on=()):
        """Stands in for run.grade: marks every pending answer graded (a pass for every second one), no Claude."""
        def grade(engine, vault, stream_path, timeout):
            self.calls.append(len(self.calls) + 1)
            if fail_on_call == len(self.calls):
                raise Boom("crash while grading")
            if len(self.calls) in time_out_on:       # a run killed by the timeout: no grade written
                return {"exit": -9, "timed_out": True, "is_error": True, "cost_usd": 0.05, "duration_ms": 1,
                        "num_turns": 1, "usage": None, "wall_s": 0.1, "stderr_tail": []}
            sp = os.path.join(vault, "_system", "state.json")
            state = run.load_json(sp)
            inbox = run.read_jsonl(os.path.join(vault, "_system", "inbox.jsonl"))
            for n, e in enumerate(inbox):
                topic = next(t for t in state["topics"] if t["id"] == e["topic"])
                topic.setdefault("history", []).append({"title": "graded", "detail": "ok", "inbox": e["id"],
                                                        "evidence": n % 2 == 0})
                state.setdefault("processed_inbox", []).append(e["id"])
            with open(sp, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            with open(stream_path, "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            return {"exit": 0, "timed_out": False, "is_error": False, "cost_usd": 0.09, "duration_ms": 1,
                    "num_turns": 1, "usage": None, "wall_s": 0.1, "stderr_tail": []}
        return grade

    def go(self, fail_on_call=None, resume=False, time_out_on=(), items=None, meta=None):
        with mock.patch.object(run, "grade", self.fake_grade(fail_on_call, time_out_on)):
            return run.run(items or self.items, 1, self.out, log=lambda *a: None, resume=resume, meta=meta)

    def ids_on_disk(self):
        return [r["id"] for r in run.read_jsonl(os.path.join(self.out, "results.jsonl"))]

    def test_results_are_on_disk_after_a_crash(self):
        with self.assertRaises(Boom):
            self.go(fail_on_call=4)                       # answers 1-3 graded, then the crash
        self.assertEqual(self.ids_on_disk(), [i["id"] for i in self.items[:3]])
        self.assertEqual(len(run.read_jsonl(os.path.join(self.out, "runs.jsonl"))), 3)

    def test_resume_grades_only_the_rest_and_keeps_each_answer_once(self):
        with self.assertRaises(Boom):
            self.go(fail_on_call=4)
        self.calls.clear()
        results, runs = self.go(resume=True)
        self.assertEqual(len(self.calls), 2)              # only the two left over
        self.assertEqual(self.ids_on_disk(), [i["id"] for i in self.items])   # all 5, each once
        self.assertEqual([r["id"] for r in results], [i["id"] for i in self.items])
        self.assertEqual(sorted(r["batch"] for r in runs), [1, 2, 3, 4, 5])   # batch numbers continue

    def test_a_rerun_without_resume_refuses_to_mix(self):
        self.go()
        with self.assertRaises(SystemExit):
            self.go()
        self.assertEqual(len(self.ids_on_disk()), 5)

    def test_a_torn_last_line_is_dropped_and_regraded(self):
        self.go()
        path = os.path.join(self.out, "results.jsonl")
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines[:4]) + "\n" + lines[4][:30])     # killed mid-write
        self.assertEqual(len(score.read_jsonl(path)), 4)              # the scorer copes too
        self.calls.clear()
        self.go(resume=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.ids_on_disk(), [i["id"] for i in self.items])

    def test_score_is_the_same_as_for_results_written_at_the_end(self):
        with self.assertRaises(Boom):
            self.go(fail_on_call=3)
        results, runs = self.go(resume=True)
        old = os.path.join(self.tmp, "old")                 # the old way: both files written whole at the end
        os.makedirs(old)
        for name, rows in (("results.jsonl", results), ("runs.jsonl", runs)):
            with open(os.path.join(old, name), "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")

        def scored(folder):
            return score.score(score.read_jsonl(os.path.join(folder, "results.jsonl")),
                               score.read_jsonl(os.path.join(folder, "runs.jsonl")))
        self.assertEqual(scored(self.out), scored(old))
        self.assertEqual(score.report(scored(self.out)), score.report(scored(old)))

    def test_resume_regrades_answers_that_got_no_grade_and_keeps_each_id_once(self):
        self.go(time_out_on=(2,))                          # batch 2 times out: its answer has no grade
        before = run.read_jsonl(os.path.join(self.out, "results.jsonl"))
        bad = [r["id"] for r in before if r["verdict"] not in ("pass", "partial", "fail")]
        self.assertEqual(bad, [self.items[1]["id"]])
        self.calls.clear()
        results, runs = self.go(resume=True)
        self.assertEqual(len(self.calls), 1)               # only that answer
        on_disk = run.read_jsonl(os.path.join(self.out, "results.jsonl"))
        self.assertEqual(sorted(r["id"] for r in on_disk), sorted(i["id"] for i in self.items))
        self.assertEqual(sorted(r["id"] for r in results), sorted(r["id"] for r in on_disk))
        self.assertTrue(all(r["verdict"] in ("pass", "partial", "fail") for r in on_disk))
        # the money spent on the timed-out run still counts in the result that replaced it
        new = next(r for r in on_disk if r["id"] == bad[0])
        self.assertAlmostEqual(new["cost_share_usd"], 0.09 + 0.05)

    def test_the_cost_row_is_saved_before_the_results_rows(self):
        with mock.patch.object(run, "verdict", side_effect=Boom("crash between")):
            with mock.patch.object(run, "grade", self.fake_grade()):
                with self.assertRaises(Boom):
                    run.run(self.items, 1, self.out, log=lambda *a: None)
        self.assertEqual(len(run.read_jsonl(os.path.join(self.out, "runs.jsonl"))), 1)
        self.assertEqual(run.read_done(os.path.join(self.out, "results.jsonl")), [])

    def test_resume_with_a_different_set_is_refused(self):
        self.go(items=self.items[:3], meta={"set": "made-up"})
        self.assertTrue(os.path.isfile(os.path.join(self.out, "meta.json")))
        with self.assertRaises(SystemExit) as c:
            self.go(items=self.items[:3], resume=True, meta={"set": "saf"})
        self.assertIn("set", str(c.exception))
        self.assertEqual(len(self.ids_on_disk()), 3)

    def test_resume_with_a_different_case_list_is_refused(self):
        self.go(items=self.items[:3], meta={"set": "made-up"})
        with self.assertRaises(SystemExit) as c:
            self.go(resume=True, meta={"set": "made-up"})   # 5 cases now, 3 before
        self.assertIn("cases", str(c.exception))

    def test_a_bad_line_in_the_middle_is_an_error_and_the_file_is_left_alone(self):
        path = os.path.join(self.tmp, "r.jsonl")
        text = '{"id": 1}\nnot json\n{"id": 3}\n'
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        with self.assertRaises(SystemExit) as c:
            run.read_done(path)
        self.assertIn("line 2", str(c.exception))
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), text)


if __name__ == "__main__":
    unittest.main()
