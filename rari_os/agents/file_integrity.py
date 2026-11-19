"""File Integrity Monitor (FIM): hashes every file in the watched folders and reports
anything added, changed or deleted since the last run — the same idea as Wazuh/Tripwire FIM."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path

from .base import Agent, Result

MAX_FILES = 5000
MAX_BYTES = 50 * 1024 * 1024  # skip files over 50 MB


def watched_paths() -> list[Path]:
    raw = os.getenv("RARI_OS_WATCH", str(Path.home() / "Documents"))
    return [Path(p).expanduser() for p in raw.split(",") if p.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class FileIntegrityAgent(Agent):
    name = "file_integrity"
    title = "File Integrity Monitor"
    description = "Hashes files in your watched folders and flags anything added, changed or deleted."
    default_interval = 900

    def run(self) -> Result:
        current: dict[str, str] = {}
        skipped = 0
        for root in watched_paths():
            if not root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fn in filenames:
                    if fn.startswith("."):
                        continue
                    p = Path(dirpath) / fn
                    try:
                        if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                            skipped += 1
                            continue
                        current[str(p)] = sha256(p)
                    except (PermissionError, OSError):
                        skipped += 1
                    if len(current) >= MAX_FILES:
                        break

        state = self.load_state()
        baseline: dict[str, str] = state.get("hashes", {})
        self.save_state({"hashes": current})

        folders = ", ".join(str(p) for p in watched_paths())
        if not baseline:
            return Result(
                "ok",
                f"Baseline created: {len(current)} files in {folders}",
                {"files": len(current), "skipped": skipped},
            )

        added = sorted(set(current) - set(baseline))
        deleted = sorted(set(baseline) - set(current))
        changed = sorted(k for k in current.keys() & baseline.keys() if current[k] != baseline[k])
        details = {"added": added[:100], "changed": changed[:100], "deleted": deleted[:100],
                   "files": len(current), "skipped": skipped}
        if added or changed or deleted:
            return Result(
                "alert",
                f"{len(added)} added · {len(changed)} changed · {len(deleted)} deleted",
                details,
            )
        return Result("ok", f"No changes across {len(current)} files", details)
