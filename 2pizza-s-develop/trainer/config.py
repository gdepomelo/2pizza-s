import json
import logging
import os
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "trainer.db"
MODULES_DIR = pathlib.Path(os.environ.get("WORD_MODULES_DIR") or DATA_DIR / "word_lists" / "modules")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_modules():
    """Модули слов: data/word_lists/modules/*.json в порядке имён файлов (01_..., 02_...).

    Формат файла: {"id": "m1", "title": "Модуль 1 · ...", "topic": "о чём модуль",
                   "words": [ {...слово...}, ... ]}.
    Если папки нет — весь старый банк it_terms.json считается одним модулем.
    """
    files = sorted(MODULES_DIR.glob("*.json")) if MODULES_DIR.is_dir() else []
    if not files:
        words = load_json(DATA_DIR / "word_lists" / "it_terms.json")
        return [{"id": "base", "title": "Базовая лексика B1", "topic": "", "words": words}]
    modules = []
    seen = set()
    for path in files:
        data = load_json(path)
        words = []
        for w in data["words"]:
            if w["id"] in seen:
                logging.getLogger(__name__).warning("Повтор слова %s в %s пропущен", w["id"], path.name)
                continue
            seen.add(w["id"])
            words.append(w)
        modules.append({"id": data.get("id") or path.stem, "title": data.get("title") or path.stem,
                        "topic": data.get("topic") or "", "words": words})
    return modules


MODULES = load_modules()
WORDS = []
for _m in MODULES:
    for _w in _m["words"]:
        _w["module"] = _m["id"]
        WORDS.append(_w)
WORD_BY_ID = {w["id"]: w for w in WORDS}
MODULE_BY_ID = {m["id"]: m for m in MODULES}
RULES = load_json(DATA_DIR / "settings_rules.json")


def get_profile(profile_key):
    return RULES["profiles"].get(profile_key, RULES["profiles"]["steady"])


def resolve_params(profile_key):
    return dict(get_profile(profile_key))
