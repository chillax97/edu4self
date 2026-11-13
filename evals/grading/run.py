#!/usr/bin/env python3
"""The honesty test's runner: grade labelled answers through the product's real grading path.

For each batch it makes a fresh vault with `edu4self init`, adds one task per answer (a lesson page,
plus a checker folder for code tasks), submits the answers to the inbox with the dashboard's own
code (server.clean_submission + server.append_inbox), then starts the same fenced Claude Code run the
Grade button starts (server.claude_args(server.GRADE_PROMPT, None, "grade")), in the vault, and reads
each verdict back from state.json. Nothing the grader can read names the gold label, the category or the
case id: those stay in the output folder, outside the vault. The grading run may read the engine
folder, and this one holds the labels (evals/), so the runner works from a copy of the engine without
evals/, tests/ and docs media, in a neutrally named temp folder: same code, nothing to peek at.

    python3 evals/grading/run.py --fake                    # the whole set, with the test stand-in (free)
    python3 evals/grading/run.py --limit 10 --yes          # 10 cases, real Claude Code (costs money)
    python3 evals/grading/run.py --set saf --batch 10 --yes

Output (--out, default evals/grading/out/<time>/): results.jsonl (one line per answer), runs.jsonl (one
line per Claude run, with its $ cost), and batch-NN/ (the stream, the vault as Claude left it).
Then: python3 evals/grading/score.py <out folder>. Standard library only.
"""
import argparse
import hashlib
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(os.path.dirname(HERE))
FAKE = os.path.join(ENGINE, "tests", "fake_claude.py")
SETS = {"made-up": os.path.join(HERE, "cases.jsonl"), "saf": os.path.join(HERE, "saf", "sample.jsonl")}
# Named subsets of both sets: a file of case ids, one per line (# starts a comment). See the file for why each id is in.
SUBSETS = {"small": os.path.join(HERE, "small.txt")}
QUESTIONS = os.path.join(HERE, "questions.json")
# Left out of the engine copy the grader runs from: the labels, the tests and docs media.
NOT_COPIED = ("evals", "tests", ".git", ".github", "node_modules", "images", "video", "__pycache__")
PORT = 4799                       # only written into the vault's CLAUDE.md; no server is started
SEED = 2026
TOPICS = {"made-up": ("cs-basics", "Computer science basics", "#3b6fd4"),
          "saf": ("networks", "Communication networks", "#c2410c")}
CONFIDENCE = ("guessed", "shaky", "solid")

# A grade is a history entry whose `inbox` is the submission's id (PROTOCOL.md section 1 and 3).
# evidence: true is what the product counts as a pass. The product has no partial verdict, so a
# non-pass is split into partial / fail by these words in the entry's title and detail: a heuristic,
# used only for the 3-class kappa. The false-pass rate never depends on it. "Not yet" is the product's
# word for any non-pass, so it is not a partial word.
PARTIAL_WORDS = re.compile(
    r"\b(partly|partial(ly)?|half|halfway|mostly|most of|some of|part of it|one of (the )?(two|three|2|3)|"
    r"almost|nearly|incomplete|on the right track|right idea|good start|not quite|one part|"
    r"the first part|the second part)\b", re.I)


# ---------------------------------------------------------------- the cases

def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def subset_ids(name):
    with open(SUBSETS[name], encoding="utf-8") as fh:
        return [l.split("#", 1)[0].strip() for l in fh if l.split("#", 1)[0].strip()]


def load_items(which):
    """[item] for the chosen set(s), each with `source`. Made-up cases get their question from questions.json.
    A named subset (SUBSETS) is those ids from both sets."""
    if which in SUBSETS:
        want = subset_ids(which)
        by_id = {it["id"]: it for it in load_items("all")}
        missing = [i for i in want if i not in by_id]
        if missing:
            sys.exit("%s names unknown case ids: %s" % (SUBSETS[which], ", ".join(missing)))
        return [by_id[i] for i in want]
    questions = {q["id"]: q for q in load_json(QUESTIONS)}
    items = []
    for name in (["made-up", "saf"] if which == "all" else [which]):
        path = SETS[name]
        if not os.path.isfile(path):
            sys.exit("%s is missing. For SAF, run: python3 evals/grading/saf/fetch_saf.py" % path)
        for it in read_jsonl(path):
            it = dict(it, source=name)
            if name == "made-up":
                it["q"] = questions[it["qid"]]
            else:                 # SAF: the lesson the learner read is the reference answer, as lecture notes
                it["q"] = {"id": it["qid"], "title": it.get("title") or "Networks question",
                           "lesson": ["Notes from the lecture on this question:"] + it["reference"].split("\n"),
                           "question": it["question"], "hint": None, "reference": it["reference"]}
            items.append(it)
    return items


