from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AvatarSnapshot:
    connection_state: Optional[str]
    active_animation_layers: list
    voice_state: Optional[str]   # digabung di sini — spec tidak sediakan slot terpisah untuk Voice


def build_avatar_snapshot(avatar_manager, voice_manager) -> AvatarSnapshot:
    """READ-ONLY MURNI — cuma baca property publik `.state`/`.animation_state`
    yang sudah ada sejak v0.5/v0.6.1/v0.4. TIDAK PERNAH memanggil method yang
    mengirim command (trigger_hotkey, update_parameter_layer, dst)."""
    connection_state = avatar_manager.state.value if avatar_manager else None
    layers = list(avatar_manager.animation_state.active_layers) if avatar_manager else []
    voice_state = voice_manager.state.value if voice_manager else None
    return AvatarSnapshot(connection_state=connection_state, active_animation_layers=layers, voice_state=voice_state)