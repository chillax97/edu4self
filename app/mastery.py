import math
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

P_INIT = 0.1
P_LEARN = 0.3
P_GUESS = 0.15
P_SLIP = 0.1
STABILITY0 = 3.0
GROW = 2.5
SHRINK = 0.5
FLOOR = 1.0
BAR = 0.8
LEARNED_BAR = 0.5
SPACING_DAYS = 3
PERMANENT_DAYS = 30
DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class Obs:
    day: float
    met: bool
    kind: str = ""


@dataclass(frozen=True)
class Estimate:
    p_learned: float
    stability: float
    anchor: Optional[float]
    value: float
    now: float


def parse_iso(text) -> datetime:
    value = str(text).strip()
    if value.endswith("Z") or value.endswith("z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def day_of(text) -> float:
    return parse_iso(text).timestamp() / DAY_SECONDS


def _newer(ts, index, old_ts, old_index) -> bool:
    if ts is None and old_ts is None:
        return index > old_index
    if ts is None:
        return False
    if old_ts is None:
        return True
    if ts != old_ts:
        return ts > old_ts
    return index > old_index


def kept_grades(grades, topic=None, task=None) -> List[dict]:
    kept = {}
    for index, grade in enumerate(grades or []):
        if not isinstance(grade, dict) or grade.get("type") != "grade":
            continue
        if topic is not None and grade.get("topic") != topic:
            continue
        if task is not None and grade.get("task") != task:
            continue
        attempt = grade.get("attempt")
        try:
            hash(attempt)
        except TypeError:
            continue
        try:
            ts = parse_iso(grade.get("ts"))
        except (TypeError, ValueError):
            ts = None
        key = (grade.get("topic"), grade.get("task"), attempt)
        previous = kept.get(key)
        if previous is None or _newer(ts, index, previous[1], previous[2]):
            kept[key] = (grade, ts, index)
    return [entry[0] for entry in kept.values()]


def observations(grades, topic: str, skill: str) -> List[Obs]:
    result = []
    for grade in kept_grades(grades, topic):
        if grade.get("honor") is False:
            continue
        if "first-try" in (grade.get("kind"), grade.get("task")):
            continue
        questions = [q for q in grade.get("questions") or []
                     if isinstance(q, dict) and q.get("skill") == skill and q.get("outcome") != "unsure"]
        if not questions:
            continue
        try:
            day = day_of(grade.get("answered"))
        except (TypeError, ValueError):
            continue
        result.append(Obs(day, all(q.get("outcome") == "met" for q in questions), grade.get("kind") or ""))
    result.sort(key=lambda obs: obs.day)
    return result


def estimate(obs, now_day: float) -> Estimate:
    counted = [o for o in obs if o.day <= now_day]
    if not counted:
        return Estimate(P_INIT, STABILITY0, None, 0.0, now_day)
    p = P_INIT
    stability = STABILITY0
    anchor = None
    for observation in counted:
        pc = p * (1 - P_SLIP) + (1 - p) * P_GUESS
        if observation.met:
            p = p * (1 - P_SLIP) / pc
            stability *= GROW
            anchor = observation.day
        else:
            p = p * P_SLIP / (1 - pc)
            stability = max(FLOOR, stability * SHRINK)
        p = p + (1 - p) * P_LEARN
    if anchor is None:
        anchor = counted[-1].day
    value = p * math.exp(-(now_day - anchor) / stability)
    return Estimate(p, stability, anchor, value, now_day)


def _base_level(obs, now_day: float) -> int:
    counted = [o for o in obs if o.day <= now_day]
    if not counted:
        return 0
    current = estimate(counted, now_day)
    if current.p_learned < LEARNED_BAR:
        return 1
    met_days = [o.day for o in counted if o.met]
    spaced = len(met_days) >= 2 and met_days[-1] - met_days[0] >= SPACING_DAYS
    return 3 if current.value >= BAR and spaced else 2


def level(obs, now_day: float) -> int:
    base = _base_level(obs, now_day)
    if base < 3:
        return base
    days = sorted({o.day for o in obs if o.day <= now_day})
    first = next(day for day in days if _base_level(obs, day) >= 3)
    reached = any(o.met and first + PERMANENT_DAYS <= o.day <= now_day for o in obs)
    return 4 if reached else 3


def due(obs, est: Estimate) -> Optional[float]:
    if est.p_learned < LEARNED_BAR or est.anchor is None:
        return None
    met_days = [o.day for o in obs if o.met and o.day <= est.now]
    if not met_days:
        return None
    first_met = min(met_days)
    if est.p_learned > BAR:
        bar_day = est.anchor + est.stability * math.log(est.p_learned / BAR)
    else:
        bar_day = est.anchor
    return max(first_met + SPACING_DAYS, bar_day)
