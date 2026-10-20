import random
import re
from datetime import date
from difflib import SequenceMatcher

from markupsafe import escape

from .config import WORDS, WORD_BY_ID
from . import srs
from . import ai as ai_client


def _word_pattern(word):
    return re.compile(r"\b" + re.escape(word["word"]) + r"\w*", re.IGNORECASE)


def _sentence_with_blank(word):
    example = word["example"]
    pattern = _word_pattern(word)
    if pattern.search(example):
        return pattern.sub("_____", example, count=1)
    return "The team discussed the _____ during the meeting."


def sentence_html(word, insert=None):
    """Пример с выделенным словом. insert — подставить другое слово (неверный вариант)."""
    example = word["example"]
    pattern = _word_pattern(word)
    m = pattern.search(example)
    if not m:
        return str(escape(example))
    shown = insert if insert is not None else m.group(0)
    return (
        str(escape(example[: m.start()]))
        + "<b>" + str(escape(shown)) + "</b>"
        + str(escape(example[m.end():]))
    )


def _ru_candidates(translation):
    text = re.sub(r"\(.*?\)", "", translation)
    return [c.lower() for c in re.findall(r"[А-Яа-яЁё]+", text) if len(c) >= 4]


def _ru_matches(token, cand):
    m = SequenceMatcher(None, token, cand).find_longest_match(0, len(token), 0, len(cand))
    return m.size >= max(4, (len(cand) + 1) // 2) and m.a <= 3 and m.b <= 1


def ru_sentence_html(word):
    """Перевод примера с выделенным переводом слова (с учётом словоформ)."""
    text = word["example_ru"]
    exact = word.get("example_ru_word")
    if exact and exact in text:
        i = text.index(exact)
        return (str(escape(text[:i])) + "<b>" + str(escape(exact)) + "</b>"
                + str(escape(text[i + len(exact):])))
    cands = _ru_candidates(word["translation"])
    parts = []
    last = 0
    for m in re.finditer(r"[А-Яа-яЁё]+", text):
        token = m.group(0).lower()
        if any(_ru_matches(token, c) for c in cands):
            parts.append(str(escape(text[last:m.start()])))
            parts.append("<b>" + str(escape(m.group(0))) + "</b>")
            last = m.end()
    parts.append(str(escape(text[last:])))
    return "".join(parts)


def make_card(word_id):
    w = WORD_BY_ID[word_id]
    return {
        "kind": "card",
        "word_id": word_id,
        "word": w["word"],
        "pos": w["pos"],
        "translation": w["translation"],
        "definition": w["definition"],
        "example_html": sentence_html(w),
        "example_ru_html": ru_sentence_html(w),
    }


def make_choice(word_id, hints=0, alias=None):
    w = WORD_BY_ID[word_id]
    options = ai_client.get_distractors(word_id, count=3, alias=alias)
    options = [o for o in options if o.lower() != w["word"].lower()] + [w["word"]]
    random.shuffle(options)
    return {
        "kind": "choice",
        "word_id": word_id,
        "sentence": _sentence_with_blank(w),
        "options": options,
        "answer": w["word"],
        "hints": hints,
        "hint_letter": w["word"][0] if hints >= 2 else "",
        "hint_len": len(w["word"]) if hints >= 2 else 0,
    }


def make_exercise(kind, word_id, hints=0, alias=None):
    if kind == "card":
        return make_card(word_id)
    if kind == "choice":
        return make_choice(word_id, hints, alias=alias)
    raise ValueError(f"unknown exercise kind: {kind}")


def explain_choice(word_id, options, alias=None):
    """Единая справка по заданию: правильный ответ в контексте + разбор неверных вариантов."""
    w = WORD_BY_ID[word_id]
    wrong = [o for o in options if o.lower() != w["word"].lower()]
    details = ai_client.explain_options(word_id, wrong, alias=alias)
    return {
        "answer": {
            "word": w["word"],
            "translation": w["translation"],
            "sentence_html": sentence_html(w),
            "sentence_ru_html": ru_sentence_html(w),
        },
        "options": [
            {
                "word": o,
                "sentence_html": sentence_html(w, insert=o),
                "translation": details.get(o, {}).get("translation", ""),
                "explanation": details.get(o, {}).get("explanation", ""),
                "source": details.get(o, {}).get("source", "bank"),
            }
            for o in wrong
        ],
    }


def build_block(db, alias, params, exclude=()):
    """Набор слов для нового блока: повторения по расписанию + новые слова.

    Слова, которые уже тренировались сегодня или были в предыдущем блоке, не берутся,
    поэтому каждый следующий блок отличается от предыдущего.
    """
    size = max(3, int(params.get("new_words") or 8))
    exclude = set(exclude)
    today = date.today().isoformat()
    last = srs.last_practiced(db, alias)
    practiced_today = {wid for wid, ts in last.items() if ts and ts.startswith(today)}
    skip = exclude | practiced_today

    learned = srs.learned_ids(db, alias)
    due = [
        r["word_id"] for r in srs.due_words(db, alias)
        if r["word_id"] in WORD_BY_ID and r["word_id"] not in skip
    ]
    new_pool = [w["id"] for w in WORDS if w["id"] not in learned and w["id"] not in skip]
    random.shuffle(new_pool)

    reviews = due[: size // 2]
    new_words = new_pool[: size - len(reviews)]
    reviews += due[len(reviews): len(reviews) + size - len(reviews) - len(new_words)]

    words = [{"word_id": wid, "is_new": True} for wid in new_words]
    words += [{"word_id": wid, "is_new": False} for wid in reviews]
    if not words:
        # Всё пройдено на сегодня: дополнительное повторение давно не встречавшихся слов,
        # но не тех, что были в прошлом блоке.
        pool = [w["id"] for w in WORDS if w["id"] not in exclude] or [w["id"] for w in WORDS]
        pool.sort(key=lambda wid: last.get(wid) or "")
        words = [{"word_id": wid, "is_new": wid not in learned} for wid in pool[:size]]
    random.shuffle(words)
    for w in words:
        w["word"] = WORD_BY_ID[w["word_id"]]["word"]
        w["translation"] = WORD_BY_ID[w["word_id"]]["translation"]
    return words
