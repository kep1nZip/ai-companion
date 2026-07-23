from __future__ import annotations

import json

from google import genai
from google.genai import types

from config.logger import logger

_EXTRACTION_SYSTEM_PROMPT = """
Kamu adalah sistem ekstraksi memori jangka panjang untuk AI companion bernama Arona.

Tugasmu: baca satu pesan dari Teacher (user), lalu tentukan apakah pesan itu berisi
fakta jangka panjang yang layak diingat tentang Teacher (preferensi, identitas, relasi,
project, jadwal, atau fakta umum penting).

JANGAN simpan basa-basi, sapaan, ucapan terima kasih, atau obrolan sesaat
(contoh: "halo", "selamat pagi", "haha", "makasih", "jam berapa sekarang").

Kategori yang valid HANYA: preference, relationship, identity, project, schedule, general.

Balas HANYA dengan JSON array, tanpa teks lain, tanpa markdown code fence.
Format setiap item: {"category": "...", "content": "..."}
Jika tidak ada yang layak diingat, balas dengan array kosong: []
"""


class MemoryExtractor:
    """Decision layer: menentukan apakah sebuah pesan layak jadi memori jangka panjang.
    Pakai Gemini call terpisah & ringan, bukan RAG/vector DB, bukan if-statement bertumpuk."""

    def __init__(self, api_key: str, model_name: str):
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._config = types.GenerateContentConfig(
            system_instruction=_EXTRACTION_SYSTEM_PROMPT,
            temperature=0.0,
        )

    def extract(self, user_input: str) -> list[dict]:
        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=user_input)])],
                config=self._config,
            )
            raw = (response.text or "").strip()
            facts = json.loads(raw)

            if not isinstance(facts, list):
                return []

            cleaned = []
            for fact in facts:
                if isinstance(fact, dict) and "category" in fact and "content" in fact:
                    cleaned.append({"category": str(fact["category"]), "content": str(fact["content"])})
            return cleaned

        except Exception as e:
            logger.warning("Ekstraksi memori gagal, diabaikan dengan aman: {}", e)
            return []