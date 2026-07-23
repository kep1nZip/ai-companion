from __future__ import annotations

from dataclasses import dataclass

from behavior.emotion_state import Emotion, EmotionState
from config.logger import logger


@dataclass(frozen=True)
class EmotionTransitionProposal:
    """Usulan transisi dari EmotionAnalyzer. BUKAN keputusan final — file inilah
    (emotion_rules.py) yang menentukan bagaimana usulan diterapkan jadi EmotionState baru."""

    emotion: Emotion
    intensity: float
    reason: str


# Emosi jangka-pendek meluruh MENUJU emosi ini kalau tidak ada interaksi baru.
# Semua ujungnya NEUTRAL — bukan "Calm", karena Calm itu Mood jangka panjang
# (rencana v0.6.4), bukan bagian dari daftar Emotion di spec ini.
_DECAY_TARGET: dict[Emotion, Emotion] = {
    Emotion.EXCITED: Emotion.HAPPY,
    Emotion.HAPPY: Emotion.NEUTRAL,
    Emotion.PROUD: Emotion.HAPPY,
    Emotion.SURPRISED: Emotion.NEUTRAL,
    Emotion.EMBARRASSED: Emotion.NEUTRAL,
    Emotion.SAD: Emotion.NEUTRAL,
    Emotion.WORRIED: Emotion.NEUTRAL,
    Emotion.THINKING: Emotion.NEUTRAL,
    Emotion.SLEEPY: Emotion.NEUTRAL,
    Emotion.NEUTRAL: Emotion.NEUTRAL,
}

# Kecepatan peluruhan intensity per detik. Emosi "meledak-ledak" (excited,
# surprised) meluruh lebih cepat daripada emosi tenang (sad, worried).
_DECAY_RATE_PER_SECOND: dict[Emotion, float] = {
    Emotion.EXCITED: 0.0015,
    Emotion.SURPRISED: 0.002,
    Emotion.HAPPY: 0.0008,
    Emotion.PROUD: 0.0009,
    Emotion.EMBARRASSED: 0.0012,
    Emotion.SAD: 0.0004,
    Emotion.WORRIED: 0.0005,
    Emotion.THINKING: 0.001,
    Emotion.SLEEPY: 0.0003,
    Emotion.NEUTRAL: 0.0,
}

_DECAY_STEP_THRESHOLD = 0.15  # di bawah ini, pindah ke decay target


def decay(state: EmotionState) -> EmotionState:
    """Terapkan peluruhan alami berbasis waktu berlalu. Dipanggil SETIAP kali
    sebelum menerapkan proposal baru — supaya emosi tidak pernah "macet" walau
    Teacher lama tidak berinteraksi."""
    if state.current == Emotion.NEUTRAL and state.intensity <= 0.0:
        return state

    elapsed = state.elapsed_seconds()
    rate = _DECAY_RATE_PER_SECOND.get(state.current, 0.0005)
    decayed_intensity = max(0.0, state.intensity - (rate * elapsed))

    if decayed_intensity <= _DECAY_STEP_THRESHOLD and state.current != Emotion.NEUTRAL:
        target = _DECAY_TARGET.get(state.current, Emotion.NEUTRAL)
        logger.info("Emotion Decayed: {} -> {}", state.current.value, target.value)
        return EmotionState(
            current=target,
            intensity=0.3 if target != Emotion.NEUTRAL else 0.0,
            previous=state.current,
            reason="natural decay",
            duration_seconds=elapsed,
        )

    if decayed_intensity == state.intensity:
        return state

    return EmotionState(
        current=state.current,
        intensity=decayed_intensity,
        previous=state.previous,
        reason=state.reason,
        duration_seconds=elapsed,
    )


def apply_transition(base_state: EmotionState, proposal: EmotionTransitionProposal) -> EmotionState:
    """Terapkan usulan EmotionAnalyzer jadi EmotionState baru. Satu-satunya tempat
    aturan transisi hidup — EmotionAnalyzer TIDAK PERNAH bikin EmotionState langsung."""
    if proposal.emotion == base_state.current:
        new_intensity = min(1.0, max(base_state.intensity, proposal.intensity))
        logger.info("Rule Applied: reinforce {} ({:.2f} -> {:.2f})",
                    proposal.emotion.value, base_state.intensity, new_intensity)
        return EmotionState(
            current=proposal.emotion,
            intensity=new_intensity,
            previous=base_state.previous,
            reason=proposal.reason,
            duration_seconds=0.0,
        )

    logger.info("Rule Applied: transition {} -> {} ({:.2f})",
                base_state.current.value, proposal.emotion.value, proposal.intensity)
    return EmotionState(
        current=proposal.emotion,
        intensity=proposal.intensity,
        previous=base_state.current,
        reason=proposal.reason,
        duration_seconds=0.0,
    )