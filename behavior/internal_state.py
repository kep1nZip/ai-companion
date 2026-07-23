from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from behavior.mood import Mood, DEFAULT_MOOD
from behavior.energy import EnergyState, DEFAULT_ENERGY
from behavior.curiosity import CuriosityState, DEFAULT_CURIOSITY
from behavior.initiative import InitiativeState, DEFAULT_INITIATIVE
from behavior.internal_state_rules import (
    propose_mood, apply_mood, compute_energy_delta,
    compute_curiosity_delta, compute_curiosity_decay, compute_initiative_delta,
)
from behavior.internal_state_history import InternalStateHistory
from behavior.emotion_state import EmotionState
from behavior.relationship_state import RelationshipState
from database.memory_manager import MemoryManager
from config.logger import logger

_PERSISTENCE_MARKER = "__ARONA_INTERNAL_STATE__"


@dataclass(frozen=True)
class InternalState:
    """Kondisi internal jangka-panjang Arona: Mood + Energy + Curiosity + Initiative
    digabung jadi SATU blok (rekomendasi GPT). Kalau nanti nambah Stress/Confidence/
    Focus, cukup nambah field DI SINI — BehaviorState (behavior_state.py) tidak
    perlu berubah sama sekali."""

    mood: Mood = DEFAULT_MOOD
    energy: EnergyState = field(default_factory=lambda: DEFAULT_ENERGY)
    curiosity: CuriosityState = field(default_factory=lambda: DEFAULT_CURIOSITY)
    initiative: InitiativeState = field(default_factory=lambda: DEFAULT_INITIATIVE)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def elapsed_seconds(self) -> float:
        now = datetime.now(timezone.utc)
        return max(0.0, (now - self.timestamp).total_seconds())


DEFAULT_INTERNAL_STATE = InternalState()


def _serialize(state: InternalState) -> str:
    payload = {
        "mood": state.mood.value,
        "energy": state.energy.value,
        "curiosity_level": state.curiosity.level,
        "curiosity_topic": state.curiosity.topic,
        "initiative_level": state.initiative.level,
    }
    return f"{_PERSISTENCE_MARKER}:{json.dumps(payload)}"


def _deserialize(content: str) -> Optional[InternalState]:
    try:
        raw = content.split(f"{_PERSISTENCE_MARKER}:", 1)[1]
        payload = json.loads(raw)
        return InternalState(
            mood=Mood(payload["mood"]),
            energy=EnergyState(value=int(payload["energy"])),
            curiosity=CuriosityState(level=int(payload["curiosity_level"]), topic=payload.get("curiosity_topic")),
            initiative=InitiativeState(level=int(payload["initiative_level"])),
        )
    except Exception as e:
        logger.warning("Gagal parse internal state tersimpan, pakai default: {}", e)
        return None


