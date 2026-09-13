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

# v3.1 Phase 1+2 (Conversation Continuity + Return-from-Idle Awareness).
#
# Reuse TOTAL `idle_seconds` yang SUDAH ADA sejak v2.7
# (`BehaviorState.internal.elapsed_seconds()`, dikonfirmasi ulang v3.1
# Phase 0 Audit §1 akurat merepresentasikan "detik sejak pesan Teacher
# terakhir" — direset HANYA oleh `chat()`, TIDAK PERNAH oleh jalur
# autonomous read-only). TIDAK ADA timer baru, TIDAK ADA state baru.
#
# `_LONG_GAP_SECONDS` = 900.0 — ANGKA YANG SAMA PERSIS dengan
# `IdleRule.threshold_seconds` (initiative/initiative_rules.py) — BUKAN
# angka baru yang saya tebak, ini komplemen logis dari batas yang SUDAH
# disetujui & dipakai sejak v2.7.
# `_SHORT_GAP_SECONDS` = 60.0 — satu angka baru yang genuinely ditambahkan
# (tidak ada di kode manapun sebelumnya), dipilih sebagai perkiraan wajar
# "masih di tengah pertukaran pesan yang sama" (waktu baca+ketik normal),
# BUKAN keputusan bisnis yang sensitif — kalau ternyata kurang pas, tinggal
# satu angka ini yang perlu disesuaikan, tidak ada logic lain yang bergantung
# padanya.
_SHORT_GAP_SECONDS = 60.0
_LONG_GAP_SECONDS = 900.0

CONTINUITY_ACTIVE = "active"
CONTINUITY_RETURNING_SHORT_GAP = "returning_after_short_gap"
CONTINUITY_RETURNING_LONG_GAP = "returning_after_long_gap"


def categorize_continuity(idle_seconds: float) -> str:
    """v3.1 Phase 1+2/7 — SATU-SATUNYA tempat kategorisasi idle_seconds jadi
    3 state (ACTIVE/RETURNING_AFTER_SHORT_GAP/RETURNING_AFTER_LONG_GAP),
    dipakai BERSAMA oleh `ContextBuilder._format_continuity()` (sinyal ke
    prompt) DAN `Companion` (observability Dashboard, Phase 7) — supaya
    kategorisasi yang Teacher lihat di Dashboard SELALU sinkron dengan
    sinyal yang benar-benar dikirim ke model, tidak pernah dihitung dua
    kali dengan cara berbeda."""
    if idle_seconds < _SHORT_GAP_SECONDS:
        return CONTINUITY_ACTIVE
    if idle_seconds < _LONG_GAP_SECONDS:
        return CONTINUITY_RETURNING_SHORT_GAP
    return CONTINUITY_RETURNING_LONG_GAP


class ContextBuilder:
    """SATU-SATUNYA modul yang merangkai teks Ephemeral Context. Menggabungkan
    Behavior + Vision (v0.7) + Routine (v0.8) + Initiative (v0.9) Context —
    Vision, Routine, dan Initiative semuanya OPSIONAL; pipeline tetap jalan
    normal walau salah satu (atau semua) mati.

    Routine & Initiative section HARUS ditulis sebagai peluang/saran netral,
    bukan instruksi yang mendikte kalimat Arona (Routine Decision Policy,
    Autonomous Permission Policy) — Gemini yang memutuskan bagaimana
    meresponsnya. Initiative section malah tidak pernah muncul sama sekali
    kecuali `decision_result.should_start == True`.

    v1.9 (Companion Intelligence — Routine Relevance §10): Routine Suggestion
    section SEKARANG JUGA cuma muncul kalau `decision_result.should_start ==
    True` — sebelumnya routine_event yang masih pending SELALU ditempel ke
    context apa pun topik obrolannya (mis. reminder minum air nyempil di
    tengah pertanyaan debug Python). Initiative sudah menjadi 'apakah momen
    ini pas untuk hal kasual seperti ini' — reuse gate itu, bukan bikin
    intent classifier baru. Untuk giliran otonom (v1.8) ini TIDAK berubah
    perilakunya sama sekali, karena should_start SUDAH PASTI True di sana
    sebelum ContextBuilder.build() dipanggil."""

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
            self._format_continuity(behavior_state),
            self._format_emotion(behavior_state),
            self._format_relationship(behavior_state),
            self._format_internal(behavior_state),
        ]

        if vision_context is not None:
            sections.append(self._format_vision(vision_context))

        should_start = decision_result is not None and decision_result.should_start

        if routine_event is not None and should_start:
            sections.append(self._format_routine(routine_event))

        if should_start:
            sections.append(self._format_initiative(decision_result))

        return "\n\n".join(s for s in sections if s)

    def _format_time(self) -> str:
        now = datetime.now(ZoneInfo(self._timezone_name))
        hari = _HARI[now.weekday()]
        bulan = _BULAN[now.month - 1]
        return f"Current Time\n{hari}, {now.day} {bulan} {now.year}, pukul {now.strftime('%H:%M')} WIB"

    def _format_continuity(self, state: BehaviorState) -> str:
        """v3.1 Phase 1+2 — MURNI context signal, BUKAN instruksi/perintah.
        Arona TIDAK diwajibkan berkomentar soal jeda waktu ini — cukup jadi
        bahan pertimbangan supaya dia tidak bersikap seolah percakapan baru
        saja terpotong 2 detik lalu kalau sebenarnya sudah berjam-jam, atau
        sebaliknya menyapa ulang dari nol padahal masih di tengah pertukaran
        pesan yang sama (Continuity ≠ autonomous planner, spec v3.1 §Phase 1)."""
        idle_seconds = state.internal.elapsed_seconds()
        state_label = categorize_continuity(idle_seconds)
        minutes = int(idle_seconds // 60)

        if state_label == CONTINUITY_ACTIVE:
            return "Conversation Status\nMasih di tengah percakapan yang sama (belum ada jeda berarti)."
        if state_label == CONTINUITY_RETURNING_SHORT_GAP:
            return (
                f"Conversation Status\nTeacher baru saja kembali setelah jeda singkat "
                f"(~{minutes} menit). Boleh menyambung natural dari topik terakhir kalau "
                f"masih relevan, tidak perlu formal menyapa ulang dari nol."
            )
        return (
            f"Conversation Status\nTeacher kembali setelah jeda cukup lama "
            f"(~{minutes} menit sejak interaksi terakhir). Wajar untuk menyapa hangat "
            f"seperti awal baru, atau menanyakan kabar, sebelum lanjut ke topik lama "
            f"kalau memang masih relevan."
        )

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