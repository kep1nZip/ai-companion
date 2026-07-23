from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel

from config.logger import logger


class SpeechToText:
    """Cuma mengubah audio jadi teks. Tidak tahu GUI atau Gemini."""

    def __init__(self, model_size: str, device: str = "cpu", compute_type: str = "int8"):
        logger.info("Loading Faster Whisper model: {}", model_size)
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray, samplerate: int) -> str:
        if audio.size == 0:
            return ""

        segments, _ = self._model.transcribe(audio, language=None, beam_size=1)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text