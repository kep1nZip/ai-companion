from __future__ import annotations

from behavior._ring_buffer import RingBufferHistory
from behavior.relationship_state import RelationshipState


class RelationshipHistory(RingBufferHistory[RelationshipState]):
    """Riwayat perubahan RelationshipState, in-memory (ring buffer) — konsisten
    dengan pola EmotionHistory (v0.6.2). Dipakai untuk analisis masa depan (mis.
    tren jangka panjang untuk Mood System di v0.6.4)."""
    pass