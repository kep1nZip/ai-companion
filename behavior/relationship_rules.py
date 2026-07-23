from __future__ import annotations

from dataclasses import dataclass

from behavior.relationship_state import RelationshipState, DIMENSION_NAMES
from config.logger import logger

_MAX_STEP = 5  # Growth Policy: no sudden jumps, +5 = maksimum & sangat jarang

_FAMILIARITY_DECAY_PER_DAY = 1.0
_DECAY_GRACE_SECONDS = 3 * 24 * 3600  # 3 hari sebelum decay mulai berlaku


@dataclass(frozen=True)
class RelationshipDelta:
    dimension: str
    amount: float
    reason: str


@dataclass(frozen=True)
class RelationshipTransitionProposal:
    deltas: tuple[RelationshipDelta, ...]


def decay(state: RelationshipState) -> RelationshipState:
    """Peluruhan alami: HANYA familiarity yang turun sedikit kalau Teacher menghilang
    berhari-hari. Trust/Comfort/Affection/Respect TIDAK meluruh otomatis — hubungan
    yang sudah terbentuk tidak boleh hilang cuma karena waktu, beda dengan Emotion
    yang memang jangka pendek."""
    elapsed = state.elapsed_seconds()
    if elapsed <= _DECAY_GRACE_SECONDS:
        return state

    days_over = (elapsed - _DECAY_GRACE_SECONDS) / (24 * 3600)
    delta = -min(_FAMILIARITY_DECAY_PER_DAY * days_over, 5.0)
    if delta >= -0.5:
        return state

    new_familiarity = state.familiarity.adjust(delta)
    if new_familiarity.current == state.familiarity.current:
        return state

    logger.info("Familiarity Updated (decay): {} -> {}", state.familiarity.current, new_familiarity.current)
    return state.with_dimension("familiarity", new_familiarity)


def apply_transition(state: RelationshipState, proposal: RelationshipTransitionProposal) -> RelationshipState:
    """SATU-SATUNYA tempat delta diterapkan ke dimensi. Tiap delta di-clamp ke
    ±_MAX_STEP (Growth Policy: no sudden jumps)."""
    new_state = state
    for delta in proposal.deltas:
        if delta.dimension not in DIMENSION_NAMES:
            logger.warning("Dimensi tidak dikenal di proposal, dilewati: {}", delta.dimension)
            continue

        clamped_amount = max(-_MAX_STEP, min(_MAX_STEP, delta.amount))
        current_dim = new_state.get_dimension(delta.dimension)
        updated_dim = current_dim.adjust(clamped_amount)

        if updated_dim.current != current_dim.current:
            logger.info(
                "{} Updated: {} -> {} (reason='{}')",
                delta.dimension.capitalize(), current_dim.current, updated_dim.current, delta.reason,
            )
            new_state = new_state.with_dimension(delta.dimension, updated_dim)

    if new_state is not state:
        logger.info("Relationship Changed")

    return new_state