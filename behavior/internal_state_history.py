from __future__ import annotations

from typing import TYPE_CHECKING

# TYPE_CHECKING guard: menghindari circular import dengan internal_state.py
# (yang mendefinisikan InternalState DAN meng-impor class ini). Type hint tetap
# ada untuk IDE/linter, tidak dieksekusi saat runtime.
if TYPE_CHECKING:
    from behavior.internal_state import InternalState


class InternalStateHistory:
    """Riwayat perubahan InternalState, in-memory ring buffer — pola sama persis
    EmotionHistory/RelationshipHistory."""

    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._entries: list["InternalState"] = []

    def record(self, state: "InternalState") -> None:
        self._entries.append(state)
        if len(self._entries) > self._max_size:
            self._entries.pop(0)

    def recent(self, limit: int = 20) -> list["InternalState"]:
        return list(self._entries[-limit:])

    def clear(self) -> None:
        self._entries.clear()