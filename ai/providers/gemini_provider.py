from __future__ import annotations

import time
from typing import Optional

from google.genai import types
from google.genai.errors import ClientError, ServerError

from ai.gemini import GeminiClient, GeminiResponseError
from ai.providers.base import LanguageModelProvider, ProviderError, ProviderRateLimitError, ProviderResponseError
from config.logger import logger

# v2.6.1 — Reliability fix (dilaporkan Teacher: "google.genai.errors.
# ServerError: 503 UNAVAILABLE... high demand" sering muncul saat pakai
# Gemini). Root cause DIKONFIRMASI lewat audit: `ServerError` (5xx, transient
# — overload SEMENTARA di sisi Google, BUKAN bug di kode kita) SEBELUMNYA
# TIDAK DITANGKAP SAMA SEKALI di sini — cuma `ClientError` (4xx) dan
# `GeminiResponseError` yang diterjemahkan. Akibatnya `ServerError` mentah
# lolos ke atas, melewati `Companion.chat()`'s `except ProviderError` (baris
# ~275) begitu saja karena `ServerError` BUKAN subclass `ProviderError` —
# Teacher dapat traceback mentah alih-alih pesan error yang jelas.
_TRANSIENT_RETRY_ATTEMPTS = 3  # 1 percobaan awal + 2 retry
_TRANSIENT_RETRY_BACKOFF_SECONDS = 1.5  # bertambah linear tiap percobaan (1.5s, 3.0s)


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
    apa adanya di __init__.

    v2.2: `temperature` OPSIONAL ditambahkan HANYA supaya instance provider
    TERPISAH bisa dikonstruksi untuk Memory Extraction (temperature=0.0)
    tanpa memengaruhi instance chat utama (yang tetap tidak pernah mengisi
    parameter ini, persis seperti sebelum v2.2 — lihat GeminiClient)."""

    def __init__(self, api_key: str, model_name: str, system_prompt: str, temperature: Optional[float] = None):
        self._client = GeminiClient(
            api_key=api_key, model_name=model_name, system_prompt=system_prompt, temperature=temperature
        )

    def generate(self, contents: list[types.Content]) -> str:
        for attempt in range(1, _TRANSIENT_RETRY_ATTEMPTS + 1):
            try:
                return self._client.send(contents)
            except GeminiResponseError as e:
                raise ProviderResponseError(str(e)) from e
            except ClientError as e:
                if "429" in str(e):
                    raise ProviderRateLimitError(str(e)) from e
                raise ProviderError(str(e)) from e
            except ServerError as e:
                # v2.6.1: 5xx = masalah SEMENTARA di sisi Google (server
                # overload), BUKAN salah konfigurasi Teacher — retry singkat
                # ke provider yang SAMA (BUKAN silent fallback ke Local/
                # provider lain, itu tetap dilarang §5.1 v2.4) sebelum
                # menyerah dengan ProviderError yang jelas.
                if attempt < _TRANSIENT_RETRY_ATTEMPTS:
                    wait_seconds = _TRANSIENT_RETRY_BACKOFF_SECONDS * attempt
                    logger.warning(
                        "Gemini ServerError (percobaan {}/{}), retry dalam {}s: {}",
                        attempt, _TRANSIENT_RETRY_ATTEMPTS, wait_seconds, e,
                    )
                    time.sleep(wait_seconds)
                    continue
                logger.error("Gemini ServerError setelah {} percobaan, menyerah: {}", _TRANSIENT_RETRY_ATTEMPTS, e)
                raise ProviderError(f"Gemini sedang mengalami gangguan sementara (server error): {e}") from e