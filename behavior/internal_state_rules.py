from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from behavior.mood import Mood
from behavior.emotion_state import Emotion, EmotionState
from behavior.relationship_state import RelationshipState
from config.logger import logger

_MAX_STEP = 5  # Update Policy: no sudden jumps, ±5 = maksimum & jarang

_POSITIVE_EMOTIONS = {Emotion.HAPPY, Emotion.EXCITED, Emotion.PROUD, Emotion.SURPRISED}
_NEGATIVE_EMOTIONS = {Emotion.SAD, Emotion.WORRIED}
_MOOD_STREAK_THRESHOLD = 3  # butuh 3 emosi searah BERTURUT-TURUT sebelum mood ikut bergeser

_CURIOSITY_TRIGGER_PATTERNS = [
    r"\bkenapa\b", r"\bbagaimana\b", r"\bapa itu\b", r"\bternyata\b", r"\bbaru\b", r"\bsebenarnya\b",
]


def _clamp_step(delta: float) -> float:
    return max(-_MAX_STEP, min(_MAX_STEP, delta))


@dataclass(frozen=True)
class MoodProposal:
    target: Optional[Mood]  # None = tidak ada dorongan pindah mood saat ini
    reason: str


def propose_mood(recent_emotions: Sequence[EmotionState], current_energy_value: int) -> MoodProposal:
    """Mood TIDAK instan mengikuti Emotion — cuma bergeser kalau ada TREN emosi
    yang konsisten (Emotion Integration: 'Repeated Happy -> Mood gradually Cheerful')."""
    if current_energy_value <= 20:
        return MoodProposal(Mood.SLEEPY, "energi sangat rendah")

    if len(recent_emotions) < _MOOD_STREAK_THRESHOLD:
        return MoodProposal(None, "belum cukup riwayat emosi")

    last_n = recent_emotions[-_MOOD_STREAK_THRESHOLD:]
    positive_streak = all(e.current in _POSITIVE_EMOTIONS for e in last_n)
    negative_streak = all(e.current in _NEGATIVE_EMOTIONS for e in last_n)

    if positive_streak:
        return MoodProposal(Mood.CHEERFUL, "emosi positif berulang")
    if negative_streak:
        return MoodProposal(Mood.LONELY, "emosi negatif berulang")

    return MoodProposal(None, "tidak ada tren emosi yang jelas")


def apply_mood(current: Mood, proposal: MoodProposal) -> Mood:
    if proposal.target is None or proposal.target == current:
        return current
    logger.info("Mood Changed: {} -> {} (reason='{}')", current.value, proposal.target.value, proposal.reason)
    return proposal.target


def compute_energy_delta(mood: Mood, elapsed_seconds: float) -> float:
    """Energy berkurang tiap pertukaran pesan (biaya 'ngobrol'), pulih perlahan
    seiring waktu idle. Mood Cheerful/Relaxed mempercepat pemulihan (State
    Interaction: 'Mood = Cheerful -> Energy Recovery Faster')."""
    base_cost = -1.5
    recovery_rate = 0.02 if mood in (Mood.CHEERFUL, Mood.RELAXED) else 0.01
    recovery = min(3.0, recovery_rate * elapsed_seconds)
    return _clamp_step(base_cost + recovery)


def compute_curiosity_delta(user_input: str) -> tuple[float, Optional[str]]:
    if any(re.search(p, user_input, re.IGNORECASE) for p in _CURIOSITY_TRIGGER_PATTERNS):
        return _clamp_step(3.0), user_input[:80]
    return _clamp_step(-0.3), None


def compute_curiosity_decay(elapsed_seconds: float) -> float:
    return _clamp_step(-0.01 * elapsed_seconds / 60)


def compute_initiative_delta(
    energy_value: int,
    curiosity_level: int,
    relationship_state: Optional[RelationshipState],
    idle_seconds: float,
) -> float:
    """High Energy -> Initiative Higher. High Curiosity -> Initiative Slightly Higher.
    High Trust -> Initiative slightly increases. Low Comfort -> Initiative slightly
    decreases. Idle lama -> Initiative naik (dorongan 'menyapa duluan' untuk versi
    mendatang — TIDAK memicu chat otomatis apa pun di v0.6.4)."""
    delta = 0.0

    if energy_value >= 70:
        delta += 1.0
    elif energy_value <= 30:
        delta -= 0.5

    if curiosity_level >= 70:
        delta += 0.5

    if relationship_state is not None:
        if relationship_state.trust.current >= 70:
            delta += 0.5
        if relationship_state.comfort.current <= 30:
            delta -= 0.5

    if idle_seconds >= 600:
        delta += 1.0

    return _clamp_step(delta)