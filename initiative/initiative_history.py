from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from database.memory_manager import MemoryManager
from database.persistence_helper import save_by_marker, load_by_marker
from config.logger import logger

_PERSISTENCE_MARKER = "__ARONA_INITIATIVE_HISTORY__"


class InitiativeHistory:
    """Melacak kapan percakapan otonom terakhir dimulai — dipakai untuk Cooldown
    Policy DAN Conversation Budget (rekomendasi GPT #3). Persistence lewat method
    PUBLIK MemoryManager (pola sama Relationship/Internal State/Routine),
    MemoryManager itu sendiri TIDAK diubah."""

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        auto_load: bool = True,
        max_per_hour: int = 3,
        max_per_day: int = 10,
        cooldown: timedelta = timedelta(minutes=45),
    ):
        self._memory_manager = memory_manager
        self._starts: list[datetime] = []
        self._max_per_hour = max_per_hour
        self._max_per_day = max_per_day
        self._cooldown = cooldown

        if auto_load and memory_manager is not None:
            self.load()

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=1)
        self._starts = [t for t in self._starts if t >= cutoff]

    def last_started(self) -> Optional[datetime]:
        return self._starts[-1] if self._starts else None

    def in_cooldown(self, now: datetime) -> bool:
        last = self.last_started()
        return last is not None and (now - last) < self._cooldown

    def cooldown_remaining(self, now: datetime) -> Optional[timedelta]:
        last = self.last_started()
        if last is None:
            return None
        remaining = self._cooldown - (now - last)
        return remaining if remaining > timedelta(0) else None

    def remaining_budget(self, now: datetime) -> dict[str, int]:
        self._prune(now)
        hour_cutoff = now - timedelta(hours=1)
        used_hour = len([t for t in self._starts if t >= hour_cutoff])
        used_day = len(self._starts)
        return {
            "hourly_remaining": max(0, self._max_per_hour - used_hour),
            "daily_remaining": max(0, self._max_per_day - used_day),
        }

    def budget_exceeded(self, now: datetime) -> bool:
        budget = self.remaining_budget(now)
        return budget["hourly_remaining"] <= 0 or budget["daily_remaining"] <= 0

    def record_start(self, now: datetime) -> None:
        self._starts.append(now)
        self._prune(now)
        logger.info("Conversation Started (autonomous)")
        self.save()

    def save(self) -> None:
        payload = [t.isoformat() for t in self._starts]
        content = f"{_PERSISTENCE_MARKER}:{json.dumps(payload)}"
        save_by_marker(self._memory_manager, _PERSISTENCE_MARKER, content)

    def load(self) -> None:
        content = load_by_marker(self._memory_manager, _PERSISTENCE_MARKER)
        if content is None:
            return
        try:
            raw = content.split(f"{_PERSISTENCE_MARKER}:", 1)[1]
            payload = json.loads(raw)
            self._starts = [datetime.fromisoformat(t) for t in payload]
        except Exception as e:
            logger.warning("Gagal memuat initiative history, pakai default: {}", e)