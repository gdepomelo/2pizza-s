import random
import re
from datetime import date
from difflib import SequenceMatcher

from markupsafe import escape

from .config import MODULES, RULES, WORDS, WORD_BY_ID
from . import srs
from . import ai as ai_client


def _surface_variants(text):
    """Варианты написания фразы из словаря, от длинных к коротким:
    «a/one hundred» → «a hundred», «one hundred»; «call / phone» → «call», «phone»;
    «the (United) States» → с «United» и без; «1st (first)» → «1st», «first»;
    «Would you like...?» → «Would you like»."""
    text = re.sub(r"[.?!]+$", "", text.strip())
    bases = {text}
    for sep in (" / ", "/"):
        for base in list(bases):
            if sep in base:
                bases.update(x.strip() for x in base.split(sep))
    expanded = set()
    for base in bases:
        expanded.add(re.sub(r"\s*\([^)]*\)", "", base))           # без скобок
        expanded.add(re.sub(r"[()]", "", base))                       # с содержимым скобок
        expanded.update(re.findall(r"\(([^)]*)\)", base))            # только содержимое скобок
    variants = set()
    for base in expanded:
        for part in re.split(r"\.\.\.|…", base):
            part = re.sub(r"\s+", " ", part.strip(" ,"))
            if not part:
                continue
            options = [[]]
            for tok in part.split():
                alts = tok.split("/") if "/" in tok else [tok]
                options = [o + [x] for o in options for x in alts if x][:16]
            variants.update(" ".join(o) for o in options if o)
    # «at (time)» — в скобках пометка, само слово короткое; «a/one hundred» — «a» не берём.
    core = re.sub(r"\s*\([^)]*\)", "", text)
    min_len = 3 if len(core) > 3 else 1
    return sorted((v for v in variants if len(v) >= min_len), key=len, reverse=True)


_DETERMINERS = r"(?:a|an|the|my|your|his|her|our|their|its|some)"
_BE = r"(?:be|am|is|are|was|were|been|being|'m|'s|'re)"


def _token_pattern(tok, last):
    low = tok.lower()
    if low in ("a", "an", "the", "my", "your", "his", "her", "our", "their", "its", "some"):
        return _DETERMINERS
    if low == "be":
        return _BE
    # окончания: -s, -es, -ed, -ing, -'s; у первого и последнего слова фразы
    return re.escape(tok) + (r"\w*" if last or True else "")


def find_word(word, text):
    """Позиция слова/фразы в предложении или None.

    Учитывает окончания (reads, uploaded), формы be (is lucky), замену артикля/местоимения
    (share a photo → share the photo) и до двух вставленных слов
    (have long hair → have really long hair).
    """
    for strict in (True, False):
        for v in _surface_variants(word["word"]):
            toks = v.split()
            if not toks:
                continue
            parts = [_token_pattern(t, i == len(toks) - 1) for i, t in enumerate(toks)]
            if strict:
                parts = [re.escape(t) for t in toks[:-1]] + [re.escape(toks[-1]) + r"\w*"]
                gap = r"\s+"
            else:
                gap = r"\s+(?:[\w'-]+\s+){0,2}?"
            pat = r"(?<![\w'])" + gap.join(parts) + r"(?![\w])" if not strict else r"(?<![\w'])" + r"\s+".join(parts)
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m
    return None


def option_text(text):
    """Как показывать вариант ответа: «Would you like...?» → «Would you like»."""
    v = _surface_variants(text)
    return v[-1] if len(v) == 1 else re.sub(r"[.?!]+$", "", text.strip())


def _sentence_with_blank(word):
    m = find_word(word, word["example"])
    if not m:
        return None
    return word["example"][: m.start()] + "_____" + word["example"][m.end():]


