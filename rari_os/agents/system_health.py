"""Watches the Mac mini's CPU, memory, disk and uptime, and raises an alert past a limit."""
import time

import psutil

from .base import Agent, Result

LIMITS = {"cpu": 85.0, "memory": 90.0, "disk": 90.0}


class SystemHealthAgent(Agent):
    name = "system_health"
    title = "System Health"
    description = "Checks CPU, memory and disk on this machine and alerts when one runs hot."
    default_interval = 300

    def run(self) -> Result:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        uptime_h = round((time.time() - psutil.boot_time()) / 3600, 1)
        top = sorted(
            (p.info for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"])),
            key=lambda i: i.get("memory_percent") or 0,
            reverse=True,
        )[:5]
        details = {
            "cpu_percent": cpu,
            "memory_percent": mem,
            "disk_percent": disk,
            "uptime_hours": uptime_h,
            "top_memory_processes": [
                {"name": t.get("name"), "memory_percent": round(t.get("memory_percent") or 0, 1)} for t in top
            ],
        }
        over = [k for k, v in (("cpu", cpu), ("memory", mem), ("disk", disk)) if v >= LIMITS[k]]
        summary = f"CPU {cpu:.0f}% · Memory {mem:.0f}% · Disk {disk:.0f}% · Up {uptime_h}h"
        if over:
            return Result("alert", f"High {', '.join(over)} — {summary}", details)
        return Result("ok", summary, details)
