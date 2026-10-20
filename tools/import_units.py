"""Импорт слов English File из папки «units eng file» в модули тренажёра.

Запуск из корня проекта:  python tools/import_units.py ["путь к папке"]

Каждый файл «unit N [part M].json» становится модулем в data/word_lists/modules/
(порядок — по номеру юнита и части). Слово, уже встречавшееся в предыдущих
модулях, пропускается; файл без новых слов не становится модулем.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "units eng file"
DST = ROOT / "data" / "word_lists" / "modules"
SKIP_TOPICS = re.compile(r"^(More words|Practical English|Social English)", re.I)


def unit_key(path):
    m = re.match(r"unit\s*(\d+)(?:\s*part\s*(\d+))?", path.stem, re.I)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (999, 0)


def norm(word):
    return re.sub(r"\s+", " ", word.lower().strip())


def main():
    files = sorted(SRC.glob("*.json"), key=unit_key)
    if not files:
        sys.exit(f"Нет файлов в {SRC}")
    DST.mkdir(parents=True, exist_ok=True)
    for old in DST.glob("*.json"):
        old.unlink()

    seen_words, seen_ids = {}, set()
    n = 0
    for path in files:
        unit, part = unit_key(path)
        items = json.loads(path.read_text(encoding="utf-8-sig"))
        words, dups = [], 0
        for w in items:
            key = norm(w["word"])
            if key in seen_words:
                dups += 1
                continue
            wid = w["id"]
            while wid in seen_ids:
                wid = f"{w['id']}_u{unit}" if wid == w["id"] else wid + "x"
            seen_ids.add(wid)
            seen_words[key] = path.stem
            words.append(dict(w, id=wid))
        title = f"Unit {unit}" + (f" · Part {part}" if part else "")
        if not words:
            print(f"  ПРОПУЩЕН {path.name}: все {len(items)} слов уже есть в предыдущих модулях")
            continue
        topics = []
        for w in words:
            t = w.get("topic") or ""
            if t and not SKIP_TOPICS.match(t) and t not in topics:
                topics.append(t)
        n += 1
        module = {"id": f"u{unit}p{part}" if part else f"u{unit}", "title": title,
                  "topic": ", ".join(topics[:5]), "words": words}
        out = DST / f"{n:02d}_unit{unit:02d}_part{part}.json"
        out.write_text(json.dumps(module, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{out.name}: {title} — {len(words)} слов" + (f" (повторов пропущено: {dups})" if dups else "")
              + f" · {module['topic']}")
    print(f"Итого модулей: {n}, слов: {len(seen_words)}")


if __name__ == "__main__":
    main()
