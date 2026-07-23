from __future__ import annotations

import re
import time

from google import genai
from google.genai import types
from httpx import ReadError, ConnectError, RemoteProtocolError

from config.logger import logger

_STAGE_DIRECTION_PATTERN = re.compile(r"\([^)]*\)")
_TRANSIENT_ERRORS = (ReadError, ConnectError, RemoteProtocolError)
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 1.0


def _strip_stage_directions(text: str) -> str:
    cleaned = _STAGE_DIRECTION_PATTERN.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class TextToSpeech:
    """Cuma menghasilkan audio dari teks (Gemini Native TTS). Tidak tahu playback."""

    SAMPLE_RATE = 24000
    SAMPLE_WIDTH = 2
    CHANNELS = 1

    def __init__(self, api_key: str, model_name: str, voice_name: str = "Kore"):
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._voice_name = voice_name

    def synthesize(self, text: str) -> bytes | None:
        speakable = _strip_stage_directions(text)

        if not speakable:
            logger.info("Tidak ada teks yang perlu diucapkan setelah dibersihkan dari stage direction.")
            return None

        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 2):
            try:
                logger.info("Generating TTS audio via {} (percobaan {})", self._model_name, attempt)
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=speakable,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice_name)
                            )
                        ),
                    ),
                )
                return response.candidates[0].content.parts[0].inline_data.data

            except _TRANSIENT_ERRORS as e:
                last_error = e
                logger.warning(
                    "Koneksi TTS terputus (percobaan {}/{}), mencoba lagi: {}",
                    attempt, _MAX_RETRIES + 1, e,
                )
                if attempt <= _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY_SECONDS)

        logger.exception("TTS gagal setelah {} percobaan: {}", _MAX_RETRIES + 1, last_error)
        raise last_error