from __future__ import annotations

import io
from abc import ABC, abstractmethod

from PIL import Image
from google import genai
from google.genai import types

from config.logger import logger

VISION_PROMPT = (
    "Describe what is currently visible in this image, in natural language, "
    "in Indonesian. On the first line, write 'Application: ' followed by the "
    "name of the active application/window if identifiable (or 'Unknown' if not). "
    "Then on the following lines, write 'Summary: ' followed by a short natural "
    "description of what appears to be happening."
)
# v2.3: nama publik (tanpa underscore) SEJAK MILESTONE INI — sebelumnya privat
# karena cuma dipakai di file ini sendiri. Sekarang diimpor juga oleh
# vision/local_image_analyzer.py (§11: "Menggunakan prompt Vision yang sudah
# ada apabila masih kompatibel" — BUKAN menduplikasi isinya, mengimpor
# konstanta yang sama persis). Pola identik dengan `EXTRACTION_SYSTEM_PROMPT`
# di ai/memory_extractor.py (v2.2, alasan sama).


class VisionAnalysisError(Exception):
    """Terjadi saat provider Vision (Gemini ATAU Local — v2.3) mengembalikan
    respons kosong/tidak valid — pola sama dengan GeminiResponseError
    (gemini.py) dan CompanionError (companion.py), sesuai CODE_STYLE §7.

    v2.3: exception ini SENGAJA dipakai bersama oleh GeminiImageAnalyzer dan
    LocalImageAnalyzer (bukan dipisah per-provider) — supaya Vision.analyze()
    (vision/vision.py) TIDAK PERNAH perlu tahu provider mana yang gagal, cuma
    "analisis gagal, context dikosongkan" (§12 Phase 3: tidak boleh ada
    `if provider == local` di banyak tempat)."""


class ImageAnalyzer(ABC):
    """Boundary provider Vision (v2.3 Phase 1, §10) — pola IDENTIK dengan
    `ScreenCapture` (vision/screen_capture.py): ABC generik + implementasi
    konkret per backend (`MssScreenCapture` di sana, `GeminiImageAnalyzer`/
    `LocalImageAnalyzer` di sini). `Vision` (vision/vision.py) HANYA kenal
    tipe ABSTRAK ini — TIDAK PERNAH tahu implementasi konkretnya Gemini atau
    Local (Vision Independence Policy tetap utuh, sekarang juga
    Provider-Independence).

    v2.3 §10 eksplisit melarang membuat abstraksi kedua yang tumpang tindih
    dengan `LanguageModelProvider` (ai/providers/base.py) KECUALI abstraksi
    itu tidak bisa dipakai bersih untuk multimodal — dan itu persis yang
    terjadi di sini: `LocalProvider.generate()` (ai/providers/local_provider.py)
    membangun payload OpenAI Chat Completions dengan `content` berupa STRING
    POLOS (`content.parts[0].text`), tidak pernah menangani `Part.from_bytes`
    (gambar) — mengirim gambar lewat situ akan diam-diam jadi string kosong,
    bukan gagal dengan jelas. Vision Independence Policy juga sudah berlaku
    sejak v0.7 (Vision TIDAK PERNAH impor apa pun dari `ai/`) — jadi boundary
    terpisah ini bukan duplikasi, tapi kelanjutan pola yang memang sudah ada."""

    @abstractmethod
    def analyze(self, image: Image.Image) -> str:
        """Kirim `image`, kembalikan deskripsi natural language (BUKAN JSON —
        Image Analysis Policy tetap berlaku, lihat vision_context.py). Harus
        melempar VisionAnalysisError (atau membiarkan exception provider
        aslinya menjalar) kalau gagal — TIDAK PERNAH mengembalikan string
        kosong secara diam-diam untuk menandakan kegagalan (Observability,
        §19: "jangan menelan error sampai hasilnya tidak dapat dibedakan
        antara 'no useful visual information' dan 'provider failure'")."""
        ...


class GeminiImageAnalyzer(ImageAnalyzer):
    """v2.3: RENAME MURNI dari `ImageAnalyzer` (v0.7-v2.2) — badan method,
    logic, dan perilaku TIDAK BERUBAH SATU BARIS PUN, cuma nama class +
    `(ImageAnalyzer)` sebagai induk ABC (pola sama dengan `MssScreenCapture`
    di screen_capture.py). Satu-satunya pemanggil yang perlu tahu nama baru
    ini adalah main_gui.py (yang memang perlu diedit untuk pemilihan
    provider Vision — bukan blast radius tambahan di luar itu)."""

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
                    types.Part(text=VISION_PROMPT),
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