class InternalStateCoordinator:
    """Public API / koordinator Mood+Energy+Curiosity+Initiative. Satu-satunya
    titik masuk yang boleh dipanggil BehaviorEngine untuk urusan internal state.

    TIDAK PERNAH memanggil Gemini. TIDAK PERNAH import Qt. TIDAK PERNAH bicara ke
    AvatarManager/VoiceManager langsung. Persistence pakai method PUBLIK
    MemoryManager (pola identik RelationshipCoordinator — kategori 'general' +
    marker unik, MemoryManager itu sendiri TIDAK diubah)."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None, auto_load: bool = True):
        self._memory_manager = memory_manager
        self._history = InternalStateHistory()
        self._current: InternalState = DEFAULT_INTERNAL_STATE
        self._emotion_window: list[EmotionState] = []

        if auto_load and memory_manager is not None:
            self.load()

    @property
    def current(self) -> InternalState:
        return self._current

    def process_message(
        self,
        user_input: str,
        emotion_state: Optional[EmotionState] = None,
        relationship_state: Optional[RelationshipState] = None,
    ) -> InternalState:
        try:
            elapsed = self._current.elapsed_seconds()

            if emotion_state is not None:
                self._emotion_window.append(emotion_state)
                self._emotion_window = self._emotion_window[-10:]

            mood_proposal = propose_mood(self._emotion_window, self._current.energy.value)
            new_mood = apply_mood(self._current.mood, mood_proposal)

            energy_delta = compute_energy_delta(new_mood, elapsed)
            new_energy = self._current.energy.adjust(energy_delta)
            if new_energy.value != self._current.energy.value:
                logger.info("Energy Updated: {} -> {}", self._current.energy.value, new_energy.value)

            curiosity_delta, topic = compute_curiosity_delta(user_input)
            decay_delta = compute_curiosity_decay(elapsed)
            new_curiosity = self._current.curiosity.adjust(curiosity_delta + decay_delta, topic=topic)
            if new_curiosity.level != self._current.curiosity.level:
                logger.info("Curiosity Updated: {} -> {}", self._current.curiosity.level, new_curiosity.level)

            initiative_delta = compute_initiative_delta(
                new_energy.value, new_curiosity.level, relationship_state, elapsed,
            )
            new_initiative = self._current.initiative.adjust(initiative_delta, idle_seconds=elapsed)
            if new_initiative.level != self._current.initiative.level:
                logger.info("Initiative Updated: {} -> {}", self._current.initiative.level, new_initiative.level)

            self._history.record(self._current)
            self._current = InternalState(
                mood=new_mood, energy=new_energy, curiosity=new_curiosity, initiative=new_initiative,
            )
            self.save()
            return self._current

        except Exception as e:
            logger.warning("InternalStateCoordinator gagal memproses pesan, fallback ke state sebelumnya: {}", e)
            return self._current

    def manual_override(self, component: str, value) -> InternalState:
        """component: 'mood' (value: str nama Mood, mis. 'cheerful') | 'energy' /
        'curiosity' / 'initiative' (value: int). Automatic update TETAP LANJUT
        setelahnya — kebijakan sama persis dengan Relationship System."""
        self._history.record(self._current)

        if component == "mood":
            new_mood = Mood(value) if isinstance(value, str) else value
            self._current = InternalState(
                mood=new_mood, energy=self._current.energy,
                curiosity=self._current.curiosity, initiative=self._current.initiative,
            )
        elif component == "energy":
            self._current = InternalState(
                mood=self._current.mood, energy=EnergyState(value=int(value)),
                curiosity=self._current.curiosity, initiative=self._current.initiative,
            )
        elif component == "curiosity":
            self._current = InternalState(
                mood=self._current.mood, energy=self._current.energy,
                curiosity=CuriosityState(level=int(value), topic=self._current.curiosity.topic),
                initiative=self._current.initiative,
            )
        elif component == "initiative":
            self._current = InternalState(
                mood=self._current.mood, energy=self._current.energy,
                curiosity=self._current.curiosity, initiative=InitiativeState(level=int(value)),
            )
        else:
            raise ValueError(f"Komponen tidak dikenal: {component}")

        logger.info("Manual Override: {} -> {}", component, value)
        self.save()
        return self._current

    def reset(self) -> InternalState:
        logger.info("Internal State direset ke default.")
        self._current = DEFAULT_INTERNAL_STATE
        self._history.clear()
        self._emotion_window.clear()
        self.save()
        return self._current

    def get_history(self, limit: int = 20) -> list[InternalState]:
        return self._history.recent(limit)

    def save(self) -> None:
        if self._memory_manager is None:
            return
        try:
            content = _serialize(self._current)
            existing = self._memory_manager.search_memory(_PERSISTENCE_MARKER, limit=1)
            if existing:
                self._memory_manager.update_memory(existing[0].id, content=content)
            else:
                self._memory_manager.save_memory("general", content)
            logger.info("Persistence Saved")
        except Exception as e:
            logger.warning("Gagal menyimpan internal state, akan dicoba lagi nanti: {}", e)

    def load(self) -> None:
        if self._memory_manager is None:
            return
        try:
            existing = self._memory_manager.search_memory(_PERSISTENCE_MARKER, limit=1)
            if not existing:
                return
            loaded = _deserialize(existing[0].content)
            if loaded is not None:
                self._current = loaded
                logger.info("Persistence Loaded")
        except Exception as e:
            logger.warning("Gagal memuat internal state tersimpan, pakai default: {}", e)