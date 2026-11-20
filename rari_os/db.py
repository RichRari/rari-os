"""SQLite storage: agent settings, run history, and chat messages."""
from __future__ import annotations
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.getenv("RARI_OS_DATA") or Path(__file__).resolve().parent.parent / "data")
DB_PATH = DATA_DIR / "rari_os.db"
_lock = threading.RLock()
_local = threading.local()
_initialized = False


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_local(iso):
    """UTC ISO timestamp -> readable local time, e.g. 'Thu Nov 19, 6:52 PM'."""
    if not iso:
        return None
    d = datetime.fromisoformat(iso).astimezone()
    return d.strftime("%a %b %d, ") + d.strftime("%I:%M %p").lstrip("0")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def conn() -> sqlite3.Connection:
    """One connection per thread: SQLite connections must not be shared across threads."""
    global _initialized
    c = getattr(_local, "conn", None)
    if c is None:
        c = connect()
        _local.conn = c
    if not _initialized:
        with _lock:
            if not _initialized:
                init(c)
                _initialized = True
    return c


def init(c: sqlite3.Connection) -> None:
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS agents (
            name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            interval_seconds INTEGER NOT NULL,
            last_run TEXT,
            last_status TEXT,
            state TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            started TEXT NOT NULL,
            status TEXT NOT NULL,          -- ok | alert | error
            summary TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,            -- user | assistant
            content TEXT NOT NULL,
            created TEXT NOT NULL
        );
        """
    )
    c.commit()


def ensure_agent(name: str, interval: int, enabled: bool) -> None:
    with _lock:
        conn().execute(
            "INSERT OR IGNORE INTO agents (name, enabled, interval_seconds) VALUES (?, ?, ?)",
            (name, int(enabled), interval),
        )
        conn().commit()


def get_agent(name: str) -> dict:
    row = conn().execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else {}


def update_agent(name: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _lock:
        conn().execute(f"UPDATE agents SET {cols} WHERE name = ?", (*fields.values(), name))
        conn().commit()


def get_state(name: str) -> dict:
    return json.loads(get_agent(name).get("state") or "{}")


def set_state(name: str, state: dict) -> None:
    update_agent(name, state=json.dumps(state))


def add_run(agent: str, status: str, summary: str, details: dict) -> int:
    with _lock:
        cur = conn().execute(
            "INSERT INTO runs (agent, started, status, summary, details) VALUES (?, ?, ?, ?, ?)",
            (agent, now(), status, summary, json.dumps(details, default=str)),
        )
        conn().commit()
        return cur.lastrowid


def recent_runs(limit: int = 50, agent: str | None = None) -> list[dict]:
    if agent:
        rows = conn().execute(
            "SELECT * FROM runs WHERE agent = ? ORDER BY id DESC LIMIT ?", (agent, limit)
        ).fetchall()
    else:
        rows = conn().execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"])
        out.append(d)
    return out


def add_message(role: str, content: str) -> None:
    with _lock:
        conn().execute(
            "INSERT INTO messages (role, content, created) VALUES (?, ?, ?)", (role, content, now())
        )
        conn().commit()


def recent_messages(limit: int = 20) -> list[dict]:
    rows = conn().execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in reversed(rows)]
