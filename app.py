import logging
import os
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

load_dotenv()

from trainer import db as dbm
from trainer import ai as ai_client
from trainer import diag_logic, exercises, srs
from trainer.config import DATA_DIR, DATABASE_PATH, RULES, WORDS, WORD_BY_ID, get_profile, resolve_params


def setup_logging():
    logs_dir = DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(logs_dir / "ai_errors.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    ai_logger = logging.getLogger("trainer.ai")
    ai_logger.setLevel(logging.WARNING)
    ai_logger.addHandler(handler)


def daily_backup():
    backups_dir = DATA_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"trainer_{date.today().isoformat()}.db"
    if target.exists():
        return
    src = sqlite3.connect(str(DATABASE_PATH))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["DATABASE"] = str(
        os.environ.get("TRAINER_DB") or DATABASE_PATH
    )
    setup_logging()
    dbm.init_app(app)
    daily_backup()
    register_routes(app)
    return app


def current_alias():
    return session.get("alias")


def teacher_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_teacher"):
            return redirect(url_for("teacher_login"))
        return f(*args, **kwargs)

    return wrapper


def student_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_alias():
            return redirect(url_for("consent"))
        return f(*args, **kwargs)

    return wrapper


def get_params(db, alias):
    row = db.execute("SELECT * FROM students WHERE alias=?", (alias,)).fetchone()
    if not row or not row["params_json"]:
        import json

        diag = db.execute(
            "SELECT * FROM diagnostics WHERE alias=? ORDER BY id DESC LIMIT 1",
            (alias,),
        ).fetchone()
        profile = diag["profile"] if diag else "steady"
        return resolve_params(profile), row
    import json

    return json.loads(row["params_json"]), row


def register_routes(app):
    @app.context_processor
    def inject_globals():
        return {"alias": current_alias(), "RULES": RULES}

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/start", methods=["GET", "POST"])
    def consent():
        db = dbm.get_db()
        if request.method == "POST":
            alias = (request.form.get("alias") or "").strip()
            consented = request.form.get("consent") == "on"
            if not alias or len(alias) > 40:
                flash("Введите псевдоним (до 40 символов).")
                return render_template("consent.html", form=request.form)
            if not consented:
                flash("Нужно согласие на обработку данных.")
                return render_template("consent.html", form=request.form)
            now = datetime.now().isoformat(timespec="seconds")
            row = db.execute("SELECT alias FROM students WHERE alias=?", (alias,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO students (alias, created_at, consent_at) VALUES (?,?,?)",
                    (alias, now, now),
                )
            else:
                db.execute(
                    "UPDATE students SET consent_at=? WHERE alias=?", (now, alias)
                )
            db.commit()
            session["alias"] = alias
            return redirect(url_for("diagnostics_hub"))
        return render_template("consent.html", form={})

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/diagnostics")
    @student_required
    def diagnostics_hub():
        db = dbm.get_db()
        alias = current_alias()
        diag = db.execute(
            "SELECT * FROM diagnostics WHERE alias=? ORDER BY id DESC LIMIT 1",
            (alias,),
        ).fetchone()
        return render_template("diagnostics_hub.html", diag=diag)

    @app.route("/diagnostics/test")
    @student_required
    def diagnostics_test():
        words = [w for w in WORDS]
        random_module = __import__("random")
        random_module.shuffle(words)
        return render_template("diag_test.html", words=words)

    @app.route("/diagnostics/tapping")
    @student_required
    def diagnostics_tapping():
        return render_template("diag_tapping.html", duration=RULES["tapping"]["duration_sec"])

    @app.route("/diagnostics/memory")
    @student_required
    def diagnostics_memory():
        conf = RULES["memory"]
        return render_template("diag_memory.html", conf=conf)

    @app.route("/diagnostics/anxiety")
    @student_required
    def diagnostics_anxiety():
        questions = [
            {"id": 1, "text": "Я спокойно отвечаю, когда подбираю слова на английском.", "reverse": True},
            {"id": 2, "text": "Ошибки в лексике сильно портят мне настроение на весь день.", "reverse": False},
            {"id": 3, "text": "Перед новым типом задания я немного волнуюсь.", "reverse": False},
            {"id": 4, "text": "Если не помню слово, я быстро теряюсь и отвечаю хуже.", "reverse": False},
            {"id": 5, "text": "Мне неприятно вслух произносить незнакомые слова.", "reverse": False},
        ]
        return render_template("diag_anxiety.html", questions=questions)

    @app.route("/diagnostics/result")
    @student_required
    def diagnostics_result():
        db = dbm.get_db()
        alias = current_alias()
        diag = db.execute(
            "SELECT * FROM diagnostics WHERE alias=? ORDER BY id DESC LIMIT 1",
            (alias,),
        ).fetchone()
        if not diag:
            return redirect(url_for("diagnostics_hub"))
        params, _ = get_params(db, alias)
        profile_label = get_profile(diag["profile"])["label"]
        return render_template(
            "diag_result.html", diag=diag, params=params, profile_label=profile_label
        )

    @app.route("/api/diagnostics/test", methods=["POST"])
    @student_required
    def api_diagnostics_test():
        data = request.get_json(force=True)
        items = data.get("items") or []
        vocab_pct, known, fluent = diag_logic.score_entry_test(items)
        session["diag_vocab"] = {
            "vocab_pct": vocab_pct,
            "known": known,
            "fluent": fluent,
        }
        return jsonify({"vocab_pct": vocab_pct, "known": len(known), "fluent": len(fluent)})

    @app.route("/api/diagnostics/tapping", methods=["POST"])
    @student_required
    def api_diagnostics_tapping():
        data = request.get_json(force=True)
        taps = int(data.get("taps") or 0)
        duration = float(data.get("duration") or RULES["tapping"]["duration_sec"])
        taps_per_sec = round(taps / duration, 2) if duration > 0 else 0
        session["diag_tapping"] = taps_per_sec
        return jsonify({"taps_per_sec": taps_per_sec})

    @app.route("/api/diagnostics/memory", methods=["POST"])
    @student_required
    def api_diagnostics_memory():
        data = request.get_json(force=True)
        span = int(data.get("span") or 0)
        session["diag_memory"] = span
        return jsonify({"memory_span": span})

    @app.route("/api/diagnostics/anxiety", methods=["POST"])
    @student_required
    def api_diagnostics_anxiety():
        import json

        data = request.get_json(force=True)
        answers = data.get("answers") or {}
        questions = [
            {"id": 1, "reverse": True},
            {"id": 2, "reverse": False},
            {"id": 3, "reverse": False},
            {"id": 4, "reverse": False},
            {"id": 5, "reverse": False},
        ]
        vals = []
        for q in questions:
            v = float(answers.get(str(q["id"])) or answers.get(q["id"]) or 3)
            v = max(1, min(5, v))
            vals.append((5 - v + 1) if q["reverse"] else v)
        anxiety = round(sum(vals) / len(vals), 2)

        vocab = session.get("diag_vocab") or {"vocab_pct": 0, "known": [], "fluent": []}
        taps_per_sec = session.get("diag_tapping") or 0
        memory_span = session.get("diag_memory") or 0
        readiness, tempo_s, memory_s, anxiety_s = diag_logic.compute_readiness(
            vocab["vocab_pct"], taps_per_sec, memory_span, anxiety
        )
        profile = diag_logic.profile_for_readiness(readiness)
        params = resolve_params(profile, taps_per_sec)
        alias = current_alias()
        db = dbm.get_db()
        now = datetime.now().isoformat(timespec="seconds")
        db.execute(
            """INSERT INTO diagnostics
               (alias, vocab_pct, known_count, fluent_count, taps_per_sec,
                memory_span, anxiety, readiness, profile, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                alias,
                vocab["vocab_pct"],
                len(vocab["known"]),
                len(vocab["fluent"]),
                taps_per_sec,
                memory_span,
                anxiety,
                readiness,
                profile,
                now,
            ),
        )
        db.execute(
            "UPDATE students SET level=?, profile=?, params_json=? WHERE alias=?",
            (
                _level_for_profile(profile),
                profile,
                json.dumps(params, ensure_ascii=False),
                alias,
            ),
        )
        db.commit()
        for wid in vocab["known"]:
            srs.get_or_create(db, alias, wid)
        return jsonify({"ok": True, "readiness": readiness, "profile": profile})

    def _level_for_profile(profile):
        mapping = {
            "confident": "B2",
            "steady": "B1",
            "guided": "A2",
            "supportive": "A2",
        }
        return mapping.get(profile, "B1")

    @app.route("/practice")
    @student_required
    def practice():
        db = dbm.get_db()
        alias = current_alias()
        student = db.execute(
            "SELECT * FROM students WHERE alias=?", (alias,)
        ).fetchone()
        if not student or not student["level"]:
            flash("Сначала пройдите диагностику.")
            return redirect(url_for("diagnostics_hub"))
        params, _ = get_params(db, alias)
        return render_template("practice.html", params=params)

    @app.route("/api/practice/start", methods=["POST"])
    @student_required
    def api_practice_start():
        db = dbm.get_db()
        alias = current_alias()
        params, student = get_params(db, alias)
        if not student or not student["level"]:
            return jsonify({"error": "no_diagnostics"}), 400
        plan = exercises.build_plan(db, alias, params)
        if not plan:
            pool = [w for w in WORDS]
            __import__("random").shuffle(pool)
            plan = [{"kind": "card", "word_id": w["id"], "is_new": True} for w in pool[: params["block_length"]]]
        block_id = secrets.token_hex(8)
        session["block_id"] = block_id
        return jsonify(
            {
                "block_id": block_id,
                "plan": plan,
                "params": params,
                "total": len(plan),
            }
        )

    @app.route("/api/practice/exercise")
    @student_required
    def api_practice_exercise():
        word_id = request.args.get("word_id")
        kind = request.args.get("kind")
        if word_id not in WORD_BY_ID or kind not in ("card", "choice", "fill"):
            return jsonify({"error": "bad_request"}), 400
        db = dbm.get_db()
        alias = current_alias()
        params, _ = get_params(db, alias)
        payload = exercises.make_exercise(kind, word_id, params.get("hints", 0), alias=alias)
        return jsonify(payload)

    @app.route("/api/practice/answer", methods=["POST"])
    @student_required
    def api_practice_answer():
        data = request.get_json(force=True)
        alias = current_alias()
        db = dbm.get_db()
        word_id = data.get("word_id")
        kind = data.get("kind")
        correct = bool(data.get("correct"))
        response_time_ms = data.get("response_time_ms")
        hint_used = 1 if data.get("hint_used") else 0
        block_id = data.get("block_id") or session.get("block_id") or "unknown"
        if word_id not in WORD_BY_ID:
            return jsonify({"error": "bad_word"}), 400
        params, _ = get_params(db, alias)
        box = srs.schedule(
            db, alias, word_id, correct, response_time_ms, params["answer_limit_sec"]
        )
        now = datetime.now().isoformat(timespec="seconds")
        db.execute(
            """INSERT INTO answers
               (alias, block_id, word_id, exercise, correct, response_time_ms,
                hint_used, box_after, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (alias, block_id, word_id, kind, 1 if correct else 0,
             response_time_ms, hint_used, box, now),
        )
        db.commit()
        return jsonify({"ok": True, "box": box})

    @app.route("/api/practice/feedback", methods=["POST"])
    @student_required
    def api_practice_feedback():
        data = request.get_json(force=True)
        alias = current_alias()
        word_id = data.get("word_id")
        kind = data.get("kind")
        correct = bool(data.get("correct"))
        mode = data.get("mode") or "brief"
        if word_id not in WORD_BY_ID:
            return jsonify({"error": "bad_word"}), 400
        w = WORD_BY_ID[word_id]
        if correct:
            return jsonify(
                {
                    "correct": True,
                    "message": "Верно!" if mode != "encouraging" else "Отлично, получается!",
                    "translation": w["translation"],
                }
            )
        explanation = None
        if mode in ("detailed", "encouraging"):
            given = data.get("given") or ""
            explanation = ai_client.explain_error(
                word_id, given, data.get("correct_answer") or w["word"], alias=alias
            )
        return jsonify(
            {
                "correct": False,
                "message": "Пока мимо." if mode != "encouraging" else "Ничего, разберёмся — это часть обучения.",
                "translation": w["translation"],
                "example": w["example"],
                "example_ru": w["example_ru"],
                "explanation": explanation,
            }
        )

    @app.route("/api/practice/example", methods=["POST"])
    @student_required
    def api_practice_example():
        data = request.get_json(force=True)
        alias = current_alias()
        word_id = data.get("word_id")
        if word_id not in WORD_BY_ID:
            return jsonify({"error": "bad_word"}), 400
        result = ai_client.get_example(word_id, alias=alias)
        return jsonify(result or {})

    @app.route("/api/practice/finish", methods=["POST"])
    @student_required
    def api_practice_finish():
        data = request.get_json(force=True)
        block_id = data.get("block_id") or session.get("block_id")
        alias = current_alias()
        db = dbm.get_db()
        rows = db.execute(
            "SELECT * FROM answers WHERE alias=? AND block_id=? ORDER BY id",
            (alias, block_id),
        ).fetchall()
        if not rows:
            return jsonify({"message": "Блок пуст.", "fatigue": False})
        total = len(rows)
        correct = sum(r["correct"] for r in rows)
        times = [r["response_time_ms"] or 0 for r in rows if r["response_time_ms"]]
        avg = sum(times) / len(times) if times else 0
        fatigue = False
        fatigue_msg = None
        conf = RULES["fatigue"]
        if total >= conf["min_answers"] and len(times) >= conf["min_answers"]:
            half = len(times) // 2
            first = times[:half]
            second = times[half:]
            first_err = 1 - sum(r["correct"] for r in rows[:half]) / max(1, half)
            second_err = 1 - sum(r["correct"] for r in rows[half:]) / max(1, len(rows) - half)
            avg_first = sum(first) / max(1, len(first))
            avg_second = sum(second) / max(1, len(second))
            if (
                avg_first > 0
                and avg_second / avg_first >= conf["time_growth"]
                and second_err > first_err
            ):
                fatigue = True
                fatigue_msg = "Ответы замедлились, ошибок стало больше. Лучше сделать паузу и вернуться позже."
        rec_message = None
        params, student = get_params(db, alias)
        conf_lu = RULES["level_up"]
        fluent = srs.fluent_words(db, alias)
        acc, n = srs.accuracy_since(db, alias, 7)
        pending = db.execute(
            "SELECT id FROM recommendations WHERE alias=? AND type='level_up' AND status='pending'",
            (alias,),
        ).fetchone()
        if (
            student
            and student["level"] in conf_lu["levels"]
            and len(fluent) >= conf_lu["min_box3_words"]
            and acc is not None
            and acc >= conf_lu["min_accuracy_7d"]
            and n >= 10
            and not pending
        ):
            idx = conf_lu["levels"].index(student["level"])
            if idx + 1 < len(conf_lu["levels"]):
                new_level = conf_lu["levels"][idx + 1]
                import json as _json

                now = datetime.now().isoformat(timespec="seconds")
                message = (
                    f"Рекомендация смены уровня: {student['level']} → {new_level}. "
                    f"Слов на закреплённом уровне: {len(fluent)}, точность за 7 дней: {acc:.0%}. "
                    "Ждёт подтверждения преподавателя."
                )
                db.execute(
                    """INSERT INTO recommendations
                       (alias, type, message, payload_json, status, created_at)
                       VALUES (?,?,?,?, 'pending', ?)""",
                    (
                        alias,
                        "level_up",
                        message,
                        _json.dumps({"from": student["level"], "to": new_level}),
                        now,
                    ),
                )
                db.commit()
                rec_message = message
        accuracy = round(correct / total, 2)
        return jsonify(
            {
                "total": total,
                "correct": correct,
                "accuracy": accuracy,
                "avg_time_ms": round(avg),
                "fatigue": fatigue,
                "fatigue_message": fatigue_msg,
                "recommendation": rec_message,
            }
        )

    @app.route("/teacher/login", methods=["GET", "POST"])
    def teacher_login():
        if request.method == "POST":
            password = request.form.get("password") or ""
            expected = os.environ.get("TEACHER_PASSWORD", "teacher123")
            if password == expected:
                session["is_teacher"] = True
                return redirect(url_for("teacher_dashboard"))
            flash("Неверный пароль.")
        return render_template("teacher_login.html")

    @app.route("/teacher/logout")
    def teacher_logout():
        session.pop("is_teacher", None)
        return redirect(url_for("index"))

    @app.route("/teacher")
    @teacher_required
    def teacher_dashboard():
        import json as _json

        db = dbm.get_db()
        students = db.execute("SELECT * FROM students ORDER BY alias").fetchall()
        stats = []
        for st in students:
            acc, n = srs.accuracy_since(db, st["alias"], 7)
            fluent = srs.fluent_words(db, st["alias"])
            due = srs.due_words(db, st["alias"])
            pending = db.execute(
                "SELECT * FROM recommendations WHERE alias=? AND status='pending' ORDER BY id DESC",
                (st["alias"],),
            ).fetchall()
            params = _json.loads(st["params_json"]) if st["params_json"] else {}
            stats.append(
                {
                    "student": st,
                    "accuracy": acc,
                    "answers_n": n,
                    "fluent": len(fluent),
                    "due": len(due),
                    "params": params,
                    "pending": pending,
                }
            )
        all_pending = db.execute(
            "SELECT * FROM recommendations WHERE status='pending' ORDER BY id DESC"
        ).fetchall()
        return render_template("teacher_dashboard.html", stats=stats, pending=all_pending)

    @app.route("/teacher/student/<alias>")
    @teacher_required
    def teacher_student(alias):
        import json as _json

        db = dbm.get_db()
        st = db.execute("SELECT * FROM students WHERE alias=?", (alias,)).fetchone()
        if not st:
            abort(404)
        answers = db.execute(
            "SELECT * FROM answers WHERE alias=? ORDER BY id DESC LIMIT 100", (alias,)
        ).fetchall()
        srs_rows = db.execute(
            "SELECT * FROM srs WHERE alias=? ORDER BY box DESC, word_id", (alias,)
        ).fetchall()
        diags = db.execute(
            "SELECT * FROM diagnostics WHERE alias=? ORDER BY id DESC", (alias,)
        ).fetchall()
        recs = db.execute(
            "SELECT * FROM recommendations WHERE alias=? ORDER BY id DESC", (alias,)
        ).fetchall()
        params = _json.loads(st["params_json"]) if st["params_json"] else {}
        acc, n = srs.accuracy_since(db, alias, 7)
        return render_template(
            "teacher_student.html",
            st=st,
            answers=answers,
            srs_rows=srs_rows,
            diags=diags,
            recs=recs,
            params=params,
            word_map=WORD_BY_ID,
            accuracy=acc,
            answers_n=n,
        )

    @app.route("/teacher/student/<alias>/params", methods=["POST"])
    @teacher_required
    def teacher_update_params(alias):
        import json as _json

        db = dbm.get_db()
        st = db.execute("SELECT * FROM students WHERE alias=?", (alias,)).fetchone()
        if not st:
            abort(404)
        params = {
            "new_words": int(request.form.get("new_words") or 8),
            "answer_limit_sec": int(request.form.get("answer_limit_sec") or 20),
            "hints": int(request.form.get("hints") or 1),
            "block_length": int(request.form.get("block_length") or 12),
            "feedback_mode": request.form.get("feedback_mode") or "detailed",
        }
        db.execute(
            "UPDATE students SET params_json=? WHERE alias=?",
            (_json.dumps(params, ensure_ascii=False), alias),
        )
        db.commit()
        flash("Параметры обновлены.")
        return redirect(url_for("teacher_student", alias=alias))

    @app.route("/teacher/student/<alias>/level", methods=["POST"])
    @teacher_required
    def teacher_update_level(alias):
        db = dbm.get_db()
        level = request.form.get("level")
        if level not in RULES["level_up"]["levels"]:
            abort(400)
        db.execute("UPDATE students SET level=? WHERE alias=?", (level, alias))
        db.commit()
        flash("Уровень изменён.")
        return redirect(url_for("teacher_student", alias=alias))

    @app.route("/teacher/recommendation/<int:rec_id>/<action>", methods=["POST"])
    @teacher_required
    def teacher_recommendation(rec_id, action):
        import json as _json
        from datetime import datetime as _dt

        db = dbm.get_db()
        rec = db.execute("SELECT * FROM recommendations WHERE id=?", (rec_id,)).fetchone()
        if not rec or rec["status"] != "pending":
            abort(400)
        now = _dt.now().isoformat(timespec="seconds")
        if action == "approve":
            db.execute(
                "UPDATE recommendations SET status='approved', resolved_at=? WHERE id=?",
                (now, rec_id),
            )
            if rec["type"] == "level_up" and rec["payload_json"]:
                payload = _json.loads(rec["payload_json"])
                db.execute(
                    "UPDATE students SET level=? WHERE alias=?",
                    (payload["to"], rec["alias"]),
                )
        elif action == "reject":
            db.execute(
                "UPDATE recommendations SET status='rejected', resolved_at=? WHERE id=?",
                (now, rec_id),
            )
        else:
            abort(400)
        db.commit()
        return redirect(request.referrer or url_for("teacher_dashboard"))

    @app.route("/teacher/export/<alias>.csv")
    @teacher_required
    def teacher_export(alias):
        import csv
        import io

        db = dbm.get_db()
        rows = db.execute(
            """SELECT a.created_at, a.alias, a.word_id, a.exercise, a.correct,
                      a.response_time_ms, a.hint_used, a.box_after
               FROM answers a WHERE a.alias=? ORDER BY a.id""",
            (alias,),
        ).fetchall()
        return _csv_response(rows, f"answers_{alias}.csv")

    @app.route("/teacher/export/all.csv")
    @teacher_required
    def teacher_export_all():
        db = dbm.get_db()
        rows = db.execute(
            """SELECT created_at, alias, word_id, exercise, correct,
                      response_time_ms, hint_used, box_after
               FROM answers ORDER BY id"""
        ).fetchall()
        return _csv_response(rows, "answers_all.csv")

    def _csv_response(rows, filename):
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["created_at", "alias", "word_id", "exercise", "correct",
             "response_time_ms", "hint_used", "box_after"]
        )
        for r in rows:
            writer.writerow(
                [
                    r["created_at"], r["alias"], r["word_id"], r["exercise"],
                    r["correct"], r["response_time_ms"], r["hint_used"], r["box_after"],
                ]
            )
        resp = app.response_class(
            buf.getvalue(), mimetype="text/csv; charset=utf-8"
        )
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return resp


app = create_app()

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
    )
