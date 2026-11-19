"""Reads what every other agent reported in the last day and has the AI brain write a
short briefing: what happened, what needs attention, what to do next."""
import json
from datetime import datetime, timedelta, timezone

from .. import db, llm
from .base import Agent, Result

SYSTEM = (
    "You are the briefing agent inside Rari OS, a personal AI operating system running on "
    "Rari's Mac mini. Rari is a cybersecurity student and aspiring SOC analyst. Write a short "
    "briefing from the agent reports you are given: 1) overall status in one line, 2) anything "
    "that needs attention, written like a SOC analyst's triage note, 3) up to three next steps. "
    "Be concise and plain. Do not invent events that are not in the reports."
)


class DailyBriefingAgent(Agent):
    name = "daily_briefing"
    title = "Daily Briefing"
    description = "Uses the AI brain to summarize the last 24 hours of agent activity."
    default_interval = 86400

    def run(self) -> Result:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        runs = [r for r in db.recent_runs(300) if r["started"] >= cutoff and r["agent"] != self.name]
        if not runs:
            return Result("ok", "Nothing to brief yet — no agent activity in the last 24 hours.")
        compact = [
            {"agent": r["agent"], "time": r["started"], "status": r["status"], "summary": r["summary"]}
            for r in runs[:150]
        ]
        if not llm.available():
            alerts = sum(1 for r in runs if r["status"] == "alert")
            return Result(
                "ok",
                f"{len(runs)} runs, {alerts} alerts in 24h (add an API key for an AI-written briefing)",
                {"runs": len(runs), "alerts": alerts},
            )
        text = llm.ask(SYSTEM, [{"role": "user", "content": json.dumps(compact)}], max_tokens=700)
        first = text.strip().splitlines()[0][:160] if text.strip() else "Briefing ready"
        return Result("ok", first, {"briefing": text, "runs_reviewed": len(runs)})
