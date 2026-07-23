from __future__ import annotations

import numpy as np
import sounddevice as sd

from config.logger import logger


class AudioPlayer:
    """Cuma memutar audio PCM. Tidak tahu Gemini, TTS, atau recording."""

    def play(self, pcm_data: bytes, samplerate: int, channels: int = 1) -> None:
        audio = np.frombuffer(pcm_data, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)

        logger.info("Playback started.")
        sd.play(audio, samplerate=samplerate)
        sd.wait()
        logger.info("Playback completed.")