def sentence_html(word, insert=None):
    """Пример с выделенным словом. insert — подставить другое слово (неверный вариант)."""
    example = word["example"]
    m = find_word(word, example)
    if not m:
        return str(escape(example))
    shown = option_text(insert) if insert is not None else m.group(0)
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
    sentence = _sentence_with_blank(w)
    return {
        "kind": "choice",
        "word_id": word_id,
        # Если слова нет в примере дословно — вопрос по определению вместо пропуска.
        "prompt": ("Выберите слово для пропуска и нажмите «Ответить»:" if sentence
                   else "Какое слово или фраза подходит под определение? Выберите и нажмите «Ответить»:"),
        "sentence": sentence or w["definition"],
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


def module_progress(db, alias):
    """Прогресс по модулям: сколько слов начато и закреплено; текущий — первый незавершённый."""
    rows = db.execute("SELECT word_id, box FROM srs WHERE alias=?", (alias,)).fetchall()
    box = {r["word_id"]: r["box"] for r in rows}
    fluent_box = RULES["srs"]["fluent_box"]
    result = []
    current_found = False
    for m in MODULES:
        ids = [w["id"] for w in m["words"]]
        started = sum(1 for i in ids if i in box)
        passed = sum(1 for i in ids if box.get(i, 0) >= 1)
        fluent = sum(1 for i in ids if box.get(i, 0) >= fluent_box)
        if started == len(ids):
            status = "done"
        elif not current_found:
            status = "current"
            current_found = True
        else:
            status = "started" if started else "locked"
        result.append({"id": m["id"], "title": m["title"], "topic": m.get("topic", ""), "total": len(ids),
                       "started": started, "passed": passed, "fluent": fluent, "status": status})
    return result


def current_module(db, alias):
    """Первый модуль, в котором остались ещё не изученные слова."""
    learned = srs.learned_ids(db, alias)
    for m in MODULES:
        if any(w["id"] not in learned for w in m["words"]):
            return m
    return None


def module_finished(db, alias, module_id):
    learned = srs.learned_ids(db, alias)
    m = next((m for m in MODULES if m["id"] == module_id), None)
    return bool(m) and all(w["id"] in learned for w in m["words"])


def next_module(module_id):
    ids = [m["id"] for m in MODULES]
    if module_id in ids and ids.index(module_id) + 1 < len(ids):
        return MODULES[ids.index(module_id) + 1]
    return None


def build_block(db, alias, params, exclude=(), mode="auto"):
    """Слова для нового блока.

    1. Если есть слова, срок повторения которых подошёл, — блок повторения (день начинается с них).
    2. Иначе — новые слова только из текущего модуля. Если их осталось меньше размера блока,
       блок короче, а после него модуль завершается.
    3. Если всё пройдено — дополнительное повторение давно не встречавшихся слов.
    mode="new" пропускает шаг 1 (кнопка «Приступить к следующему модулю»).
    Слова сегодняшних блоков и предыдущего блока не повторяются.
    """
    size = max(3, int(params.get("new_words") or 8))
    exclude = set(exclude)
    today = date.today().isoformat()
    last = srs.last_practiced(db, alias)
    practiced_today = {wid for wid, ts in last.items() if ts and ts.startswith(today)}
    skip = exclude | practiced_today
    learned = srs.learned_ids(db, alias)

    kind, module_id, ids = None, None, []
    due = [
        r["word_id"] for r in srs.due_words(db, alias)
        if r["word_id"] in WORD_BY_ID and r["word_id"] not in skip
    ]
    if due and mode != "new":
        kind, ids = "review", due[:size]
    else:
        m = current_module(db, alias)
        if m:
            fresh = [w["id"] for w in m["words"] if w["id"] not in learned]
            random.shuffle(fresh)
            kind, module_id, ids = "new", m["id"], fresh[:size]
    if not ids:
        pool = [w["id"] for w in WORDS if w["id"] not in exclude] or [w["id"] for w in WORDS]
        pool.sort(key=lambda wid: last.get(wid) or "")
        kind, ids = "extra", pool[:size]

    random.shuffle(ids)
    words = [
        {"word_id": wid, "is_new": wid not in learned,
         "word": WORD_BY_ID[wid]["word"], "translation": WORD_BY_ID[wid]["translation"]}
        for wid in ids
    ]
    return {"kind": kind, "module_id": module_id, "words": words}