def order(items, seed=SEED):
    """A fixed shuffle that takes turns across questions, so a batch rarely holds two answers to one question.
    Each set keeps to itself (made-up first, then SAF), so no run mixes the two."""
    out = []
    for src in ("made-up", "saf"):
        out += _order([i for i in items if i.get("source", "made-up") == src], seed)
    return out


def _order(items, seed):
    rng = random.Random(seed)
    groups = OrderedDict()
    for it in sorted(items, key=lambda i: i["id"]):
        groups.setdefault(it["qid"], []).append(it)
    for g in groups.values():
        rng.shuffle(g)
    keys = list(groups)
    rng.shuffle(keys)
    out = []
    while any(groups.values()):
        for k in keys:
            if groups[k]:
                out.append(groups[k].pop())
    return out


def batches(items, size):
    """Runs of up to size answers; a new run starts where the set changes, or where a question would repeat.
    A real inbox rarely holds two answers to one question, and a grader that sees two compares them."""
    out = []
    for it in items:
        if (not out or len(out[-1]) == size or out[-1][-1].get("source") != it.get("source")
                or any(o["qid"] == it["qid"] for o in out[-1])):
            out.append([])
        out[-1].append(it)
    return out


def confidence_for(item_id):
    """The 'How sure are you?' the dashboard requires: fixed per case, independent of the gold label."""
    return CONFIDENCE[int(hashlib.sha256(item_id.encode()).hexdigest(), 16) % 3]


def is_code(answer):
    return bool(re.match(r"\s*(def |import |from \w+ import )", answer))


# ---------------------------------------------------------------- the engine copy

SERVER = {"mod": None, "engine": None}


def copy_engine(dest):
    """Copy the engine (the code the dashboard runs) without NOT_COPIED. Returns dest."""
    shutil.copytree(ENGINE, dest, ignore=shutil.ignore_patterns(*NOT_COPIED))
    return dest


