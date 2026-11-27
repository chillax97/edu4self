import copy
import json
import os

import evidence


class MigrateError(Exception):
    pass


def _ts(now):
    return now.isoformat(timespec="seconds")


def _topics(state):
    return [topic for topic in state.get("topics") or [] if isinstance(topic, dict)]


def _topic_id(topic):
    tid = topic.get("id") if isinstance(topic.get("id"), str) else topic.get("path")
    return tid if isinstance(tid, str) else None


def _legacy_events(state, now):
    events = []
    for topic in _topics(state):
        tid = _topic_id(topic)
        if tid is None:
            continue
        history = topic.get("history") if isinstance(topic.get("history"), list) else []
        n = 0
        for entry in reversed(history):
            n += 1
            events.append({"type": "legacy", "id": "legacy-%s-%03d" % (tid, n), "ts": _ts(now),
                           "topic": tid, "entry": entry})
    return events


def _legacy_topic_events(state, now):
    events = []
    for topic in _topics(state):
        tid = _topic_id(topic)
        if tid is None:
            continue
        regions = topic.get("regions")
        done = sorted(task["id"] for task in topic.get("queue") or []
                      if isinstance(task, dict) and task.get("status") == "done" and task.get("submit")
                      and isinstance(task.get("id"), str))
        events.append({"type": "legacy_topic", "id": "legacy-%s" % tid, "ts": _ts(now), "topic": tid,
                       "regions": regions if isinstance(regions, list) else [], "done": done})
    return events


def _ack_events(state, now):
    processed = state.get("processed_inbox") if isinstance(state.get("processed_inbox"), list) else []
    seen = set()
    for topic in _topics(state):
        for entry in topic.get("history") or []:
            if isinstance(entry, dict) and isinstance(entry.get("inbox"), str):
                seen.add(entry["inbox"])
    events = []
    seen_ids = set()
    for inbox_id in processed:
        if not isinstance(inbox_id, str) or inbox_id in seen or inbox_id in seen_ids:
            continue
        seen_ids.add(inbox_id)
        events.append({"type": "ack", "id": "legacy-ack-%s" % inbox_id, "ts": _ts(now),
                       "attempt": inbox_id, "legacy": True})
    return events


def _new_state(state):
    out = copy.deepcopy(state)
    out["schema"] = 2
    out.pop("processed_inbox", None)
    for topic in out.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        topic.pop("history", None)
        topic.pop("regions", None)
        for task in topic.get("queue") or []:
            if isinstance(task, dict) and task.get("status") == "done" and task.get("submit"):
                task["status"] = "todo"
    return out


def plan(state, grades, now):
    existing = {grade.get("id") for grade in grades or []
                if isinstance(grade, dict) and isinstance(grade.get("id"), str)}
    events = [event for event in _legacy_events(state, now) + _legacy_topic_events(state, now) + _ack_events(state, now)
              if event["id"] not in existing]
    append = {"legacy": 0, "legacy_topic": 0, "ack": 0}
    for event in events:
        append[event["type"]] += 1
    undone = [task["id"] for topic in _topics(state) for task in topic.get("queue") or []
              if isinstance(task, dict) and task.get("status") == "done" and task.get("submit")
              and isinstance(task.get("id"), str)]
    return {"events": events, "append": append, "undone": undone, "state": _new_state(state)}


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


def _backup(vault, data, now):
    folder = os.path.join(vault, "_system", "backup")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        names = []
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as fh:
                if fh.read() == data:
                    return path
        except OSError:
            continue
    return os.path.join(folder, "state-%s.json" % now.strftime("%Y%m%dT%H%M%S"))


def _write(path, data):
    tmp = path + ".migrate.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def run(vault, now, dry_run=False):
    state_path = os.path.join(vault, "_system", "state.json")
    try:
        with open(state_path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise MigrateError("state.json is missing or unreadable: %s" % exc)
    try:
        state = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise MigrateError("state.json does not parse: %s" % exc)
    if not isinstance(state, dict):
        raise MigrateError("state.json does not parse: the top level is not an object")
    if state.get("schema") == 2:
        return {"schema": 2, "backup": None, "append": {"legacy": 0, "legacy_topic": 0, "ack": 0}, "undone": [],
                "dry_run": bool(dry_run)}

    grades_path = os.path.join(vault, "_system", "grades.jsonl")
    report = {"schema": 1, "backup": _backup(vault, data, now), "append": {"legacy": 0, "legacy_topic": 0, "ack": 0},
              "undone": [], "dry_run": bool(dry_run)}
    if dry_run:
        built = plan(state, _read_jsonl(grades_path), now)
        report["append"] = built["append"]
        report["undone"] = built["undone"]
        report["backup"] = os.path.relpath(report["backup"], vault)
        return report

    try:
        with evidence.grades_lock(vault, wait=0):
            built = plan(state, _read_jsonl(grades_path), now)
            report["append"] = built["append"]
            report["undone"] = built["undone"]
            folder = os.path.dirname(report["backup"])
            os.makedirs(folder, exist_ok=True)
            if not os.path.isfile(report["backup"]):
                with open(report["backup"], "wb") as fh:
                    fh.write(data)
            fd = os.open(grades_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                os.write(fd, "".join(json.dumps(event, ensure_ascii=False) + "\n"
                                     for event in built["events"]).encode("utf-8"))
            finally:
                os.close(fd)
            _write(state_path, json.dumps(built["state"], indent=1, ensure_ascii=False) + "\n")
    except evidence.LockTimeout:
        raise MigrateError("another process is writing grades; try again in a moment")
    report["backup"] = os.path.relpath(report["backup"], vault)
    return report
