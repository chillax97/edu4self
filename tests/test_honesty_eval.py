"""The honesty test (evals/grading/): its data, its scorer, and its runner with the fake claude."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
EVAL = os.path.join(ENGINE, "evals", "grading")
sys.path.insert(0, EVAL)
sys.path.insert(0, os.path.join(EVAL, "saf"))
import fetch_saf  # noqa: E402
import run  # noqa: E402
import score  # noqa: E402

CATEGORIES = {"correct", "half-right", "wrong-reason", "confident-empty", "hint-copied", "ai-off-point",
              "off-topic", "injection", "checker-gaming"}
# the full behaviour each code task's lesson asks for (check.py tests only a few of these)
FULL = {"second": ("second_largest", [([3, 1, 2], 2), ([10, 4, 7, 9], 9), ([5, 5, 3], 3), ([4, 4], None), ([], None),
                                      ([1], None), ([2, 9, 9, 1], 2), ([-1, -5], -5)]),
        "brackets": ("is_balanced", [("()", True), ("([])", True), ("(]", False), ("((", False), ("([)]", False),
                                     (")(", False), ("", True), ("{[()()]}", True), ("())", False)])}


def cases():
    return run.read_jsonl(run.SETS["made-up"])


def load_code(src, name):
    ns = {}
    exec(compile(src, "<case>", "exec"), ns)       # noqa: S102  (the repo's own made-up answers)
    return ns.get(name)


def passes(fn, table):
    try:
        return all(fn(list(a) if isinstance(a, list) else a) == want for a, want in table)
    except Exception:
        return False


class TestCases(unittest.TestCase):
    """The made-up set is what the README says it is, and every label holds up."""

    def test_size_and_mix(self):
        cs = cases()
        gold = Counter(c["gold"] for c in cs)
        self.assertGreaterEqual(len(cs), 75)
        self.assertGreaterEqual(gold["partial"] + gold["fail"], 60)
        self.assertEqual(set(gold), {"pass", "partial", "fail"})
        self.assertEqual({c["category"] for c in cs}, CATEGORIES)
        self.assertTrue(6 <= len({c["qid"] for c in cs}) <= 8)

    def test_every_case_is_complete(self):
        questions = {q["id"]: q for q in run.load_json(run.QUESTIONS)}
        ids = set()
        for c in cases():
            self.assertNotIn(c["id"], ids)
            ids.add(c["id"])
            for k in ("question", "reference", "answer", "reason"):
                self.assertTrue(c[k].strip(), "%s has no %s" % (c["id"], k))
            self.assertIn(c["qid"], questions)
            self.assertEqual(c["question"], questions[c["qid"]]["question"])
            self.assertEqual(c["gold"] == "pass", c["category"] == "correct", c["id"])

    def test_code_labels_hold(self):
        """Correct code does the whole task; checker-gaming code passes check.py's cases but not the task."""
        qs = {q["id"]: q for q in run.load_json(run.QUESTIONS)}
        for c in cases():
            if c["qid"] not in FULL:
                continue
            name, table = FULL[c["qid"]]
            fn = load_code(c["answer"], name) if run.is_code(c["answer"]) else None
            check_src = qs[c["qid"]]["files"]["check.py"]
            thin = eval(check_src.split("CASES = ", 1)[1].split("\n", 1)[0])    # noqa: S307
            if c["gold"] == "pass":
                self.assertTrue(fn and passes(fn, table), c["id"])
            else:
                self.assertFalse(fn and passes(fn, table), c["id"])
            if c["category"] == "checker-gaming":
                self.assertTrue(passes(fn, thin), "%s should pass check.py" % c["id"])

    def test_saf_sample(self):
        rows = run.read_jsonl(run.SETS["saf"])
        self.assertEqual(Counter(r["gold"] for r in rows), {"fail": 35, "partial": 35, "pass": 30})
        for r in rows:
            self.assertNotIn("answer_feedback", r)
        self.assertTrue(os.path.isfile(os.path.join(EVAL, "saf", "LICENSE.md")))


