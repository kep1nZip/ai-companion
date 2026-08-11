from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from routine.routine_event import RoutineEvent, RoutineEventType
from database.memory_manager import MemoryManager
from database.persistence_helper import save_by_marker, load_by_marker
from config.logger import logger

_PERSISTENCE_MARKER = "__ARONA_ROUTINE_HISTORY__"


class RoutineHistory:
    """Menyimpan kapan tiap RoutineEventType terakhir DISELESAIKAN (bukan cuma
    diusulkan) — dipakai untuk Cooldown Policy. Persistence lewat method PUBLIK
    MemoryManager (pola sama Relationship/Internal State), MemoryManager itu
    sendiri TIDAK diubah."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None, auto_load: bool = True, max_recent: int = 50):
        self._memory_manager = memory_manager
        self._last_triggered: dict[RoutineEventType, datetime] = {}
        self._recent: list[RoutineEvent] = []
        self._max_recent = max_recent

        if auto_load and memory_manager is not None:
            self.load()

    def last_triggered(self, event_type: RoutineEventType) -> Optional[datetime]:
        return self._last_triggered.get(event_type)

    def record(self, event: RoutineEvent) -> None:
        self._last_triggered[event.event_type] = event.created_at
        self._recent.append(event)
        if len(self._recent) > self._max_recent:
            self._recent.pop(0)
        logger.info("Routine Completed: {}", event.event_type.value)
        self.save()

    def recent(self, limit: int = 10) -> list[RoutineEvent]:
        return list(self._recent[-limit:])

    def last_event(self) -> Optional[RoutineEvent]:
        return self._recent[-1] if self._recent else None

    def save(self) -> None:
        payload = {k.value: v.isoformat() for k, v in self._last_triggered.items()}
        content = f"{_PERSISTENCE_MARKER}:{json.dumps(payload)}"
        save_by_marker(self._memory_manager, _PERSISTENCE_MARKER, content)

    def load(self) -> None:
        content = load_by_marker(self._memory_manager, _PERSISTENCE_MARKER)
        if content is None:
            return
        try:
            raw = content.split(f"{_PERSISTENCE_MARKER}:", 1)[1]
            payload = json.loads(raw)
            self._last_triggered = {
                RoutineEventType(k): datetime.fromisoformat(v) for k, v in payload.items()
            }
        except Exception as e:
            logger.warning("Gagal memuat routine history, pakai default: {}", e)