"""The kernel: a background loop that runs each enabled agent when it is due."""
from __future__ import annotations
import threading
import time
import traceback
from datetime import datetime, timezone

from . import db
from .agents import AGENTS, BY_NAME

_running: set[str] = set()
_run_lock = threading.Lock()
_stop = threading.Event()


def register_all() -> None:
    for a in AGENTS:
        db.ensure_agent(a.name, a.default_interval, a.default_enabled)


def run_agent(name: str) -> dict:
    agent = BY_NAME[name]
    with _run_lock:
        if name in _running:
            return {"status": "busy", "summary": "Already running"}
        _running.add(name)
    try:
        try:
            res = agent.run()
            status, summary, details = res.status, res.summary, res.details
        except Exception as e:  # an agent crash never takes down the OS
            status, summary = "error", f"{type(e).__name__}: {e}"
            details = {"traceback": traceback.format_exc()[-2000:]}
        db.add_run(name, status, summary, details)
        db.update_agent(name, last_run=db.now(), last_status=status)
        return {"status": status, "summary": summary}
    finally:
        with _run_lock:
            _running.discard(name)


def is_running(name: str) -> bool:
    return name in _running


def _due(row: dict) -> bool:
    if not row.get("enabled"):
        return False
    if not row.get("last_run"):
        return True
    last = datetime.fromisoformat(row["last_run"])
    return (datetime.now(timezone.utc) - last).total_seconds() >= row["interval_seconds"]


def _loop() -> None:
    while not _stop.is_set():
        for a in AGENTS:
            row = db.get_agent(a.name)
            if _due(row) and not is_running(a.name):
                threading.Thread(target=run_agent, args=(a.name,), daemon=True).start()
        _stop.wait(10)


def start() -> None:
    register_all()
    threading.Thread(target=_loop, daemon=True, name="rari-os-kernel").start()


def stop() -> None:
    _stop.set()
