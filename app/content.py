import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Region:
    code: str
    name: str


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    region: str
    can: str
    requires: Tuple[str, ...] = ()
    retired: bool = False


@dataclass(frozen=True)
class Graph:
    schema: int
    topic: str
    version: int
    regions: Tuple[Region, ...]
    skills: Tuple[Skill, ...]
    changes: Tuple[dict, ...] = ()


@dataclass(frozen=True)
class KeySection:
    n: int
    skill: Optional[str]
    skill_count: int


@dataclass(frozen=True)
class TopicContent:
    graph: Optional[Graph]
    keys: Dict[str, List[KeySection]]


class ContentError(Exception):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems) or "invalid content")


SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SECTION = re.compile(r"^##\s+(\d+)\.\s*")
SKILL_LINE = re.compile(r"^Skill:\s*(.*?)\s*$")


def parse_graph(raw: dict) -> Graph:
    problems = []
    if not isinstance(raw, dict):
        raise ContentError(["graph.json: the top level must be an object"])
    if "schema" not in raw:
        problems.append("graph.json: missing required field schema")
    elif type(raw["schema"]) is not int or raw["schema"] != 1:
        problems.append("graph.json: schema must be 1")
    if "topic" not in raw:
        problems.append("graph.json: missing required field topic")
    elif not isinstance(raw["topic"], str) or not raw["topic"].strip():
        problems.append("graph.json: topic must be a non-empty string")
    if "version" not in raw:
        problems.append("graph.json: missing required field version")
    elif type(raw["version"]) is not int or raw["version"] < 1:
        problems.append("graph.json: version must be an integer of at least 1")
    regions = []
    if "regions" not in raw:
        problems.append("graph.json: missing required field regions")
    elif not isinstance(raw["regions"], list):
        problems.append("graph.json: regions must be a list")
    else:
        for i, r in enumerate(raw["regions"]):
            if not isinstance(r, dict):
                problems.append("graph.json: regions[%d] must be an object" % i)
                continue
            if "code" not in r:
                problems.append("graph.json: regions[%d] missing code" % i)
            elif not isinstance(r["code"], str) or not r["code"].strip():
                problems.append("graph.json: regions[%d] code must be a non-empty string" % i)
            if "name" not in r:
                problems.append("graph.json: regions[%d] missing name" % i)
            elif not isinstance(r["name"], str):
                problems.append("graph.json: regions[%d] name must be a string" % i)
            regions.append(Region(r.get("code") if isinstance(r.get("code"), str) else "",
                                  r.get("name") if isinstance(r.get("name"), str) else ""))
    skills = []
    if "skills" not in raw:
        problems.append("graph.json: missing required field skills")
    elif not isinstance(raw["skills"], list):
        problems.append("graph.json: skills must be a list")
    else:
        for i, s in enumerate(raw["skills"]):
            if not isinstance(s, dict):
                problems.append("graph.json: skills[%d] must be an object" % i)
                continue
            label = s.get("id") if isinstance(s.get("id"), str) else "skills[%d]" % i
            for key in ("id", "name", "region", "can", "requires"):
                if key not in s:
                    problems.append("graph.json: skill %s missing %s" % (label, key))
            if "id" in s and (not isinstance(s["id"], str) or not s["id"].strip()):
                problems.append("graph.json: skill %s id must be a non-empty string" % label)
            if "name" in s and not isinstance(s["name"], str):
                problems.append("graph.json: skill %s name must be a string" % label)
            if "region" in s and not isinstance(s["region"], str):
                problems.append("graph.json: skill %s region must be a string" % label)
            if "can" in s and not isinstance(s["can"], str):
                problems.append("graph.json: skill %s can must be a string" % label)
            if "requires" in s:
                if not isinstance(s["requires"], list) or not all(isinstance(x, str) for x in s["requires"]):
                    problems.append("graph.json: skill %s requires must be a list of skill ids" % label)
            if "retired" in s and not isinstance(s["retired"], bool):
                problems.append("graph.json: skill %s retired must be true or false" % label)
            skills.append(Skill(s.get("id") if isinstance(s.get("id"), str) else "",
                                s.get("name") if isinstance(s.get("name"), str) else "",
                                s.get("region") if isinstance(s.get("region"), str) else "",
                                s.get("can") if isinstance(s.get("can"), str) else "",
                                tuple(s.get("requires") or ()),
                                s.get("retired") is True))
    changes = ()
    if "changes" in raw:
        if not isinstance(raw["changes"], list):
            problems.append("graph.json: changes must be a list")
        else:
            for i, c in enumerate(raw["changes"]):
                if not isinstance(c, dict):
                    problems.append("graph.json: changes[%d] must be an object" % i)
                    continue
                if type(c.get("version")) is not int:
                    problems.append("graph.json: changes[%d] version must be an integer" % i)
                if not isinstance(c.get("date"), str):
                    problems.append("graph.json: changes[%d] date must be a string" % i)
                if not isinstance(c.get("why"), str):
                    problems.append("graph.json: changes[%d] why must be a string" % i)
            changes = tuple(raw["changes"])
    if problems:
        raise ContentError(problems)
    return Graph(raw["schema"], raw["topic"], raw["version"], tuple(regions), tuple(skills), changes)


