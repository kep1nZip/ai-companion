from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Callable, Optional

from routine.routine_event import RoutineEventType, EventPriority
from routine.routine_scheduler import TimeWindow, current_window
from routine.routine_clock import RoutineClock
from vision.vision_context import VisionContext

# ---------- Cooldown Policy (rekomendasi GPT #2) ----------
# Cooldown WAJIB dicek, bukan cuma mengandalkan history keberadaan record.
COOLDOWNS: dict[RoutineEventType, timedelta] = {
    RoutineEventType.MORNING_GREETING: timedelta(hours=24),
    RoutineEventType.LUNCH_REMINDER: timedelta(hours=20),
    RoutineEventType.DRINK_WATER: timedelta(hours=2),
    RoutineEventType.STRETCH: timedelta(minutes=90),
    RoutineEventType.SLEEP_REMINDER: timedelta(hours=20),
    RoutineEventType.WELCOME_HOME: timedelta(hours=6),
    RoutineEventType.IDLE_CHAT: timedelta(minutes=30),
}

_PRIORITY: dict[RoutineEventType, EventPriority] = {
    RoutineEventType.MORNING_GREETING: EventPriority.MEDIUM,
    RoutineEventType.LUNCH_REMINDER: EventPriority.LOW,
    RoutineEventType.DRINK_WATER: EventPriority.LOW,
    RoutineEventType.STRETCH: EventPriority.LOW,
    RoutineEventType.SLEEP_REMINDER: EventPriority.MEDIUM,
    RoutineEventType.WELCOME_HOME: EventPriority.MEDIUM,
    RoutineEventType.IDLE_CHAT: EventPriority.LOWEST,
}

_PAYLOAD: dict[RoutineEventType, str] = {
    RoutineEventType.MORNING_GREETING: "Teacher baru memulai pagi. Pertimbangkan menyapa dengan hangat.",
    RoutineEventType.LUNCH_REMINDER: "Sudah waktunya makan siang. Pertimbangkan mengingatkan Teacher.",
    RoutineEventType.DRINK_WATER: "Sudah cukup lama. Pertimbangkan mengingatkan Teacher untuk minum air.",
    RoutineEventType.STRETCH: "Teacher mungkin sudah lama duduk. Pertimbangkan menyarankan peregangan sebentar.",
    RoutineEventType.SLEEP_REMINDER: "Sudah larut malam. Pertimbangkan mengingatkan Teacher untuk istirahat.",
    RoutineEventType.WELCOME_HOME: "Teacher baru kembali setelah cukup lama tidak berinteraksi. Pertimbangkan menyambutnya.",
    RoutineEventType.IDLE_CHAT: "Sempat idle cukup lama. Pertimbangkan menanyakan kabar Teacher secara ringan.",
}

_EXPIRY: dict[RoutineEventType, timedelta] = {
    RoutineEventType.MORNING_GREETING: timedelta(hours=1),
    RoutineEventType.LUNCH_REMINDER: timedelta(minutes=45),
    RoutineEventType.DRINK_WATER: timedelta(minutes=15),
    RoutineEventType.STRETCH: timedelta(minutes=15),
    RoutineEventType.SLEEP_REMINDER: timedelta(minutes=30),
    RoutineEventType.WELCOME_HOME: timedelta(minutes=10),
    RoutineEventType.IDLE_CHAT: timedelta(minutes=10),
}


def get_priority(event_type: RoutineEventType) -> EventPriority:
    return _PRIORITY[event_type]


def get_payload(event_type: RoutineEventType) -> str:
    return _PAYLOAD[event_type]


def get_expiry_delta(event_type: RoutineEventType) -> timedelta:
    return _EXPIRY[event_type]


# ---------- Trigger Conditions ----------

def _check_morning_greeting(clock: RoutineClock, idle_seconds: float) -> bool:
    return current_window(clock) == TimeWindow.EARLY_MORNING

def _check_lunch_reminder(clock: RoutineClock, idle_seconds: float) -> bool:
    return current_window(clock) == TimeWindow.LUNCH

def _check_drink_water(clock: RoutineClock, idle_seconds: float) -> bool:
    window = current_window(clock)
    return window not in (TimeWindow.NIGHT,)

