from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

_MIN_VALUE = 0
_MAX_VALUE = 100
_DIMENSION_NAMES = ("trust", "comfort", "affection", "respect", "familiarity")


@dataclass(frozen=True)
class DimensionValue:
    """Satu dimensi relationship, dipisah Base/Current sesuai rekomendasi GPT.

    - base: anchor point yang diatur MANUAL (GUI/preset/manual override).
    - current: nilai yang benar-benar dipakai Behavior Engine, bergerak naik/turun
      lewat interaksi otomatis TANPA pernah mengubah base — sehingga preset bisa
      dikembalikan kapan saja tanpa kehilangan riwayat pergerakan current.

    Contoh dari rekomendasi GPT: Base Trust=80, Current Trust=84 — artinya developer
    set preset "sudah cukup dekat" (base=80), lalu 4 poin naik lagi lewat interaksi
    natural (current=84), tanpa base ikut berubah.
    """

    base: int = 0
    current: int = 0

    def __post_init__(self) -> None:
        if not _MIN_VALUE <= self.base <= _MAX_VALUE:
            raise ValueError(f"DimensionValue.base harus 0-100, dapat {self.base}")
        if not _MIN_VALUE <= self.current <= _MAX_VALUE:
            raise ValueError(f"DimensionValue.current harus 0-100, dapat {self.current}")

    def adjust(self, delta: float) -> "DimensionValue":
        """Return instance BARU dengan current bergeser oleh delta (clamp 0-100).
        base TIDAK PERNAH berubah lewat adjust() — cuma override() yang boleh."""
        new_current = max(_MIN_VALUE, min(_MAX_VALUE, round(self.current + delta)))
        return DimensionValue(base=self.base, current=new_current)

    def override(self, value: int) -> "DimensionValue":
        """Manual override: reset BASE dan CURRENT ke value yang sama — anchor point
        baru, mis. saat load preset. Riwayat pergerakan sebelumnya tetap ada di
        RelationshipHistory, cuma tidak lagi memengaruhi current setelah titik ini."""
        clamped = max(_MIN_VALUE, min(_MAX_VALUE, value))
        return DimensionValue(base=clamped, current=clamped)


@dataclass(frozen=True)
class RelationshipState:
    """Snapshot IMMUTABLE hubungan Arona-Teacher. 
    
    Beda dengan Emotion (jangka pendek), Relationship PERSISTEN lintas restart aplikasi — lewat RelationshipCoordinator di
    relationship.py. File ini sendiri TIDAK tahu apa pun soal persistence/MemoryManager.
    
    Field `manual_override` disimpan untuk kebutuhan Developer Panel/GUI di masa depan dan saat ini 
    belum digunakan oleh runtime."""

    trust: DimensionValue = field(default_factory=DimensionValue)
    comfort: DimensionValue = field(default_factory=DimensionValue)
    affection: DimensionValue = field(default_factory=DimensionValue)
    respect: DimensionValue = field(default_factory=DimensionValue)
    familiarity: DimensionValue = field(default_factory=DimensionValue)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Reserved for future Developer Panel/GUI. Runtime saat ini belum
    # menggunakan field ini, tetapi tetap disimpan agar UI nantinya dapat
    # membedakan state hasil manual override dari state hasil update otomatis.
    manual_override: bool = False

    def elapsed_seconds(self) -> float:
        now = datetime.now(timezone.utc)
        return max(0.0, (now - self.timestamp).total_seconds())

    def get_dimension(self, name: str) -> DimensionValue:
        if name not in _DIMENSION_NAMES:
            raise ValueError(f"Dimensi tidak dikenal: {name}")
        return getattr(self, name)

    def with_dimension(self, name: str, value: DimensionValue, manual_override: bool = False) -> "RelationshipState":
        if name not in _DIMENSION_NAMES:
            raise ValueError(f"Dimensi tidak dikenal: {name}")
        kwargs = {
            "trust": self.trust, "comfort": self.comfort, "affection": self.affection,
            "respect": self.respect, "familiarity": self.familiarity,
        }
        kwargs[name] = value
        return RelationshipState(**kwargs, manual_override=manual_override)


DEFAULT_RELATIONSHIP_STATE = RelationshipState()
DIMENSION_NAMES = _DIMENSION_NAMES