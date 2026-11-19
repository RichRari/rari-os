"""Rari OS server: the control panel and its API. Start with ./run.sh"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from typing import Optional  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from . import __version__, db, llm, scheduler  # noqa: E402
from .agents import AGENTS, BY_NAME  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.conn()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Rari OS", version=__version__, lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    return {"version": __version__, "ai_online": llm.available(),
            "model": os.getenv("RARI_OS_MODEL", llm.DEFAULT_MODEL)}


@app.get("/api/agents")
def agents():
    out = []
    for a in AGENTS:
        row = db.get_agent(a.name)
        out.append({
            "name": a.name, "title": a.title, "description": a.description,
            "enabled": bool(row.get("enabled")), "interval_seconds": row.get("interval_seconds"),
            "last_run": row.get("last_run"), "last_status": row.get("last_status"),
            "running": scheduler.is_running(a.name),
            "last_summary": (db.recent_runs(1, a.name) or [{}])[0].get("summary"),
        })
    return out


class AgentUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = None


@app.patch("/api/agents/{name}")
def update_agent(name: str, body: AgentUpdate):
    if name not in BY_NAME:
        raise HTTPException(404, "No such agent")
    fields = {}
    if body.enabled is not None:
        fields["enabled"] = int(body.enabled)
    if body.interval_seconds is not None:
        fields["interval_seconds"] = max(30, body.interval_seconds)
    db.update_agent(name, **fields)
    return {"ok": True}


@app.post("/api/agents/{name}/run")
async def run_now(name: str):
    if name not in BY_NAME:
        raise HTTPException(404, "No such agent")
    return await run_in_threadpool(scheduler.run_agent, name)


@app.get("/api/runs")
def runs(limit: int = 50, agent: Optional[str] = None):
    return db.recent_runs(min(limit, 500), agent)


class Chat(BaseModel):
    message: str


CHAT_SYSTEM = (
    "You are the AI brain of Rari OS, a personal AI operating system running on Rari's Mac mini. "
    "You can see the current state of every agent and their most recent reports, given below. "
    "Answer questions about what the agents found, explain alerts the way a SOC analyst would, "
    "and suggest next steps. If asked to do something no agent can do yet, say so and describe "
    "what new agent would do it. Be concise.\n\nCURRENT AGENT STATE:\n"
)


@app.get("/api/chat")
def chat_history():
    return db.recent_messages(30)


@app.post("/api/chat")
async def chat(body: Chat):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Empty message")
    context = json.dumps({"agents": agents(), "recent_runs": [
        {k: r[k] for k in ("agent", "started", "status", "summary")} for r in db.recent_runs(40)
    ]}, default=str)
    history = [{"role": m["role"], "content": m["content"]} for m in db.recent_messages(12)]
    db.add_message("user", text)
    reply = await run_in_threadpool(
        llm.ask, CHAT_SYSTEM + context, history + [{"role": "user", "content": text}]
    )
    db.add_message("assistant", reply)
    return {"reply": reply}
