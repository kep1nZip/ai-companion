from __future__ import annotations

from google.genai import types
from google.genai.errors import ClientError

from ai.gemini import GeminiClient, GeminiResponseError
from ai.providers.base import LanguageModelProvider, ProviderError, ProviderRateLimitError, ProviderResponseError


class GeminiProvider(LanguageModelProvider):
    """Adapter tipis di atas GeminiClient (ai/gemini.py) yang SUDAH ADA sejak
    v0.1 — TIDAK DITULIS ULANG sama sekali (v2.0 §36: "Existing Gemini
    behavior should be wrapped/adapted rather than rewritten unnecessarily").
    Satu-satunya pekerjaan kelas ini: menerjemahkan exception SPESIFIK Gemini
    (GeminiResponseError, google.genai.errors.ClientError, termasuk deteksi
    "429" di pesan error-nya — logic yang SEBELUMNYA ada di Companion, pindah
    ke sini karena itu memang tanggung jawab provider, bukan Companion, per
    v2.0 §34) menjadi exception provider-agnostic (ProviderResponseError/
    ProviderRateLimitError/ProviderError) yang Companion pahami.

    System prompt, konfigurasi model, dan seluruh perilaku generate SAMA
    PERSIS dengan sebelumnya — dipertahankan lewat GeminiClient yang di-reuse
    apa adanya di __init__."""

    def __init__(self, api_key: str, model_name: str, system_prompt: str):
        self._client = GeminiClient(api_key=api_key, model_name=model_name, system_prompt=system_prompt)

    def generate(self, contents: list[types.Content]) -> str:
        try:
            return self._client.send(contents)
        except GeminiResponseError as e:
            raise ProviderResponseError(str(e)) from e
        except ClientError as e:
            if "429" in str(e):
                raise ProviderRateLimitError(str(e)) from e
            raise ProviderError(str(e)) from e