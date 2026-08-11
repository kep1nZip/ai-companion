from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from behavior.behavior_state import BehaviorState
from behavior.mood import Mood
from routine.routine_event import RoutineEvent
from vision.vision_context import VisionContext
from vision.vision_signals import matches_presentation, matches_focused_work


@dataclass(frozen=True)
class DecisionContext:
    """Snapshot input untuk 1 evaluasi. Immutable, read-only terhadap sumber aslinya."""

    idle_seconds: float
    behavior_state: BehaviorState
    vision_context: Optional[VisionContext]
    routine_event: Optional[RoutineEvent]
    hour: int


class DecisionRule:
    """Weighted Rule Object (rekomendasi GPT #2). Tiap aturan = 1 object dengan
    bobot sendiri — bobot bisa diubah/dikonfigurasi dari luar (GUI/config file
    masa depan) TANPA mengubah InitiativeEngine sama sekali, karena engine cuma
    iterasi list generic `list[DecisionRule]`."""

    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        """Return alasan (str) kalau aturan ini AKTIF (kontribusi `weight` ke skor),
        atau None kalau tidak relevan sama sekali."""
        raise NotImplementedError


class IdleRule(DecisionRule):
    def __init__(self, weight: float = 20.0, threshold_seconds: float = 900.0):
        super().__init__("idle", weight)
        self._threshold = threshold_seconds

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        if ctx.idle_seconds >= self._threshold:
            return f"Teacher idle selama {int(ctx.idle_seconds // 60)} menit"
        return None


class RelationshipRule(DecisionRule):
    def __init__(self, weight: float = 15.0, min_average: int = 60):
        super().__init__("relationship", weight)
        self._min_average = min_average

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        r = ctx.behavior_state.relationship
        avg = (r.trust.current + r.comfort.current + r.affection.current) / 3
        if avg >= self._min_average:
            return f"Relationship dengan Teacher cukup dekat (avg {avg:.0f})"
        return None


class MoodBonusRule(DecisionRule):
    _POSITIVE = {Mood.CHEERFUL, Mood.CURIOUS, Mood.RELAXED}

    def __init__(self, weight: float = 10.0):
        super().__init__("mood_bonus", weight)

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        mood = ctx.behavior_state.internal.mood
        if mood in self._POSITIVE:
            return f"Mood Arona sedang {mood.value}"
        return None


class EnergyPenaltyRule(DecisionRule):
    def __init__(self, weight: float = -15.0, low_threshold: int = 30):
        super().__init__("energy_penalty", weight)
        self._low_threshold = low_threshold

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        energy = ctx.behavior_state.internal.energy.value
        if energy <= self._low_threshold:
            return f"Energi Arona rendah ({energy})"
        return None


class CuriosityRule(DecisionRule):
    def __init__(self, weight: float = 10.0, min_level: int = 60):
        super().__init__("curiosity", weight)
        self._min_level = min_level

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        level = ctx.behavior_state.internal.curiosity.level
        if level >= self._min_level:
            return f"Curiosity Arona tinggi ({level})"
        return None


class InitiativeLevelRule(DecisionRule):
    def __init__(self, weight: float = 15.0, min_level: int = 60):
        super().__init__("initiative_level", weight)
        self._min_level = min_level

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        level = ctx.behavior_state.internal.initiative.level
        if level >= self._min_level:
            return f"Internal InitiativeState tinggi ({level})"
        return None


class RoutinePendingRule(DecisionRule):
    def __init__(self, weight: float = 25.0):
        super().__init__("routine_pending", weight)

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        if ctx.routine_event is not None:
            return f"Ada routine event pending: {ctx.routine_event.event_type.value}"
        return None


DEFAULT_RULES: list[DecisionRule] = [
    IdleRule(),
    RelationshipRule(),
    MoodBonusRule(),
    EnergyPenaltyRule(),
    CuriosityRule(),
    InitiativeLevelRule(),
    RoutinePendingRule(),
]

DEFAULT_THRESHOLD = 50.0


# ---------- Suppression Policy (hard override, DI lewat boolean bukan import modul) ----------

def check_suppression(
    vision_context: Optional[VisionContext],
    is_voice_active: bool = False,
    is_actively_typing: bool = False,
) -> tuple[bool, Optional[str]]:
    """Suppression OVERRIDE skor (spec eksplisit) — bukan cuma bobot negatif besar.
    is_voice_active/is_actively_typing sengaja BOOLEAN (Dependency Injection nilai,
    bukan import speech/*) — titik ekstensi siap pakai untuk nanti Companion
    menyambungkan sinyal VoiceManager tanpa Initiative pernah import speech."""
    if is_voice_active:
        return True, "Teacher sedang menggunakan microphone"
    if is_actively_typing:
        return True, "Teacher sedang mengetik"

    if matches_presentation(vision_context):
        return True, "Teacher sedang meeting/presentasi"
    if matches_focused_work(vision_context):
        return True, "Teacher sedang coding/fokus kerja"

    return False, None