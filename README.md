# Rari OS

A personal AI operating system that runs on a Mac mini. A background **kernel** runs a
set of **agents** on a schedule, logs everything they find, and an **AI brain** (Claude)
can read all of it and answer questions about it. A local **control panel** lets you
turn agents on and off, change their schedules, run them on demand, read the activity
log and chat with the AI.

```
┌──────────── Control panel (http://127.0.0.1:8787) ────────────┐
│  Agent cards · on/off · schedule · Run now │  AI brain chat   │
│  Activity log (click a row for full details)                  │
└───────────────────────────────┬───────────────────────────────┘
                     FastAPI server (rari_os/main.py)
          ┌─────────────────────┼─────────────────────┐
     Kernel/scheduler       SQLite store           AI brain
     (scheduler.py)          (db.py)               (llm.py → Claude)
          │
   ┌──────┼───────────────┬──────────────────┐
 System Health   File Integrity Monitor   Daily Briefing
```

## Agents in v0.1

| Agent | What it does | Default schedule |
|---|---|---|
| System Health | CPU, memory, disk, uptime, top processes; alerts past 85% / 90% / 90% | Every 5 min |
| File Integrity Monitor | SHA-256 hashes every file in your watched folders; alerts on added / changed / deleted files (same idea as Wazuh or Tripwire FIM) | Every 15 min |
| Daily Briefing | Has Claude write a triage-style summary of the last 24 hours of agent activity | Daily |

## Install (Mac)

1. Make sure you have Python 3.9 or newer: `python3 --version`
   (if it's missing: `xcode-select --install`, or `brew install python`).
2. Unzip this folder somewhere, e.g. `~/rari-os`.
3. In Terminal:
   ```bash
   cd ~/rari-os
   ./run.sh
   ```
   The first run sets up its own Python environment (about a minute) and creates `.env`.
4. Open **http://127.0.0.1:8787** in your browser.

### Turn on the AI brain
Open `.env`, paste your key from console.anthropic.com after `ANTHROPIC_API_KEY=`,
then stop (Ctrl+C) and run `./run.sh` again. API usage is billed by Anthropic.

### Choose what the File Integrity Monitor watches
In `.env`, set `RARI_OS_WATCH` to one or more folders, comma-separated:
`RARI_OS_WATCH=~/Documents,~/Desktop`. The first run records a baseline; every run
after that reports changes against it.

## Security notes
- The control panel listens on `127.0.0.1` only, so nothing else on your network can reach it.
- Your API key stays in `.env` on your Mac. Don't commit `.env` to GitHub (`.gitignore` already excludes it).
- Agents only read; none of them change files or settings.

## Add your own agent
Create `rari_os/agents/my_agent.py`:

```python
from .base import Agent, Result

class MyAgent(Agent):
    name = "my_agent"
    title = "My Agent"
    description = "One line about what it does."
    default_interval = 3600  # seconds

    def run(self) -> Result:
        # do the work; self.load_state()/self.save_state() keep memory between runs
        return Result("ok", "One-line summary for the panel", {"any": "details"})
```

Then add `MyAgent()` to `AGENTS` in `rari_os/agents/__init__.py` and restart.
Return `"alert"` instead of `"ok"` when it finds something worth a look.

## API
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | Version and whether the AI brain is configured |
| GET | `/api/agents` | All agents with state and last result |
| PATCH | `/api/agents/{name}` | `{"enabled": bool, "interval_seconds": int}` |
| POST | `/api/agents/{name}/run` | Run an agent now |
| GET | `/api/runs?limit=&agent=` | Activity log |
| GET/POST | `/api/chat` | Chat history / send `{"message": "..."}` |

Data lives in `data/rari_os.db` (SQLite).
