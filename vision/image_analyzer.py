from __future__ import annotations

import io

from PIL import Image
from google import genai
from google.genai import types

from config.logger import logger

_VISION_PROMPT = (
    "Describe what is currently visible in this image, in natural language, "
    "in Indonesian. On the first line, write 'Application: ' followed by the "
    "name of the active application/window if identifiable (or 'Unknown' if not). "
    "Then on the following lines, write 'Summary: ' followed by a short natural "
    "description of what appears to be happening."
)


class VisionAnalysisError(Exception):
    """Terjadi saat Gemini Vision mengembalikan respons kosong/tidak valid —
    pola sama dengan GeminiResponseError (gemini.py) dan CompanionError
    (companion.py), sesuai CODE_STYLE §7."""


class ImageAnalyzer:
    """Cuma mengirim gambar ke Gemini Vision dan menerima deskripsi natural
    language. TIDAK membangun prompt akhir, TIDAK tahu behavior/memory/GUI."""

    def __init__(self, api_key: str, model_name: str):
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def analyze(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    types.Part(text=_VISION_PROMPT),
                ],
            )
        ]

        logger.info("Vision Request")
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
        )
        logger.info("Vision Response")

        text = response.text
        if not text:
            raise VisionAnalysisError("Gemini Vision mengembalikan respons kosong.")
        return text