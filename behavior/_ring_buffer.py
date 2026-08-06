from __future__ import annotations
from typing import Generic, TypeVar

T = TypeVar("T")

class RingBufferHistory(Generic[T]):
    """Ring buffer in-memory generik — dasar untuk EmotionHistory/
    RelationshipHistory/InternalStateHistory. Perilaku (bukan tanggung jawab)
    yang dibagi; masing-masing subclass tetap nama class sendiri untuk
    kejelasan import di modul lain."""

    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._entries: list[T] = []

    def record(self, state: T) -> None:
        self._entries.append(state)
        if len(self._entries) > self._max_size:
            self._entries.pop(0)

    def recent(self, limit: int = 20) -> list[T]:
        return list(self._entries[-limit:])

    def clear(self) -> None:
        self._entries.clear()