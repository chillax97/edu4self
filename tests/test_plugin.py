"""The Claude Code plugin: every skill folder holds a SKILL.md Claude Code can load."""
import os
import re
import unittest

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ENGINE, "plugin", "skills")


def frontmatter(text):
    """The `key: value` lines between the opening and closing `---`, or None when there is no block."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip().strip('"')
    return out


class SkillFilesTest(unittest.TestCase):
    def skills(self):
        names = sorted(d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)))
        self.assertTrue(names, "plugin/skills has no skills")
        return names

    def read(self, name, file="SKILL.md"):
        with open(os.path.join(SKILLS, name, file), encoding="utf-8") as fh:
            return fh.read()

    def test_every_skill_has_a_name_and_a_description(self):
        for name in self.skills():
            with self.subTest(skill=name):
                self.assertTrue(os.path.isfile(os.path.join(SKILLS, name, "SKILL.md")), "missing SKILL.md")
                meta = frontmatter(self.read(name))
                self.assertIsNotNone(meta, "SKILL.md must start with a --- frontmatter block")
                self.assertEqual(meta.get("name"), name, "name must match the folder")
                self.assertGreater(len(meta.get("description", "")), 40, "say what it does and when to use it")
                self.assertLessEqual(len(meta["description"]), 1024)

    def test_links_between_skill_files_resolve(self):
        for name in self.skills():
            folder = os.path.join(SKILLS, name)
            for file in os.listdir(folder):
                if not file.endswith(".md"):
                    continue
                for target in re.findall(r"\]\((\.{1,2}/[^)#\s]+)", self.read(name, file)):
                    with self.subTest(skill=name, file=file, link=target):
                        self.assertTrue(os.path.exists(os.path.normpath(os.path.join(folder, target))))

    def test_skills_use_no_em_dashes(self):
        for name in self.skills():
            for file in os.listdir(os.path.join(SKILLS, name)):
                if file.endswith(".md") and file != "PROTOCOL.md":   # PROTOCOL.md is a copy of docs/
                    with self.subTest(skill=name, file=file):
                        self.assertNotIn("—", self.read(name, file))


if __name__ == "__main__":
    unittest.main()
