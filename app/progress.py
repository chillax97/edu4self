from datetime import datetime
from typing import Optional

import content
import mastery


def _round(value: float) -> float:
    return round(value, 3)


def _date(day: float, tz) -> str:
    return datetime.fromtimestamp(day * mastery.DAY_SECONDS, tz=tz).date().isoformat()


def _when(grade: dict) -> float:
    for field in ("answered", "ts"):
        try:
            return mastery.parse_iso(grade.get(field)).timestamp()
        except (TypeError, ValueError):
            continue
    return 0.0


def _latest_grade(grades, topic: str, task: str) -> Optional[dict]:
    lines = mastery.kept_grades(grades, topic, task)
    if not lines:
        return None
    return max(enumerate(lines), key=lambda pair: (_when(pair[1]), pair[0]))[1]


def _topic_projection(tid, item, tc, graph, grades, skips, now_day, tz):
    skills = [s for s in graph.skills if not s.retired]
    by_id = {s.id: s for s in skills}
    entries = {}
    for skill in skills:
        observed = mastery.observations(grades, tid, skill.id)
        counted = [o for o in observed if o.day <= now_day]
        current = mastery.estimate(observed, now_day)
        current_level = mastery.level(observed, now_day)
        due_day = mastery.due(observed, current) if current_level >= 2 else None
        met = [o for o in counted if o.met]
        missed = [o for o in counted if not o.met]
        entries[skill.id] = {
            "name": skill.name,
            "region": skill.region,
            "level": current_level,
            "estimate": _round(current.value),
            "p_learned": _round(current.p_learned),
            "stability_days": _round(current.stability),
            "met": len(met),
            "missed": len(missed),
            "first_met": _date(met[0].day, tz) if met else None,
            "last_met": _date(met[-1].day, tz) if met else None,
            "last_tried": _date(counted[-1].day, tz) if counted else None,
            "due": _date(due_day, tz) if due_day is not None else None,
            "skipped": (tid, skill.id) in skips,
        }

    regions = {}
    lows = {}
    for region in graph.regions:
        regions[region.code] = {"name": region.name, "level": 0, "skills": 0, "started": 0}
        lows[region.code] = None
    for skill in skills:
        projection = regions.get(skill.region)
        if projection is None:
            continue
        projection["skills"] += 1
        entry = entries[skill.id]
        if entry["met"] + entry["missed"] > 0:
            projection["started"] += 1
            if lows[skill.region] is None or entry["level"] < lows[skill.region]:
                lows[skill.region] = entry["level"]
    for code, low in lows.items():
        regions[code]["level"] = low if low is not None else 0

    tasks = {}
    for task in item.get("queue") or []:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            continue
        task_id = task["id"]
        if task_id not in tc.keys:
            continue
        own = content.task_skills(tc, task_id)
        needs = set()
        for skill_id in own:
            skill = by_id.get(skill_id)
            if skill is None:
                continue
            for required in skill.requires:
                if required in own or required not in entries:
                    continue
                if entries[required]["level"] < 2 and not entries[required]["skipped"]:
                    needs.add(required)
        line = _latest_grade(grades, tid, task_id)
        tasks[task_id] = {
            "passed": bool(line and line.get("passed") is True),
            "grade": line.get("id") if line else None,
            "needs": sorted(needs),
            "ready": not needs,
        }

    projection = {"skills": entries, "regions": regions, "tasks": tasks}
    unpassed = [task_id for task_id, task in tasks.items() if not task["passed"]]
    if unpassed and not any(tasks[task_id]["ready"] for task_id in unpassed):
        blocked = set()
        for task_id in unpassed:
            blocked.update(tasks[task_id]["needs"])
        projection["blocked"] = {"skills": sorted(blocked)}
    return projection


def project(state, content, inbox, grades, now, topic: Optional[str] = None) -> dict:
    now_day = now.timestamp() / mastery.DAY_SECONDS
    tz = now.tzinfo
    skips = {(entry.get("topic"), entry.get("skill")) for entry in inbox or []
             if isinstance(entry, dict) and entry.get("kind") == "skip"}
    topics_out = {}
    unlinked = []
    for item in state.get("topics") or []:
        if not isinstance(item, dict):
            continue
        tid = item.get("id") if isinstance(item.get("id"), str) else item.get("path")
        if not isinstance(tid, str):
            continue
        if topic is not None and tid != topic:
            continue
        tc = content.get(tid)
        if tc is None and isinstance(item.get("path"), str):
            tc = content.get(item["path"])
        graph = tc.graph if tc is not None else None
        if graph is None:
            unlinked.append("topic %s has no graph.json" % tid)
            continue
        topics_out[tid] = _topic_projection(tid, item, tc, graph, grades, skips, now_day, tz)

    today = _date(now_day, tz)
    recall_due = []
    for tid, projection in topics_out.items():
        for skill_id, entry in projection["skills"].items():
            if entry["due"] is not None and entry["due"] <= today:
                recall_due.append({"topic": tid, "skill": skill_id, "due": entry["due"]})
    recall_due.sort(key=lambda row: (row["due"], row["topic"], row["skill"]))
    return {"topics": topics_out, "recall_due": recall_due, "unlinked": unlinked}


