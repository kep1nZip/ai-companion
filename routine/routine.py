from __future__ import annotations

from datetime import datetime
from typing import Optional

from routine.routine_clock import RoutineClock
from routine.routine_engine import RoutineEngine
from routine.routine_history import RoutineHistory
from routine.routine_event import RoutineEvent, RoutineEventType
from routine.routine_rules import COOLDOWNS
from behavior.behavior_state import BehaviorState
from vision.vision_context import VisionContext
from database.memory_manager import MemoryManager
from config.logger import logger


class Routine:
    """Public API Routine System. Satu-satunya titik masuk yang boleh dipanggil
    Companion (Routine Independence Policy) — TIDAK PERNAH tahu Avatar/Voice/GUI/
    PromptBuilder/MemoryManager (kecuali lewat RoutineHistory yang di-inject)."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None, timezone_name: str = "Asia/Jakarta"):
        self._clock = RoutineClock(timezone_name=timezone_name)
        self._history = RoutineHistory(memory_manager=memory_manager)
        self._engine = RoutineEngine(clock=self._clock, history=self._history)
        self._pending_event: Optional[RoutineEvent] = None

    def update(self, behavior_state: BehaviorState, vision_context: Optional[VisionContext] = None) -> Optional[RoutineEvent]:
        """Evaluasi ulang, simpan sebagai pending kalau ketemu. Kalau event lama
        masih pending & belum expired, TIDAK ditimpa (biar tidak batal terus)."""
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

    # ---------- Developer Routine Panel (rekomendasi GPT #4, backend-only) ----------

    def get_pending_events(self) -> list[RoutineEvent]:
        return [self._pending_event] if self._pending_event else []

    def get_last_event(self) -> Optional[RoutineEvent]:
        return self._history.last_event()

    def get_next_schedule(self) -> dict[RoutineEventType, datetime]:
        """Estimasi kapan tiap event type berikutnya BOLEH trigger lagi (akhir cooldown).
        Event yang belum pernah trigger tidak masuk dict (artinya kapan saja boleh)."""
        result: dict[RoutineEventType, datetime] = {}
        for event_type, cooldown in COOLDOWNS.items():
            last = self._history.last_triggered(event_type)
            if last is not None:
                result[event_type] = last + cooldown
        return result

    def clear_queue(self) -> None:
        """Hapus pending event SAJA — tidak memengaruhi history/cooldown."""
        self._pending_event = None
        logger.info("Routine queue dibersihkan.")