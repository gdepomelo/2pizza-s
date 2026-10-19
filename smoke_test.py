from app import app
from trainer.config import WORDS

c = app.test_client()
print("index", c.get("/").status_code)
print("start", c.get("/start").status_code)
r = c.post("/start", data={"alias": "test_student", "consent": "on"}, follow_redirects=False)
print("consent post", r.status_code, r.headers.get("Location"))
print("hub", c.get("/diagnostics").status_code)
print("test page", c.get("/diagnostics/test").status_code)
print("tapping page", c.get("/diagnostics/tapping").status_code)
print("memory page", c.get("/diagnostics/memory").status_code)
print("anxiety page", c.get("/diagnostics/anxiety").status_code)

items = []
for w in WORDS:
    items.append(
        {
            "word_id": w["id"],
            "recognition_correct": True,
            "usage_correct": w["id"] in ("deployment", "commit", "cache"),
        }
    )
r = c.post("/api/diagnostics/test", json={"items": items})
print("diag test api", r.status_code, r.get_json())
r = c.post("/api/diagnostics/tapping", json={"taps": 120, "duration": 30})
print("tapping api", r.status_code, r.get_json())
r = c.post("/api/diagnostics/memory", json={"span": 5})
print("memory api", r.status_code, r.get_json())
r = c.post(
    "/api/diagnostics/anxiety",
    json={"answers": {"1": 4, "2": 2, "3": 3, "4": 2, "5": 1}},
)
print("anxiety api", r.status_code, r.get_json())
print("result page", c.get("/diagnostics/result").status_code)
print("practice page", c.get("/practice").status_code)

r = c.post("/api/practice/start")
data = r.get_json()
print("practice start", r.status_code, "block", data.get("block_id"), "total", data.get("total"))
print("plan head", data.get("plan", [])[:2])
if data.get("plan"):
    ex = data["plan"][0]
    url = "/api/practice/exercise?word_id={}&kind={}".format(ex["word_id"], ex["kind"])
    r = c.get(url)
    payload = r.get_json()
    print("exercise", r.status_code, payload.get("kind"), payload.get("word") or payload.get("answer"))
    r = c.post(
        "/api/practice/answer",
        json={
            "word_id": ex["word_id"],
            "kind": ex["kind"],
            "correct": True,
            "response_time_ms": 4000,
            "block_id": data["block_id"],
        },
    )
    print("answer", r.status_code, r.get_json())
    r = c.post(
        "/api/practice/feedback",
        json={
            "word_id": ex["word_id"],
            "kind": ex["kind"],
            "correct": False,
            "mode": "detailed",
            "given": "wrong",
            "correct_answer": "x",
        },
    )
    print("feedback", r.status_code, sorted(r.get_json().keys()))
    r = c.post("/api/practice/finish", json={"block_id": data["block_id"]})
    print("finish", r.status_code, r.get_json())
    r = c.post("/api/practice/example", json={"word_id": ex["word_id"]})
    print("example", r.status_code, r.get_json())

r = c.get("/teacher")
print("teacher redirect", r.status_code, r.headers.get("Location"))
r = c.post("/teacher/login", data={"password": "teacher123"}, follow_redirects=False)
print("teacher login", r.status_code, r.headers.get("Location"))
r = c.get("/teacher")
print("dashboard", r.status_code)
r = c.get("/teacher/student/test_student")
print("student page", r.status_code)
r = c.get("/teacher/export/test_student.csv")
print("csv", r.status_code, r.data[:80])
r = c.get("/teacher/export/all.csv")
print("csv all", r.status_code)
