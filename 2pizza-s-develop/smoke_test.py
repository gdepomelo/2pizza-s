import os
import tempfile

os.environ.setdefault("TRAINER_DB", os.path.join(tempfile.mkdtemp(), "smoke.db"))
os.environ.pop("OPENROUTER_API_KEY", None)

from app import app
from trainer.config import WORDS

c = app.test_client()
print("index", c.get("/").status_code)
print("start", c.get("/start").status_code)
r = c.post("/start", data={"alias": "test_student", "consent": "on"}, follow_redirects=False)
print("consent post", r.status_code, r.headers.get("Location"))
print("hub", c.get("/diagnostics").status_code)
print("test page", c.get("/diagnostics/test").status_code)
print("tapping page (removed)", c.get("/diagnostics/tapping").status_code)
print("memory page", c.get("/diagnostics/memory").status_code)
print("anxiety page", c.get("/diagnostics/anxiety").status_code)

# Начинаем с последнего этапа: диагностика не должна завершиться, пока не пройдены остальные.
r = c.post("/api/diagnostics/anxiety", json={"answers": {"q1": 4, "q2": 2, "q3": 3, "q4": 2, "q5": 1}})
print("anxiety api", r.status_code, r.get_json())
assert r.get_json()["next"] == "/diagnostics/test"
assert c.get("/diagnostics/result").status_code == 302

items = [
    {"word_id": w["id"], "recognition_correct": i % 2 == 0, "usage_correct": i % 4 == 0}
    for i, w in enumerate(WORDS[:15])
]
r = c.post("/api/diagnostics/test", json={"items": items})
print("diag test api", r.status_code, r.get_json())
assert r.get_json()["next"] == "/diagnostics/memory"
r = c.post("/api/diagnostics/memory", json={"span": 5})
print("memory api", r.status_code, r.get_json())
assert r.get_json()["next"] == "/diagnostics/result"
print("result page", c.get("/diagnostics/result").status_code)
print("practice page", c.get("/practice").status_code)

seen = set()
for n in range(3):
    r = c.post("/api/practice/start")
    data = r.get_json()
    ids = [w["word_id"] for w in data["words"]]
    print("block", n + 1, r.status_code, ids)
    assert not (set(ids) & seen), "новый блок повторяет слова"
    seen |= set(ids)
    wid = ids[0]
    card = c.get(f"/api/practice/exercise?word_id={wid}&kind=card").get_json()
    print("  card", card["word"], "|", card["example_html"], "|", card["example_ru_html"])
    ch = c.get(f"/api/practice/exercise?word_id={wid}&kind=choice").get_json()
    assert ch["answer"] in ch["options"] and len(set(ch["options"])) == 4
    print("  choice", ch["sentence"], ch["options"])
    ex = c.post("/api/practice/explain", json={"word_id": wid, "options": ch["options"]}).get_json()
    print("  explain", ex["answer"]["sentence_ru_html"], "|", ex["options"][0])
    for kind, ok in (("card", False), ("card", True), ("choice", True)):
        c.post("/api/practice/answer", json={"word_id": wid, "kind": kind, "correct": ok,
                                             "response_time_ms": 3000, "block_id": data["block_id"]})
    r = c.post("/api/practice/finish", json={
        "block_id": data["block_id"],
        "results": [{"word_id": i, "clean": i != wid, "response_time_ms": 3000} for i in ids],
    })
    print("  finish", r.status_code, r.get_json())

print("cabinet", c.get("/cabinet").status_code)

r = c.get("/teacher")
print("teacher redirect", r.status_code, r.headers.get("Location"))
r = c.post("/teacher/login", data={"password": os.environ.get("TEACHER_PASSWORD", "teacher123")})
print("teacher login", r.status_code, r.headers.get("Location"))
print("dashboard", c.get("/teacher").status_code)
r = c.get("/teacher/student/test_student")
print("student page", r.status_code, "интерпретация" if "Что это значит" in r.get_data(as_text=True) else "НЕТ интерпретации")
r = c.get("/teacher/export/test_student.csv")
print("csv", r.status_code, r.data[:80])
print("csv all", c.get("/teacher/export/all.csv").status_code)
