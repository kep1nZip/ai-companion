from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from behavior.behavior_state import BehaviorState
from behavior.mood import Mood
from routine.routine_event import RoutineEvent, EventPriority
from vision.vision_context import VisionContext
from vision.vision_signals import matches_presentation, matches_focused_work


@dataclass(frozen=True)
class DecisionContext:
    """Snapshot input untuk 1 evaluasi. Immutable, read-only terhadap sumber aslinya."""

    idle_seconds: float
    behavior_state: BehaviorState
    vision_context: Optional[VisionContext]
    routine_event: Optional[RoutineEvent]
    hour: int
    # v2.7 Phase 5+6 (Memory/Vision-aware Initiative) — SENGAJA cuma angka
    # ringkas (jumlah), BUKAN daftar Memory penuh (Teacher eksplisit:
    # "jangan memasukkan daftar memory lengkap ke Initiative"). Default 0
    # supaya pemanggil lama (kalau ada) tidak perlu diubah — backward compat.
    relevant_memory_count: int = 0
    # v2.8 Phase 5 (Conversation Closure) — SATU boolean, dihitung Companion
    # dari `Conversation.get_last_user_message()` lewat
    # `ai/conversation_signals.py::detect_closure()` (pattern matching murni,
    # TIDAK ADA LLM kedua). Default False = backward compat penuh.
    conversation_closed: bool = False


class DecisionRule:
    """Weighted Rule Object (rekomendasi GPT #2). Tiap aturan = 1 object dengan
    bobot sendiri — bobot bisa diubah/dikonfigurasi dari luar (GUI/config file
    masa depan) TANPA mengubah InitiativeEngine sama sekali, karena engine cuma
    iterasi list generic `list[DecisionRule]`."""

    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        """Return alasan (str) kalau aturan ini AKTIF (kontribusi `weight` ke skor),
        atau None kalau tidak relevan sama sekali."""
        raise NotImplementedError

    def get_weight(self, ctx: DecisionContext) -> float:
        """v2.7 Phase 3 — ekstensi KECIL, BUKAN perubahan arsitektur: default
        SELALU `self.weight` (statis), PERSIS perilaku sebelum v2.7 untuk
        SEMUA rule yang tidak meng-override method ini (IdleRule,
        RelationshipRule, MoodBonusRule, dst — nol perubahan perilaku).
        Method ini HANYA di-override `RoutinePendingRule` di bawah, supaya
        kontribusinya bisa bervariasi sesuai `EventPriority` yang SUDAH ADA
        di `RoutineEvent` (Phase 0 Audit §4 — data sudah ada, sebelumnya
        diabaikan). `InitiativeEngine.compute()` memanggil method ini
        (bukan `.weight` langsung) untuk SEMUA rule, supaya satu titik
        ekstensi ini konsisten dipakai — tapi untuk 6 dari 7 rule di
        `DEFAULT_RULES`, hasilnya identik dengan `.weight` seperti biasa."""
        return self.weight


class IdleRule(DecisionRule):
    def __init__(self, weight: float = 20.0, threshold_seconds: float = 900.0):
        super().__init__("idle", weight)
        self._threshold = threshold_seconds

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        if ctx.idle_seconds >= self._threshold:
            return f"Teacher idle selama {int(ctx.idle_seconds // 60)} menit"
        return None


class RecentInteractionPenaltyRule(DecisionRule):
    """v2.7 Phase 1 (Recent Interaction Awareness).

    Reuse `ctx.idle_seconds` yang SUDAH ADA (v2.7 Phase 0 Audit §1 — sudah
    dikonfirmasi lewat trace kode: nilai ini SUDAH akurat merepresentasikan
    "detik sejak pesan Teacher terakhir", karena `InternalState.timestamp`
    HANYA di-reset oleh `chat()` (`process_message()`), TIDAK PERNAH oleh
    jalur autonomous `check_autonomous_opportunity()` yang cuma baca
    `current_behavior_state()`). TIDAK ADA state baru, timer baru, atau
    cooldown kedua yang ditambahkan — murni rule baru yang membaca data
    yang sudah mengalir ke `DecisionContext` sejak awal.

    SENGAJA TIDAK memperkenalkan angka arbitrer apa pun (guardrail v2.7
    "Jangan memilih angka penalty secara asal"):
    - `threshold_seconds` default = PERSIS SAMA dengan `IdleRule.
      _threshold` (900 detik / 15 menit) — bukan angka baru, ini
      komplemen logis dari IdleRule: "idle" (>= 900s, dapat bonus) vs
      "baru berinteraksi" (< 900s, dapat penalty) adalah DUA SISI dari
      variabel kontinu yang SAMA, dengan titik potong yang SAMA PERSIS.
    - `weight` default = -20.0, magnitude PERSIS SAMA dengan `IdleRule.
      weight` (+20.0) — desain simetris: rule yang "berlawanan" secara
      konsep dari IdleRule memakai magnitude yang sama, bukan angka baru
      yang saya tebak sendiri.

    Baseline diverifikasi lewat enumerasi kombinasi `DEFAULT_RULES` (v2.7
    Phase 0 Audit §3, ulang lewat script terpisah sebelum memilih angka
    ini): TANPA rule ini, kombinasi `routine_pending(+25) + relationship
    (+15) + mood_bonus(+10) = 50` PERSIS SAMA DENGAN threshold — bisa
    `should_start=True` walau Teacher baru saja chat. DENGAN penalty -20
    (berlaku penuh selama idle_seconds < 900), skor kombinasi itu jadi 30
    — aman di bawah threshold dengan margin jelas (20 poin), bukan cuma
    selisih tipis 1 poin."""

    def __init__(self, weight: float = -20.0, threshold_seconds: float = 900.0):
        super().__init__("recent_interaction_penalty", weight)
        self._threshold = threshold_seconds

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        if ctx.idle_seconds < self._threshold:
            minutes_ago = ctx.idle_seconds / 60
            return f"Teacher baru berinteraksi {minutes_ago:.1f} menit lalu"
        return None


