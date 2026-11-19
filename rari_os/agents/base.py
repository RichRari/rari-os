"""Base class every agent extends. To add an agent: subclass Agent, implement run(),
and add it to AGENTS in rari_os/agents/__init__.py."""
from dataclasses import dataclass, field

from .. import db


@dataclass
class Result:
    status: str              # "ok", "alert" or "error"
    summary: str             # one line shown on the control panel
    details: dict = field(default_factory=dict)


class Agent:
    name: str = "agent"
    title: str = "Agent"
    description: str = ""
    default_interval: int = 3600     # seconds between runs
    default_enabled: bool = True

    # Per-agent memory that survives restarts
    def load_state(self) -> dict:
        return db.get_state(self.name)

    def save_state(self, state: dict) -> None:
        db.set_state(self.name, state)

    def run(self) -> Result:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError
