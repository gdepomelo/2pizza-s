import json
import os
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "trainer.db"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


WORDS = load_json(DATA_DIR / "word_lists" / "it_terms.json")
WORD_BY_ID = {w["id"]: w for w in WORDS}
RULES = load_json(DATA_DIR / "settings_rules.json")


def get_profile(profile_key):
    return RULES["profiles"].get(profile_key, RULES["profiles"]["steady"])


def resolve_params(profile_key):
    return dict(get_profile(profile_key))
