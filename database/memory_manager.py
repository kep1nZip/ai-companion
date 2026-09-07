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

# v2.5 Phase 1/5 — Relation Model & History/Current State (§8/§12 spec
# v2.5). Status TIDAK PERNAH destructive-delete (§12: "Old Memory status =
# superseded" lebih disukai daripada "DELETE old row") — history tetap ada
# di database untuk traceability/debugging, cuma tidak lagi dianggap
# "current" oleh load_memories()/search_memory() (lihat filter di bawah).
STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"


@dataclass
class Memory:
    id: int
    category: str
    content: str
    created_at: str
    updated_at: str
    # v2.5 Phase 1/5: default "active" — SEMUA row lama (dibuat sebelum
    # v2.5, termasuk 4 marker row internal state RoutineHistory/
    # InitiativeHistory/InternalState/Relationship, lihat Phase 0 Audit §4)
    # otomatis jadi "active" lewat migration kolom di _ensure_schema() di
    # bawah — TIDAK PERNAH otomatis di-supersede oleh migration ini sendiri.
    status: str = STATUS_ACTIVE


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

            # v2.5 Phase 1/5 (§10 "Minimum schema change, Maximum reuse"):
            # ADD COLUMN dengan DEFAULT, BUKAN membuat tabel baru/migration
            # besar. SQLite tidak punya "ADD COLUMN IF NOT EXISTS" native
            # (baru didukung versi sangat baru & belum tentu tersedia di
            # semua environment Teacher) — jadi dicek manual lewat
            # PRAGMA table_info(), idempoten aman dipanggil berkali-kali
            # (tiap kali MemoryManager() diinstansiasi). SEMUA row lama
            # (dibuat sebelum v2.5 — termasuk 4 marker row internal state,
            # Phase 0 Audit §4) otomatis dapat status="active" dari DEFAULT
            # ini, TIDAK PERNAH otomatis "superseded" oleh migration ini
            # sendiri (§20: "No mass migration. Existing memory tetap valid").
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(memories)")}
            if "status" not in existing_columns:
                conn.execute(
                    f"ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT '{STATUS_ACTIVE}'"
                )
                logger.info("Memory schema migrated: kolom 'status' ditambahkan (default 'active').")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status)"
            )

    def save_memory(self, category: str, content: str) -> Memory:
        category = category.strip().lower()
        content = content.strip()

        if category not in VALID_CATEGORIES:
            category = "general"

        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            # v2.5 Phase 1 (§14 Duplicate Handling): dedup exact-match SEKARANG
            # cuma dibandingkan terhadap memory yang MASIH "active" — memory
            # yang sudah "superseded" TIDAK dianggap match, supaya fakta lama
            # yang sudah dibatalkan tidak diam-diam "dihidupkan lagi" cuma
            # karena kontennya kebetulan sama persis dengan yang baru mau
            # disimpan sebagai NEW biasa (kasus ini di luar cakupan
            # relation-aware SUPERSEDES/UPDATE — itu jalur terpisah, lihat
            # supersede_memory()/update_memory() di bawah).
            existing = conn.execute(
                "SELECT * FROM memories WHERE category = ? AND content = ? COLLATE NOCASE AND status = ?",
                (category, content, STATUS_ACTIVE),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE memories SET updated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                logger.info("Memory sudah ada, timestamp diperbarui: {}", content)
                return Memory(existing["id"], category, content, existing["created_at"], now, existing["status"])

            cursor = conn.execute(
                "INSERT INTO memories (category, content, created_at, updated_at, status) VALUES (?, ?, ?, ?, ?)",
                (category, content, now, now, STATUS_ACTIVE),
            )
            logger.info("Memory baru dibuat [{}]: {}", category, content)
            return Memory(cursor.lastrowid, category, content, now, now, STATUS_ACTIVE)

    def supersede_memory(self, old_memory_id: int, category: str, content: str) -> Memory:
        """v2.5 Phase 1/4/5 (§6C, §11 Persistence Semantics) — SATU-SATUNYA
        cara relation SUPERSEDES dipersist: ATOMIC dalam SATU koneksi/
        transaksi (§11: "Jangan membuat extractor langsung melakukan SQL
        update/delete" — extractor cuma MEMUTUSKAN relation, method inilah
        yang benar-benar menjalankan efeknya).

        `old_memory_id` -> status diubah jadi "superseded" (BUKAN DELETE —
        §12 "History Preservation": tetap ada di database untuk
        traceability/debugging, cuma tidak lagi muncul di load_memories()/
        search_memory() default). Row BARU dibuat dengan status="active"
        untuk fakta yang menggantikannya.

        Kalau `old_memory_id` ternyata tidak ada/sudah dihapus manual lewat
        GUI Memory (race condition wajar antara background worker & user
        yang sedang edit memory), method ini TETAP membuat memory baru
        (fakta baru dari Teacher tetap valid & layak disimpan) — cuma
        supersede-nya yang dilewati dengan warning, TIDAK melempar exception
        yang bisa menjatuhkan seluruh task ekstraksi (selaras §31 Error
        Isolation di ai/memory_worker.py)."""
        category = category.strip().lower()
        content = content.strip()
        if category not in VALID_CATEGORIES:
            category = "general"

        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            result = conn.execute(
                "UPDATE memories SET status = ? WHERE id = ? AND status = ?",
                (STATUS_SUPERSEDED, old_memory_id, STATUS_ACTIVE),
            )
            if result.rowcount == 0:
                logger.warning(
                    "Supersede: memory id={} tidak ditemukan/sudah tidak active, "
                    "tetap membuat memory baru tanpa supersede.",
                    old_memory_id,
                )
            else:
                logger.info("Memory id={} ditandai superseded.", old_memory_id)

            cursor = conn.execute(
                "INSERT INTO memories (category, content, created_at, updated_at, status) VALUES (?, ?, ?, ?, ?)",
                (category, content, now, now, STATUS_ACTIVE),
            )
            logger.info("Memory baru dibuat (SUPERSEDES id={}) [{}]: {}", old_memory_id, category, content)
            return Memory(cursor.lastrowid, category, content, now, now, STATUS_ACTIVE)

    def load_memories(self, limit: int = 10, include_superseded: bool = False) -> list[Memory]:
        # v2.5 Phase 5 (§12 "Current Valid Memory"): DEFAULT sekarang cuma
        # mengembalikan memory "active" — SEBELUM v2.5 tidak ada bedanya
        # (semua row implisit "active" karena kolom status belum ada), jadi
        # ini TIDAK mengubah perilaku untuk database yang belum pernah
        # menghasilkan satu pun "superseded" row. `include_superseded=True`
        # opsional untuk kebutuhan debugging/histori (mis. Memory GUI kalau
        # nanti Teacher ingin lihat riwayat) — TIDAK dipakai default di mana
        # pun saat ini, ditambahkan supaya tidak perlu ubah signature lagi
        # kalau kebutuhan itu muncul nanti.
        query = "SELECT * FROM memories"
        params: list = []
        if not include_superseded:
            query += " WHERE status = ?"
            params.append(STATUS_ACTIVE)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        memories = [
            Memory(r["id"], r["category"], r["content"], r["created_at"], r["updated_at"], r["status"])
            for r in rows
        ]
        logger.info("Memuat {} memori.", len(memories))
        return memories

    def search_memory(self, keyword: str, limit: int = 10, include_superseded: bool = False) -> list[Memory]:
        # v2.5 Phase 5: pola IDENTIK load_memories() di atas — default
        # active-only, TIDAK mengubah perilaku database lama (nol row
        # "superseded" sebelum v2.5 pernah dibuat).
        pattern = f"%{keyword.strip()}%"
        query = "SELECT * FROM memories WHERE content LIKE ?"
        params: list = [pattern]
        if not include_superseded:
            query += " AND status = ?"
            params.append(STATUS_ACTIVE)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            Memory(r["id"], r["category"], r["content"], r["created_at"], r["updated_at"], r["status"])
            for r in rows
        ]

    def touch_memory(self, memory_id: int) -> None:
        """v2.5 Phase 4 (§6C relation DUPLICATE: "no duplicate active
        memory" — TIDAK membuat row baru, TIDAK menimpa konten asli yang
        sudah tersimpan, cuma menandai memory ini baru saja "diafirmasi
        ulang" oleh Teacher lewat refresh `updated_at`). Beda dari
        `update_memory()` yang mengubah isi — method ini SENGAJA tidak
        menerima parameter content/category sama sekali, supaya tidak ada
        cara tidak sengaja menimpa konten lewat jalur ini."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            result = conn.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (now, memory_id))
        if result.rowcount == 0:
            logger.warning("Touch memory: id={} tidak ditemukan.", memory_id)
        else:
            logger.info("Memory di-touch (duplicate diafirmasi ulang): id={}", memory_id)

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