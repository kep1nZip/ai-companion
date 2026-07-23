from __future__ import annotations

from google import genai
from google.genai import types

from config.logger import logger


class GeminiResponseError(Exception):
    """Terjadi saat Gemini mengembalikan balasan kosong/tidak valid (mis. diblokir
    safety filter, atau tidak ada text part sama sekali)."""


class GeminiClient:
    def __init__(self, api_key: str, model_name: str, system_prompt: str):
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._config = types.GenerateContentConfig(
            system_instruction=system_prompt,
        )

    def send(self, contents: list[types.Content]) -> str:
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=self._config,
        )

        text = response.text

        if not text:
            finish_reason = None
            try:
                finish_reason = response.candidates[0].finish_reason
            except Exception:
                pass

            logger.error("Gemini mengembalikan balasan kosong. finish_reason={}", finish_reason)
            raise GeminiResponseError(
                f"Gemini tidak memberikan balasan teks (finish_reason={finish_reason})"
            )

        return text