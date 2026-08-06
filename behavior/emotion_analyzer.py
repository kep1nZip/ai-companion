from __future__ import annotations

from typing import Optional

from behavior.emotion_rules import EmotionTransitionProposal
from behavior.emotion_state import Emotion, EmotionState
from behavior.text_match import matches_any
from config.logger import logger
from database.memory_manager import MemoryManager

# Heuristik kata kunci SEDERHANA — BUKAN sentiment analysis berbasis AI/Gemini
# (dilarang eksplisit di spec). Pattern matching kasar untuk v0.6.2; boleh
# diperhalus di milestone berikutnya tanpa mengubah interface analyze().
_PRAISE_PATTERNS = [r"\bhebat\b", r"\bkeren\b", r"\bpintar\b", r"\bbagus\b", r"\bmakasih\b", r"\bterima kasih\b"]
_GOOD_NEWS_PATTERNS = [r"\blulus\b", r"\bpromosi\b", r"\bmenang\b", r"\bberhasil\b", r"\bsukses\b"]
_BAD_NEWS_PATTERNS = [r"\bsedih\b", r"\bgagal\b", r"\bcapek\b", r"\blelah\b", r"\bkecewa\b", r"\bsakit\b"]
_SURPRISE_PATTERNS = [r"\btiba-tiba\b", r"\bkaget\b", r"\bwow\b", r"\bwaduh\b"]


class EmotionAnalyzer:
    """Menganalisis pesan Teacher untuk mengusulkan transisi emosi Arona.

    PENTING: emosi Arona TIDAK SAMA dengan emosi Teacher — pesan Teacher cuma
    MEMENGARUHI, bukan MENENTUKAN LANGSUNG. Contoh: Teacher cerita "aku dipromosikan!"
    (emosi Teacher: senang) -> Arona jadi EXCITED (ikut senang UNTUK Teacher),
    bukan disamakan begitu saja jadi "Happy".

    TIDAK PERNAH memanggil Gemini. TIDAK PERNAH akses SQLite langsung — memory_manager
    di-inject lewat constructor (Dependency Injection), sama pola dengan modul lain."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self._memory_manager = memory_manager

    def analyze(self, user_input: str, current_state: EmotionState) -> EmotionTransitionProposal:
        try:
            if matches_any(_PRAISE_PATTERNS, user_input):
                if current_state.current == Emotion.EMBARRASSED:
                    # Rule dari spec: "Embarrassed -> Happy jika Teacher memuji Arona"
                    return EmotionTransitionProposal(Emotion.HAPPY, 0.7, "dipuji Teacher")
                return EmotionTransitionProposal(Emotion.EMBARRASSED, 0.6, "dipuji Teacher")

            if matches_any(_GOOD_NEWS_PATTERNS, user_input):
                return EmotionTransitionProposal(Emotion.EXCITED, 0.85, "Teacher berbagi kabar baik")

            if matches_any(_BAD_NEWS_PATTERNS, user_input):
                return EmotionTransitionProposal(Emotion.WORRIED, 0.65, "Teacher terlihat kurang baik")

            if matches_any(_SURPRISE_PATTERNS, user_input):
                return EmotionTransitionProposal(Emotion.SURPRISED, 0.6, "sesuatu yang mengejutkan")

            return EmotionTransitionProposal(
                current_state.current, current_state.intensity, current_state.reason or "tidak ada sinyal baru"
            )

        except Exception as e:
            logger.warning("EmotionAnalyzer gagal menganalisis, fallback netral: {}", e)
            return EmotionTransitionProposal(Emotion.NEUTRAL, 0.0, "analyzer error, fallback")