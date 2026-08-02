from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from behavior.behavior_state import BehaviorState
from vision.vision_context import VisionContext

from routine.routine_event import RoutineEvent

from initiative.initiative_decision import DecisionResult

_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


class ContextBuilder:
    """SATU-SATUNYA modul yang merangkai teks Ephemeral Context. Menggabungkan
    Behavior + Vision (v0.7) + Routine (v0.8) + Initiative (v0.9) Context —
    Vision, Routine, dan Initiative semuanya OPSIONAL; pipeline tetap jalan
    normal walau salah satu (atau semua) mati.

    Routine & Initiative section HARUS ditulis sebagai peluang/saran netral,
    bukan instruksi yang mendikte kalimat Arona (Routine Decision Policy,
    Autonomous Permission Policy) — Gemini yang memutuskan bagaimana
    meresponsnya. Initiative section malah tidak pernah muncul sama sekali
    kecuali `decision_result.should_start == True`."""

    def __init__(self, timezone_name: str = "Asia/Jakarta"):
        self._timezone_name = timezone_name

    def build(
        self,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
        routine_event: Optional[RoutineEvent] = None,
        decision_result: Optional[DecisionResult] = None,
    ) -> str:
        sections = [
            self._format_time(),
            self._format_emotion(behavior_state),
            self._format_relationship(behavior_state),
            self._format_internal(behavior_state),
        ]

        if vision_context is not None:
            sections.append(self._format_vision(vision_context))

        if routine_event is not None:
            sections.append(self._format_routine(routine_event))

        if decision_result is not None and decision_result.should_start:
            sections.append(self._format_initiative(decision_result))

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

    def _format_routine(self, event: RoutineEvent) -> str:
        return f"Routine Suggestion\n{event.payload}"

    def _format_initiative(self, result: DecisionResult) -> str:
        reasons_text = "; ".join(result.reasons) if result.reasons else "kondisi mendukung"
        return (
            "Initiative Context\n"
            f"Momen ini cukup mendukung Arona untuk lebih proaktif/hangat dalam percakapan "
            f"({reasons_text}). Ini cuma peluang — Arona tetap boleh merespons secara natural."
        )