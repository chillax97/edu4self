import hashlib
import json
import os
import threading
import uuid
from datetime import datetime

import content
import mastery

INGEST_LOCK = threading.Lock()
FORBIDDEN = ("outcome", "passed", "skill", "level")
GRADABLE = ("answers", "done", "recall", "follow-up")
NEVER_GRADED = ("dispute", "skip", "withdraw")


def _forbidden(value, reasons):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN:
                reasons.append("%s is not allowed in a grade request" % key)
            _forbidden(item, reasons)
    elif isinstance(value, list):
        for item in value:
            _forbidden(item, reasons)


def _is_text(value, length=None):
    if not isinstance(value, str):
        return False
    if length is not None and not 1 <= len(value) <= length:
        return False
    return True


def _grader(value):
    if not isinstance(value, dict):
        return ["missing or invalid grader"]
    reasons = []
    for key in ("agent", "model", "session"):
        if not isinstance(value.get(key), str) or not value.get(key):
            reasons.append("grader.%s must be a non-empty string" % key)
    return reasons


def _when(grade):
    for field in ("answered", "ts"):
        try:
            return mastery.parse_iso(grade.get(field)).timestamp()
        except (TypeError, ValueError):
            continue
    return 0.0


def _latest_grade(lines):
    if not lines:
        return None
    return max(enumerate(lines), key=lambda pair: (_when(pair[1]), pair[0]))[1]


def _attempt_grades(grades, attempt):
    return [g for g in grades or []
            if isinstance(g, dict) and g.get("type") == "grade" and g.get("attempt") == attempt]


def _recall_entries(state, topic):
    found = []
    for entry in state.get("recall") or []:
        if isinstance(entry, dict):
            found.append(entry)
    for item in state.get("topics") or []:
        if isinstance(item, dict) and item.get("id") == topic:
            for entry in item.get("recall") or []:
                if isinstance(entry, dict):
                    found.append(entry)
    return found


def _split_key(key):
    if not isinstance(key, str) or "#" not in key:
        return None, None
    task, _, number = key.rpartition("#")
    try:
        return task, int(number)
    except ValueError:
        return None, None


def _section(sections, n):
    for section in sections or []:
        if section.n == n:
            return section
    return None


def _check_points(points, section, label, reasons):
    if not isinstance(points, dict):
        reasons.append("%s: points must be an object" % label)
        return
    required = list(section.points) if section is not None else None
    if required is not None and sorted(points) != sorted(required):
        reasons.append("%s: point ids must be %s" % (label, ", ".join(required) or "(none)"))
    for point, value in points.items():
        if type(value) is not bool:
            reasons.append("%s: point %s must be true or false" % (label, point))


def _check_errors(errors, label, reasons):
    if not isinstance(errors, list) or not all(isinstance(e, str) for e in errors):
        reasons.append("%s: errors must be a list of strings" % label)
        return False
    return True


def _section_question(item, section, qid, label, reasons):
    points = item.get("points")
    errors = item.get("errors")
    unsure = item.get("unsure", False)
    _check_points(points, section, label, reasons)
    if not _check_errors(errors, label, reasons):
        errors = []
    if not isinstance(unsure, bool):
        reasons.append("%s: unsure must be true or false" % label)
        unsure = False
    if not isinstance(points, dict):
        points = {}
    if unsure:
        outcome = "unsure"
    elif all(points.values()) and not errors:
        outcome = "met"
    else:
        outcome = "missed"
    return {"q": qid, "skill": section.skill if section is not None else None,
            "points": points, "errors": errors, "outcome": outcome}


def _answer_questions(questions, task, sections, reasons):
    keyed = {section.n: section for section in sections}
    if not isinstance(questions, list) or not questions:
        reasons.append("questions must be a non-empty list")
        return [], {}
    seen = set()
    stored = []
    raw = {}
    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            reasons.append("question %d must be an object" % (index + 1))
            continue
        extra = set(item) - {"n", "points", "errors", "unsure"}
        if extra:
            reasons.append("question %d has unexpected fields: %s" % (index + 1, ", ".join(sorted(extra))))
        n = item.get("n")
        if type(n) is not int:
            reasons.append("question %d: n must be a section number" % (index + 1))
            continue
        label = "question %d" % n
        section = keyed.get(n)
        if section is None:
            reasons.append("%s is not a section of %s.md" % (label, task))
        elif n in seen:
            reasons.append("%s appears more than once" % label)
        seen.add(n)
        raw[n] = item
        stored.append(_section_question(item, section, "%s#%d" % (task, n), label, reasons))
    if seen != set(keyed):
        missing = sorted(set(keyed) - seen)
        if missing:
            reasons.append("%s.md is missing sections: %s" % (task, ", ".join(str(n) for n in missing)))
    return stored, raw


