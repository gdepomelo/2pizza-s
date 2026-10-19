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
    "You are a lexical trainer assistant for English learners (Russian speakers, IT students). "
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
    pool = [
        w["word"]
        for w in WORDS
        if w["id"] != word_id and w["pos"] == word["pos"] and w["word"] != word["word"]
    ]
    if len(pool) < count:
        pool = [w["word"] for w in WORDS if w["id"] != word_id]
    return random.sample(pool, count)


def get_distractors(word_id, count=3, alias=None):
    from .db import get_db

    db = get_db()
    key = f"distr:{word_id}"
    cached = _cache_get(db, key)
    if cached:
        return cached
    word = WORD_BY_ID.get(word_id)
    if not word:
        return []
    if not _rate_ok(alias):
        return _fallback_distractors(word_id, count)
    prompt = (
        f"English word: '{word['word']}' ({word['pos']}), Russian: '{word['translation']}'. "
        f"Context: {word['example']} "
        f"Give {count} plausible WRONG translations/options in the same language and part of speech, "
        "similar difficulty, that a learner might pick by mistake. "
        'JSON: {"distractors": ["..."]}'
    )
    data = _chat(prompt, max_tokens=200)
    if data and isinstance(data.get("distractors"), list):
        distractors = [str(d) for d in data["distractors"] if str(d) != word["word"]][:count]
        if distractors:
            _cache_put(db, key, distractors)
            return distractors
    return _fallback_distractors(word_id, count)


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
        "Write ONE short fresh example sentence in professional IT English "
        "(documentation, code comments or team chat style). Different from this existing example: "
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


def explain_error(word_id, given, correct, alias=None):
    from .db import get_db

    db = get_db()
    key = f"err:{word_id}|{given}|{correct}"
    cached = _cache_get(db, key)
    if cached:
        return cached
    word = WORD_BY_ID.get(word_id)
    if not word:
        return None
    bank = {
        "explanation": (
            f"«{correct}» — это «{word['translation']}». "
            f"Обратите внимание на контекст: {word['example']}"
        ),
        "source": "bank",
    }
    if not _rate_ok(alias):
        return bank
    prompt = (
        f"Word: '{word['word']}', Russian: '{word['translation']}'. "
        f"Learner answered '{given}' instead of '{correct}'. "
        "Explain in 1-2 short sentences in RUSSIAN why the answer is wrong and how to tell them apart. "
        "Be concrete, no personal data. "
        'JSON: {"explanation": "..."}'
    )
    data = _chat(prompt, max_tokens=200)
    if data and data.get("explanation"):
        result = {"explanation": str(data["explanation"]), "source": "ai"}
        _cache_put(db, key, result)
        return result
    return bank
