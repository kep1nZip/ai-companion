from __future__ import annotations

from typing import Optional

from behavior.behavior_state import BehaviorState, DEFAULT_BEHAVIOR_STATE
from behavior.emotion import EmotionCoordinator
from behavior.relationship import RelationshipCoordinator
from behavior.internal_state import InternalStateCoordinator
from database.memory_manager import MemoryManager
from config.logger import logger


class BehaviorEngine:
    """v0.6.4: Emotion, Relationship, DAN Internal State (Mood/Energy/Curiosity/
    Initiative) TERISI PENUH. BehaviorState sekarang single source of truth
    dengan 3 blok besar, siap disambungkan utuh ke Companion di v0.6.5.

    ATURAN KERAS (tidak berubah sejak v0.6.0): TIDAK PERNAH bicara ke Gemini/Avatar/
    Voice/GUI langsung. TIDAK PERNAH akses SQLite langsung. BELUM dipanggil dari
    Companion/ui manapun — tetap terisolasi sampai v0.6.5."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self._memory_manager = memory_manager
        self._emotion = EmotionCoordinator(memory_manager=memory_manager)
        self._relationship = RelationshipCoordinator(memory_manager=memory_manager)
        self._internal = InternalStateCoordinator(memory_manager=memory_manager)
        self._current_state: BehaviorState = DEFAULT_BEHAVIOR_STATE

    @property
    def current(self) -> BehaviorState:
        return self._current_state

    def update(self, user_input: str, reply: str) -> BehaviorState:
        try:
            emotion_state = self._emotion.process_message(user_input)
            relationship_state = self._relationship.process_message(user_input, emotion_state=emotion_state)
            internal_state = self._internal.process_message(
                user_input, emotion_state=emotion_state, relationship_state=relationship_state,
            )

            self._current_state = BehaviorState(
                emotion=emotion_state,
                relationship=relationship_state,
                internal=internal_state,
            )
            return self._current_state

        except Exception as e:
            logger.warning("BehaviorEngine.update gagal, fallback ke state sebelumnya: {}", e)
            return self._current_state

    def reset(self) -> None:
        logger.info("BehaviorState direset ke default.")
        self._emotion.reset()
        self._relationship.reset()
        self._internal.reset()
        self._current_state = DEFAULT_BEHAVIOR_STATE