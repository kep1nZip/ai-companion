from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from behavior.behavior_state import BehaviorState


@dataclass(frozen=True)
class BehaviorSnapshot:
    """Immutable snapshot (rekomendasi GPT #1) — GUI/Developer Panel baca INI,
    tidak pernah baca BehaviorState/BehaviorEngine langsung."""

    emotion: str
    emotion_intensity: float
    trust: int
    comfort: int
    affection: int
    respect: int
    familiarity: int
    mood: str
    energy: int
    curiosity: int
    initiative: int


def build_behavior_snapshot(state: Optional[BehaviorState]) -> Optional[BehaviorSnapshot]:
    if state is None:
        return None
    return BehaviorSnapshot(
        emotion=state.emotion.current.value,
        emotion_intensity=state.emotion.intensity,
        trust=state.relationship.trust.current,
        comfort=state.relationship.comfort.current,
        affection=state.relationship.affection.current,
        respect=state.relationship.respect.current,
        familiarity=state.relationship.familiarity.current,
        mood=state.internal.mood.value,
        energy=state.internal.energy.value,
        curiosity=state.internal.curiosity.level,
        initiative=state.internal.initiative.level,
    )