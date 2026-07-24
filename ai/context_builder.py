from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from behavior.behavior_state import BehaviorState
from vision.vision_context import VisionContext

_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


class ContextBuilder:
    """SATU-SATUNYA modul yang merangkai teks Ephemeral Context. Sekarang
    menggabungkan Behavior Context + Vision Context (OPSIONAL — rekomendasi GPT
    #4: pipeline harus tetap jalan normal walau Vision mati)."""

    def __init__(self, timezone_name: str = "Asia/Jakarta"):
        self._timezone_name = timezone_name

    def build(self, behavior_state: BehaviorState, vision_context: Optional[VisionContext] = None) -> str:
        sections = [
            self._format_time(),
            self._format_emotion(behavior_state),
            self._format_relationship(behavior_state),
            self._format_internal(behavior_state),
        ]

        if vision_context is not None:
            sections.append(self._format_vision(vision_context))

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

    def _format_vision(self, vc: VisionContext) -> str:
        app_line = f"Active Application: {vc.application}\n" if vc.application else ""
        return (
            "Visual Context\n"
            f"{app_line}{vc.summary}\n\n"
            f"Captured\n{vc.timestamp.strftime('%H:%M:%S')}\n"
            f"Age\n{int(vc.age_seconds())} seconds"
        )