def server_from(engine):
    """The copy's app/server.py as a module of its own, so its ENGINE (and the Read rule built from it)
    is the copy. One module per engine folder."""
    if SERVER["engine"] != engine:
        import importlib.util
        spec = importlib.util.spec_from_file_location("edu4self_eval_server", os.path.join(engine, "app", "server.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        SERVER.update(mod=mod, engine=engine)
    return SERVER["mod"]


# ---------------------------------------------------------------- the vault

def key_text(task_id, page, q):
    """The task's answer key (PROTOCOL.md section 7), built from the question alone, never from a case: the same
    for every answer to that question. Made-up questions carry a written key in questions.json; a SAF key is the
    lecturer's notes (the lesson text), as written, under the general rule."""
    out = ["# Answer key: %s" % task_id, "", "For %s." % page, "", "## 1. %s" % " ".join(q["question"].split()), ""]
    k = q.get("key")
    if k:
        out.append("Required (each one must be in the answer, in any words):")
        out += ["- 1%s. %s" % ("abcdefghijklmnopqrstuvwxyz"[i], p) for i, p in enumerate(k["required"])]
        wrong, extra = k["wrong"], k["not_required"]
    else:
        out += ["Required (each one must be in the answer, in any words): every part the question asks for, as the",
                "lecturer's notes below answer it. Where the notes say one of several is enough, one is enough.", "",
                "The lecturer's notes, as written:", ""]
        out += ["> " + line.rstrip() if line.strip() else ">" for line in q["reference"].strip().splitlines()]
        wrong = ["Anything that contradicts the notes."]
        extra = ["Details and examples in the notes that the question doesn't ask for, and the other alternatives "
                 "where the notes say one is enough."]
    out += ["", "Wrong answers to watch for (stated as fact, each is an error):"] + ["- " + w for w in wrong]
    out += ["", "Not required (never fail an answer for leaving these out):"] + ["- " + x for x in extra]
    return "\n".join(out) + "\n"


def lesson_html(n, q):
    paras = "\n".join("<p>%s</p>" % html.escape(p) for p in q["lesson"] if p.strip())
    hint = ("<div class=\"note\"><strong>Stuck?</strong> %s</div>\n" % html.escape(q["hint"])) if q.get("hint") else ""
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<title>Lesson %02d - %s</title>\n"
            "</head>\n<body>\n<h1>%s</h1>\n%s\n%s<h2>Exercise, from memory</h2>\n<p>%s</p>\n</body>\n</html>\n"
            % (n, html.escape(q["title"]), html.escape(q["title"]), paras, hint, html.escape(q["question"])))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def build_vault(engine, vault, batch, env):
    """A fresh vault with one task per item. Returns {item id: (topic id, task id, question label)}."""
    subprocess.run([sys.executable, os.path.join(engine, "edu4self"), "init", vault, "--no-example", "--port", str(PORT)],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    server = server_from(engine)
    server.configure(vault, PORT)                 # also installs _system/edu_trace.py, which checkers need
    sp = os.path.join(vault, "_system", "state.json")
    state = load_json(sp)
    tasks, topics, lesson_no = {}, OrderedDict(), {}
    for it in batch:
        tid_topic, title, color = TOPICS[it["source"]]
        topic = topics.get(tid_topic)
        if topic is None:
            topic = topics[tid_topic] = {
                "id": tid_topic, "title": title, "tagline": "Short lessons, each with one question answered from memory.",
                "path": tid_topic, "color": color, "phase": "Lessons", "block": "lessons",
                "milestones": [{"id": "M1", "title": "Core ideas", "goal": "Explain each idea without notes",
                                "estimate": "a few lessons", "status": "active",
                                "steps": [{"title": "Answer each lesson's question", "done": False, "current": True}]}],
                "queue": [], "regions": [], "history": []}
            root = os.path.join(vault, tid_topic)
            write(os.path.join(root, "MISSION.md"), "# %s\n\nLearn the core ideas well enough to explain them without notes.\n" % title)
            write(os.path.join(root, "NOTES.md"), "# Notes\n")
            write(os.path.join(root, "GLOSSARY.md"), "# Glossary\n")
            write(os.path.join(root, "Dashboard.md"), "# %s\n" % title)
            os.makedirs(os.path.join(root, "learning-records"), exist_ok=True)
            # a topic's shared lesson parts, as the first lesson of a real topic leaves them (a redo links them)
            shutil.copytree(os.path.join(engine, "template", "how-learning-works", "assets"), os.path.join(root, "assets"))
        q = it["q"]
        key = (tid_topic, q["id"])
        if key not in lesson_no:
            lesson_no[key] = len([k for k in lesson_no if k[0] == tid_topic]) + 1
            write(os.path.join(vault, tid_topic, "lessons", "%04d-%s.html" % (lesson_no[key], q["id"])),
                  lesson_html(lesson_no[key], q))
        n = lesson_no[key]
        task_id = "%s-%d" % (q["id"], sum(1 for t in topic["queue"] if t["id"].startswith(q["id"] + "-")) + 1)
        page = "%s/lessons/%04d-%s.html" % (tid_topic, n, q["id"])
        write(os.path.join(vault, "_system", "keys", tid_topic, task_id + ".md"), key_text(task_id, page, q))
        task = {"id": task_id, "kind": "lesson", "status": "todo", "label": "Lesson %02d" % n, "title": q["title"],
                "why": "One idea, checked from memory.",
                "href": "/vault/%s/lessons/%04d-%s.html" % (tid_topic, n, q["id"]), "effort": "10 min · 1 exercise",
                "submit": {"type": "answers", "intro": "Close the lesson first and answer from memory.",
                           "fields": [q["question"]]}}
        if q.get("files"):
            ex = "%s/exercises/%s" % (tid_topic, task_id)
            task["exercise"] = ex
            folder = os.path.join(vault, *ex.split("/"))
            for name, text in q["files"].items():
                write(os.path.join(folder, name), text)
            if q.get("hint"):
                write(os.path.join(folder, "HINTS.md"), "# Hints\n\n## 1 · where to start\n\n%s\n" % q["hint"])
            if is_code(it["answer"]):             # the learner's file, and one checker run in the work record
                write(os.path.join(folder, "solution.py"), it["answer"] + "\n")
                subprocess.run([sys.executable, "check.py"], cwd=folder, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30, env=env)
        topic["queue"].append(task)
        tasks[it["id"]] = (tid_topic, task_id, q["question"])
    state["topics"] = list(topics.values())
    with open(sp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return tasks


def submit(engine, vault, batch, tasks):
    """Each answer goes to the inbox the way the dashboard's Submit does. Returns {inbox id: item id}."""
    server = server_from(engine)
    server.configure(vault, PORT)
    ids = {}
    for it in batch:
        topic, task_id, label = tasks[it["id"]]
        state = server.read_state_safe()
        entry = server.clean_submission({"topic": topic, "task": task_id, "kind": "answers", "title": it["q"]["title"],
                                         "fields": {label: it["answer"]}, "note": "", "honor": False,
                                         "confidence": confidence_for(it["id"])}, state)
        server.append_inbox(entry)
        ids[entry["id"]] = it["id"]
    return ids


def check(engine, vault, env):
    r = subprocess.run([sys.executable, os.path.join(engine, "edu4self"), "check", "--vault", vault], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, env=env)
    return r.returncode == 0, r.stdout


# ---------------------------------------------------------------- the grading run

def grade(engine, vault, stream_path, timeout):
    """Start the Grade button's run in the vault and wait for it. Returns the run's summary."""
    server = server_from(engine)
    server.configure(vault, PORT)
    cmd = server.claude_args(server.GRADE_PROMPT, None, "grade")
    if not cmd[0]:
        raise SystemExit("Claude Code isn't installed (or isn't on the PATH)")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=vault, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    result, turns = None, 0
    with open(stream_path, "w", encoding="utf-8") as raw:
        for line in proc.stdout:
            raw.write(line)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("type") == "assistant":
                turns += 1
            elif msg.get("type") == "result":
                result = msg
    err = proc.stderr.read()
    code = proc.wait()
    timer.cancel()
    result = result or {}
    return {"exit": code, "timed_out": code < 0, "is_error": bool(result.get("is_error")) or code != 0,
            "cost_usd": result.get("total_cost_usd"), "duration_ms": result.get("duration_ms"),
            "num_turns": result.get("num_turns", turns), "usage": result.get("usage"),
            "wall_s": round(time.time() - t0, 1), "stderr_tail": err.strip().splitlines()[-3:]}


def verdict(state, entry_id):
    """(verdict, the history entries that grade this submission). verdict: pass | partial | fail |
    missing (processed, no history entry names it) | ungraded (not processed)."""
    hist = [h for t in state.get("topics", []) for h in t.get("history", [])
            if isinstance(h, dict) and h.get("inbox") == entry_id]
    if not hist:
        return ("missing" if entry_id in state.get("processed_inbox", []) else "ungraded"), []
    if any(h.get("evidence") is True for h in hist):
        return "pass", hist
    text = " ".join("%s %s" % (h.get("title", ""), h.get("detail", "")) for h in hist)
    return ("partial" if PARTIAL_WORDS.search(text) else "fail"), hist


def task_status(state, topic, task_id):
    for t in state.get("topics", []):
        if t.get("id") == topic:
            for task in t.get("queue", []):
                if task.get("id") == task_id:
                    return task.get("status")
    return None


# ---------------------------------------------------------------- main

def run(items, batch_size, out, fake=False, timeout=1800, log=print):
    """Grade items in batches. Writes results.jsonl and runs.jsonl in out; returns (results, runs)."""
    os.makedirs(out, exist_ok=True)
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="edu4self-"))   # macOS: /var is /private/var
    env = dict(os.environ, EDU4SELF_CONFIG_HOME=os.path.join(tmp, "cfg"))   # init must not touch the user's settings
    engine = copy_engine(os.path.join(tmp, "edu4self"))
    if fake:
        os.environ["EDU4SELF_CLAUDE"] = FAKE
    results, runs = [], []
    try:
        for b, batch in enumerate(batches(items, batch_size), 1):
            vault = os.path.join(tmp, "vault-%02d" % b)
            tasks = build_vault(engine, vault, batch, env)
            ok, text = check(engine, vault, env)
            if not ok:
                raise SystemExit("the test vault fails its own check before grading:\n" + text)
            ids = submit(engine, vault, batch, tasks)
            bdir = os.path.join(out, "batch-%02d" % b)
            os.makedirs(bdir, exist_ok=True)
            summary = grade(engine, vault, os.path.join(bdir, "stream.jsonl"), timeout)
            summary["check_ok"], _ = check(engine, vault, env)
            summary.update(batch=b, items=len(batch), item_ids=[it["id"] for it in batch])
            runs.append(summary)
            state = load_json(os.path.join(vault, "_system", "state.json"))
            share = summary["cost_usd"] / len(batch) if isinstance(summary["cost_usd"], (int, float)) else None
            for entry_id, item_id in ids.items():
                it = next(i for i in batch if i["id"] == item_id)
                v, hist = verdict(state, entry_id)
                topic, task_id, _ = tasks[item_id]
                results.append({"id": item_id, "source": it["source"], "qid": it["qid"], "category": it["category"],
                                "gold": it["gold"], "verdict": v, "batch": b, "inbox": entry_id, "task": task_id,
                                "confidence": confidence_for(item_id), "task_status": task_status(state, topic, task_id),
                                "history": [{k: h.get(k) for k in ("title", "detail", "evidence", "points")} for h in hist],
                                "cost_share_usd": share})
            shutil.copytree(vault, os.path.join(bdir, "vault"), ignore=shutil.ignore_patterns("__pycache__"))
            with open(os.path.join(bdir, "inbox-map.json"), "w", encoding="utf-8") as fh:
                json.dump(ids, fh, indent=1)
            cost = summary["cost_usd"]
            log("batch %d: %d items · %s · %s s · %s turns%s%s" % (
                b, len(batch), "$%.4f" % cost if isinstance(cost, (int, float)) else "$?", summary["wall_s"],
                summary["num_turns"], "" if summary["check_ok"] else " · CHECK FAILED",
                " · ERROR" if summary["is_error"] else ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if fake:
            os.environ.pop("EDU4SELF_CLAUDE", None)
    with open(os.path.join(out, "results.jsonl"), "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "runs.jsonl"), "w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = sum(r["cost_usd"] for r in runs if isinstance(r["cost_usd"], (int, float)))
    log("total: %d items in %d run(s) · $%.4f · %.1f s" % (len(results), len(runs), total, sum(r["wall_s"] for r in runs)))
    return results, runs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--set", choices=["made-up", "saf", "all"] + sorted(SUBSETS), default="made-up",
                   help="which cases (default made-up; small: the fixed set in small.txt)")
    p.add_argument("--limit", type=int, help="grade only the first N cases of the fixed order")
    p.add_argument("--batch", type=int, default=10, help="answers per Claude run (default 10, a typical inbox)")
    p.add_argument("--fake", action="store_true", help="use the repo's fake claude (tests; free, verdicts mean nothing)")
    p.add_argument("--seed", type=int, default=SEED, help="the fixed order's seed (default %d)" % SEED)
    p.add_argument("--timeout", type=int, default=1800, help="seconds per Claude run before it is stopped")
    p.add_argument("--out", help="output folder (default evals/grading/out/<time>)")
    p.add_argument("--yes", action="store_true", help="really run Claude Code (each run costs money)")
    a = p.parse_args(argv)
    items = order(load_items(a.set), a.seed)
    if a.limit:
        items = items[:a.limit]
    if not items or a.batch < 1:
        sys.exit("nothing to grade")
    n_runs = len(batches(items, a.batch))
    if not a.fake:
        sys.path.insert(0, os.path.join(ENGINE, "app"))
        import server
        ready = server.claude_ready()
        if ready["problem"]:
            sys.exit("Claude Code is %s: %s" % (ready["problem"], ready["detail"] or "run `claude auth login`"))
        if not a.yes:
            sys.exit("This would start %d real Claude Code run(s) for %d answers, on your account. "
                     "Add --yes to go ahead, or --fake to try it free." % (n_runs, len(items)))
    out = a.out or os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S") + ("-fake" if a.fake else ""))
    print("grading %d answers in %d run(s) of up to %d -> %s" % (len(items), n_runs, a.batch, out))
    run(items, a.batch, out, fake=a.fake, timeout=a.timeout)
    print("score it: python3 %s %s" % (os.path.relpath(os.path.join(HERE, "score.py")), out))


if __name__ == "__main__":
    main()
