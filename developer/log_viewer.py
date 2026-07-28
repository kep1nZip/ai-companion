from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    level: str
    module: str
    message: str


def read_logs(
    log_path: Path, limit: int = 200, level_filter: Optional[str] = None, search: Optional[str] = None,
) -> list[LogEntry]:
    """Baca file log APA ADANYA — read-only murni, TIDAK PERNAH menulis ke file log."""
    if not log_path.exists():
        return []

    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    entries: list[LogEntry] = []
    for line in lines[-2000:]:
        parts = line.split(" | ", 3)
        if len(parts) < 4:
            continue

        timestamp, level, module, message = (p.strip() for p in parts)

        if level_filter and level_filter.upper() != level.upper():
            continue
        if search and search.lower() not in line.lower():
            continue

        entries.append(LogEntry(timestamp=timestamp, level=level, module=module, message=message))

    return entries[-limit:]