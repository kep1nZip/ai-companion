from __future__ import annotations

import random


class BlinkAnimator:
    """Cuma logic timing & kurva nilai kedipan mata. Tidak ada networking/GUI/AI."""

    def __init__(
        self,
        min_interval: float = 4.0,
        max_interval: float = 9.0,
        blink_duration: float = 0.15,
        double_blink_chance: float = 0.1,
    ):
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._blink_duration = blink_duration
        self._double_blink_chance = double_blink_chance

    def next_interval(self) -> float:
        """Interval acak sampai kedipan berikutnya — sengaja tidak fixed, biar tidak robotic."""
        return random.uniform(self._min_interval, self._max_interval)

    def should_double_blink(self) -> bool:
        return random.random() < self._double_blink_chance

    def blink_curve(self) -> list[tuple[float, float]]:
        """Satu siklus kedip: (delay_detik, EyeOpen_value). 1.0 = terbuka penuh, 0.0 = tertutup."""
        half = self._blink_duration / 2
        return [
            (0.0, 1.0),
            (half, 0.0),
            (half, 1.0),
        ]

    def set_timing(self, min_interval: float, max_interval: float) -> None:
        """Hook opsional untuk Behavior Engine (v0.6.5+) — belum dipanggil di v0.6.1."""
        self._min_interval = min_interval
        self._max_interval = max_interval

    def set_duration(self, blink_duration: float) -> None:
        """Hook untuk Behavior Engine (v0.6.5) — mengubah durasi kedip (mis. lebih
        lama saat Sleepy)."""
        self._blink_duration = blink_duration