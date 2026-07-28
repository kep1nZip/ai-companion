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


def build_routine_snapshot(pending_events: list, last_event, next_schedule: dict) -> RoutineSnapshot:
    pending = pending_events[0] if pending_events else None
    return RoutineSnapshot(
        pending_event_type=pending.event_type.value if pending else None,
        pending_priority=pending.priority.name if pending else None,
        pending_payload=pending.payload if pending else None,
        last_event_type=last_event.event_type.value if last_event else None,
        last_event_at=last_event.created_at.strftime("%Y-%m-%d %H:%M:%S") if last_event else None,
        next_schedule={k.value: v.strftime("%Y-%m-%d %H:%M:%S") for k, v in next_schedule.items()},
    )