def _cycle(skills: Tuple[Skill, ...]) -> Optional[List[str]]:
    ids = {s.id for s in skills}
    adj = {s.id: [r for r in s.requires if r in ids] for s in skills}
    colour = {}
    path = []

    def visit(node):
        colour[node] = 1
        path.append(node)
        for nxt in adj[node]:
            if colour.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            if not colour.get(nxt):
                found = visit(nxt)
                if found:
                    return found
        path.pop()
        colour[node] = 2
        return None

    for node in adj:
        if not colour.get(node):
            found = visit(node)
            if found:
                return found
    return None


def graph_problems(graph: Graph) -> List[str]:
    problems = []
    codes = [r.code for r in graph.regions]
    for code in sorted({c for c in codes if codes.count(c) > 1}):
        problems.append("graph.json: region code %r appears more than once" % code)
    regions = set(codes)
    seen = set()
    for s in graph.skills:
        if not SKILL_ID.match(s.id):
            problems.append("graph.json: skill id %r must match %s" % (s.id, SKILL_ID.pattern))
        if s.id in seen:
            problems.append("graph.json: skill id %r appears more than once" % s.id)
        seen.add(s.id)
    ids = {s.id for s in graph.skills}
    for s in graph.skills:
        if s.region not in regions:
            problems.append("graph.json: skill %s region %r is not a region code in the file" % (s.id, s.region))
        for req in s.requires:
            if req not in ids:
                problems.append("graph.json: skill %s requires unknown skill %r" % (s.id, req))
    cycle = _cycle(graph.skills)
    if cycle:
        problems.append("graph.json: requires cycle: %s" % " -> ".join(cycle))
    return problems


def parse_key(text: str) -> List[KeySection]:
    sections = []
    current = None
    found = []

    def flush():
        if current is not None:
            skill = None
            if len(found) == 1:
                value = found[0]
                skill = None if value.lower() == "none" else value
            sections.append(KeySection(current, skill, len(found)))

    for line in text.splitlines():
        heading = SECTION.match(line)
        if heading:
            flush()
            current = int(heading.group(1))
            found = []
            continue
        if current is None:
            continue
        stripped = line.strip()
        skill_line = SKILL_LINE.match(stripped)
        if skill_line:
            found.append(skill_line.group(1))
            continue
    flush()
    return sections


