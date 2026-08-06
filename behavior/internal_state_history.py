from __future__ import annotations

from typing import TYPE_CHECKING

from behavior._ring_buffer import RingBufferHistory

# TYPE_CHECKING guard: menghindari circular import dengan internal_state.py
# (yang mendefinisikan InternalState DAN meng-impor class ini). Type hint tetap
# ada untuk IDE/linter, tidak dieksekusi saat runtime.
if TYPE_CHECKING:
    from behavior.internal_state import InternalState


class InternalStateHistory(RingBufferHistory["InternalState"]):
    """Riwayat perubahan InternalState, in-memory ring buffer — pola sama persis
    EmotionHistory/RelationshipHistory."""
    pass