def _recall_questions(questions, entry, tc, state, reasons):
    wanted = entry.get("recall")
    if not isinstance(wanted, list) or not all(isinstance(x, str) for x in wanted):
        reasons.append("the recall attempt has no recall list")
        return []
    if not isinstance(questions, list) or not questions:
        reasons.append("questions must be a non-empty list")
        return []
    known = {q.get("id"): q for q in _recall_entries(state, entry.get("topic"))}
    seen = set()
    stored = []
    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            reasons.append("question %d must be an object" % (index + 1))
            continue
        extra = set(item) - {"recall", "points", "errors", "unsure"}
        if extra:
            reasons.append("question %d has unexpected fields: %s" % (index + 1, ", ".join(sorted(extra))))
        rid = item.get("recall")
        if not isinstance(rid, str):
            reasons.append("question %d: recall must be a question id" % (index + 1))
            continue
        if rid in seen:
            reasons.append("recall question %s appears more than once" % rid)
        seen.add(rid)
        if rid not in wanted:
            reasons.append("recall question %s is not in this attempt" % rid)
            continue
        source = known.get(rid)
        if source is None:
            reasons.append("recall question %s is not in state.json" % rid)
            continue
        task, n = _split_key(source.get("key"))
        if task is None:
            reasons.append("recall question %s has no key <task>#<n>" % rid)
            continue
        section = _section(tc.keys.get(task), n)
        if section is None:
            reasons.append("recall question %s points to a missing key section %s#%d" % (rid, task, n))
        stored.append(_section_question(item, section, source["key"], "recall question %s" % rid, reasons))
        stored[-1]["recall"] = rid
    if seen != set(wanted):
        missing = sorted(set(wanted) - seen)
        if missing:
            reasons.append("recall questions not answered: %s" % ", ".join(missing))
    return stored


def _follow_up_questions(questions, entry, tc, grades, reasons):
    if not isinstance(questions, list) or len(questions) != 1:
        reasons.append("a follow-up reply has exactly one question")
        return [], None, False
    item = questions[0]
    if not isinstance(item, dict):
        reasons.append("question 1 must be an object")
        return [], None, False
    extra = set(item) - {"n", "points", "errors", "unsure"}
    if extra:
        reasons.append("question 1 has unexpected fields: %s" % ", ".join(sorted(extra)))
    ref = entry.get("ref")
    if not isinstance(ref, str):
        reasons.append("the follow-up reply has no original attempt")
        return [], None, False
    original = _latest_grade(_attempt_grades(grades, ref))
    if original is None:
        reasons.append("the original attempt %s has no grade" % ref)
        return [], None, False
    asked = original.get("follow_up")
    if not isinstance(asked, dict) or not isinstance(asked.get("q"), str):
        reasons.append("the original grade %s asked no follow-up" % original.get("id"))
        return [], None, False
    task, n = _split_key(asked["q"])
    if task is None:
        reasons.append("the original grade's follow_up has no key")
        return [], None, False
    if item.get("n") != n:
        reasons.append("question 1 must be section %d" % n)
    section = _section(tc.keys.get(task), n)
    if section is None:
        reasons.append("%s.md has no section %d" % (task, n))
    question = _section_question(item, section, asked["q"], "question 1", reasons)
    others = [q for q in original.get("questions") or []
              if isinstance(q, dict) and q.get("q") != asked.get("q")]
    passed = question.get("outcome") == "met" and all(q.get("outcome") == "met" for q in others)
    return [question], original.get("id"), passed


def _ack_event(request, filename, request_sha, attempt, now):
    return {"type": "ack", "id": "a-" + uuid.uuid4().hex[:10], "ts": now.isoformat(timespec="seconds"),
            "request": filename, "request_sha": request_sha, "attempt": attempt,
            "grader": request["grader"]}


