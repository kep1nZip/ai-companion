from __future__ import annotations

from datetime import datetime
from typing import Optional

from routine.routine_clock import RoutineClock
from routine.routine_engine import RoutineEngine
from routine.routine_history import RoutineHistory
from routine.routine_event import RoutineEvent, RoutineEventType
from routine.routine_rules import COOLDOWNS, SuppressionLevel
from behavior.behavior_state import BehaviorState
from vision.vision_context import VisionContext
from database.memory_manager import MemoryManager
from config.logger import logger


class Routine:
    """Public API Routine System. Satu-satunya titik masuk yang boleh dipanggil
    Companion (Routine Independence Policy) — TIDAK PERNAH tahu Avatar/Voice/GUI/
    PromptBuilder/MemoryManager (kecuali lewat RoutineHistory yang di-inject).

    v1.6 (Routine Experience GUI): menambahkan lifecycle boundary MINIMAL yang
    sebelumnya tidak ada di Routine sama sekali — enable()/disable()/
    is_enabled() (spec §10: 'If Missing: Do not redesign the Routine system,
    only add the smallest possible lifecycle boundary required for GUI
    control'). Scheduler/Engine/History TIDAK diubah arsitekturnya sama
    sekali — cuma satu flag boolean yang men-gate evaluate() di update()."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None, timezone_name: str = "Asia/Jakarta"):
        self._clock = RoutineClock(timezone_name=timezone_name)
        self._history = RoutineHistory(memory_manager=memory_manager)
        self._engine = RoutineEngine(clock=self._clock, history=self._history)
        self._pending_event: Optional[RoutineEvent] = None
        # v1.6 §13: default ENABLED tiap start (Persistence Policy — TIDAK
        # ada persistence baru untuk state ini, sama seperti perilaku Routine
        # sebelum v1.6 yang selalu aktif kalau Companion(enable_routine=True)).
        self._enabled: bool = True

    def update(self, behavior_state: BehaviorState, vision_context: Optional[VisionContext] = None) -> Optional[RoutineEvent]:
        """Evaluasi ulang, simpan sebagai pending kalau ketemu. Kalau event lama
        masih pending & belum expired, TIDAK ditimpa (biar tidak batal terus).

        v1.6 §11 (Disable Semantics): kalau disabled, TIDAK ADA evaluate() baru
        yang dijalankan sama sekali — 'Routine Scheduler -> STOP', 'No new
        RoutineEvents may be generated'. History/cooldown/pending event LAMA
        tetap utuh di memori (tidak dihapus), cuma tidak dipakai Companion.chat()
        selama disabled (chat() cuma memakai return value update() ini)."""
        if not self._enabled:
            return None

        now = self._clock.now()

        if self._pending_event is not None and not self._pending_event.is_expired(now):
            return self._pending_event

        if self._pending_event is not None and self._pending_event.is_expired(now):
            logger.info("Routine Expired: {}", self._pending_event.event_type.value)
            self._pending_event = None

        self._pending_event = self._engine.evaluate(behavior_state, vision_context)
        return self._pending_event

    def poll(self) -> Optional[RoutineEvent]:
        """Peek pending event TANPA memicu evaluasi ulang."""
        return self._pending_event

    def get_pending_event(self) -> Optional[RoutineEvent]:
        return self._pending_event

    def mark_completed(self, event: Optional[RoutineEvent] = None) -> None:
        """Tandai event (default: pending saat ini) sudah dipakai — mulai cooldown,
        catat ke history, bersihkan pending."""
        target = event or self._pending_event
        if target is None:
            return

        self._history.record(target)
        if self._pending_event is not None and self._pending_event.event_type == target.event_type:
            self._pending_event = None

    # ---------- Enable / Disable Lifecycle (v1.6 §10-12) ----------

    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """§12 Re-enable Behavior: TIDAK ADA backlog replay — evaluate() cuma
        pernah mengecek kondisi SAAT DIPANGGIL, tidak pernah ada antrean event
        yang 'seharusnya terjadi' selama disabled, jadi tidak ada apa pun yang
        perlu di-replay di sini. Scheduler otomatis lanjut normal dari state
        sekarang begitu update() dipanggil lagi lewat chat() berikutnya."""
        if self._enabled:
            return
        self._enabled = True
        logger.info("Routine Enabled")

    def disable(self) -> None:
        """§11: HANYA menghentikan evaluasi routine baru ke depan. History,
        Memory, Relationship, Emotion, Behavior state semuanya TIDAK disentuh
        sama sekali — Routine tidak mengelola satu pun dari itu."""
        if not self._enabled:
            return
        self._enabled = False
        logger.info("Routine Disabled")

    # ---------- Developer Panel prep (v0.9.5) & Routine GUI (v1.6) ----------

    def get_pending_events(self) -> list[RoutineEvent]:
        return [self._pending_event] if self._pending_event else []

    def get_last_event(self) -> Optional[RoutineEvent]:
        return self._history.last_event()

    def get_recent_history(self, limit: int = 10) -> list[RoutineEvent]:
        """v1.6 §18: pakai RoutineHistory.recent() yang SUDAH ADA sejak v0.8
        (dipakai Companion.get_pending_routine_events()-style passthrough,
        sebelumnya belum pernah di-expose ke GUI). TIDAK ADA
        RoutineGuiHistory/RoutineHistoryDatabase baru — storage sama persis."""
        return self._history.recent(limit=limit)

    def get_next_schedule(self) -> dict[RoutineEventType, datetime]:
        """Estimasi kapan tiap event type berikutnya BOLEH trigger lagi (akhir cooldown).
        Event yang belum pernah trigger tidak masuk dict (artinya kapan saja boleh)."""
        result: dict[RoutineEventType, datetime] = {}
        for event_type, cooldown in COOLDOWNS.items():
            last = self._history.last_triggered(event_type)
            if last is not None:
                result[event_type] = last + cooldown
        return result

    def get_last_suppression(self) -> Optional[tuple[RoutineEventType, SuppressionLevel]]:
        """v1.6 §20 (best-effort, opsional): passthrough tipis ke
        RoutineEngine.get_last_suppression() — lihat komentar di sana."""
        return self._engine.get_last_suppression()

    def clear_queue(self) -> None:
        """Hapus pending event SAJA — tidak memengaruhi history/cooldown."""
        self._pending_event = None
        logger.info("Routine queue dibersihkan.")