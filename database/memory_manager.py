from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

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