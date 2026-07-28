from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSnapshot:
    name: str
    last_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    count: int


class PerformanceTracker:
    """Pencatat waktu eksekusi. Modul lain (Companion) MENULIS lewat record()/
    timer(); Developer Tools cuma MEMBACA lewat snapshot() — tidak pernah menulis."""

    def __init__(self, window_size: int = 50):
        self._window_size = window_size
        self._data: dict[str, deque] = {}
        self._lock = threading.Lock()

    def record(self, name: str, duration_ms: float) -> None:
        with self._lock:
            if name not in self._data:
                self._data[name] = deque(maxlen=self._window_size)
            self._data[name].append(duration_ms)

    def snapshot(self) -> dict[str, MetricSnapshot]:
        with self._lock:
            result = {}
            for name, values in self._data.items():
                if not values:
                    continue
                result[name] = MetricSnapshot(
                    name=name, last_ms=values[-1], avg_ms=statistics.fmean(values),
                    min_ms=min(values), max_ms=max(values), count=len(values),
                )
            return result

    def timer(self, name: str) -> "_Timer":
        return _Timer(self, name)


class _Timer:
    """Context manager kecil: `with tracker.timer('gemini'): ...`"""

    def __init__(self, tracker: PerformanceTracker, name: str):
        self._tracker = tracker
        self._name = name
        self._start = 0.0

    def __enter__(self) -> "_Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self._tracker.record(self._name, elapsed_ms)