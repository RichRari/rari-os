"""Reads what every other agent reported in the last day and has the AI brain write a
short briefing: what happened, what needs attention, what to do next."""
import json
import re
from datetime import datetime, timedelta, timezone

from .. import db, llm
from .base import Agent, Result

SYSTEM = (
    "You are the briefing agent inside Rari OS, a personal AI operating system running on "
    "Rari's Mac mini. Rari is a cybersecurity student and aspiring SOC analyst. Write a short "
    "briefing from the agent reports you are given: 1) overall status in one line, 2) anything "
    "that needs attention, written like a SOC analyst's triage note, 3) up to three next steps. "
    "All times are already in Rari's local time: always use local time. Alert runs include full "
    "details such as file paths: name them. Be concise and plain. Do not invent events that are "
    "not in the reports."
)


def plain(text: str) -> str:
    """Strip Markdown so a one-line preview reads cleanly."""
    text = re.sub(r"[*`]+", "", text)
    return re.sub(r"^[#>\-\s]+", "", text).strip()


def build_briefing_input(hours: int = 24) -> tuple:
    """What the AI sees: the last day of runs in local time, with full details for alerts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    runs = [r for r in db.recent_runs(300) if r["started"] >= cutoff and r["agent"] != "daily_briefing"]
    compact = []
    for r in runs[:150]:
        item = {"agent": r["agent"], "time": db.to_local(r["started"]), "status": r["status"],
                "summary": r["summary"]}
        if r["status"] in ("alert", "error"):
            details = json.dumps(r["details"], default=str)
            item["details"] = details if len(details) <= 3000 else details[:3000] + "...(truncated)"
        compact.append(item)
    now = datetime.now().astimezone()
    header = f"CURRENT LOCAL TIME: {db.to_local(now.isoformat())} ({now.tzname()})\n"
    return runs, header + json.dumps(compact, default=str)


class DailyBriefingAgent(Agent):
    name = "daily_briefing"
    title = "Daily Briefing"
    description = "Uses the AI brain to summarize the last 24 hours of agent activity."
    default_interval = 86400

    def run(self) -> Result:
        runs, prompt = build_briefing_input()
        if not runs:
            return Result("ok", "Nothing to brief yet — no agent activity in the last 24 hours.")
        if not llm.available():
            alerts = sum(1 for r in runs if r["status"] == "alert")
            return Result(
                "ok",
                f"{len(runs)} runs, {alerts} alerts in 24h (add an API key for an AI-written briefing)",
                {"runs": len(runs), "alerts": alerts},
            )
        text = llm.ask(SYSTEM, [{"role": "user", "content": prompt}], max_tokens=700)
        lines = [plain(ln) for ln in text.strip().splitlines() if plain(ln)]
        first = lines[0][:160] if lines else "Briefing ready"
        return Result("ok", first, {"briefing": text, "runs_reviewed": len(runs)})
