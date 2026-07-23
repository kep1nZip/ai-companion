from __future__ import annotations

from typing import Optional

from behavior.emotion_state import Emotion, DEFAULT_EMOTION, EmotionState, DEFAULT_EMOTION_STATE
from behavior.emotion_analyzer import EmotionAnalyzer
from behavior.emotion_rules import apply_transition, decay
from behavior.emotion_history import EmotionHistory
from database.memory_manager import MemoryManager
from config.logger import logger

# Re-export untuk backward compatibility — `from behavior.emotion import Emotion`
# (kontrak dari v0.6.0) tetap jalan persis sama walau definisi fisiknya sekarang
# di emotion_state.py (dipindah untuk menghindari circular import dengan EmotionState).
__all__ = ["Emotion", "DEFAULT_EMOTION", "EmotionState", "DEFAULT_EMOTION_STATE", "EmotionCoordinator"]


class EmotionCoordinator:
    """Public interface / koordinator Emotion System. Satu-satunya titik masuk yang
    boleh dipanggil BehaviorEngine untuk urusan emosi.

    TIDAK PERNAH memanggil Gemini. TIDAK PERNAH import Qt. TIDAK PERNAH bicara ke
    AvatarManager/VoiceManager langsung. TIDAK PERNAH akses SQLite langsung."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self._analyzer = EmotionAnalyzer(memory_manager=memory_manager)
        self._history = EmotionHistory()
        self._current: EmotionState = DEFAULT_EMOTION_STATE

    @property
    def current(self) -> EmotionState:
        return self._current

    def process_message(self, user_input: str) -> EmotionState:
        """Dipanggil dari BehaviorEngine.update(). Emosi Arona bereaksi terhadap
        pesan Teacher SEBELUM Gemini membalas, sesuai Core Philosophy spec."""
        try:
            decayed = decay(self._current)
            proposal = self._analyzer.analyze(user_input, decayed)
            new_state = apply_transition(decayed, proposal)

            if new_state.current != self._current.current:
                logger.info(
                    "Emotion Changed: {} -> {} (intensity={:.2f}, reason='{}')",
                    self._current.current.value, new_state.current.value,
                    new_state.intensity, new_state.reason,
                )
            elif abs(new_state.intensity - self._current.intensity) > 1e-6:
                logger.info(
                    "Intensity Changed: {} {:.2f} -> {:.2f}",
                    new_state.current.value, self._current.intensity, new_state.intensity,
                )

            self._history.record(self._current)
            self._current = new_state
            return self._current

        except Exception as e:
            logger.warning("EmotionCoordinator gagal memproses pesan, fallback ke state sebelumnya: {}", e)
            return self._current

    def reset(self) -> None:
        logger.info("Emotion Reset")
        self._current = DEFAULT_EMOTION_STATE
        self._history.clear()

    def get_history(self, limit: int = 20) -> list[EmotionState]:
        return self._history.recent(limit)