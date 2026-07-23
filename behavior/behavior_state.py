from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from behavior.emotion_state import EmotionState, DEFAULT_EMOTION_STATE
from behavior.relationship_state import RelationshipState, DEFAULT_RELATIONSHIP_STATE
from behavior.internal_state import InternalState, DEFAULT_INTERNAL_STATE


@dataclass(frozen=True)
class BehaviorState:
    """Single source of truth kondisi Arona (rekomendasi GPT, v0.6.4). Cuma 3
    blok besar — nanti (v0.6.5+) PromptBuilder/Avatar/Voice/Vision/Routine System
    cukup baca objek ini, tanpa perlu tahu detail implementasi tiap subsystem."""

    emotion: EmotionState = field(default_factory=lambda: DEFAULT_EMOTION_STATE)
    relationship: RelationshipState = field(default_factory=lambda: DEFAULT_RELATIONSHIP_STATE)
    internal: InternalState = field(default_factory=lambda: DEFAULT_INTERNAL_STATE)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


DEFAULT_BEHAVIOR_STATE = BehaviorState()