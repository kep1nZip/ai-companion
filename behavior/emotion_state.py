from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Emotion(Enum):
    """Emosi Arona saat ini. Diperluas dari v0.6.0 (7 nilai) jadi 10 nilai
    sesuai daftar emosi awal di spec v0.6.2."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    EMBARRASSED = "embarrassed"
    SAD = "sad"
    WORRIED = "worried"
    THINKING = "thinking"
    SURPRISED = "surprised"
    PROUD = "proud"
    SLEEPY = "sleepy"


DEFAULT_EMOTION = Emotion.NEUTRAL


@dataclass(frozen=True)
class EmotionState:
    """Satu snapshot IMMUTABLE dari emosi Arona. Emosi adalah state machine yang
    BERGERAK secara alami (Emotion Transition) — bukan nilai statis yang di-overwrite
    tiap pesan. Setiap perubahan menghasilkan EmotionState BARU, tidak pernah mutasi.

    Contoh alur transisi (rekomendasi GPT):
        Neutral -> Happy(0.45) -> [Teacher memuji] -> Excited(0.92)
                 -> [waktu berlalu, decay] -> Happy(0.60)
                 -> [tidak ada interaksi, decay] -> Neutral(0.20)
    """

    current: Emotion = DEFAULT_EMOTION
    intensity: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    previous: Optional[Emotion] = None
    reason: Optional[str] = None
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.intensity <= 1.0:
            raise ValueError("EmotionState.intensity harus berada di antara 0.0-1.0")

    def elapsed_seconds(self) -> float:
        """Detik sejak state ini terbentuk — dihitung LIVE saat dipanggil, bukan
        field statis, supaya tetap akurat tanpa perlu bikin objek baru tiap tick."""
        now = datetime.now(timezone.utc)
        return max(0.0, (now - self.timestamp).total_seconds())


DEFAULT_EMOTION_STATE = EmotionState()