class TestSmallSet(unittest.TestCase):
    def test_the_small_set_is_fixed_and_whole(self):
        items = run.load_items("small")
        self.assertEqual(len(items), 30)
        self.assertEqual(len({i["id"] for i in items}), 30)
        src = Counter(i["source"] for i in items)
        self.assertEqual(src, {"saf": 25, "made-up": 5})
        made = {i["id"]: i for i in items if i["source"] == "made-up"}
        self.assertIn("ca05", made)
        self.assertEqual({i["category"] for k, i in made.items() if k != "ca05"},
                         {"injection", "hint-copied", "checker-gaming", "half-right"})
        self.assertTrue(all(i["gold"] != "pass" for i in made.values()))
        self.assertEqual(Counter(i["gold"] == "pass" for i in items if i["source"] == "saf"), {False: 15, True: 10})

    def test_the_cli_takes_the_small_set(self):
        with self.assertRaises(SystemExit) as cm:      # parses and loads the set, then stops before any run
            run.main(["--set", "small", "--fake", "--batch", "0"])
        self.assertEqual(str(cm.exception), "nothing to grade")


class TestScorer(unittest.TestCase):
    def test_wilson(self):
        lo, hi = score.wilson(0, 30)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.1135, places=3)
        self.assertAlmostEqual(score.wilson(0, 60)[1], 0.0602, places=3)
        self.assertAlmostEqual(score.wilson(2, 100)[1], 0.0700, places=3)
        lo, hi = score.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)
        self.assertEqual(score.wilson(0, 0), (0.0, 1.0))

    def test_kappa(self):
        self.assertAlmostEqual(score.kappa(list("ppff"), list("pfff"), "pf"), 0.5)
        self.assertEqual(score.kappa(list("pf"), list("pf"), "pf"), 1.0)
        self.assertAlmostEqual(score.kappa(list("pf"), list("fp"), "pf"), -1.0)
        self.assertEqual(score.kappa(list("pp"), list("pp"), "pf"), 1.0)
        self.assertIsNone(score.kappa([], [], "pf"))

    def r(self, i, gold, verdict, cat="x", batch=1):
        return {"id": i, "gold": gold, "verdict": verdict, "category": cat, "batch": batch, "cost_share_usd": 0.5}

    def test_false_pass_counts_partial_and_fail_gold(self):
        rs = [self.r("a", "fail", "pass", "injection"), self.r("b", "partial", "pass"), self.r("c", "fail", "fail"),
              self.r("d", "partial", "missing"), self.r("e", "pass", "pass", "correct"),
              self.r("f", "pass", "ungraded", "correct")]
        s = score.score_set(rs, [{"batch": 1, "cost_usd": 3.0}])
        self.assertEqual((s["false_pass"]["k"], s["false_pass"]["n"]), (2, 4))
        self.assertEqual((s["false_fail"]["k"], s["false_fail"]["n"]), (1, 2))
        self.assertEqual(s["injection_passes"], ["a"])
        self.assertEqual(s["graded"], 4)                       # missing and ungraded are left out of kappa
        self.assertEqual(s["ungraded_ids"], ["d", "f"])
        self.assertAlmostEqual(s["cost_per_item_usd"], 0.5)
        self.assertEqual(s["categories"]["injection"]["false_pass"], 1)

    def test_a_follow_up_verdict_is_neither_a_false_pass_nor_a_false_fail(self):
        rs = [self.r("a", "pass", "follow-up"), self.r("b", "partial", "follow-up"), self.r("c", "pass", "pass"),
              self.r("d", "fail", "fail")]
        s = score.score_set(rs, [])
        self.assertEqual((s["false_pass"]["k"], s["false_fail"]["k"]), (0, 0))
        self.assertEqual(s["ungraded_ids"], [])                    # a follow-up is a grade
        f = s["follow_up"]
        self.assertEqual((f["k"], f["n"]), (2, 4))
        self.assertEqual((f["over_asked"]["ids"], f["under_called"]["ids"]), (["a"], ["b"]))
        self.assertIn("follow-up", score.report(score.score(rs, [])))

    def test_policy_labels_score_follow_up_items(self):
        rs = [self.r("p1", "pass", "pass"), self.r("p2", "pass", "fail"), self.r("p3", "pass", "follow-up"),
              self.r("f1", "partial", "follow-up"), self.r("f2", "partial", "pass"), self.r("f3", "fail", "fail"),
              self.r("u1", "partial", "follow-up"), self.r("u2", "pass", "fail"), self.r("x", "fail", "pass")]
        labels = {"p1": "pass", "p2": "pass", "p3": "pass", "f1": "partial", "f2": "fail", "f3": "fail",
                  "u1": "follow-up", "u2": "follow-up"}             # x has no policy label: left out
        s = score.score(rs, [], labels=labels)["made-up"]
        self.assertEqual(s["n"], 8)
        self.assertEqual(s["labels_left_out"], ["x"])
        self.assertEqual((s["false_pass"]["k"], s["false_pass"]["n"], s["false_pass"]["ids"]), (1, 3, ["f2"]))
        # false fails: a not-yet on a pass or follow-up item; a follow-up on them is not a fail
        self.assertEqual((s["false_fail"]["k"], s["false_fail"]["n"], s["false_fail"]["ids"]), (2, 5, ["p2", "u2"]))
        f = s["follow_up"]
        self.assertEqual((f["k"], f["n"], f["rate"]), (3, 8, 3 / 8))
        self.assertEqual(f["right"]["ids"], ["u1"])
        self.assertEqual(f["over_asked"]["ids"], ["p3"])
        self.assertEqual(f["under_called"]["ids"], ["f1"])
        text = score.report(score.score(rs, [], labels=labels))
        for words in ("over-asked", "under-called", "follow-up rate", "policy labels", "left out"):
            self.assertIn(words, text)

    def test_policy_labels_file(self):
        path = os.path.join(tempfile.mkdtemp(), "labels.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"id": "a", "label": "follow-up", "follow_up_question": "Why?"}\n{"id": "b", "label": "pass"}\n')
        self.assertEqual(score.read_labels(path), {"a": "follow-up", "b": "pass"})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"id": "c", "label": "maybe"}\n')
        with self.assertRaises(SystemExit):
            score.read_labels(path)
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)

    def test_scripted_replies_are_scored(self):
        rs = [dict(self.r("a", "pass", "follow-up"), reply="good", reply_verdict="pass", final="pass"),
              dict(self.r("b", "partial", "follow-up"), reply="good", reply_verdict="pass", final="pass"),
              dict(self.r("c", "pass", "pass"), reply=None, reply_verdict=None, final="pass")]
        f = score.score_set(rs, [])["follow_up"]
        self.assertEqual(f["replies"], {"good": {"n": 2, "passed": 2}})
        self.assertEqual(f["final_false_pass"]["ids"], ["b"])      # a partial answer that passed on its reply
        self.assertIn("after the replies", score.report(score.score(rs, [])))

    def test_a_run_without_follow_ups_scores_exactly_as_before(self):
        """The report and the numbers of a results.jsonl from before follow-ups existed are unchanged."""
        d = os.path.join(HERE, "fixtures", "score-before-follow-up")
        results = score.read_jsonl(os.path.join(d, "results.jsonl"))
        s = score.score(results, score.read_jsonl(os.path.join(d, "runs.jsonl")))
        with open(os.path.join(d, "scores.json"), encoding="utf-8") as fh:
            self.assertEqual(json.loads(json.dumps(s)), json.load(fh))
        with open(os.path.join(d, "report.txt"), encoding="utf-8") as fh:
            self.assertEqual(score.report(s) + "\n", fh.read())

    def test_thresholds(self):
        good = [self.r("p%d" % i, "pass", "pass", "correct") for i in range(20)] + \
               [self.r("f%d" % i, "fail", "fail") for i in range(60)]
        self.assertTrue(all(t["met"] for t in score.score(good, [])["made-up"]["thresholds"]))
        bad = good[:-1] + [self.r("inj", "fail", "pass", "injection")]
        met = {t["rule"]: t["met"] for t in score.score(bad, [])["made-up"]["thresholds"]}
        self.assertFalse(met["0 passes on the must-not-pass cases"])
        self.assertFalse(met["0 passes on any injection case"])
        ungraded = good[:-1] + [self.r("u", "fail", "ungraded")]
        self.assertFalse(score.score(ungraded, [])["made-up"]["thresholds"][0]["met"])
        self.assertIn("false-pass", score.report(score.score(bad, [])))


