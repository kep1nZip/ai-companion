from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RoutineSnapshot:
    pending_event_type: Optional[str]
    pending_priority: Optional[str]
    pending_payload: Optional[str]
    last_event_type: Optional[str]
    last_event_at: Optional[str]
    next_schedule: dict
    enabled: bool  # v1.7 §14: dari Companion.is_routine_enabled() (v1.6)
    last_suppression_type: Optional[str]  # v1.7 §14: dari Companion.get_routine_suppression() (v1.6)
    last_suppression_level: Optional[str]
    recent_history_count: int  # v1.7 §14: len(Companion.get_routine_history()) (v1.6)


def build_routine_snapshot(
    pending_events: list,
    last_event,
    next_schedule: dict,
    enabled: bool = True,
    last_suppression: Optional[tuple] = None,
    recent_history_count: int = 0,
) -> RoutineSnapshot:
    pending = pending_events[0] if pending_events else None
    sup_type, sup_level = last_suppression if last_suppression else (None, None)
    return RoutineSnapshot(
        pending_event_type=pending.event_type.value if pending else None,
        pending_priority=pending.priority.name if pending else None,
        pending_payload=pending.payload if pending else None,
        last_event_type=last_event.event_type.value if last_event else None,
        last_event_at=last_event.created_at.strftime("%Y-%m-%d %H:%M:%S") if last_event else None,
        next_schedule={k.value: v.strftime("%Y-%m-%d %H:%M:%S") for k, v in next_schedule.items()},
        enabled=enabled,
        last_suppression_type=sup_type.value if sup_type else None,
        last_suppression_level=sup_level.value if sup_level else None,
        recent_history_count=recent_history_count,
    )