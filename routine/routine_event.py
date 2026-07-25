from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, IntEnum


class RoutineEventType(Enum):
    """Type-safe (rekomendasi GPT #1) — bukan string bebas, gampang diperluas."""

    MORNING_GREETING = "morning_greeting"
    LUNCH_REMINDER = "lunch_reminder"
    DRINK_WATER = "drink_water"
    STRETCH = "stretch"
    SLEEP_REMINDER = "sleep_reminder"
    WELCOME_HOME = "welcome_home"
    IDLE_CHAT = "idle_chat"


class EventPriority(IntEnum):
    LOWEST = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5


@dataclass(frozen=True)
class RoutineEvent:
    """Immutable event object — 'laporan peluang', BUKAN perintah. Companion/Gemini
    yang memutuskan apakah peluang ini dipakai (Routine Decision Policy)."""

    event_type: RoutineEventType
    priority: EventPriority
    payload: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, at: datetime) -> bool:
        return at >= self.expires_at