def judge(request, filename, request_sha, inbox, state, content_map, grades, now):
    if not isinstance(request, dict):
        return None, ["the request must be an object"]
    reasons = []
    attempt = request.get("attempt")
    if not _is_text(attempt) or not attempt:
        reasons.append("missing or invalid attempt")
    grader = request.get("grader")
    reasons.extend(_grader(grader))
    _forbidden(request, reasons)
    ack = request.get("ack") is True
    if "ack" in request and request.get("ack") is not True:
        reasons.append("ack must be true")
    if ack:
        extra = set(request) - {"attempt", "grader", "ack"}
        if extra:
            reasons.append("an ack carries only attempt, grader and ack")
    else:
        if not _is_text(request.get("title"), 200):
            reasons.append("title must be a string of 1-200 characters")
        if not isinstance(request.get("detail"), str):
            reasons.append("detail must be a string")
        if "questions" not in request:
            reasons.append("missing required field questions")
        if request.get("record") is not None and not isinstance(request.get("record"), str):
            reasons.append("record must be a string")
        if request.get("regrade_of") is not None and not isinstance(request.get("regrade_of"), str):
            reasons.append("regrade_of must be a grade id")
        if request.get("follow_up") is not None and not isinstance(request.get("follow_up"), dict):
            reasons.append("follow_up must be an object")
    if isinstance(attempt, str):
        regrade = request.get("regrade_of")
        expected = attempt + (".regrade.json" if isinstance(regrade, str) else ".json")
        if filename != expected:
            reasons.append("the file name must be %s" % expected)
    if reasons:
        return None, reasons

    entry = next((e for e in inbox or [] if isinstance(e, dict) and e.get("id") == attempt), None)
    if entry is None:
        return None, ["attempt %s is not in the inbox" % attempt]
    if any(e.get("kind") == "withdraw" and e.get("ref") == attempt for e in inbox or []):
        return None, ["attempt %s was withdrawn" % attempt]
    kind = entry.get("kind")
    if kind in NEVER_GRADED:
        return None, ["a %s entry is never graded" % kind]
    special = kind == "note" or entry.get("task") == "first-try"
    if ack:
        if not special:
            return None, ["ack is only for a note or first-try attempt"]
        return _ack_event(request, filename, request_sha, attempt, now), []
    if special:
        return None, ["a note or first-try attempt is only acknowledged with ack"]
    if kind not in GRADABLE:
        return None, ["a %s attempt is never graded" % kind]

    lines = _attempt_grades(grades, attempt)
    regrade_of = request.get("regrade_of")
    if isinstance(regrade_of, str):
        latest = _latest_grade(lines)
        if latest is None or latest.get("id") != regrade_of:
            return None, ["regrade_of must be the latest grade of this attempt"]
        dispute = any(e.get("kind") == "dispute" and e.get("ref") == regrade_of for e in inbox or [])
        if not dispute:
            return None, ["no open dispute for grade %s" % regrade_of]
        answered = any(g.get("type") == "grade" and g.get("regrade_of") == regrade_of for g in grades or [])
        if answered:
            return None, ["the dispute for grade %s is already answered" % regrade_of]
        if request["grader"].get("session") == (latest.get("grader") or {}).get("session"):
            return None, ["a regrade needs a different grader session"]
    elif lines:
        return None, ["attempt %s already has a grade" % attempt]

    topic = entry.get("topic")
    tc = content_map.get(topic) if isinstance(topic, str) else None
    if tc is None or tc.graph is None:
        return None, ["the attempt's topic has no graph.json"]
    task = entry.get("task")
    if not isinstance(task, str):
        return None, ["the attempt has no task"]
    if kind in ("answers", "done") and task not in tc.keys:
        return None, ["the task has no answer key"]

    questions = request.get("questions")
    stored = []
    raw = {}
    passed = False
    follows = None
    if kind in ("answers", "done"):
        stored, raw = _answer_questions(questions, task, tc.keys[task], reasons)
        passed = bool(stored) and all(q["outcome"] == "met" for q in stored)
    elif kind == "recall":
        stored = _recall_questions(questions, entry, tc, state, reasons)
        passed = bool(stored) and all(q["outcome"] == "met" for q in stored)
    else:
        stored, follows, passed = _follow_up_questions(questions, entry, tc, grades, reasons)

    follow_up = None
    if request.get("follow_up") is not None:
        asked = request["follow_up"]
        if kind != "answers":
            reasons.append("a follow_up is only asked on an answers attempt")
        elif isinstance(regrade_of, str):
            reasons.append("a regrade cannot ask a follow_up")
        else:
            if set(asked) != {"n", "point", "q"}:
                reasons.append("follow_up must be {n, point, q}")
            n = asked.get("n")
            point = asked.get("point")
            text = asked.get("q")
            if type(n) is not int:
                reasons.append("follow_up.n must be a section number")
            elif n not in raw:
                reasons.append("follow_up.n must be a question in the request")
            elif raw[n].get("unsure") is not True:
                reasons.append("follow_up.n must be a question marked unsure")
            if not isinstance(point, str):
                reasons.append("follow_up.point must be a point id")
            elif type(n) is int and n in raw and point not in (raw[n].get("points") or {}):
                reasons.append("follow_up.point must be one of the question's point ids")
            if not _is_text(text, 200):
                reasons.append("follow_up.q must be a string of 1-200 characters")
            if type(n) is int and isinstance(point, str) and _is_text(text, 200):
                follow_up = {"q": "%s#%d" % (task, n), "point": point, "text": text}

    if reasons:
        return None, reasons

    event = {"type": "grade", "id": "g-" + uuid.uuid4().hex[:10],
             "ts": now.isoformat(timespec="seconds"), "request": filename,
             "request_sha": request_sha, "attempt": attempt, "answered": entry.get("ts"),
             "topic": topic, "task": task, "kind": kind, "honor": entry.get("honor") is True,
             "grader": request["grader"], "title": request["title"], "detail": request["detail"]}
    if request.get("record") is not None:
        event["record"] = request["record"]
    if follow_up is not None:
        event["follow_up"] = follow_up
    if follows is not None:
        event["follows"] = follows
    if isinstance(regrade_of, str):
        event["regrade_of"] = regrade_of
    event["questions"] = stored
    event["passed"] = passed
    return event, []


