import random

from .config import RULES, WORDS


def score_entry_test(items):
    known = []
    fluent = []
    for it in items:
        if it.get("recognition_correct"):
            known.append(it["word_id"])
            if it.get("usage_correct"):
                fluent.append(it["word_id"])
    vocab_pct = (len(known) + len(fluent)) / (len(WORDS) + len(known)) * 100 if WORDS else 0
    return round(vocab_pct, 1), known, fluent


def memory_score(memory_span):
    conf = RULES["memory"]
    low = conf["min_span"] - 1
    return min(100.0, max(0.0, (memory_span - low) / (conf["max_span"] - low) * 100))


def compute_readiness(vocab_pct, memory_span, anxiety):
    w = RULES["weights"]
    mem_s = memory_score(memory_span)
    anxiety_s = max(0.0, min(100.0, (5 - anxiety) / 4 * 100))
    readiness = w["vocab"] * vocab_pct + w["memory"] * mem_s + w["anxiety"] * anxiety_s
    return round(readiness, 1), round(mem_s, 1), round(anxiety_s, 1)


def profile_for_readiness(readiness):
    for band in RULES["readiness_bands"]:
        if readiness >= band["min"]:
            return band["profile"]
    return RULES["readiness_bands"][-1]["profile"]


def sample_usage_words(known_ids, limit=10):
    pool = [w for w in WORDS if w["id"] in known_ids]
    random.shuffle(pool)
    return pool[:limit]


PROFILE_DESCRIPTIONS = {
    "confident": (
        "Большая часть лексики уже знакома, поэтому за блок даётся больше новых слов, "
        "подсказок нет, а обратная связь — короткая."
    ),
    "steady": (
        "Хорошая база: новые слова идут средними порциями, есть одна подсказка "
        "и подробные объяснения ошибок."
    ),
    "guided": (
        "Новые слова идут небольшими порциями, с подсказками (первая буква и длина слова) "
        "и подробными объяснениями ошибок."
    ),
    "supportive": (
        "Маленькие порции слов, максимум подсказок и мягкая обратная связь — "
        "чтобы спокойно набрать базу без перегрузки."
    ),
}


def describe_profile(profile):
    return PROFILE_DESCRIPTIONS.get(profile, PROFILE_DESCRIPTIONS["steady"])


def interpret(diag):
    """Что данные диагностики говорят об обучающемся — для кабинета преподавателя."""
    if not diag:
        return []
    out = []
    vocab = diag["vocab_pct"] or 0
    if vocab >= 70:
        text = "Узнаёт большую часть лексики набора. Можно давать больше новых слов и убирать подсказки."
    elif vocab >= 40:
        text = "Базовый запас сформирован частично: часть слов знакома, часть — нет. Подходит средний темп ввода новых слов."
    else:
        text = "Большая часть слов набора незнакома. Начинать с карточек и небольших порций, с подсказками."
    out.append(("Словарный запас", f"{vocab}%", text))

    known, fluent = diag["known_count"] or 0, diag["fluent_count"] or 0
    if known == 0:
        text = "Ни одно слово не узнано — вероятно, лексика набора полностью новая."
    elif fluent / known >= 0.7:
        text = "Знакомые слова в основном умеет употреблять в контексте: пассивный и активный запас близки."
    else:
        text = (
            "Многие слова узнаёт, но не может употребить в предложении: они в пассивном запасе. "
            "Полезны упражнения на заполнение пропусков."
        )
    out.append(("Узнаёт / употребляет", f"{known} / {fluent}", text))

    span = diag["memory_span"] or 0
    if span <= 3:
        text = (
            "Небольшой объём кратковременной памяти: новые слова лучше давать маленькими порциями "
            "и чаще повторять."
        )
    elif span <= 5:
        text = "Средний объём кратковременной памяти: стандартные порции новых слов подходят."
    else:
        text = "Высокий объём кратковременной памяти (максимум теста): справится с крупными порциями слов."
    out.append(("Кратковременная память", f"{span} цифр", text))

    anx = diag["anxiety"] or 0
    if anx <= 2:
        text = "Спокойно относится к ошибкам — можно давать короткую обратную связь и лимиты времени."
    elif anx <= 3.5:
        text = "Умеренное волнение. Полезны подробные объяснения ошибок, без давления по времени."
    else:
        text = (
            "Высокая тревожность при ответах: ошибки выбивают из колеи. Нужны мягкая обратная связь, "
            "подсказки и похвала за прогресс."
        )
    out.append(("Тревожность (1–5)", f"{anx}", text))

    out.append(
        (
            "Готовность / профиль",
            f"{diag['readiness']} · {diag['profile']}",
            describe_profile(diag["profile"]),
        )
    )
    return out
