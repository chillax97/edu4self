import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
CLI = os.path.join(ENGINE, "edu4self")
SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+", re.MULTILINE)
SKILL_LINE_RE = re.compile(r"^Skill:\s*.*$", re.MULTILINE)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


def split_sections(text):
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return text, []
    preamble = text[:matches[0].start()]
    sections = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((int(match.group(1)), text[match.start():end]))
    return preamble, sections


def set_section_skills(text, skill_map):
    preamble, sections = split_sections(text)
    rebuilt = [preamble]
    for num, body in sections:
        cleaned = SKILL_LINE_RE.sub("", body)
        lines = cleaned.splitlines(True)
        header = lines[0]
        rest = "".join(lines[1:]).lstrip("\n")
        skill_lines = skill_map.get(num, [])
        if isinstance(skill_lines, str):
            skill_lines = [skill_lines]
        if skill_lines:
            inserted = "\n" + "\n".join("Skill: " + s for s in skill_lines) + "\n\n"
        else:
            inserted = "\n"
        rebuilt.append(header + inserted + rest)
    return "".join(rebuilt)


class ContentCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edu4self-content-")
        self.env = dict(
            os.environ,
            EDU4SELF_CONFIG_HOME=os.path.join(self.tmp, "cfg"),
            HOME=self.tmp,
            CLAUDE_CONFIG_DIR=os.path.join(self.tmp, "claude"),
            EDU4SELF_NO_UPDATE_CHECK="1",
        )
        self.env.pop("EDU4SELF_PORT", None)
        self.env.pop("EDU4SELF_VAULT", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, CLI, *args],
            env=self.env,
            stdin=subprocess.DEVNULL,
            timeout=60,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )

    def init_vault(self, name="vault"):
        vault = os.path.join(self.tmp, name)
        res = self.run_cli("init", vault, "--name", "Kim", "--port", "4800")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return vault

    def check_vault(self, vault):
        res = self.run_cli("check", "--vault", vault)
        return res.returncode, res.stdout + res.stderr

    def example_topic(self, vault):
        state_path = os.path.join(vault, "_system", "state.json")
        state = read_json(state_path)
        self.assertTrue(state.get("topics"), "fresh vault should have an example topic")
        topic = state["topics"][0]
        topic_id = topic["id"]
        topic_path = topic["path"]
        keys_dir = os.path.join(vault, "_system", "keys", topic_path)
        key_files = sorted(
            os.path.join(keys_dir, fn)
            for fn in os.listdir(keys_dir)
            if fn.endswith(".md")
        )
        self.assertTrue(key_files, "example topic should have answer keys")
        return state_path, state, topic_id, topic_path, key_files

    def base_graph(self, topic_id):
        return {
            "schema": 1,
            "topic": topic_id,
            "version": 1,
            "regions": [
                {"code": "A", "name": "Core concepts"},
                {"code": "B", "name": "Practice"},
            ],
            "skills": [
                {
                    "id": "skill-alpha",
                    "name": "Alpha concept",
                    "region": "A",
                    "can": "Explain alpha from memory.",
                    "requires": [],
                },
                {
                    "id": "skill-beta",
                    "name": "Beta application",
                    "region": "B",
                    "can": "Apply beta using alpha.",
                    "requires": ["skill-alpha"],
                },
                {
                    "id": "retired-skill",
                    "name": "Retired concept",
                    "region": "A",
                    "can": "Old skill no longer assigned.",
                    "requires": [],
                    "retired": True,
                },
            ],
            "changes": [
                {"version": 1, "date": "2026-11-26", "why": "Initial skill map."}
            ],
        }

    def prepare_graphed_vault(self, name="vault"):
        vault = self.init_vault(name=name)
        state_path, state, topic_id, topic_path, key_files = self.example_topic(vault)
        graph_path = os.path.join(vault, topic_path, "graph.json")
        graph = self.base_graph(topic_id)
        write_json(graph_path, graph)
        for key_path in key_files:
            text = read_text(key_path)
            _, sections = split_sections(text)
            skill_map = {
                num: ("skill-alpha" if idx == 0 else "none")
                for idx, (num, _) in enumerate(sections)
            }
            write_text(key_path, set_section_skills(text, skill_map))
        return vault, state_path, state, topic_id, topic_path, graph_path, graph, key_files

    def test_fresh_init_vault_passes(self):
        vault = self.init_vault()
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 0, out)

    def test_template_example_topic_ships_graph_and_skill_lines(self):
        vault = self.init_vault()
        _, _, topic_id, topic_path, key_files = self.example_topic(vault)
        self.assertEqual(topic_id, "how-learning-works")
        graph_path = os.path.join(vault, topic_path, "graph.json")
        self.assertTrue(os.path.isfile(graph_path), "example topic must ship graph.json")
        graph = read_json(graph_path)
        self.assertEqual(graph.get("topic"), topic_id)
        self.assertEqual(len(key_files), 2)
        for key_path in key_files:
            _, sections = split_sections(read_text(key_path))
            self.assertTrue(sections, key_path)
            for num, body in sections:
                matches = SKILL_LINE_RE.findall(body)
                self.assertEqual(
                    len(matches),
                    1,
                    f"{os.path.basename(key_path)} section {num} must have one Skill line",
                )

    def test_topic_without_graph_passes_as_today(self):
        vault = self.init_vault()
        _, _, _, topic_path, key_files = self.example_topic(vault)
        graph_path = os.path.join(vault, topic_path, "graph.json")
        if os.path.exists(graph_path):
            os.remove(graph_path)
        for key_path in key_files:
            text = read_text(key_path)
            _, sections = split_sections(text)
            write_text(key_path, set_section_skills(text, {num: [] for num, _ in sections}))
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 0, out)

    def test_valid_graph_skill_lines_and_recall_key_pass(self):
        vault, state_path, state, _, _, _, _, key_files = self.prepare_graphed_vault()
        first_key_stem = os.path.splitext(os.path.basename(key_files[0]))[0]
        state["topics"][0]["recall"] = [
            {
                "id": "r-valid",
                "q": "Explain alpha from memory.",
                "from": first_key_stem,
                "key": f"{first_key_stem}#1",
            }
        ]
        write_json(state_path, state)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 0, out)

    def test_invalid_json_graph_fails(self):
        vault, _, _, _, _, graph_path, _, _ = self.prepare_graphed_vault()
        write_text(graph_path, "{not valid json")
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("graph.json", out)

    def test_graph_missing_required_fields_fails(self):
        for idx, field in enumerate(("schema", "topic", "version", "regions", "skills")):
            with self.subTest(missing=field):
                vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault(f"vault-{idx}")
                broken = dict(graph)
                del broken[field]
                write_json(graph_path, broken)
                rc, out = self.check_vault(vault)
                self.assertEqual(rc, 1, out)
                self.assertTrue(field in out or "graph.json" in out, out)

    def test_skill_missing_required_field_fails(self):
        vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault()
        del graph["skills"][0]["can"]
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertTrue("skill-alpha" in out or "can" in out, out)

    def test_skill_id_breaking_pattern_fails(self):
        bad_ids = ["Bad_Skill", "-leading-dash", "a" * 49]
        for idx, bad_id in enumerate(bad_ids):
            with self.subTest(bad_id=bad_id):
                vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault(f"vault-{idx}")
                graph["skills"].append(
                    {
                        "id": bad_id,
                        "name": "Broken id skill",
                        "region": "A",
                        "can": "Do something.",
                        "requires": [],
                    }
                )
                write_json(graph_path, graph)
                rc, out = self.check_vault(vault)
                self.assertEqual(rc, 1, out)
                self.assertIn(bad_id, out)

    def test_duplicate_skill_id_fails(self):
        vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault()
        graph["skills"].append(
            {
                "id": "skill-alpha",
                "name": "Duplicate alpha",
                "region": "A",
                "can": "Duplicate entry.",
                "requires": [],
            }
        )
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("skill-alpha", out)

    def test_duplicate_region_code_fails(self):
        vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault()
        graph["regions"].append({"code": "A", "name": "Duplicate region"})
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("A", out)

    def test_skill_with_unknown_region_fails(self):
        vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault()
        graph["skills"].append(
            {
                "id": "orphan-region-skill",
                "name": "Orphan region",
                "region": "ZZ",
                "can": "Lives in an unknown region.",
                "requires": [],
            }
        )
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertTrue("orphan-region-skill" in out or "ZZ" in out, out)

    def test_requires_unknown_skill_fails(self):
        vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault()
        graph["skills"][1]["requires"] = ["ghost-prereq"]
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("ghost-prereq", out)

    def test_requires_cycle_fails(self):
        vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault()
        graph["skills"].extend(
            [
                {
                    "id": "cycle-one",
                    "name": "Cycle one",
                    "region": "A",
                    "can": "Needs cycle two.",
                    "requires": ["cycle-two"],
                },
                {
                    "id": "cycle-two",
                    "name": "Cycle two",
                    "region": "A",
                    "can": "Needs cycle one.",
                    "requires": ["cycle-one"],
                },
            ]
        )
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertTrue("cycle-one" in out or "cycle-two" in out, out)

    def test_requires_self_cycle_fails(self):
        vault, _, _, _, _, graph_path, graph, _ = self.prepare_graphed_vault()
        graph["skills"].append(
            {
                "id": "self-loop",
                "name": "Self loop",
                "region": "A",
                "can": "Needs itself.",
                "requires": ["self-loop"],
            }
        )
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("self-loop", out)

    def test_graph_topic_mismatch_fails(self):
        vault, _, _, topic_id, _, graph_path, graph, _ = self.prepare_graphed_vault()
        graph["topic"] = "wrong-topic-id"
        write_json(graph_path, graph)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertTrue("wrong-topic-id" in out or topic_id in out, out)

    def test_key_section_missing_skill_line_fails(self):
        vault, _, _, _, _, _, _, key_files = self.prepare_graphed_vault()
        key_path = key_files[0]
        key_stem = os.path.splitext(os.path.basename(key_path))[0]
        text = read_text(key_path)
        _, sections = split_sections(text)
        skill_map = {num: "skill-alpha" for num, _ in sections}
        skill_map[2] = []
        write_text(key_path, set_section_skills(text, skill_map))
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn(key_stem, out)
        self.assertIn("2", out)

    def test_key_section_with_two_skill_lines_fails(self):
        vault, _, _, _, _, _, _, key_files = self.prepare_graphed_vault()
        key_path = key_files[0]
        key_stem = os.path.splitext(os.path.basename(key_path))[0]
        text = read_text(key_path)
        _, sections = split_sections(text)
        skill_map = {num: "skill-alpha" for num, _ in sections}
        skill_map[2] = ["skill-alpha", "skill-beta"]
        write_text(key_path, set_section_skills(text, skill_map))
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn(key_stem, out)
        self.assertIn("2", out)

    def test_key_section_with_unknown_skill_fails(self):
        vault, _, _, _, _, _, _, key_files = self.prepare_graphed_vault()
        key_path = key_files[0]
        text = read_text(key_path)
        _, sections = split_sections(text)
        skill_map = {num: "skill-alpha" for num, _ in sections}
        skill_map[1] = "unknown-key-skill"
        write_text(key_path, set_section_skills(text, skill_map))
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("unknown-key-skill", out)

    def test_key_section_with_retired_skill_fails(self):
        vault, _, _, _, _, _, _, key_files = self.prepare_graphed_vault()
        key_path = key_files[0]
        text = read_text(key_path)
        _, sections = split_sections(text)
        skill_map = {num: "skill-alpha" for num, _ in sections}
        skill_map[1] = "retired-skill"
        write_text(key_path, set_section_skills(text, skill_map))
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("retired-skill", out)

    def test_recall_key_pointing_to_missing_file_fails(self):
        vault, state_path, state, _, _, _, _, key_files = self.prepare_graphed_vault()
        first_key_stem = os.path.splitext(os.path.basename(key_files[0]))[0]
        state["topics"][0]["recall"] = [
            {
                "id": "r-missing-file",
                "q": "Explain alpha from memory.",
                "from": first_key_stem,
                "key": "no-such-task#1",
            }
        ]
        write_json(state_path, state)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertTrue("no-such-task" in out or "r-missing-file" in out, out)

    def test_recall_key_pointing_to_missing_section_fails(self):
        vault, state_path, state, _, _, _, _, key_files = self.prepare_graphed_vault()
        first_key_stem = os.path.splitext(os.path.basename(key_files[0]))[0]
        state["topics"][0]["recall"] = [
            {
                "id": "r-missing-sec",
                "q": "Explain alpha from memory.",
                "from": first_key_stem,
                "key": f"{first_key_stem}#99",
            }
        ]
        write_json(state_path, state)
        rc, out = self.check_vault(vault)
        self.assertEqual(rc, 1, out)
        self.assertIn("99", out)
        self.assertTrue(first_key_stem in out or "r-missing-sec" in out, out)


if __name__ == "__main__":
    unittest.main()
