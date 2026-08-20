from __future__ import annotations

from database.memory_manager import Memory
from config.logger import logger

# Marker yang sama dipakai RoutineHistory/InitiativeHistory/RelationshipState/
# InternalState lewat database/persistence_helper.py (save_by_marker) untuk
# menyimpan bookkeeping internal di kategori 'general'. developer/memory_debug.py
# sudah menyaring pola yang sama untuk Developer Tools; konstanta ini SENGAJA
# didefinisikan ulang di sini (bukan di-import dari developer/) supaya ui/ tidak
# coupled ke developer/ (Developer Tools Independence Policy) — dua konsumen
# berbeda kebetulan butuh menyaring hal yang sama untuk alasan berbeda:
# devtools untuk inspeksi teknis, di sini supaya Teacher tidak melihat sampah
# bookkeeping internal di Memory GUI.
_INTERNAL_MARKER_PREFIX = "__ARONA_"


class MemoryReadError(Exception):
    """Terjadi saat baca memori gagal (mis. database terkunci/tidak bisa diakses)."""


class MemoryService:
    """Read boundary tipis antara Memory GUI dan Companion. HANYA memanggil
    Companion.list_memories() / Companion.search_memories() — TIDAK PERNAH
    memanggil save_memory/update_memory/delete_memory/clear_all/clear_memories
    (Memory GUI Read-Only Policy v1.1). Tidak menduplikasi logic MemoryManager;
    murni filtering presentation-facing + error mapping ke exception yang bisa
    ditangani GUI thread secara aman."""

    def __init__(self, companion):
        self._companion = companion

    def list_recent(self, limit: int = 50) -> list[Memory]:
        try:
            memories = self._companion.list_memories(limit=limit)
        except Exception as e:
            logger.warning("MemoryService: gagal memuat memori: {}", e)
            raise MemoryReadError("Gagal memuat memori, Teacher.") from e
        return self._filter_internal(memories)

    def search(self, query: str, limit: int = 50) -> list[Memory]:
        query = query.strip()
        if not query:
            return self.list_recent(limit=limit)
        try:
            memories = self._companion.search_memories(query, limit=limit)
        except Exception as e:
            logger.warning("MemoryService: gagal mencari memori (query='{}'): {}", query, e)
            raise MemoryReadError("Gagal mencari memori, Teacher.") from e
        return self._filter_internal(memories)

    @staticmethod
    def _filter_internal(memories: list[Memory]) -> list[Memory]:
        return [m for m in memories if not m.content.startswith(_INTERNAL_MARKER_PREFIX)]