def _check_stretch(clock: RoutineClock, idle_seconds: float) -> bool:
    window = current_window(clock)
    return window not in (TimeWindow.NIGHT,) and idle_seconds < 120  # masih aktif ngobrol, bukan lagi AFK

def _check_sleep_reminder(clock: RoutineClock, idle_seconds: float) -> bool:
    return current_window(clock) == TimeWindow.NIGHT

def _check_welcome_home(clock: RoutineClock, idle_seconds: float) -> bool:
    return idle_seconds >= 6 * 3600  # tidak berinteraksi >= 6 jam

def _check_idle_chat(clock: RoutineClock, idle_seconds: float) -> bool:
    return 600 <= idle_seconds < 6 * 3600  # 10 menit - 6 jam (di bawah threshold welcome_home)


TRIGGER_CHECKS: dict[RoutineEventType, Callable[[RoutineClock, float], bool]] = {
    RoutineEventType.MORNING_GREETING: _check_morning_greeting,
    RoutineEventType.LUNCH_REMINDER: _check_lunch_reminder,
    RoutineEventType.DRINK_WATER: _check_drink_water,
    RoutineEventType.STRETCH: _check_stretch,
    RoutineEventType.SLEEP_REMINDER: _check_sleep_reminder,
    RoutineEventType.WELCOME_HOME: _check_welcome_home,
    RoutineEventType.IDLE_CHAT: _check_idle_chat,
}

# Urutan evaluasi = urutan prioritas (WELCOME_HOME dicek sebelum IDLE_CHAT supaya
# tidak keduanya "benar" sekaligus dianggap idle_chat biasa).
EVALUATION_ORDER: list[RoutineEventType] = [
    RoutineEventType.SLEEP_REMINDER,
    RoutineEventType.MORNING_GREETING,
    RoutineEventType.WELCOME_HOME,
    RoutineEventType.LUNCH_REMINDER,
    RoutineEventType.STRETCH,
    RoutineEventType.DRINK_WATER,
    RoutineEventType.IDLE_CHAT,
]


# ---------- Routine Suppression Policy (rekomendasi GPT #3) ----------

class SuppressionLevel(Enum):
    NONE = "none"
    NON_CASUAL = "non_casual"          # tunda idle chat & reminder santai
    ALL_NON_CRITICAL = "all_non_critical"  # tunda SEMUA kecuali priority CRITICAL


_NON_CASUAL_KEYWORDS = [r"\bcoding\b", r"\bmengetik\b", r"\bmenulis kode\b", r"\bemail\b"]
_ALL_SUPPRESS_KEYWORDS = [r"\bmeeting\b", r"\brapat\b", r"\bpresentasi\b", r"\bpresentation\b", r"\bcall\b", r"\bzoom\b"]


def suppression_level(vision_context: Optional[VisionContext]) -> SuppressionLevel:
    """Routine tidak cuma tahu KAPAN harus muncul, tapi juga KAPAN harus diam.
    Vision dibaca READ-ONLY, tidak pernah dimodifikasi."""
    if vision_context is None:
        return SuppressionLevel.NONE

    text = f"{vision_context.application or ''} {vision_context.summary}".lower()

    if any(re.search(p, text) for p in _ALL_SUPPRESS_KEYWORDS):
        return SuppressionLevel.ALL_NON_CRITICAL

    if any(re.search(p, text) for p in _NON_CASUAL_KEYWORDS):
        return SuppressionLevel.NON_CASUAL

    return SuppressionLevel.NONE


_NON_CASUAL_TYPES = {RoutineEventType.IDLE_CHAT, RoutineEventType.STRETCH, RoutineEventType.DRINK_WATER}


def is_suppressed(event_type: RoutineEventType, priority: EventPriority, level: SuppressionLevel) -> bool:
    if level == SuppressionLevel.NONE:
        return False
    if level == SuppressionLevel.ALL_NON_CRITICAL:
        return priority < EventPriority.CRITICAL
    if level == SuppressionLevel.NON_CASUAL:
        return event_type in _NON_CASUAL_TYPES
    return False