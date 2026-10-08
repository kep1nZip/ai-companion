from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from behavior.behavior_state import BehaviorState
from vision.vision_context import VisionContext

from routine.routine_event import RoutineEvent

from initiative.initiative_decision import DecisionResult

from ai.temporal_signals import TemporalSignals
from ai.response_calibration import ResponseCalibration
from ai.conversation_feedback import ConversationFeedback

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
        temporal_signals: Optional[TemporalSignals] = None,
        response_calibration: Optional[ResponseCalibration] = None,
    ) -> str:
        sections = [
            self._format_time(),
            self._format_continuity(behavior_state),
            self._format_emotion(behavior_state),
            self._format_relationship(behavior_state),
            self._format_internal(behavior_state),
        ]

        # v3.5 Phase 10/11 (Temporal Awareness & Task Continuity) —
        # `ContextBuilder` TETAP assembly-only (spec §15: "ContextBuilder
        # remains assembly-only"): deteksi sinyal SUDAH dilakukan Companion
        # lewat `ai/temporal_signals.py::detect_temporal_signals()` SEBELUM
        # `build()` dipanggil (pola IDENTIK `vision_context`/`routine_event`/
        # `decision_result` — semua dihitung Companion, method ini cuma
        # merangkai teks). Section HANYA muncul kalau ADA sinyal terdeteksi
        # (`temporal_signals.is_empty()` False) — spec §15 "optional",
        # jangan menambah noise section kosong untuk pesan yang memang
        # tidak mengandung sinyal waktu/kontinuitas apa pun. Diletakkan
        # SETELAH `_format_continuity` (v3.1) — keduanya sama-sama soal
        # waktu/kesinambungan, wajar bersebelahan; TIDAK mengubah urutan
        # section lain yang sudah ada (spec §16: "Do not rearrange the
        # whole context pipeline").
        if temporal_signals is not None and not temporal_signals.is_empty():
            sections.append(self._format_temporal(temporal_signals))

        # v3.6 Phase 8 (ContextBuilder Integration) — pola IDENTIK
        # `temporal_signals` di atas: deteksi SUDAH dilakukan Companion
        # SEBELUM `build()` dipanggil (`ai/response_calibration.py::
        # build_response_calibration()`), method ini TETAP assembly-only.
        # Section HANYA muncul kalau ADA evidence (`is_empty()` False) —
        # spec §13: "section should only appear when useful evidence
        # exists." Diletakkan SETELAH Temporal Context — keduanya SAMA-
        # SAMA evidence per-pesan-saat-ini (bukan state behavior jangka
        # panjang seperti Emotion/Relationship di atas), wajar
        # bersebelahan; urutan section LAIN tidak diubah (spec §25: tidak
        # merombak pipeline context yang sudah ada).
        if response_calibration is not None and not response_calibration.is_empty():
            sections.append(self._format_response_calibration(response_calibration))

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

    def _format_temporal(self, signals: TemporalSignals) -> str:
        """v3.5 Phase 10 — section BARU, FAKTUAL & KOMPAK (spec §15: "must
        be factual, compact, provider-agnostic, optional, free of
        imperative instructions"). Setiap baris HANYA muncul kalau field
        terkait tidak kosong — TIDAK PERNAH menulis "Task Status: ACTIVE"
        atau kalimat perintah seperti "Arona should continue the task"
        (Hard Boundary spec §4.2/§4.3/§15 eksplisit melarang ini). Label
        "Sinyal ..." dipilih SENGAJA (bukan "Status") — supaya jelas ini
        OBSERVASI leksikal, bukan kesimpulan."""
        lines = ["Temporal Context"]
        if signals.relative_terms:
            lines.append(f"Rujukan waktu relatif: {', '.join(signals.relative_terms)}")
        if signals.normalized_dates:
            lines.append(f"Tanggal (dihitung dari kalender): {', '.join(signals.normalized_dates)}")
        if signals.continuation_cues:
            lines.append(f"Sinyal kelanjutan aktivitas: {', '.join(signals.continuation_cues)}")
        if signals.completion_cues:
            lines.append(f"Sinyal penyelesaian: {', '.join(signals.completion_cues)}")
        if signals.unresolved_cues:
            lines.append(f"Sinyal belum tuntas: {', '.join(signals.unresolved_cues)}")
        return "\n".join(lines)

    def measure_sections(
        self,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
        temporal_signals: Optional[TemporalSignals] = None,
        response_calibration: Optional[ResponseCalibration] = None,
    ) -> dict:
        """v3.9 Phase 1 (Adaptive Context Budget & Attention Allocation) —
        PURE measurement helper, NOL side effect, NOL capture Vision baru,
        NOL deteksi ulang apa pun. Reuse LANGSUNG method `_format_*` yang
        SUDAH ADA (satu-satunya tempat yang tahu persis bagaimana tiap
        section dirender) — supaya angka yang dilaporkan selalu PERSIS
        SAMA dengan apa yang benar-benar dikirim `build()`, tidak pernah
        bisa diam-diam berbeda (dua tempat kode beda yang kebetulan harus
        selalu sinkron adalah sumber bug klasik, di sini sengaja dihindari
        dengan memanggil formatter yang SAMA).

        Return dict `{nama_section: jumlah_karakter}` — section yang TIDAK
        akan muncul (evidence kosong/`None`) dilaporkan `0`, BUKAN
        dihilangkan dari dict (supaya pemanggil tidak perlu menduga-duga
        key mana yang ada)."""
        sizes = {
            "time": len(self._format_time()),
            "continuity": len(self._format_continuity(behavior_state)),
            "emotion": len(self._format_emotion(behavior_state)),
            "relationship": len(self._format_relationship(behavior_state)),
            "internal": len(self._format_internal(behavior_state)),
            "temporal": 0,
            "calibration": 0,
            "vision": 0,
        }
        if temporal_signals is not None and not temporal_signals.is_empty():
            sizes["temporal"] = len(self._format_temporal(temporal_signals))
        if response_calibration is not None and not response_calibration.is_empty():
            sizes["calibration"] = len(self._format_response_calibration(response_calibration))
        if vision_context is not None:
            sizes["vision"] = len(self._format_vision(vision_context))
        return sizes

    def build_feedback_section(self, feedback: ConversationFeedback) -> str:
        """v3.7 Phase 10/11/15 — BEDA dari section lain (`_format_temporal`/
        `_format_response_calibration`, dipanggil dari dalam `build()` dan
        selalu muncul di AWAL ephemeral block) — method PUBLIK TERPISAH,
        SENGAJA, supaya `Companion._build_contents()` bisa menaruh hasilnya
        di PALING AKHIR `contents` (setelah riwayat, dekat titik generasi),
        bukan di awal. Spec §16 eksplisit: "Concrete situational evidence
        should remain close to the generation point, following the same
        architectural lesson used by earlier milestones" — merujuk pola
        yang SAMA dengan reinforcement note hotfix v3.3 (`_build_contents`,
        bukan lewat `ContextBuilder` sama sekali) dan `autonomous_note` di
        `_build_autonomous_contents`.

        `ContextBuilder` TETAP satu-satunya yang merangkai teks (prinsip
        "assembly-only" tidak dilanggar — Companion CUMA memutuskan DI MANA
        menaruh potongan teks ini di `contents`, bukan APA ISINYA). Return
        string kosong `""` kalau `feedback.is_empty()` True — pemanggil
        HARUS cek ini sebelum menambahkan `Content` baru (spec §15: jangan
        menambah blok metadata kosong)."""
        if feedback.is_empty():
            return ""
        return self._format_conversation_feedback(feedback)

    def _format_conversation_feedback(self, feedback: ConversationFeedback) -> str:
        """v3.7 Phase 10 — FAKTUAL & KOMPAK (spec §18 Telemetry Rules:
        "Good: Correction detected: true. Bad: Arona was wrong: true").
        Wording OBSERVASIONAL ("Teacher indicates...", "Teacher asks
        for..."), BUKAN kesimpulan kualitas jawaban Arona sendiri. Setiap
        baris independen & HANYA muncul kalau kategori terkait benar-benar
        terdeteksi — TIDAK PERNAH menulis "Arona's previous answer was
        wrong/bad" (Hard Boundary §4.2)."""
        lines = ["Conversation Feedback"]
        label_map = {
            "confusion": "Teacher tampak belum memahami balasan sebelumnya.",
            "correction": "Teacher menunjukkan interpretasi sebelumnya bukan yang dimaksud.",
            "negative_length_feedback": "Teacher menilai balasan sebelumnya terlalu panjang.",
            "negative_complexity_feedback": "Teacher menilai balasan sebelumnya terlalu rumit/teknis.",
            "repeat_request": "Teacher meminta pengulangan/penjelasan ulang.",
            "simplification_request": "Teacher meminta penjelasan yang lebih sederhana.",
            "expansion_request": "Teacher meminta penjelasan yang lebih lengkap/mendalam.",
            "positive_acknowledgement": "Teacher mengonfirmasi sudah paham.",
            "closure": "Teacher tampak ingin menutup topik ini.",
        }
        for cue in feedback.feedback_cues:
            label = label_map.get(cue)
            if label:
                lines.append(f"- {label}")
        if feedback.explicit_phrases:
            phrases = ", ".join(f'"{p}"' for p in feedback.explicit_phrases)
            lines.append(f"- Frasa eksplisit Teacher: {phrases}.")
        if feedback.conflicting_feedback:
            lines.append("- Catatan: sinyal feedback di atas tampak saling bertentangan — gunakan pertimbangan wajar.")
        return "\n".join(lines)

    def _format_response_calibration(self, calibration: ResponseCalibration) -> str:
        """v3.6 Phase 8/9 — section BARU, FAKTUAL & KOMPAK (spec §13/§14:
        "must be factual, compact... Avoid rigid commands such as 'Arona
        MUST answer in exactly 3 sentences'"). Wording dipilih bentuk
        OBSERVASI ("Teacher explicitly asked for..."), BUKAN perintah
        ("You must...") — spec §14 contoh eksplisit. `explicit_phrases`
        ditulis VERBATIM (bukan cuma label kategori) — konkret > abstrak,
        pelajaran dari hotfix v3.3 round 2 untuk model yang lebih lemah.
        TIDAK PERNAH menulis angka confidence/skor apa pun (Hard Boundary
        spec §19/§24)."""
        lines = ["Response Calibration"]
        if calibration.conversation_form:
            form_label = calibration.conversation_form.replace("_", " ")
            lines.append(f"Bentuk pesan Teacher saat ini tampak seperti: {form_label}.")
        if calibration.explicit_phrases:
            phrases = ", ".join(f'"{p}"' for p in calibration.explicit_phrases)
            lines.append(f"Teacher menyebutkan instruksi gaya jawaban secara eksplisit: {phrases}.")
        if calibration.conflicting_cues:
            lines.append(
                "Catatan: instruksi gaya jawaban di atas tampak saling bertentangan "
                "(diminta detail sekaligus singkat) — gunakan pertimbangan wajar."
            )
        return "\n".join(lines)

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