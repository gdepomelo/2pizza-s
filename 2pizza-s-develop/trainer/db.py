import sqlite3
from flask import g, current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    alias TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    consent_at TEXT,
    level TEXT,
    profile TEXT,
    params_json TEXT
);

CREATE TABLE IF NOT EXISTS diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    vocab_pct REAL,
    known_count INTEGER,
    fluent_count INTEGER,
    taps_per_sec REAL,
    memory_span INTEGER,
    anxiety REAL,
    readiness REAL,
    profile TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS srs (
    alias TEXT NOT NULL,
    word_id TEXT NOT NULL,
    box INTEGER NOT NULL DEFAULT 0,
    due_date TEXT NOT NULL,
    reviews INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    last_time_ms INTEGER,
    PRIMARY KEY (alias, word_id)
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    block_id TEXT NOT NULL,
    word_id TEXT NOT NULL,
    exercise TEXT NOT NULL,
    correct INTEGER NOT NULL,
    response_time_ms INTEGER,
    hint_used INTEGER DEFAULT 0,
    box_after INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
