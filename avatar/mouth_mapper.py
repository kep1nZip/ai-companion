from __future__ import annotations


class MouthMapper:
    """Konversi amplitude ternormalisasi -> nilai logical MouthOpen (0.0-1.0).
    Tidak ada networking, tidak ada GUI, tidak tahu VTube Studio."""

    def __init__(self, silence_threshold: float = 0.05, gain: float = 1.4):
        self._silence_threshold = silence_threshold
        self._gain = gain

    def map(self, amplitude: float) -> float:
        if amplitude < self._silence_threshold:
            return 0.0

        value = amplitude * self._gain
        return max(0.0, min(1.0, value))