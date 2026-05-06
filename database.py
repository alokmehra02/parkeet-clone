"""
database.py — SQLite persistence layer for MeetAssist.

Tables:
  sessions(id, started_at, ended_at)
  transcripts(id, session_id, timestamp, speaker, text)
  answers(id, session_id, timestamp, prompt, answer)
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from config import DB_PATH, ensure_app_dir

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        ensure_app_dir()
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _create_tables(_conn)
    return _conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS transcripts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            timestamp  TEXT NOT NULL,
            speaker    TEXT NOT NULL DEFAULT 'remote',
            text       TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS answers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            timestamp  TEXT NOT NULL,
            prompt     TEXT NOT NULL,
            answer     TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ────────────────────────────────────────────────────────────────

def create_session() -> int:
    """Insert a new session row and return its id."""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO sessions (started_at) VALUES (?)", (_now(),)
        )
        conn.commit()
        return cur.lastrowid


def end_session(session_id: int) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        conn.commit()


def save_transcript(session_id: int, text: str, speaker: str = "remote") -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO transcripts (session_id, timestamp, speaker, text) VALUES (?, ?, ?, ?)",
            (session_id, _now(), speaker, text),
        )
        conn.commit()


def save_answer(session_id: int, prompt: str, answer: str) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO answers (session_id, timestamp, prompt, answer) VALUES (?, ?, ?, ?)",
            (session_id, _now(), prompt, answer),
        )
        conn.commit()


def get_recent_transcripts(session_id: int, limit: int = 50) -> list[dict]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT timestamp, speaker, text FROM transcripts "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
