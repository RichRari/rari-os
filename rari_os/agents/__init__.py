from .daily_briefing import DailyBriefingAgent
from .file_integrity import FileIntegrityAgent
from .system_health import SystemHealthAgent

# Register agents here. Order = order on the control panel.
AGENTS = [SystemHealthAgent(), FileIntegrityAgent(), DailyBriefingAgent()]
BY_NAME = {a.name: a for a in AGENTS}