def load_content(root: str, state: dict) -> Dict[str, TopicContent]:
    content = {}
    for topic in state.get("topics", []) or []:
        if not isinstance(topic, dict):
            continue
        tid = topic.get("id") if isinstance(topic.get("id"), str) else topic.get("path")
        if not isinstance(tid, str):
            continue
        path = topic.get("path") if isinstance(topic.get("path"), str) else ""
        graph = None
        graph_path = os.path.join(root, path, "graph.json")
        if os.path.isfile(graph_path):
            try:
                with open(graph_path, encoding="utf-8") as fh:
                    raw = json.load(fh)
            except (OSError, ValueError) as exc:
                raise ContentError(["topic %s: graph.json is not valid JSON: %s" % (tid, exc)])
            try:
                graph = parse_graph(raw)
            except ContentError as exc:
                raise ContentError(["topic %s: %s" % (tid, p) for p in exc.problems])
        keys = {}
        key_dir = os.path.join(root, "_system", "keys", path)
        if os.path.isdir(key_dir):
            for name in sorted(os.listdir(key_dir)):
                full = os.path.join(key_dir, name)
                if name.endswith(".md") and os.path.isfile(full):
                    with open(full, encoding="utf-8") as fh:
                        keys[name[:-3]] = parse_key(fh.read())
        content[tid] = TopicContent(graph, keys)
    return content


def _owner(entry: dict, task_topic: Dict[str, dict]) -> Optional[str]:
    for field_name in ("from", "key"):
        value = entry.get(field_name)
        if isinstance(value, str):
            task = value.split("#", 1)[0]
            if task in task_topic:
                return task_topic[task].get("id")
    return None


def link_problems(state: dict, content: Dict[str, TopicContent]) -> List[str]:
    problems = []
    topics = [t for t in state.get("topics", []) or [] if isinstance(t, dict)]
    task_topic = {}
    for topic in topics:
        for task in topic.get("queue", []) or []:
            if isinstance(task, dict) and isinstance(task.get("id"), str):
                task_topic.setdefault(task["id"], topic)
    for topic in topics:
        tid = topic.get("id")
        tc = content.get(tid)
        if tc is None and isinstance(topic.get("path"), str):
            tc = content.get(topic["path"])
        if tc is None or tc.graph is None:
            continue
        if tc.graph.topic != tid:
            problems.append("topic %s: graph.json topic is %r" % (tid, tc.graph.topic))
        skills = {s.id: s for s in tc.graph.skills}
        for task_id, sections in tc.keys.items():
            for section in sections:
                label = "%s.md section %d" % (task_id, section.n)
                if section.skill_count == 0:
                    problems.append("key %s: no Skill: line" % label)
                elif section.skill_count > 1:
                    problems.append("key %s: more than one Skill: line" % label)
                elif section.skill is not None:
                    skill = skills.get(section.skill)
                    if skill is None:
                        problems.append("key %s: Skill: %s is not a skill in graph.json" % (label, section.skill))
                    elif skill.retired:
                        problems.append("key %s: Skill: %s is retired" % (label, section.skill))
        recalls = [r for r in topic.get("recall", []) or [] if isinstance(r, dict)]
        for entry in state.get("recall", []) or []:
            if isinstance(entry, dict) and _owner(entry, task_topic) == tid:
                recalls.append(entry)
        for entry in recalls:
            key = entry.get("key")
            if not isinstance(key, str):
                continue
            if "#" not in key:
                problems.append("recall %s: key %r must be <task-id>#<section>" % (entry.get("id"), key))
                continue
            task, _, number = key.rpartition("#")
            try:
                n = int(number)
            except ValueError:
                problems.append("recall %s: key %r must be <task-id>#<section>" % (entry.get("id"), key))
                continue
            sections = tc.keys.get(task)
            if sections is None:
                problems.append("recall %s: key %r points to a missing key file %s.md" % (entry.get("id"), key, task))
            elif not any(section.n == n for section in sections):
                problems.append("recall %s: key %r points to a missing section %d in %s.md"
                                % (entry.get("id"), key, n, task))
    return problems
