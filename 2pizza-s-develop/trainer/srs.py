from datetime import date, timedelta

from .config import RULES


def _today():
    return date.today()


def get_or_create(db, alias, word_id):
    row = db.execute(
        "SELECT * FROM srs WHERE alias=? AND word_id=?", (alias, word_id)
    ).fetchone()
    if row is None:
        today = _today().isoformat()
        db.execute(
            "INSERT INTO srs (alias, word_id, box, due_date) VALUES (?,?,0,?)",
            (alias, word_id, today),
        )
        db.commit()
        return db.execute(
            "SELECT * FROM srs WHERE alias=? AND word_id=?", (alias, word_id)
        ).fetchone()
    return row


def schedule(db, alias, word_id, correct, response_time_ms, limit_sec):
    conf = RULES["srs"]
    intervals = conf["intervals_days"]
    slow_factor = conf["slow_factor"]
    row = get_or_create(db, alias, word_id)
    box = row["box"]
    slow = (
        correct
        and response_time_ms is not None
        and limit_sec
        and response_time_ms > limit_sec * 1000 * slow_factor
    )
    if correct and not slow:
        box = min(box + 1, len(intervals) - 1)
    elif correct and slow:
        box = box
    else:
        box = 0
    due = _today() + timedelta(days=intervals[box])
    db.execute(
        """UPDATE srs SET box=?, due_date=?, reviews=reviews+1,
           correct_count=correct_count+?, last_time_ms=?
           WHERE alias=? AND word_id=?""",
        (box, due.isoformat(), 1 if correct else 0, response_time_ms, alias, word_id),
    )
    db.commit()
    return box


def due_words(db, alias):
    rows = db.execute(
        """SELECT * FROM srs WHERE alias=? AND due_date<=? ORDER BY box, due_date""",
        (alias, _today().isoformat()),
    ).fetchall()
    return rows


def learned_ids(db, alias):
    rows = db.execute(
        "SELECT word_id FROM srs WHERE alias=?", (alias,)
    ).fetchall()
    return {r["word_id"] for r in rows}


def fluent_words(db, alias):
    conf = RULES["srs"]
    rows = db.execute(
        "SELECT * FROM srs WHERE alias=? AND box>=?",
        (alias, conf["fluent_box"]),
    ).fetchall()
    return rows


def last_practiced(db, alias):
    rows = db.execute(
        "SELECT word_id, MAX(created_at) AS last FROM answers WHERE alias=? GROUP BY word_id",
        (alias,),
    ).fetchall()
    return {r["word_id"]: r["last"] for r in rows}


def accuracy_since(db, alias, days=7):
    since = (_today() - timedelta(days=days)).isoformat()
    row = db.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(correct),0) AS c
           FROM answers WHERE alias=? AND created_at>=?""",
        (alias, since),
    ).fetchone()
    if not row or row["n"] == 0:
        return None, 0
    return row["c"] / row["n"], row["n"]
