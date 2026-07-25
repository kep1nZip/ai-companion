from __future__ import annotations

from datetime import time
from enum import Enum

from routine.routine_clock import RoutineClock


class TimeWindow(Enum):
    EARLY_MORNING = "early_morning"   # 05:00-08:00
    MORNING = "morning"                # 08:00-11:00
    LUNCH = "lunch"                      # 11:00-14:00
    AFTERNOON = "afternoon"               # 14:00-18:00
    EVENING = "evening"                    # 18:00-22:00
    NIGHT = "night"                          # 22:00-05:00


_WINDOWS: list[tuple[time, time, TimeWindow]] = [
    (time(5, 0), time(8, 0), TimeWindow.EARLY_MORNING),
    (time(8, 0), time(11, 0), TimeWindow.MORNING),
    (time(11, 0), time(14, 0), TimeWindow.LUNCH),
    (time(14, 0), time(18, 0), TimeWindow.AFTERNOON),
    (time(18, 0), time(22, 0), TimeWindow.EVENING),
]


def current_window(clock: RoutineClock) -> TimeWindow:
    """Cuma penjadwalan periode hari. TIDAK ADA logic AI apa pun."""
    now = clock.time_of_day()
    for start, end, window in _WINDOWS:
        if start <= now < end:
            return window
    return TimeWindow.NIGHT