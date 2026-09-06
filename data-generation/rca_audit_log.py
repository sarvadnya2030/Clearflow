#!/usr/bin/env python3
"""Persistent audit trail for rca_tool.py diagnoses -- the "episodic
memory" pattern from Hermes Agent's memory_store.db, applied to this
project's existing deterministic tool. Does NOT change what rca_tool.py
predicts or how -- purely records what it said, when, and why, so past
diagnoses are queryable without re-running ES queries. No LLM anywhere in
this file; the accuracy of rca_tool.py's own predictions is unaffected.
"""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "rca_audit_log.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_key TEXT UNIQUE NOT NULL,
    injection_time TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    trigger TEXT NOT NULL,
    prediction TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence TEXT NOT NULL,
    diagnosed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS heartbeat_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def already_diagnosed(conn, incident_key):
    row = conn.execute("SELECT 1 FROM diagnoses WHERE incident_key = ?", (incident_key,)).fetchone()
    return row is not None


def record(conn, incident_key, injection_time, duration_seconds, trigger, result):
    """result: the {prediction, source, evidence} dict rca_tool.diagnose() returns."""
    conn.execute(
        "INSERT OR IGNORE INTO diagnoses "
        "(incident_key, injection_time, duration_seconds, trigger, prediction, source, evidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (incident_key, str(injection_time), float(duration_seconds), trigger,
         result["prediction"], result["source"], result["evidence"]),
    )
    conn.commit()


def get_state(conn, key, default=None):
    row = conn.execute("SELECT value FROM heartbeat_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_state(conn, key, value):
    conn.execute("INSERT INTO heartbeat_state (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
    conn.commit()


def recent(conn, limit=20):
    rows = conn.execute(
        "SELECT incident_key, injection_time, trigger, prediction, source, diagnosed_at "
        "FROM diagnoses ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(zip(["incident_key", "injection_time", "trigger", "prediction", "source", "diagnosed_at"], r))
            for r in rows]


if __name__ == "__main__":
    conn = connect()
    for row in recent(conn):
        print(json.dumps(row))
