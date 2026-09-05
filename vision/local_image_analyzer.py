from __future__ import annotations

import base64
import io

import requests
from PIL import Image

from ai.providers.base import ProviderError, ProviderRateLimitError, ProviderResponseError
from vision.image_analyzer import ImageAnalyzer, VisionAnalysisError, VISION_PROMPT
from config.logger import logger


class LocalImageAnalyzer(ImageAnalyzer):
    """Local Vision (v2.3) — kirim gambar ke server local yang expose REST
    API bergaya OpenAI Chat Completions dengan dukungan input gambar
    (`image_url` dengan data URI base64), format yang dipakai LM Studio untuk
    model VLM (mis. `qwen/qwen3-vl-8b` — nama vl = vision-language, memang
    multimodal, BUKAN diasumsikan dari nama semata: lihat Model Compatibility
    Check di bawah).

    v2.3 §7/§8: SENGAJA reuse `LOCAL_PROVIDER_BASE_URL`/
    `LOCAL_PROVIDER_MODEL_NAME` yang SAMA dengan chat & Memory Extraction
    Local (bukan `LOCAL_VISION_BASE_URL`/`LOCAL_VISION_MODEL_NAME` baru) —
    `base_url`/`model_name` di sini diterima sebagai parameter dari
    pemanggil (main_gui.py), class ini sendiri TIDAK membaca config apa pun
    secara langsung, konsisten dengan `LocalProvider`.

    ## Model Compatibility Check (v2.3 §8)
    Class ini TIDAK memvalidasi/menebak kemampuan model dari namanya
    (`.endswith("-vl")` atau semacamnya) — kalau model yang di-load di
    LM Studio TERNYATA text-only, server akan menolak/mengembalikan error
    untuk request bergambar, dan itu akan menjalar sebagai
    ProviderError/VisionAnalysisError APA ADANYA (bukan ditelan diam-diam,
    bukan di-downgrade jadi "tidak ada info visual" — §19 Observability).
    Teacher yang bertanggung jawab memastikan model yang di-load memang
    mendukung gambar, sama seperti Teacher bertanggung jawab memilih model
    yang cocok untuk chat (Provider != Model, v2.0 §38).

    ## Kenapa bukan lewat LanguageModelProvider/LocalProvider
    Lihat docstring panjang `ImageAnalyzer` (vision/image_analyzer.py) —
    `LocalProvider.generate()` membangun `content` sebagai STRING POLOS,
    tidak pernah menangani part gambar. Class ini jalur TERPISAH yang
    membangun payload multimodal OpenAI (`content` sebagai LIST blok
    `text`/`image_url`) secara eksplisit, alih-alih memaksa
    `LanguageModelProvider.generate(list[types.Content])` menangani bentuk
    yang tidak pernah dirancang untuknya.

    ## Prompt
    Memakai `VISION_PROMPT` yang SAMA PERSIS dengan GeminiImageAnalyzer
    (diimpor langsung dari vision/image_analyzer.py, TIDAK diduplikasi/
    ditulis ulang) — v2.3 §22 "No New Prompt Files" & §11 "Menggunakan
    prompt Vision yang sudah ada apabila masih kompatibel". Format
    Application/Summary yang diminta prompt ini adalah teks natural biasa,
    tidak butuh kemampuan JSON-mode apa pun, jadi kompatibel untuk model apa
    saja yang bisa mengikuti instruksi sederhana.

    ## SAFETY: max_dimension (ditambahkan setelah temuan Teacher)
    Test v2.3 (`test_vision_quality_validation.py`, E02 — gambar 4K
    3840x2160) SEMPAT membuat GPU Teacher (AMD, backend Vulkan di LM
    Studio) mengalami "device lost"/driver timeout SUNGGUHAN di level OS —
    bukan sekadar error API yang bersih. Root cause pastinya (bug driver
    Vulkan AMD spesifik, batas VRAM, atau batas jumlah vision token yang
    tidak tertangani baik di backend mtmd llama.cpp) tidak bisa dipastikan
    dari sini — tapi SIAPA PUN penyebab pastinya, mengirim gambar
    beresolusi sangat besar ke inference engine Local TERBUKTI berisiko
    men-crash GPU, bukan cuma soal lambat/boros token.

    Ini beda dengan `GeminiImageAnalyzer` yang mengirim resolusi PENUH
    tanpa masalah (server Gemini yang menangani, bukan hardware Teacher
    sendiri) — jadi cuma `LocalImageAnalyzer` yang butuh mitigasi ini,
    `GeminiImageAnalyzer` SENGAJA TIDAK diubah. `max_dimension` (default
    1280px sisi terpanjang, mempertahankan aspect ratio) diterapkan
    SEBELUM encoding ke base64 — nilai ini KONSERVATIF, belum tentu batas
    aman pasti untuk semua kombinasi GPU/driver/model, Teacher mungkin
    perlu menurunkannya lebih jauh lewat parameter constructor ini kalau
    crash masih terjadi di resolusi 1280px sekalipun."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout: float = 120.0,
        max_dimension: int = 1280,
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout = timeout
        self._max_dimension = max_dimension

    def _resize_for_safety(self, image: Image.Image) -> Image.Image:
        """Turunkan resolusi SEBELUM dikirim ke Local, mempertahankan aspect
        ratio, TIDAK PERNAH memperbesar gambar yang sudah kecil (thumbnail()
        cuma mengecilkan, tidak pernah membesarkan). Lihat catatan panjang
        "SAFETY: max_dimension" di docstring class ini untuk alasan
        lengkapnya."""
        if image.width <= self._max_dimension and image.height <= self._max_dimension:
            return image
        resized = image.copy()
        resized.thumbnail((self._max_dimension, self._max_dimension), Image.LANCZOS)
        logger.info(
            "Local Vision: gambar diperkecil dari {}x{} ke {}x{} sebelum dikirim (safety cap, lihat LocalImageAnalyzer docstring).",
            image.width, image.height, resized.width, resized.height,
        )
        return resized

    def analyze(self, image: Image.Image) -> str:
        image = self._resize_for_safety(image)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

        payload = {
            "model": self._model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
            # v2.3: temperature TIDAK diset (beda dengan LocalProvider chat
            # yang default 0.85 kreatif) — deskripsi visual harus konsisten
            # menggambarkan APA YANG ADA di layar, bukan variasi kreatif;
            # dibiarkan default server (mirip GeminiImageAnalyzer yang juga
            # tidak set temperature eksplisit untuk Vision, lihat
            # GenerateContentConfig di gemini.py — tidak ada preseden
            # temperature=0 khusus Vision untuk ditiru di sana).
        }

        logger.info("Vision Request (local)")
        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                timeout=self._timeout,
            )
        except requests.exceptions.ConnectionError as e:
            raise ProviderError(
                "Tidak bisa terhubung ke local model server untuk Vision. "
                "Pastikan LM Studio sedang berjalan dan model yang di-load "
                "mendukung input gambar."
            ) from e
        except requests.exceptions.Timeout as e:
            raise ProviderError("Local model server tidak merespons (timeout) saat analisis gambar.") from e
        except requests.exceptions.RequestException as e:
            raise ProviderError(str(e)) from e

        if response.status_code == 429:
            raise ProviderRateLimitError(f"Local model server rate limit: {response.text}")
        if response.status_code >= 400:
            # v2.3: TIDAK di-downgrade jadi "tidak ada info visual" (§19) —
            # kalau model yang di-load tidak mendukung gambar, server
            # biasanya menolak di titik ini dengan error jelas, dan itu HARUS
            # sampai ke Teacher sebagai error, bukan context kosong yang
            # terlihat sama dengan "layar memang tidak ada apa-apa".
            raise ProviderError(f"Local model server error {response.status_code}: {response.text}")

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            logger.warning("Local Vision: format respons tak terduga: {}", e)
            raise ProviderResponseError(f"Local model server mengembalikan format tak terduga: {e}") from e

        logger.info("Vision Response (local)")

        if not text:
            raise VisionAnalysisError("Local Vision mengembalikan respons kosong.")
        return text