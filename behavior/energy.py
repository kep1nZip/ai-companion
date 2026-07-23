from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyState:
    """Stamina Arona, 0-100. Berkurang seiring pertukaran pesan, pulih perlahan
    seiring waktu idle (lihat internal_state_rules.compute_energy_delta)."""

    value: int = 100

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValueError("EnergyState.value harus berada di antara 0-100")

    def adjust(self, delta: float) -> "EnergyState":
        return EnergyState(value=max(0, min(100, round(self.value + delta))))


DEFAULT_ENERGY = EnergyState()