def envelope(state, content_map, inbox, grades, now, topic: Optional[str] = None) -> dict:
    out = {"schema": 1, "computed": now.isoformat(),
           "model": {"name": "memory-v1", "bar": mastery.BAR, "learned_bar": mastery.LEARNED_BAR}}
    out.update(project(state, content_map, inbox, grades, now, topic))
    return out


def _grade_item(grade, tasks):
    task = tasks.get(grade.get("task"))
    kind = task.get("kind") if task is not None else "probe"
    if grade.get("kind") == "recall":
        kind = "probe"
    answered = grade.get("answered") or grade.get("ts") or ""
    item = {"date": str(answered)[:10], "kind": kind, "title": grade.get("title"),
            "detail": grade.get("detail"), "evidence": grade.get("passed") is True,
            "inbox": grade.get("attempt"), "task": grade.get("task")}
    if "record" in grade:
        item["record"] = grade.get("record")
    follow = grade.get("follow_up")
    if isinstance(follow, dict):
        item["follow_up"] = {"q": follow.get("text"), "point": follow.get("point")}
    item["grade"] = grade.get("id")
    return item


def view(state, grades, projection) -> dict:
    if state.get("schema") != 2:
        return state
    grades = grades or []
    legacy_topic = {}
    legacy_by_topic = {}
    handled = set()
    grade_tasks = set()
    for grade in grades:
        if not isinstance(grade, dict):
            continue
        kind = grade.get("type")
        tid = grade.get("topic")
        if kind == "legacy":
            legacy_by_topic.setdefault(tid, []).append(grade)
            entry = grade.get("entry")
            if isinstance(entry, dict) and isinstance(entry.get("inbox"), str):
                handled.add(entry["inbox"])
        elif kind == "legacy_topic":
            legacy_topic[tid] = grade
        elif kind == "ack":
            if isinstance(grade.get("attempt"), str):
                handled.add(grade["attempt"])
        elif kind == "grade":
            if isinstance(grade.get("attempt"), str):
                handled.add(grade["attempt"])
            grade_tasks.add((tid, grade.get("task")))

    topics_out = []
    for item in state.get("topics") or []:
        if not isinstance(item, dict):
            continue
        tid = item.get("id") if isinstance(item.get("id"), str) else item.get("path")
        tasks = {}
        for task in item.get("queue") or []:
            if isinstance(task, dict) and isinstance(task.get("id"), str):
                tasks[task["id"]] = task
        projection_topic = (projection.get("topics") or {}).get(tid) or {}
        passed = {task_id for task_id, task in (projection_topic.get("tasks") or {}).items()
                  if task.get("passed")}
        old = legacy_topic.get(tid)
        old_done = set(old.get("done") or []) if isinstance(old, dict) else set()
        old_regions = old.get("regions") if isinstance(old, dict) else None

        entries = [_grade_item(grade, tasks) for grade in mastery.kept_grades(grades, tid)]
        for grade in reversed(legacy_by_topic.get(tid, [])):
            entry = grade.get("entry")
            if isinstance(entry, dict):
                entries.append(dict(entry, legacy=True))
        entries.sort(key=lambda entry: str(entry.get("date") or ""), reverse=True)

        queue = []
        for task in item.get("queue") or []:
            if not isinstance(task, dict):
                queue.append(task)
                continue
            out_task = dict(task)
            task_id = task.get("id")
            if task_id in passed or (task_id in old_done and (tid, task_id) not in grade_tasks):
                out_task["status"] = "done"
            queue.append(out_task)

        if projection_topic:
            old_by_code = {}
            for region in old_regions or []:
                if isinstance(region, dict):
                    old_by_code[region.get("code")] = region
            regions = []
            for code, region in (projection_topic.get("regions") or {}).items():
                row = {"code": code, "name": region.get("name"), "level": region.get("level"),
                       "skills": region.get("skills"), "started": region.get("started")}
                previous = old_by_code.get(code)
                if previous is not None and not region.get("started"):
                    row["level"] = previous.get("level")
                    row["legacy_level"] = previous.get("level")
                regions.append(row)
        elif old_regions is not None:
            regions = [dict(region, legacy_level=region.get("level"))
                       for region in old_regions if isinstance(region, dict)]
        else:
            regions = []

        topics_out.append(dict(item, history=entries, regions=regions, queue=queue))

    out = dict(state)
    out["topics"] = topics_out
    out["processed_inbox"] = sorted(attempt for attempt in handled if isinstance(attempt, str) and attempt)
    return out
