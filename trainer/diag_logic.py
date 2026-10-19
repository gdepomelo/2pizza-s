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


def compute_readiness(vocab_pct, taps_per_sec, memory_span, anxiety):
    w = RULES["weights"]
    tempo_norm = RULES["tempo_norm_taps_per_sec"]
    tempo_score = min(100.0, (taps_per_sec / tempo_norm) * 100)
    memory_score = min(100.0, max(0.0, (memory_span - 2) / 5 * 100))
    anxiety_score = max(0.0, min(100.0, (5 - anxiety) / 4 * 100))
    readiness = (
        w["vocab"] * vocab_pct
        + w["tempo"] * tempo_score
        + w["memory"] * memory_score
        + w["anxiety"] * anxiety_score
    )
    return round(readiness, 1), round(tempo_score, 1), round(memory_score, 1), round(anxiety_score, 1)


def profile_for_readiness(readiness):
    for band in RULES["readiness_bands"]:
        if readiness >= band["min"]:
            return band["profile"]
    return RULES["readiness_bands"][-1]["profile"]


def sample_usage_words(known_ids, limit=10):
    pool = [w for w in WORDS if w["id"] in known_ids]
    random.shuffle(pool)
    return pool[:limit]
