from __future__ import annotations

import numpy as np
import sounddevice as sd

from config.logger import logger


class Recorder:
    """Cuma merekam audio mikrofon. Tidak tahu STT, Gemini, atau GUI."""

    def __init__(self, samplerate: int = 16000, channels: int = 1):
        self._samplerate = samplerate
        self._channels = channels
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    def start(self) -> None:
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self._samplerate,
            channels=self._channels,
            dtype="float32",
            callback=self._on_audio_chunk,
        )
        self._stream.start()
        logger.info("Recorder: recording started.")

    def _on_audio_chunk(self, indata, frames, time_info, status) -> None:
        if status:
            logger.warning("Recorder input status: {}", status)
        self._frames.append(indata.copy())

    def stop(self) -> tuple[np.ndarray, int]:
        if self._stream is None:
            return np.array([], dtype="float32"), self._samplerate

        self._stream.stop()
        self._stream.close()
        self._stream = None
        logger.info("Recorder: recording stopped.")

        if not self._frames:
            return np.array([], dtype="float32"), self._samplerate

        audio = np.concatenate(self._frames, axis=0).flatten()
        self._frames = []
        return audio, self._samplerate