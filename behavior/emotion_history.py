from __future__ import annotations

from behavior.emotion_state import EmotionState


class EmotionHistory:
    """Riwayat perubahan emosi SEMENTARA (in-memory, belum persisten). Sesuai spec:
    'SQLite integration comes later if needed' — v0.6.2 belum menyentuh
    database/memory_manager.py untuk history ini."""

    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._entries: list[EmotionState] = []

    def record(self, state: EmotionState) -> None:
        self._entries.append(state)
        if len(self._entries) > self._max_size:
            self._entries.pop(0)

    def recent(self, limit: int = 20) -> list[EmotionState]:
        return list(self._entries[-limit:])

    def clear(self) -> None:
        self._entries.clear()