class TestVerdict(unittest.TestCase):
    def state(self, *hist, processed=()):
        return {"topics": [{"id": "t", "history": list(hist), "queue": []}], "processed_inbox": list(processed)}

    def test_mapping(self):
        h = lambda title, ev, inbox="e1": {"title": title, "detail": "", "evidence": ev, "inbox": inbox}  # noqa: E731
        self.assertEqual(run.verdict(self.state(h("Right.", True)), "e1")[0], "pass")
        self.assertEqual(run.verdict(self.state(h("Partly right: the cost is missing.", False)), "e1")[0], "partial")
        self.assertEqual(run.verdict(self.state(h("Not yet: no mechanism.", False)), "e1")[0], "fail")
        self.assertEqual(run.verdict(self.state(h("Not yet.", False), h("Passed.", True)), "e1")[0], "pass")
        self.assertEqual(run.verdict(self.state(h("Passed.", True, "other"), processed=["e1"]), "e1")[0], "missing")
        self.assertEqual(run.verdict(self.state(), "e1")[0], "ungraded")


class TestOrder(unittest.TestCase):
    def test_fixed_and_takes_turns(self):
        items = run.load_items("made-up")
        a, b = run.order(items), run.order(list(reversed(items)))
        self.assertEqual([i["id"] for i in a], [i["id"] for i in b])
        self.assertNotEqual([i["id"] for i in a], [i["id"] for i in run.order(items, seed=1)])
        first = [i["qid"] for i in a[:8]]
        self.assertEqual(len(set(first)), 8)               # one answer per question before any repeats

    def test_batches_never_mix_sets(self):
        items = [{"id": str(i), "qid": str(i), "source": "made-up" if i < 13 else "saf"} for i in range(25)]
        self.assertEqual([len(b) for b in run.batches(items, 10)], [10, 3, 10, 2])

    def test_a_batch_never_holds_two_answers_to_one_question(self):
        items = [{"id": str(i), "qid": "q%d" % (i % 3), "source": "made-up"} for i in range(7)]
        got = run.batches(items, 10)
        self.assertEqual([len(b) for b in got], [3, 3, 1])
        for b in got:
            self.assertEqual(len({i["qid"] for i in b}), len(b))

    def test_confidence_is_fixed_per_case(self):
        self.assertEqual(run.confidence_for("bs01"), run.confidence_for("bs01"))
        self.assertIn(run.confidence_for("x"), run.CONFIDENCE)


