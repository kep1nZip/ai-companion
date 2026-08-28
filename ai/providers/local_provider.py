from __future__ import annotations

import requests

from google.genai import types

from ai.providers.base import LanguageModelProvider, ProviderError, ProviderRateLimitError, ProviderResponseError
from config.logger import logger


class LocalProvider(LanguageModelProvider):
    """Provider untuk local LLM server yang expose REST API bergaya OpenAI
    Chat Completions — cocok buat LM Studio (rekomendasi utama, lihat catatan
    di bawah), tapi juga jalan ke server lain yang kompatibel format sama
    (mis. text-generation-webui/oobabooga dengan OpenAI extension, koboldcpp
    mode OpenAI, dst) — TIDAK di-hardcode ke satu software tertentu, cukup
    ganti `base_url`.

    v2.0 §37/§39: runtime & model TIDAK di-hardcode di sini secara paksa,
    keduanya jadi parameter (`base_url`, `model_name`) — Teacher yang pilih
    lewat setup local server-nya sendiri, provider ini cuma bicara ke
    endpoint yang dikonfigurasi.

    ## Setup yang direkomendasikan (hasil riset utk RX 6600 8GB, Windows):
    1. Download LM Studio (https://lmstudio.ai) — otomatis pakai backend
       Vulkan di Windows untuk GPU AMD, TIDAK butuh ROCm sama sekali (RX 6600
       memang tidak masuk daftar resmi ROCm, jadi Vulkan adalah jalur paling
       stabil, bukan cuma alternatif).
    2. Di dalam LM Studio, download model GGUF — rekomendasi awal:
       "Qwen3.5-9B" quant Q4_K_M (muat penuh di 8GB VRAM, ~54-58 tok/s
       menurut beberapa benchmark komunitas 2026). Kalau kerasa berat/lambat,
       turun ke model 7B (mis. Mistral 7B / OpenHermes 2.5 Mistral 7B).
    3. Di tab "Developer" / "Local Server" LM Studio, klik "Start Server"
       (default: http://localhost:1234).
    4. `base_url` di sini default sudah cocok dengan default LM Studio —
       cuma perlu diganti `model_name` sesuai model yang di-load.

    Pilihan model final TETAP di tangan Teacher (v2.0 §38: Provider != Model)
    — belum diukur langsung di hardware Teacher sungguhan (v2.0 §50), jadi
    BELUM dijadikan default Companion (lihat main_gui.py) sampai Teacher
    coba sendiri dan konfirmasi kualitas+performanya oke."""

    def __init__(
        self,
        system_prompt: str,
        model_name: str,
        base_url: str = "http://localhost:1234/v1",
        timeout: float = 120.0,
    ):
        self._system_prompt = system_prompt
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def generate(self, contents: list[types.Content]) -> str:
        # Terjemahkan list[types.Content] (format Gemini SDK, role "user"/
        # "model") -> format OpenAI Chat ({"role": "user"/"assistant",
        # "content": text}) DI DALAM provider ini saja — Companion/
        # ContextBuilder/Conversation TIDAK perlu tahu/berubah sama sekali
        # (v2.0 §33/§47: kontrak bersama tetap list[types.Content]).
        messages = [{"role": "system", "content": self._system_prompt}]
        for content in contents:
            role = "assistant" if content.role == "model" else "user"
            text = content.parts[0].text if content.parts else ""
            messages.append({"role": role, "content": text})

        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                json={"model": self._model_name, "messages": messages},
                timeout=self._timeout,
            )
        except requests.exceptions.ConnectionError as e:
            raise ProviderError(
                "Tidak bisa terhubung ke local model server. Pastikan LM Studio "
                "(atau server lokal lain) sedang berjalan dan server-nya sudah "
                "di-start."
            ) from e
        except requests.exceptions.Timeout as e:
            raise ProviderError("Local model server tidak merespons (timeout).") from e
        except requests.exceptions.RequestException as e:
            raise ProviderError(str(e)) from e

        if response.status_code == 429:
            raise ProviderRateLimitError(f"Local model server rate limit: {response.text}")
        if response.status_code >= 400:
            raise ProviderError(f"Local model server error {response.status_code}: {response.text}")

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            logger.warning("Local provider: format respons tak terduga: {}", e)
            raise ProviderResponseError(f"Local model server mengembalikan format tak terduga: {e}") from e

        if not text:
            raise ProviderResponseError("Local model server mengembalikan balasan kosong.")

        return text