def _read_jsonl(path):
    entries = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return entries


def _load(vault):
    try:
        with open(os.path.join(vault, "_system", "state.json"), encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    try:
        content_map = content.load_content(vault, state)
    except content.ContentError:
        content_map = {}
    return (state, content_map,
            _read_jsonl(os.path.join(vault, "_system", "inbox.jsonl")),
            _read_jsonl(os.path.join(vault, "_system", "grades.jsonl")))


def _grading_files(vault):
    folder = os.path.join(vault, "_system", "grading")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [name for name in names
            if name.endswith(".json") and os.path.isfile(os.path.join(folder, name))]


def _duplicate(grades, name, sha):
    return any(g.get("request") == name and g.get("request_sha") == sha for g in grades or [])


def _append(path, line):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def ingest(vault, now, dry=False):
    accepted = []
    rejected = {}
    waiting = []
    folder = os.path.join(vault, "_system", "grading")
    with INGEST_LOCK:
        state, content_map, inbox, grades = _load(vault)
        grades_path = os.path.join(vault, "_system", "grades.jsonl")
        for name in _grading_files(vault):
            path = os.path.join(folder, name)
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
            except OSError:
                continue
            sha = hashlib.sha1(raw).hexdigest()
            if _duplicate(grades, name, sha):
                if not dry:
                    _remove(path)
                continue
            try:
                request = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                try:
                    age = now.timestamp() - os.path.getmtime(path)
                except OSError:
                    age = 0
                if age < 5:
                    waiting.append(name)
                else:
                    rejected[name] = ["not valid JSON"]
                continue
            event, reasons = judge(request, name, sha, inbox, state, content_map, grades, now)
            if reasons:
                rejected[name] = reasons
                continue
            grades.append(event)
            accepted.append(name)
            if not dry:
                _append(grades_path, json.dumps(event, ensure_ascii=False) + "\n")
                _remove(path)
    return {"accepted": accepted, "rejected": rejected, "waiting": waiting}


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
