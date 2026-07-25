from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from routine.routine_clock import RoutineClock
from routine.routine_event import RoutineEvent, RoutineEventType
from routine.routine_history import RoutineHistory
from routine.routine_rules import (
    TRIGGER_CHECKS, EVALUATION_ORDER, COOLDOWNS,
    get_priority, get_payload, get_expiry_delta,
    suppression_level, is_suppressed,
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

    def evaluate(
        self,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
    ) -> Optional[RoutineEvent]:
        idle_seconds = behavior_state.internal.elapsed_seconds()
        level = suppression_level(vision_context)
        now = self._clock.now()

        for event_type in EVALUATION_ORDER:
            check = TRIGGER_CHECKS[event_type]
            if not check(self._clock, idle_seconds):
                continue

            priority = get_priority(event_type)

            if is_suppressed(event_type, priority, level):
                logger.info("Routine Suppressed: {} (level={})", event_type.value, level.value)
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