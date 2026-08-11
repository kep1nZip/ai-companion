from __future__ import annotations

from typing import Optional

from database.memory_manager import MemoryManager
from config.logger import logger


def save_by_marker(memory_manager: Optional[MemoryManager], marker: str, content: str) -> None:
    """Upsert generik berbasis marker teks unik di kategori 'general' — pola
    dipakai Relationship/InternalState/Routine/Initiative persistence. Tidak
    menambah kategori baru ke MemoryManager, tidak mengubah MemoryManager itu
    sendiri (sesuai Source of Truth Policy)."""
    if memory_manager is None:
        return
    try:
        existing = memory_manager.search_memory(marker, limit=1)
        if existing:
            memory_manager.update_memory(existing[0].id, content=content)
        else:
            memory_manager.save_memory("general", content)
        logger.info("Persistence Saved")
    except Exception as e:
        logger.warning("Gagal menyimpan data (marker={}): {}", marker, e)


def load_by_marker(memory_manager: Optional[MemoryManager], marker: str) -> Optional[str]:
    """Return content mentah (masih perlu di-deserialize pemanggil) atau None
    kalau tidak ada/gagal."""
    if memory_manager is None:
        return None
    try:
        existing = memory_manager.search_memory(marker, limit=1)
        if not existing:
            return None
        logger.info("Persistence Loaded")
        return existing[0].content
    except Exception as e:
        logger.warning("Gagal memuat data (marker={}): {}", marker, e)
        return None