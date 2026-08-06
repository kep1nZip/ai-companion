from __future__ import annotations

from typing import Callable, Optional, TypeVar

from config.logger import logger
from database.memory_manager import MemoryManager

T = TypeVar("T")


def save_persistent_state(
    memory_manager: Optional[MemoryManager],
    marker: str,
    content: str,
) -> None:
    """Menyimpan state persisten dengan pola upsert.

    Mencari record berdasarkan marker menggunakan search_memory(), lalu
    melakukan update_memory() bila sudah ada atau save_memory() bila belum.
    Pendekatan ini mencegah penumpukan row baru setiap kali state berubah,
    karena save_memory() hanya melakukan deduplikasi untuk content yang
    identik.
    """

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
        logger.warning("Gagal menyimpan persistence: {}", e)


def load_persistent_state(
    memory_manager: Optional[MemoryManager],
    marker: str,
    deserialize: Callable[[str], Optional[T]],
) -> Optional[T]:
    """Memuat persistence model menggunakan fungsi deserialize."""

    if memory_manager is None:
        return None

    try:
        existing = memory_manager.search_memory(marker, limit=1)

        if not existing:
            return None

        loaded = deserialize(existing[0].content)

        if loaded is not None:
            logger.info("Persistence Loaded")

        return loaded

    except Exception as e:
        logger.warning("Gagal memuat persistence: {}", e)
        return None