class RelationshipRule(DecisionRule):
    def __init__(self, weight: float = 15.0, min_average: int = 60):
        super().__init__("relationship", weight)
        self._min_average = min_average

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        r = ctx.behavior_state.relationship
        avg = (r.trust.current + r.comfort.current + r.affection.current) / 3
        if avg >= self._min_average:
            return f"Relationship dengan Teacher cukup dekat (avg {avg:.0f})"
        return None


class MoodBonusRule(DecisionRule):
    _POSITIVE = {Mood.CHEERFUL, Mood.CURIOUS, Mood.RELAXED}

    def __init__(self, weight: float = 10.0):
        super().__init__("mood_bonus", weight)

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        mood = ctx.behavior_state.internal.mood
        if mood in self._POSITIVE:
            return f"Mood Arona sedang {mood.value}"
        return None


class EnergyPenaltyRule(DecisionRule):
    def __init__(self, weight: float = -15.0, low_threshold: int = 30):
        super().__init__("energy_penalty", weight)
        self._low_threshold = low_threshold

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        energy = ctx.behavior_state.internal.energy.value
        if energy <= self._low_threshold:
            return f"Energi Arona rendah ({energy})"
        return None


class CuriosityRule(DecisionRule):
    def __init__(self, weight: float = 10.0, min_level: int = 60):
        super().__init__("curiosity", weight)
        self._min_level = min_level

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        level = ctx.behavior_state.internal.curiosity.level
        if level >= self._min_level:
            return f"Curiosity Arona tinggi ({level})"
        return None


class InitiativeLevelRule(DecisionRule):
    def __init__(self, weight: float = 15.0, min_level: int = 60):
        super().__init__("initiative_level", weight)
        self._min_level = min_level

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        level = ctx.behavior_state.internal.initiative.level
        if level >= self._min_level:
            return f"Internal InitiativeState tinggi ({level})"
        return None


class RoutinePendingRule(DecisionRule):
    """v2.7 Phase 3 (Opportunity Relevance): kontribusi sekarang MONOTONIC
    terhadap `RoutineEvent.priority` (EventPriority — data yang SUDAH ADA,
    Phase 0 Audit §4, SEBELUMNYA diabaikan sepenuhnya oleh flat +25).

    Formula: `weight * (priority.value / EventPriority.MEDIUM.value)` —
    TIDAK memperkenalkan angka baru: `weight` (25.0) adalah nilai default
    yang SUDAH ADA sebelum v2.7, `MEDIUM.value` (3) adalah nilai TENGAH
    dari enum `EventPriority` yang SUDAH ADA (bukan angka yang saya
    pilih). MEDIUM dipilih sebagai anchor karena itu prioritas paling umum
    di `routine_rules.py::_PRIORITY` — hasilnya PERSIS +25 (byte-identik
    perilaku lama) untuk event MEDIUM, jadi tidak ada regresi untuk
    mayoritas event yang sudah ada. Tidak ada sistem priority baru dibuat
    — cuma reuse `EventPriority` yang sudah ada."""

    def __init__(self, weight: float = 25.0):
        super().__init__("routine_pending", weight)

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        if ctx.routine_event is not None:
            return f"Ada routine event pending: {ctx.routine_event.event_type.value} (priority={ctx.routine_event.priority.name})"
        return None

    def get_weight(self, ctx: DecisionContext) -> float:
        if ctx.routine_event is None:
            return self.weight
        return self.weight * (ctx.routine_event.priority.value / EventPriority.MEDIUM.value)


