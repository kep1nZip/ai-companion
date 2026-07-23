from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnimationState:
    """Snapshot layer animasi yang SEDANG aktif. Immutable, read-only.
    Hanya dipakai/di-expose oleh AvatarManager — modul lain cuma boleh membaca."""

    active_layers: frozenset[str] = field(default_factory=frozenset)

    def is_active(self, layer_name: str) -> bool:
        return layer_name in self.active_layers