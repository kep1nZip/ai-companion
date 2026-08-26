from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from routine.routine_clock import RoutineClock
from routine.routine_event import RoutineEvent, RoutineEventType
from routine.routine_history import RoutineHistory
from routine.routine_rules import (
    TRIGGER_CHECKS, EVALUATION_ORDER, COOLDOWNS,
    get_priority, get_payload, get_expiry_delta,
    suppression_level, is_suppressed, SuppressionLevel,
)
from behavior.behavior_state import BehaviorState
from vision.vision_context import VisionContext
from config.logger import logger


class RoutineEngine:
    """Menggabungkan Clock + BehaviorState + VisionContext + History -> RoutineEvent.
    TIDAK PERNAH memanggil Gemini. TIDAK PERNAH memodifikasi BehaviorState/Vision —
    read-only murni."""

    def __init__(self, clock: RoutineClock, history: RoutineHistory):
        self._clock = clock
        self._history = history
        # v1.6 §20 (Suppression Visibility, best-effort/opsional): catatan
        # READ-ONLY murni tentang event_type+level TERAKHIR yang di-suppress
        # dalam satu evaluate() — TIDAK mengubah kontrak evaluate() (masih
        # Optional[RoutineEvent] seperti sebelumnya), TIDAK memindahkan logic
        # keputusan suppress ke GUI (itu tetap 100% di is_suppressed() di
        # bawah). Murni side-channel informasional untuk Routine GUI.
        self._last_suppression: Optional[tuple[RoutineEventType, SuppressionLevel]] = None

    def evaluate(
        self,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
    ) -> Optional[RoutineEvent]:
        idle_seconds = behavior_state.internal.elapsed_seconds()
        level = suppression_level(vision_context)
        now = self._clock.now()
        self._last_suppression = None  # reset tiap evaluasi baru — bukan status yang "menempel"

        for event_type in EVALUATION_ORDER:
            check = TRIGGER_CHECKS[event_type]
            if not check(self._clock, idle_seconds):
                continue

            priority = get_priority(event_type)

            if is_suppressed(event_type, priority, level):
                logger.info("Routine Suppressed: {} (level={})", event_type.value, level.value)
                self._last_suppression = (event_type, level)
                continue

            last = self._history.last_triggered(event_type)
            cooldown = COOLDOWNS[event_type]
            if last is not None and (now - last) < cooldown:
                logger.info("Routine Skipped (cooldown): {}", event_type.value)
                continue

            event = RoutineEvent(
                event_type=event_type,
                priority=priority,
                payload=get_payload(event_type),
                created_at=now,
                expires_at=now + get_expiry_delta(event_type),
            )
            logger.info("Routine Triggered: {}", event_type.value)
            return event

        return None

    # ---------- Suppression Visibility (v1.6, read-only) ----------

    def get_last_suppression(self) -> Optional[tuple[RoutineEventType, SuppressionLevel]]:
        """Hasil evaluate() TERAKHIR SAJA (bukan live/continuous) — dipakai
        Routine GUI untuk 'Understand whether a routine is ... suppressed'
        (spec §2/§6). None kalau evaluasi terakhir tidak men-suppress apa pun
        (termasuk kalau belum pernah evaluate() sama sekali)."""
        return self._last_suppression