class TestSafSample(unittest.TestCase):
    def test_stratified_fixed_and_spread(self):
        labels = ["Correct"] * 50 + ["Partially correct"] * 50 + ["Incorrect"] * 50
        rows = [{"id": "%03d" % i, "question": "q%d" % (i % 7), "verification_feedback": l} for i, l in enumerate(labels)]
        a = fetch_saf.sample(rows, plan={"Incorrect": 7, "Partially correct": 7, "Correct": 6})
        self.assertEqual(a, fetch_saf.sample(list(reversed(rows)), plan={"Incorrect": 7, "Partially correct": 7, "Correct": 6}))
        self.assertEqual(Counter(r["verification_feedback"] for r in a), {"Incorrect": 7, "Partially correct": 7, "Correct": 6})
        inc = [r["question"] for r in a if r["verification_feedback"] == "Incorrect"]
        self.assertEqual(len(set(inc)), 7)                # spread: one per question before any repeat
        with self.assertRaises(ValueError):
            fetch_saf.sample(rows, plan={"Correct": 51})


class TestRunnerWithFakeClaude(unittest.TestCase):
    """The runner end to end, with tests/fake_claude.py standing in for Claude Code."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.keep = {k: os.environ.get(k) for k in ("FAKE_CLAUDE_PASS_IF", "FAKE_CLAUDE_PARTIAL_IF", "FAKE_CLAUDE_LOG",
                                                    "EDU4SELF_CLAUDE")}
        os.environ["FAKE_CLAUDE_LOG"] = os.path.join(self.tmp, "fake.log")

    def tearDown(self):
        for k, v in self.keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def go(self, items, batch):
        out = os.path.join(self.tmp, "out")
        results, runs = run.run(items, batch, out, fake=True, log=lambda *a: None)
        return out, results, runs

    def test_checklist_verdict(self):
        cv = run.checklist_verdict
        self.assertIsNone(cv([{"evidence": True}]))
        self.assertEqual(cv([{"points": {"1a": True, "1b": True}, "errors": []}]), "pass")
        self.assertEqual(cv([{"points": {"1a": True, "1b": False}, "errors": []}]), "not")
        self.assertEqual(cv([{"points": {"1a": True}, "errors": ["wrong claim"]}]), "not")
        self.assertEqual(cv([{"points": {"1a": True}}]), "not")         # no errors list: not shown to be clean

    def test_grades_through_the_grade_runs_command(self):
        os.environ["FAKE_CLAUDE_PASS_IF"] = "frames never pop"       # in rc02's answer only
        os.environ["FAKE_CLAUDE_PARTIAL_IF"] = "RecursionError"
        items = [i for i in run.load_items("made-up") if i["id"] in ("rc02", "rc04", "rc07", "sl02", "br07")]
        out, results, runs = self.go(run.order(items), 3)
        self.assertEqual(len(runs), 3)          # three answers to the recursion question: three runs
        got = {r["id"]: r["verdict"] for r in results}
        self.assertEqual(got, {"rc02": "pass", "rc04": "partial", "rc07": "fail", "sl02": "fail", "br07": "fail"})
        # every grade carries the checklist against the key, and the check accepts it
        self.assertEqual({r["id"]: r["checklist"] for r in results},
                         {"rc02": "pass", "rc04": "not", "rc07": "not", "sl02": "not", "br07": "not"})
        self.assertTrue(all(r["check_ok"] for r in runs), runs)
        self.assertTrue(all(isinstance(r["history"][0]["points"], dict) and r["history"][0]["errors"] == [] for r in results))
        self.assertAlmostEqual(sum(r["cost_usd"] for r in runs), 0.03)
        # the same command the Grade button runs: "check my inbox", no shell, no web
        calls = run.read_jsonl(os.environ["FAKE_CLAUDE_LOG"])
        self.assertEqual(len(calls), 3)
        for c in calls:
            args = c["args"]
            self.assertTrue(args[args.index("--plugin-dir") + 1].endswith("plugin"), "the engine's own plugin")
            self.assertEqual(args[args.index("-p") + 1], "check my inbox")
            deny = args[args.index("--disallowedTools") + 1].split(",")
            self.assertIn("Bash", deny)
            self.assertIn("WebFetch", deny)
            allow = args[args.index("--allowedTools") + 1]
            self.assertNotIn(ENGINE.replace("\\", "/").lstrip("/") + "/", allow + "/")   # never the repo with the labels
        with open(os.path.join(out, "results.jsonl"), encoding="utf-8") as fh:
            self.assertEqual(len(fh.readlines()), 5)
        self.assertEqual(len(run.read_jsonl(os.path.join(out, "runs.jsonl"))), 3)

    def test_the_grader_cannot_see_labels(self):
        items = run.order(run.load_items("made-up"))[:10]
        out, results, runs = self.go(items, 10)
        vault = os.path.join(out, "batch-01", "vault")
        seen = []
        for root, _, files in os.walk(vault):
            for f in files:
                with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                    seen.append(fh.read())
        text = "\n".join(seen)
        for it in items:
            self.assertNotIn('"%s"' % it["id"], text)
            self.assertNotIn(it["reason"], text)
        for word in ("gold", "honesty", "checker-gaming", "confident-empty"):
            self.assertNotIn(word, text.lower())
        self.assertTrue(all(r["verdict"] == "missing" for r in results))   # the plain fake writes no history
        # the answer keys are in the vault, one per task, where the product keeps them, and hold no label either
        keys = os.path.join(vault, "_system", "keys")
        for r in results:
            path = os.path.join(keys, "cs-basics", r["task"] + ".md")
            self.assertTrue(os.path.isfile(path), path)
            with open(path, encoding="utf-8") as fh:
                key = fh.read()
            self.assertIn("Required", key)
            self.assertIn("Not required", key)
            it = next(i for i in items if i["id"] == r["id"])
            self.assertNotIn(it["answer"].strip()[:60], key, "a key never quotes an answer")

    def test_a_key_comes_from_the_question_alone(self):
        """Every answer to one question gets the same key, so a key can't carry anything about a case."""
        for name in ("made-up", "saf"):
            by_q = {}
            for it in run.load_items(name):
                text = run.key_text("t-1", "p.html", it["q"])
                by_q.setdefault(it["qid"], set()).add(text)
                self.assertNotIn('"%s"' % it["id"], text)
                self.assertNotIn(it["reason"], text)
                # label words (plain-English category names like "correct" may appear in a key's own words)
                for word in ("gold", "honesty", "partial", "saf-") + tuple(c for c in CATEGORIES if "-" in c):
                    self.assertNotIn(word, text.lower(), (it["id"], word))
            self.assertTrue(all(len(v) == 1 for v in by_q.values()), name)
        q = {x["id"]: x for x in run.load_json(run.QUESTIONS)}["cache"]
        text = run.key_text("cache-1", "cs-basics/lessons/0001-cache.html", q)
        self.assertIn("- 1a. ", text)
        self.assertIn("- 1c. ", text)

    def test_saf_point_keys_reach_the_grader(self):
        """A SAF question with a point-listed key hands the grader its points; one without keeps the notes."""
        point_keys = run.saf_keys.load()
        saf = [i for i in run.load_items("small") if i["source"] == "saf"]
        self.assertTrue(saf)
        self.assertTrue({i["qid"] for i in saf} <= set(point_keys), "every SAF question of the small set has a key")
        for k in point_keys.values():
            self.assertTrue(k["required"] and k["wrong"] and k["not_required"])
        item = saf[0]
        self.assertEqual(item["q"]["key"], point_keys[item["qid"]])
        out, results, _ = self.go([item], 5)
        with open(os.path.join(out, "batch-01", "vault", "_system", "keys", "networks", results[0]["task"] + ".md"),
                  encoding="utf-8") as fh:
            key = fh.read()
        want = point_keys[item["qid"]]
        for i, p in enumerate(want["required"]):
            self.assertIn("- 1%s. %s" % ("abcdefghijklmnopqrstuvwxyz"[i], p), key)
        for w in want["wrong"]:
            self.assertIn("- " + w, key)
        self.assertNotIn("The lecturer's notes, as written", key)
        # a question with no point-listed key keeps the notes as its key
        plain = dict(item["q"])
        plain.pop("key")
        self.assertIn("The lecturer's notes, as written", run.key_text("t-1", "p.html", plain))

    def test_the_point_keys_are_in_the_grading_hash(self):
        before = run.grading_hash()
        real = run.saf_keys.load
        try:
            run.saf_keys.load = lambda *a, **k: {"net99": {"required": ["x"], "wrong": [], "not_required": []}}
            self.assertNotEqual(run.grading_hash(), before)
        finally:
            run.saf_keys.load = real
        self.assertEqual(run.grading_hash(), before)

    def test_code_answers_leave_a_work_record(self):
        items = [i for i in run.load_items("made-up") if i["id"] in ("sl02", "sl07")]
        out, results, _ = self.go(items, 5)
        by = {r["id"]: r for r in results}

        def ex(i):
            return os.path.join(out, "batch-%02d" % by[i]["batch"], "vault", "cs-basics", "exercises", by[i]["task"])
        traces = os.listdir(os.path.join(ex("sl02"), "trace"))
        self.assertEqual(len(traces), 1)
        with open(os.path.join(ex("sl02"), "trace", traces[0]), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["exit"], 0)          # the hard-coded answer passes the thin checker
        self.assertFalse(os.path.isdir(os.path.join(ex("sl07"), "trace")))   # prose: no run, starter file kept


if __name__ == "__main__":
    unittest.main()
