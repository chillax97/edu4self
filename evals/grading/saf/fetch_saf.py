#!/usr/bin/env python3
"""Fetch the SAF English set and write a fixed, stratified sample of 100 answers for the honesty test.

SAF: "Your Answer is Incorrect... Would you like to know why? Introducing a Bilingual Short Answer
Feedback Dataset", Filighera, Parihar, Steuer, Meuser and Ochs, ACL 2022
(https://aclanthology.org/2022.acl-long.587). License CC BY 4.0, see LICENSE.md in this folder.
Source: the authors' Hugging Face organisation, Short-Answer-Feedback/saf_communication_networks_english,
read through Hugging Face's dataset viewer API (JSON, so no parquet reader is needed).

    python3 evals/grading/saf/fetch_saf.py               # writes sample.jsonl and ids.txt here
    python3 evals/grading/saf/fetch_saf.py --out DIR

Labels map to edu4self's verdicts: Correct -> pass, Partially correct -> partial, Incorrect -> fail.
The sample is drawn from both test splits (854 answers to 31 questions) with a fixed seed: 35 fail,
35 partial, 30 pass (70 should not pass), each label spread across questions in turn, so no single
question fills a label (one question holds 32 of the 63 incorrect answers). The experts' written feedback is left out on
purpose: it states the grade, and nothing that states the grade may reach the grader.
Standard library only.
"""
import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

DATASET = "Short-Answer-Feedback/saf_communication_networks_english"
SPLITS = ("test_unseen_answers", "test_unseen_questions")   # both test splits: 31 questions
ROWS = "https://datasets-server.huggingface.co/rows"
INFO = "https://huggingface.co/api/datasets/" + DATASET
SEED = 2026
PLAN = {"Incorrect": 35, "Partially correct": 35, "Correct": 30}
GOLD = {"Correct": "pass", "Partially correct": "partial", "Incorrect": "fail"}
HERE = os.path.dirname(os.path.abspath(__file__))


def get_json(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "edu4self-honesty-test"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            if i == tries - 1:
                raise SystemExit("couldn't read %s: %s" % (url, exc))
            time.sleep(2 * (i + 1))       # the viewer API rate-limits bursts


def fetch_split(split):
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": split,
                                    "offset": offset, "length": 100})
        page = get_json(ROWS + "?" + q)
        rows += [dict(r["row"], split=split) for r in page["rows"]]
        offset += len(page["rows"])
        if not page["rows"] or offset >= page["num_rows_total"]:
            return rows
        time.sleep(0.5)


def sample(rows, seed=SEED, plan=PLAN):
    """The fixed stratified sample. Per label: group by question, shuffle each group and the order of the
    groups with the seed, then take one answer per question in turn until the label has its k.
    Raises if a label has fewer than k answers."""
    rng = random.Random(seed)
    out = []
    for label, k in plan.items():
        groups = {}
        for r in sorted((r for r in rows if r["verification_feedback"] == label), key=lambda r: r["id"]):
            groups.setdefault(r["question"], []).append(r)
        if sum(len(g) for g in groups.values()) < k:
            raise ValueError("only %d %r answers, need %d" % (sum(len(g) for g in groups.values()), label, k))
        keys = sorted(groups)
        for q in keys:
            rng.shuffle(groups[q])
        rng.shuffle(keys)
        picked = []
        while len(picked) < k:
            for q in keys:
                if groups[q] and len(picked) < k:
                    picked.append(groups[q].pop())
        out += picked
    return sorted(out, key=lambda r: r["id"])


def to_case(row, qids):
    qid = qids.setdefault(row["question"], "net%02d" % (len(qids) + 1))
    label = row["verification_feedback"]
    return {"id": "saf-" + row["id"][:12], "saf_id": row["id"], "qid": qid, "title": "Networks question %s" % qid[3:],
            "question": row["question"], "reference": row["reference_answer"], "answer": row["provided_answer"],
            "gold": GOLD[label], "category": "saf-" + GOLD[label],
            "reason": "SAF experts: %s, score %s" % (label, row["score"]), "saf_score": row["score"],
            "saf_split": row["split"]}


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch and sample the SAF English set.")
    p.add_argument("--out", default=HERE, help="folder for sample.jsonl and ids.txt (default: this folder)")
    a = p.parse_args(argv)
    info = get_json(INFO)
    print("dataset %s, revision %s, license tag: %s" % (
        DATASET, info.get("sha"), ", ".join(t for t in info.get("tags", []) if t.startswith("license:"))))
    rows = []
    for split in SPLITS:
        rows += fetch_split(split)
        print("%s: %d answers so far" % (split, len(rows)))
    picked = sample(rows)
    qids = {}
    for r in sorted({r["question"] for r in picked}):
        qids.setdefault(r, "net%02d" % (len(qids) + 1))
    cases = [to_case(r, qids) for r in picked]
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "sample.jsonl"), "w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(os.path.join(a.out, "ids.txt"), "w", encoding="utf-8") as fh:
        fh.write("# %s, splits %s, revision %s, seed %d\n" % (DATASET, " + ".join(SPLITS), info.get("sha"), SEED))
        fh.write("".join(c["saf_id"] + "\n" for c in cases))
    digest = hashlib.sha256(open(os.path.join(a.out, "sample.jsonl"), "rb").read()).hexdigest()[:16]
    print("wrote %d answers to %s (sha256 %s)" % (len(cases), os.path.join(a.out, "sample.jsonl"), digest))


if __name__ == "__main__":
    main()
