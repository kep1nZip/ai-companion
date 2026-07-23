from __future__ import annotations

from behavior.relationship_state import RelationshipState


class RelationshipHistory:
    """Riwayat perubahan RelationshipState, in-memory (ring buffer) — konsisten
    dengan pola EmotionHistory (v0.6.2). Dipakai untuk analisis masa depan (mis.
    tren jangka panjang untuk Mood System di v0.6.4)."""

    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._entries: list[RelationshipState] = []

    def record(self, state: RelationshipState) -> None:
        self._entries.append(state)
        if len(self._entries) > self._max_size:
            self._entries.pop(0)

    def recent(self, limit: int = 20) -> list[RelationshipState]:
        return list(self._entries[-limit:])

    def clear(self) -> None:
        self._entries.clear()