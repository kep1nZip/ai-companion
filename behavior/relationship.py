from __future__ import annotations

import json
from typing import Optional

from behavior.relationship_state import (
    RelationshipState, DimensionValue, DEFAULT_RELATIONSHIP_STATE, DIMENSION_NAMES,
)
from behavior.relationship_rules import apply_transition, decay
from behavior.relationship_analyzer import RelationshipAnalyzer
from behavior.relationship_history import RelationshipHistory
from behavior.emotion_state import EmotionState
from database.memory_manager import MemoryManager
from config.logger import logger

# Re-export untuk backward compatibility dengan skeleton v0.6.0.
__all__ = [
    "RelationshipState", "DimensionValue", "DEFAULT_RELATIONSHIP_STATE", "DIMENSION_NAMES",
    "RelationshipCoordinator",
]

# Marker unik di dalam content memory — supaya kita bisa cari/update record
# relationship tanpa perlu kategori SQLite baru (MemoryManager DILARANG diubah).
_PERSISTENCE_MARKER = "__ARONA_RELATIONSHIP_STATE__"


def _serialize(state: RelationshipState) -> str:
    payload = {
        name: {"base": state.get_dimension(name).base, "current": state.get_dimension(name).current}
        for name in DIMENSION_NAMES
    }
    return f"{_PERSISTENCE_MARKER}:{json.dumps(payload)}"


def _deserialize(content: str) -> Optional[RelationshipState]:
    try:
        raw = content.split(f"{_PERSISTENCE_MARKER}:", 1)[1]
        payload = json.loads(raw)
        kwargs = {
            name: DimensionValue(base=int(payload[name]["base"]), current=int(payload[name]["current"]))
            for name in DIMENSION_NAMES
        }
        return RelationshipState(**kwargs)
    except Exception as e:
        logger.warning("Gagal parse relationship state tersimpan, pakai default: {}", e)
        return None


class RelationshipCoordinator:
    """Public API / koordinator Relationship System. Satu-satunya titik masuk yang
    boleh dipanggil BehaviorEngine (dan nanti GUI) untuk urusan relationship.

    TIDAK PERNAH memanggil Gemini. TIDAK PERNAH import Qt. TIDAK PERNAH bicara ke
    AvatarManager/VoiceManager langsung. TIDAK PERNAH akses SQLite langsung — semua
    persistence lewat method PUBLIK MemoryManager (search_memory/save_memory/
    update_memory), bukan sqlite3 langsung, dan TIDAK menambah kategori baru ke
    MemoryManager — pakai kategori 'general' + marker teks unik supaya tidak
    bentrok dengan memori naratif biasa dari MemoryExtractor."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None, auto_load: bool = True):
        self._memory_manager = memory_manager
        self._analyzer = RelationshipAnalyzer(memory_manager=memory_manager)
        self._history = RelationshipHistory()
        self._current: RelationshipState = DEFAULT_RELATIONSHIP_STATE

        if auto_load and memory_manager is not None:
            self.load()

    @property
    def current(self) -> RelationshipState:
        return self._current

    def process_message(self, user_input: str, emotion_state: Optional[EmotionState] = None) -> RelationshipState:
        """Dipanggil dari BehaviorEngine.update(). Growth SELALU gradual (max ±5,
        lihat relationship_rules._MAX_STEP)."""
        try:
            decayed = decay(self._current)
            proposal = self._analyzer.analyze(user_input, emotion_state)
            new_state = apply_transition(decayed, proposal)

            self._history.record(self._current)
            self._current = new_state
            self.save()
            return self._current

        except Exception as e:
            logger.warning("RelationshipCoordinator gagal memproses pesan, fallback ke state sebelumnya: {}", e)
            return self._current

    def manual_override(self, dimension: str, value: int) -> RelationshipState:
        """Override manual (GUI/debug/preset — BACKEND ONLY di v0.6.3, belum ada GUI-nya).
        Set base DAN current dimensi tsb ke value yang sama (anchor point baru).
        Automatic growth TETAP lanjut setelahnya — manual override TIDAK mematikan
        sistem otomatis, sesuai Manual Override Policy di spec."""
        if dimension not in DIMENSION_NAMES:
            raise ValueError(f"Dimensi tidak dikenal: {dimension}")

        new_dim = self._current.get_dimension(dimension).override(value)
        self._history.record(self._current)
        self._current = self._current.with_dimension(dimension, new_dim, manual_override=True)

        logger.info("Manual Override: {} -> base={}, current={}", dimension, new_dim.base, new_dim.current)
        self.save()
        return self._current

    def reset(self) -> RelationshipState:
        logger.info("Relationship direset ke default.")
        self._current = DEFAULT_RELATIONSHIP_STATE
        self._history.clear()
        self.save()
        return self._current

    def get_history(self, limit: int = 20) -> list[RelationshipState]:
        return self._history.recent(limit)

    def save(self) -> None:
        """Upsert manual: cari dulu record lama (search_memory), lalu update_memory
        kalau ada / save_memory kalau belum ada. Ini menghindari row baru menumpuk
        tiap kali disimpan (save_memory sendiri cuma dedup exact-match, sementara
        JSON kita berubah tiap panggilan)."""
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
            logger.warning("Gagal menyimpan relationship state, akan dicoba lagi nanti: {}", e)

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
            logger.warning("Gagal memuat relationship state tersimpan, pakai default: {}", e)