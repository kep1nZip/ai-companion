from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from behavior.behavior_state import BehaviorState

_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


class ContextBuilder:
    """SATU-SATUNYA modul yang merangkai teks Ephemeral Context dari BehaviorState
    (+ waktu real-time). Companion TIDAK boleh merangkai string context sendiri —
    ini Context Builder Separation Policy (rekomendasi GPT, v0.6.5).

    TIDAK PERNAH memanggil Gemini. TIDAK PERNAH akses SQLite. TIDAK PERNAH import Qt.
    Hasil build() TIDAK PERNAH disimpan permanen (bukan prompt file, bukan memory) —
    dibangun ulang setiap request, sesuai Ephemeral Context Injection Policy.

    Kalau nanti v0.7 (Vision) atau v0.8 (Routine System) perlu menambah sumber
    informasi ke context, cukup tambah method _format_xxx() di sini dan panggil
    dari build() — Companion tidak perlu diubah sama sekali."""

    def __init__(self, timezone_name: str = "Asia/Jakarta"):
        self._timezone_name = timezone_name

    def build(self, behavior_state: BehaviorState) -> str:
        sections = [
            self._format_time(),
            self._format_emotion(behavior_state),
            self._format_relationship(behavior_state),
            self._format_internal(behavior_state),
        ]
        return "\n\n".join(s for s in sections if s)

    def _format_time(self) -> str:
        now = datetime.now(ZoneInfo(self._timezone_name))
        hari = _HARI[now.weekday()]
        bulan = _BULAN[now.month - 1]
        return f"Current Time\n{hari}, {now.day} {bulan} {now.year}, pukul {now.strftime('%H:%M')} WIB"

    def _format_emotion(self, state: BehaviorState) -> str:
        e = state.emotion
        return f"Current Emotion\n{e.current.value.capitalize()} ({e.intensity:.2f})"

    def _format_relationship(self, state: BehaviorState) -> str:
        r = state.relationship
        return (
            "Relationship\n"
            f"Trust: {r.trust.current}\n"
            f"Comfort: {r.comfort.current}\n"
            f"Affection: {r.affection.current}\n"
            f"Respect: {r.respect.current}\n"
            f"Familiarity: {r.familiarity.current}"
        )

    def _format_internal(self, state: BehaviorState) -> str:
        i = state.internal
        return (
            "Internal State\n"
            f"Mood: {i.mood.value.capitalize()}\n"
            f"Energy: {i.energy.value}\n"
            f"Curiosity: {i.curiosity.level}\n"
            f"Initiative: {i.initiative.level}"
        )