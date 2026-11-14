"""Point-listed answer keys for the SAF questions the small set uses (see keys.json).

Each key is written from the question and the lecturer's reference answer alone, never from a student answer
or a label. run.py hands a key to the grader the way it hands a made-up question's key: required points,
wrong answers to watch for, and what is not required. A question without an entry here keeps the older key
(the lecturer's notes as prose)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "keys.json")


def load(path=PATH):
    """{qid: {"required": [...], "wrong": [...], "not_required": [...]}}; empty if the file is missing."""
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
