from __future__ import annotations

import numpy as np

from config.logger import logger


class AudioAnalyzer:
    """Cuma membaca audio PCM 16-bit mono dan menghasilkan amplitude ternormalisasi (RMS).
    Tidak tahu avatar, tidak tahu websocket, tidak ada AI/ML apa pun — RMS sederhana."""

    def __init__(self, window_ms: int = 50):
        self._window_ms = window_ms

    def analyze(self, pcm_data: bytes, samplerate: int) -> tuple[list[float], float]:
        """Return (list amplitude 0.0-1.0 per window, durasi tiap window dalam detik).
        Tidak membaca ulang PCM yang sama dua kali — satu pass numpy saja."""
        audio = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0

        window_size = max(1, int(samplerate * self._window_ms / 1000))
        num_windows = max(1, len(audio) // window_size)

        raw_rms: list[float] = []
        peak = 1e-6

        for i in range(num_windows):
            chunk = audio[i * window_size: (i + 1) * window_size]
            if chunk.size == 0:
                continue
            rms = float(np.sqrt(np.mean(np.square(chunk))))
            raw_rms.append(rms)
            peak = max(peak, rms)

        amplitudes = [min(1.0, rms / peak) for rms in raw_rms]
        window_seconds = window_size / samplerate

        logger.info("Amplitude Calculated: {} window, {:.3f}s/window", len(amplitudes), window_seconds)
        return amplitudes, window_seconds