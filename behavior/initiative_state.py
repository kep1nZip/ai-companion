from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InitiativeState:
    """Kecenderungan Arona memulai obrolan sendiri, 0-100. Milestone ini HANYA
    menyimpan nilainya — TIDAK ADA autonomous chatting sungguhan (sesuai spec)."""

    level: int = 0
    idle_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.level <= 100:
            raise ValueError("InitiativeState.level harus berada di antara 0-100")

    def adjust(self, delta: float, idle_seconds: Optional[float] = None) -> "InitiativeState":
        new_level = max(0, min(100, round(self.level + delta)))
        return InitiativeState(
            level=new_level,
            idle_seconds=idle_seconds if idle_seconds is not None else self.idle_seconds,
        )


DEFAULT_INITIATIVE = InitiativeState()