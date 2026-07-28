from __future__ import annotations

from dataclasses import dataclass

_INTERNAL_MARKER_PREFIX = "__ARONA_"


@dataclass(frozen=True)
class MemorySnapshot:
    total_count: int
    category_counts: dict
    recent: list
    internal_marker_count: int   # BARU — supaya tetap transparan berapa banyak yang disembunyikan


def build_memory_snapshot(memories: list) -> MemorySnapshot:
    category_counts: dict = {}
    for m in memories:
        category_counts[m.category] = category_counts.get(m.category, 0) + 1

    # Filter internal bookkeeping (RoutineHistory/InternalState/RelationshipState)
    # dari tampilan "recent" — ini Developer Tools untuk INSPEKSI, bukan debug
    # persistence layer mentah. Tetap dihitung di total_count (tidak disembunyikan
    # sepenuhnya, cuma tidak ditampilkan di daftar "recent").
    visible = [m for m in memories if not m.content.startswith(_INTERNAL_MARKER_PREFIX)]
    internal_count = len(memories) - len(visible)

    recent = [f"({m.category}) {m.content}" for m in visible[:10]]
    return MemorySnapshot(
        total_count=len(memories),
        category_counts=category_counts,
        recent=recent,
        internal_marker_count=internal_count,
    )