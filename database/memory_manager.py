from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from config.logger import logger

DB_PATH = Path(__file__).resolve().parent / "memory.db"

VALID_CATEGORIES = {
    "preference",
    "relationship",
    "identity",
    "project",
    "schedule",
    "general",
}


@dataclass
class Memory:
    id: int
    category: str
    content: str
    created_at: str
    updated_at: str


class MemoryManager:
    """Satu-satunya modul yang boleh menyentuh memory.db.
    Tanggung jawab: save, load, search, update, delete. Tidak lebih."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """v2.2.2 hotfix (ditemukan Teacher lewat crash Windows saat
        menjalankan test_memory_quality_validation.py): SEBELUMNYA method
        ini `return` sqlite3.Connection polos, dipakai lewat
        `with self._connect() as conn:` di 7 tempat berbeda di file ini.

        BUG TERSEMBUNYI: `with conn:` pada objek sqlite3.Connection HANYA
        mengelola TRANSACTION (commit saat sukses, rollback saat
        exception) — TIDAK PERNAH memanggil `conn.close()`. Connection
        tetap "hidup" (file handle OS tetap terbuka) sampai Python
        garbage-collect objeknya sendiri, bukan segera setelah `with`
        block selesai seperti yang terlihat dari bentuk kodenya.

        Di Linux/macOS ini nyaris tidak pernah kelihatan sebagai bug
        (refcounting CPython biasanya langsung membuang objek begitu
        keluar scope + POSIX mengizinkan unlink file yang masih ada
        handle terbuka) — tapi di Windows, OS MELARANG menghapus/
        memindah file yang masih ada handle terbuka sama sekali. Ini
        persis penyebab `PermissionError: [WinError 32]` yang Teacher
        temui saat `test_memory_quality_validation.py` (v2.2.2) mencoba
        membersihkan direktori temporary-nya — bukan bug di script test
        itu sendiri, tapi di sini, yang kebetulan baru ketahuan lewat
        script itu.

        Perbaikan: `_connect()` sekarang generator-based context manager
        (`@contextmanager`, sudah diimpor sejak awal tapi belum pernah
        dipakai — `Iterator` juga) — `with conn:` (commit/rollback) TETAP
        jalan PERSIS seperti sebelumnya, DITAMBAH `conn.close()` di
        `finally` (dijamin jalan walau ada exception). KE-7 caller
        (`with self._connect() as conn:` di seluruh file ini, termasuk
        yang dipakai `test_memory_quality_validation.py`) TIDAK PERLU
        diubah SATU BARIS PUN — sintaksnya identik, cuma semantiknya
        sekarang benar. Nol perubahan pada skema, query, atau perilaku
        dedupe/validasi kategori — murni resource cleanup."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)"
            )

    def save_memory(self, category: str, content: str) -> Memory:
        category = category.strip().lower()
        content = content.strip()

        if category not in VALID_CATEGORIES:
            category = "general"

        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM memories WHERE category = ? AND content = ? COLLATE NOCASE",
                (category, content),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE memories SET updated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                logger.info("Memory sudah ada, timestamp diperbarui: {}", content)
                return Memory(existing["id"], category, content, existing["created_at"], now)

            cursor = conn.execute(
                "INSERT INTO memories (category, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (category, content, now, now),
            )
            logger.info("Memory baru dibuat [{}]: {}", category, content)
            return Memory(cursor.lastrowid, category, content, now, now)

    def load_memories(self, limit: int = 10) -> list[Memory]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        memories = [
            Memory(r["id"], r["category"], r["content"], r["created_at"], r["updated_at"])
            for r in rows
        ]
        logger.info("Memuat {} memori.", len(memories))
        return memories

    def search_memory(self, keyword: str, limit: int = 10) -> list[Memory]:
        pattern = f"%{keyword.strip()}%"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE content LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (pattern, limit),
            ).fetchall()

        return [
            Memory(r["id"], r["category"], r["content"], r["created_at"], r["updated_at"])
            for r in rows
        ]

    def update_memory(self, memory_id: int, content: str | None = None, category: str | None = None) -> None:
        fields, values = [], []

        if content is not None:
            fields.append("content = ?")
            values.append(content.strip())

        if category is not None:
            category = category.strip().lower()
            if category not in VALID_CATEGORIES:
                category = "general"
            fields.append("category = ?")
            values.append(category)

        if not fields:
            return

        fields.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(memory_id)

        with self._connect() as conn:
            conn.execute(f"UPDATE memories SET {', '.join(fields)} WHERE id = ?", values)
        logger.info("Memory diperbarui: id={}", memory_id)

    def delete_memory(self, memory_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        logger.info("Memory dihapus: id={}", memory_id)

    def clear_all(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM memories")
        logger.warning("Seluruh memori dihapus.")