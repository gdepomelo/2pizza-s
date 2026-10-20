import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime

import requests

from .config import WORD_BY_ID

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"
AI_RATE_LIMIT = int(os.environ.get("AI_RATE_LIMIT", "10"))
AI_RATE_WINDOW = 60

SYSTEM_PROMPT = (
    "You are a helpful English teacher assistant creating materials for school students (Russian speakers) at the B1 (Intermediate) level. "
    "Your sentences must be grammatically simple but natural, using vocabulary appropriate for teenagers. "
    "Answer ONLY with valid JSON matching the requested schema. "
    "Never ask for or use personal data, names or identifiers of learners."

)

logger = logging.getLogger("trainer.ai")

_calls = defaultdict(deque)


def _rate_ok(alias):
    now = time.time()
    q = _calls[alias or "_anon"]
    while q and q[0] < now - AI_RATE_WINDOW:
        q.popleft()
    if len(q) >= AI_RATE_LIMIT:
        logger.warning("AI rate limit exceeded for session key, using fallback")
        return False
    q.append(now)
    return True


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _cache_get(db, key):
    row = db.execute("SELECT payload FROM ai_cache WHERE cache_key=?", (key,)).fetchone()
    if row:
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None
    return None


def _cache_put(db, key, payload):
    db.execute(
        "INSERT OR REPLACE INTO ai_cache (cache_key, payload, created_at) VALUES (?,?,?)",
        (key, json.dumps(payload, ensure_ascii=False), _now()),
    )
    db.commit()


def _chat(user_prompt, max_tokens=400):
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "Adaptive Lexical Trainer",
            },
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": max_tokens,
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as exc:
        logger.exception("OpenRouter request failed: %s", exc)
        return None


def _fallback_distractors(word_id, count=3):
    from .config import WORDS
    import random

    word = WORD_BY_ID[word_id]
    pool = [w["word"] for w in WORDS if w["id"] != word_id and w["pos"] == word["pos"]]
    if len(pool) < count:
        pool = [w["word"] for w in WORDS if w["id"] != word_id]
    return random.sample(pool, min(count, len(pool)))


def get_distractors(word_id, count=3, alias=None):
    """Неверные варианты (английские слова) для пропуска в примере. Правильное слово не входит."""
    from .db import get_db

    word = WORD_BY_ID.get(word_id)
    if not word:
        return []
    db = get_db()
    key = f"distr2:{word_id}"
    cached = _cache_get(db, key)
    if cached:
        return cached
    if not _rate_ok(alias):
        return _fallback_distractors(word_id, count)
    prompt = (
        f"Sentence with a gap: {word['example'].replace(word['word'], '_____')} "
        f"The correct word is '{word['word']}' ({word['pos']}). "
        f"Give {count} other English words of the same part of speech and similar difficulty "
        "that a learner might wrongly put into the gap, but that do NOT fit the meaning. "
        'JSON: {"distractors": ["..."]}'
    )
    data = _chat(prompt, max_tokens=200)
    if data and isinstance(data.get("distractors"), list):
        distractors = []
        for d in data["distractors"]:
            d = str(d).strip()
            if d and d.lower() != word["word"].lower() and d not in distractors:
                distractors.append(d)
        distractors = distractors[:count]
        if len(distractors) == count:
            _cache_put(db, key, distractors)
            return distractors
    return _fallback_distractors(word_id, count)


def _word_by_text(text):
    t = (text or "").strip().lower()
    for w in WORD_BY_ID.values():
        if w["word"].lower() == t:
            return w
    return None


def _bank_option_explanation(word, option):
    other = _word_by_text(option)
    need = f"здесь нужно «{word['translation']}»"
    if other and other["pos"] != word["pos"]:
        return f"Другая часть речи ({other['pos']} вместо {word['pos']}), а {need}."
    return f"Не подходит по смыслу: предложение теряет смысл, а {need}."


def explain_options(word_id, wrong_options, alias=None):
    """Объяснение для каждого неверного варианта: {option: {"translation", "explanation", "source"}}."""
    from .db import get_db

    word = WORD_BY_ID.get(word_id)
    if not word:
        return {}
    result = {}
    for opt in wrong_options:
        other = _word_by_text(opt)
        result[opt] = {
            "translation": other["translation"] if other else "",
            "explanation": _bank_option_explanation(word, opt),
            "source": "bank",
        }
    if not wrong_options:
        return result
    db = get_db()
    key = "expl:" + word_id + "|" + "|".join(sorted(wrong_options))
    cached = _cache_get(db, key)
    if cached is None and _rate_ok(alias):
        prompt = (
            f"Sentence with a gap: {word['example'].replace(word['word'], '_____')} "
            f"Correct word: '{word['word']}' (Russian: '{word['translation']}'). "
            f"Wrong options: {', '.join(wrong_options)}. "
            "For EACH wrong option give its Russian translation and explain in ONE short sentence "
            "in RUSSIAN why it does not fit this sentence. "
            'JSON: {"options": {"<option>": {"translation": "...", "explanation": "..."}}}'
        )
        data = _chat(prompt, max_tokens=400)
        if data and isinstance(data.get("options"), dict):
            cached = data["options"]
            _cache_put(db, key, cached)
    if isinstance(cached, dict):
        for opt in wrong_options:
            item = cached.get(opt)
            if isinstance(item, dict) and item.get("explanation"):
                result[opt] = {
                    "translation": str(item.get("translation") or result[opt]["translation"]),
                    "explanation": str(item["explanation"]),
                    "source": "ai",
                }
    return result


def get_example(word_id, alias=None):
    from .db import get_db

    db = get_db()
    key = f"ex:{word_id}"
    cached = _cache_get(db, key)
    if cached:
        return cached
    word = WORD_BY_ID.get(word_id)
    if not word:
        return None
    bank = {
        "example": word["example"],
        "example_ru": word["example_ru"],
        "source": "bank",
    }
    if not _rate_ok(alias):
        return bank
    prompt = (
        f"Word: '{word['word']}' ({word['pos']}), Russian: '{word['translation']}'. "
        "Write ONE short, natural example sentence suitable for a B1 level school student. "
        "The sentence should be 8-12 words long, use everyday school or teenage topics, and clearly show the word's meaning. "
        "Do NOT use complex grammar (like third conditionals or passive voice) or advanced IT terms. "
        "Different from this existing example: "
        f"{word['example']} "
        'JSON: {"example": "...", "example_ru": "..."}'
    )
    data = _chat(prompt, max_tokens=250)
    if data and data.get("example"):
        result = {
            "example": str(data["example"]),
            "example_ru": str(data.get("example_ru") or ""),
            "source": "ai",
        }
        _cache_put(db, key, result)
        return result
    return bank
