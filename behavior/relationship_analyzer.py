from __future__ import annotations

from typing import Optional

from behavior.text_match import matches_any
from behavior.relationship_rules import RelationshipDelta, RelationshipTransitionProposal
from behavior.emotion_state import Emotion, EmotionState
from database.memory_manager import MemoryManager
from config.logger import logger

_PRAISE_PATTERNS = [r"\bhebat\b", r"\bkeren\b", r"\bpintar\b", r"\bbagus\b", r"\bmanis\b"]
_THANKS_PATTERNS = [r"\bmakasih\b", r"\bterima kasih\b", r"\bthanks\b"]
_INSULT_PATTERNS = [r"\bbodoh\b", r"\bjelek\b", r"\bmenyebalkan\b"]

_POSITIVE_EMOTIONS = {Emotion.HAPPY, Emotion.EXCITED, Emotion.PROUD}
_NEGATIVE_EMOTIONS = {Emotion.SAD, Emotion.WORRIED}


class RelationshipAnalyzer:
    """Menganalisis pesan Teacher + EmotionState Arona untuk mengusulkan transisi
    relationship. TIDAK PERNAH memanggil Gemini. TIDAK PERNAH akses SQLite langsung —
    memory_manager di-inject (Dependency Injection), disiapkan untuk analisis lebih
    kaya di masa depan, belum benar-benar query apa pun di v0.6.3."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self._memory_manager = memory_manager

    def analyze(self, user_input: str, emotion_state: Optional[EmotionState]) -> RelationshipTransitionProposal:
        try:
            deltas: list[RelationshipDelta] = []

            if matches_any(_PRAISE_PATTERNS, user_input):
                deltas.append(RelationshipDelta("affection", 2, "Teacher memuji Arona"))

            if matches_any(_THANKS_PATTERNS, user_input):
                deltas.append(RelationshipDelta("trust", 1, "Teacher berterima kasih"))

            if matches_any(_INSULT_PATTERNS, user_input):
                deltas.append(RelationshipDelta("comfort", -2, "Teacher berkata kasar"))

            # Interaksi apa pun menambah familiarity sedikit — makin sering ngobrol,
            # makin akrab, walau isi obrolannya netral.
            deltas.append(RelationshipDelta("familiarity", 0.3, "berinteraksi dengan Teacher"))

            # Emotion Integration (sesuai spec): emosi ARONA (bukan kata kunci mentah)
            # ikut memengaruhi arah relationship.
            if emotion_state is not None:
                if emotion_state.current in _POSITIVE_EMOTIONS and emotion_state.intensity >= 0.5:
                    deltas.append(RelationshipDelta("trust", 1, f"Arona merasa {emotion_state.current.value}"))
                elif emotion_state.current in _NEGATIVE_EMOTIONS and emotion_state.intensity >= 0.5:
                    deltas.append(RelationshipDelta("comfort", -1, f"Arona merasa {emotion_state.current.value}"))

            return RelationshipTransitionProposal(deltas=tuple(deltas))

        except Exception as e:
            logger.warning("RelationshipAnalyzer gagal menganalisis, tidak ada perubahan: {}", e)
            return RelationshipTransitionProposal(deltas=())