class MemoryRelevanceRule(DecisionRule):
    """v2.7 Phase 5+6 (Memory-Aware + Vision-Aware Initiative, digabung —
    root cause sama, Phase 0 Audit §5/§6).

    Alur SUDAH DIPUTUSKAN eksplisit oleh Teacher (bukan asumsi saya):
        Fresh Vision -> application/summary -> retrieval Memory yang SUDAH
        ADA (`Companion._select_relevant_memories()`, TIDAK dibuat ulang)
        -> `relevant_memory_count` (angka ringkas, BUKAN daftar Memory
        penuh) -> DecisionContext -> rule ini -> bonus skor.

    Reuse murni: rule ini TIDAK pernah memanggil MemoryManager/provider
    apa pun sendiri — cuma membaca `ctx.relevant_memory_count` yang SUDAH
    dihitung Companion SEBELUM DecisionContext dibuat (lihat
    `ai/companion.py::_count_relevant_memories_for_vision()`). Initiative
    TIDAK PERNAH jadi orchestrator retrieval kedua — cuma konsumen angka.

    Weight = 10.0 — SENGAJA dipilih dari magnitude PALING KECIL yang sudah
    dipakai rule lain di DEFAULT_RULES (MoodBonusRule/CuriosityRule sama-
    sama 10.0), BUKAN angka baru yang saya karang — konservatif karena ini
    sinyal yang belum tervalidasi lewat pemakaian nyata (beda dari Phase 1
    yang punya justifikasi simetris eksplisit ke IdleRule). Bisa dinaikkan
    nanti lewat data observability (Phase 10, sudah otomatis tersedia)
    kalau terbukti terlalu lemah/kuat — bukan keputusan final saya."""

    def __init__(self, weight: float = 10.0, min_count: int = 1):
        super().__init__("memory_relevance", weight)
        self._min_count = min_count

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        if ctx.relevant_memory_count >= self._min_count:
            return f"Vision saat ini berkaitan dengan {ctx.relevant_memory_count} memori Teacher"
        return None


class ConversationClosureRule(DecisionRule):
    """v2.8 Phase 5 (Conversation Closure).

    Reuse total: sinyal `conversation_closed` DIHITUNG di Companion (lewat
    `ai/conversation_signals.py::detect_closure()`, pattern matching murni)
    SEBELUM `DecisionContext` dibuat — rule ini cuma KONSUMEN boolean,
    persis pola `MemoryRelevanceRule` (v2.7). Initiative TIDAK PERNAH
    membaca isi percakapan sendiri.

    SENGAJA soft penalty (BUKAN hard suppression seperti `check_suppression()`
    untuk meeting/coding) — spec v2.8 §10 eksplisit: "Closure signal DAPAT
    digunakan untuk MEMBANTU keputusan Initiative", bukan mengontrolnya
    secara mutlak. Kalau closure signal salah deteksi sesekali, dampaknya
    cuma skor turun sedikit, bukan Arona 100% dibungkam.

    Weight = -10.0 — dipilih dari magnitude PALING KECIL yang sudah dipakai
    rule lain (`MoodBonusRule`/`CuriosityRule`/`MemoryRelevanceRule` sama-
    sama 10.0), BUKAN angka baru — konsisten dengan alasan yang sama seperti
    `MemoryRelevanceRule` (v2.7): sinyal baru yang belum tervalidasi lewat
    pemakaian nyata, dimulai konservatif. Rule ini independen dari
    `RecentInteractionPenaltyRule` (bisa aktif BERSAMAAN — closure yang baru
    saja terjadi otomatis juga kena idle_seconds kecil, keduanya menumpuk
    jadi -30 total, semakin meyakinkan Initiative untuk diam)."""

    def __init__(self, weight: float = -10.0):
        super().__init__("conversation_closure", weight)

    def evaluate(self, ctx: DecisionContext) -> Optional[str]:
        if ctx.conversation_closed:
            return "Teacher baru saja memberi sinyal penutupan percakapan"
        return None


DEFAULT_RULES: list[DecisionRule] = [
    IdleRule(),
    RecentInteractionPenaltyRule(),
    RelationshipRule(),
    MoodBonusRule(),
    EnergyPenaltyRule(),
    CuriosityRule(),
    InitiativeLevelRule(),
    RoutinePendingRule(),
    MemoryRelevanceRule(),
    ConversationClosureRule(),
]

DEFAULT_THRESHOLD = 50.0


# ---------- Suppression Policy (hard override, DI lewat boolean bukan import modul) ----------

def check_suppression(
    vision_context: Optional[VisionContext],
    is_voice_active: bool = False,
    is_actively_typing: bool = False,
) -> tuple[bool, Optional[str]]:
    """Suppression OVERRIDE skor (spec eksplisit) — bukan cuma bobot negatif besar.
    is_voice_active/is_actively_typing sengaja BOOLEAN (Dependency Injection nilai,
    bukan import speech/*) — titik ekstensi siap pakai untuk nanti Companion
    menyambungkan sinyal VoiceManager tanpa Initiative pernah import speech."""
    if is_voice_active:
        return True, "Teacher sedang menggunakan microphone"
    if is_actively_typing:
        return True, "Teacher sedang mengetik"

    if matches_presentation(vision_context):
        return True, "Teacher sedang meeting/presentasi"
    if matches_focused_work(vision_context):
        return True, "Teacher sedang coding/fokus kerja"

    return False, None