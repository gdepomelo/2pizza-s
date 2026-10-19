import random
import re

from .config import RULES, WORDS, WORD_BY_ID
from . import srs
from . import ai as ai_client


def _sentence_with_blank(word):
    example = word["example"]
    pattern = re.compile(re.escape(word["word"]), re.IGNORECASE)
    if pattern.search(example):
        sentence = pattern.sub("_____", example, count=1)
    else:
        sentence = f"The team discussed the _____ during the meeting."
    return sentence


def make_card(word_id, fresh_example=None):
    w = WORD_BY_ID[word_id]
    example = fresh_example or w["example"]
    return {
        "kind": "card",
        "word_id": word_id,
        "word": w["word"],
        "pos": w["pos"],
        "translation": w["translation"],
        "example": example,
        "example_ru": w["example_ru"] if fresh_example is None else "",
        "definition": w["definition"],
    }


def make_choice(word_id, hints=0, alias=None):
    w = WORD_BY_ID[word_id]
    
    # Предложение с пропуском (как было)
    sentence = _sentence_with_blank(w)
    
    # Получаем 4 английских слова (1 правильное + 3 неправильных)
    options = ai_client.get_distractors(word_id, count=3, alias=alias)
    
    return {
        "kind": "choice",
        "word_id": word_id,
        "sentence": sentence,
        "options": options,           # Теперь тут английские слова
        "answer": w["word"],          # Правильный ответ - английское слово!
        "translation": w["translation"],
        "hints": hints,
        "hint_letter": w["word"][0] if hints >= 2 else "",
        "hint_len": len(w["word"]) if hints >= 2 else 0,
    }


def make_fill(word_id, hints=0):
    w = WORD_BY_ID[word_id]
    sentence = _sentence_with_blank(w)
    return {
        "kind": "fill",
        "word_id": word_id,
        "sentence": sentence,
        "answer": w["word"],
        "translation": w["translation"],
        "definition": w["definition"],
        "hints": hints,
        "hint_letter": w["word"][0] if hints >= 2 else "",
        "hint_len": len(w["word"]) if hints >= 2 else 0,
    }


def make_exercise(kind, word_id, hints=0, alias=None):
    if kind == "card":
        return make_card(word_id)
    if kind == "choice":
        return make_choice(word_id, hints, alias=alias)
    if kind == "fill":
        return make_fill(word_id, hints)
    raise ValueError(f"unknown exercise kind: {kind}")


def build_plan(db, alias, params):
    learned = srs.learned_ids(db, alias)
    due_rows = srs.due_words(db, alias)
    due = [r for r in due_rows if r["word_id"] in WORD_BY_ID]
    new_pool = [w for w in WORDS if w["id"] not in learned]
    random.shuffle(new_pool)
    new_words = new_pool[: params["new_words"]]
    plan = []
    for w in new_words:
        plan.append(("card", w["id"]))
        plan.append(("choice" if random.random() < 0.5 else "fill", w["id"]))
    due_sorted = sorted(due, key=lambda r: r["box"])
    for row in due_sorted:
        box = row["box"]
        if box >= 3:
            kind = "fill"
        elif box == 2:
            kind = "choice"
        else:
            kind = "card" if random.random() < 0.5 else "choice"
        plan.append((kind, row["word_id"]))
    target = params["block_length"]
    new_part = plan[: 2 * len(new_words)]
    due_part = plan[2 * len(new_words) :]
    random.shuffle(due_part)
    result = new_part + due_part
    if len(result) > target:
        result = result[:target]
    return [
        {"kind": k, "word_id": wid, "is_new": wid in {w["id"] for w in new_words}}
        for k, wid in result
    ]


def normalize_word(text):
    return (text or "").strip().lower().rstrip("s")


def is_correct_fill(user_text, answer):
    u = normalize_word(user_text)
    a = normalize_word(answer)
    return u == a
