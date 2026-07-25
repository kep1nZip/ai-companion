from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


class RoutineClock:
    """Cuma menyediakan waktu saat ini. TIDAK ADA business logic sama sekali."""

    def __init__(self, timezone_name: str = "Asia/Jakarta"):
        self._timezone_name = timezone_name

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self._timezone_name))

    def time_of_day(self) -> time:
        return self.now().time()

    def weekday(self) -> int:
        """0=Senin ... 6=Minggu"""
        return self.now().weekday()

    def is_weekend(self) -> bool:
        return self.weekday() >= 5