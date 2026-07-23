from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CuriosityState:
    """Minat eksplorasi Arona, 0-100. Naik saat Teacher menyinggung topik/pertanyaan
    baru, meluruh perlahan kalau tidak ada sinyal baru."""

    level: int = 0
    topic: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0 <= self.level <= 100:
            raise ValueError("CuriosityState.level harus berada di antara 0-100")

    def adjust(self, delta: float, topic: Optional[str] = None) -> "CuriosityState":
        new_level = max(0, min(100, round(self.level + delta)))
        return CuriosityState(level=new_level, topic=topic if topic is not None else self.topic)


DEFAULT_CURIOSITY = CuriosityState()