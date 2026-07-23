from __future__ import annotations

import math
import time


class BreathingAnimator:
    """Cuma logic gerakan napas kontinu (gelombang sinus lambat). Tidak ada networking/GUI/AI.
    Fallback aman kalau model tidak punya parameter napas — nilai tetap dihitung terus,
    yang menentukan dipakai/tidaknya adalah ParameterMapper (kalau parameter_id tidak ada
    di config, AvatarManager otomatis skip update, lihat parameter_mapper.py)."""

    def __init__(self, cycle_seconds: float = 4.0, midpoint: float = 0.5, amplitude: float = 0.5):
        self._cycle_seconds = cycle_seconds
        self._midpoint = midpoint
        self._amplitude = amplitude
        self._start_time = time.monotonic()

    def current_value(self) -> float:
        elapsed = time.monotonic() - self._start_time
        phase = (elapsed / self._cycle_seconds) * 2 * math.pi
        return self._midpoint + (self._amplitude * math.sin(phase) / 2)

    def set_cycle_seconds(self, cycle_seconds: float) -> None:
        """Hook opsional untuk Behavior Engine (v0.6.5+) — belum dipanggil di v0.6.1."""
        self._cycle_seconds = max(0.5, cycle_seconds)