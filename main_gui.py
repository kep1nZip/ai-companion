import sys

from PySide6.QtWidgets import QApplication

from ai.companion import Companion
from ai.personality import load_prompts
from ai.prompt_builder import build_system_prompt
from ai.providers.gemini_provider import GeminiProvider
from ai.providers.local_provider import LocalProvider
from ai.memory_extractor import EXTRACTION_SYSTEM_PROMPT
from config.settings import (
    GEMINI_API_KEY,
    AI_PROVIDER,
    LOCAL_PROVIDER_BASE_URL,
    LOCAL_PROVIDER_MODEL_NAME,
    MEMORY_PROVIDER,
    VISION_PROVIDER,
)
from ui.window import MainWindow
from ui.theme import DARK_STYLESHEET
from config.constants import APP_NAME, VERSION, MODEL_NAME
from config.logger import logger

from vision.vision import Vision
from vision.screen_capture import MssScreenCapture
from vision.image_analyzer import GeminiImageAnalyzer
from vision.local_image_analyzer import LocalImageAnalyzer
from config.constants import VISION_MODEL_NAME, VISION_DEFAULT_TTL

from developer.performance_debug import PerformanceTracker
from developer.developer import DeveloperService

def main() -> None:
    logger.info("GUI application starting. {} v{}", APP_NAME, VERSION)

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)

    # v2.3 — Local Vision Provider Selection. KEPUTUSAN TERPISAH dari
    # AI_PROVIDER/MEMORY_PROVIDER di bawah (§6) — blok if/else sendiri,
    # BUKAN mengikuti pilihan Language/Memory Provider. `base_url`/
    # `model_name` SENGAJA reuse LOCAL_PROVIDER_* yang sama (§7/§20: tidak
    # membuat server LM Studio kedua otomatis — Vision Local, kalau aktif,
    # bicara ke server & model YANG SAMA dengan chat/memory Local). TIDAK
    # ADA try/except yang diam-diam fallback ke Gemini di sini (No Silent
    # Fallback, §11/§25 poin 6) — kalau Local Vision gagal saat runtime,
    # errornya menjalar natural lewat Vision.analyze()'s existing except
    # Exception (vision/vision.py, TIDAK DIUBAH — context jadi None +
    # log warning, sama seperti kegagalan Gemini Vision selama ini),
    # BUKAN diam-diam beralih ke provider lain.
    if VISION_PROVIDER == "local":
        image_analyzer = LocalImageAnalyzer(
            base_url=LOCAL_PROVIDER_BASE_URL,
            model_name=LOCAL_PROVIDER_MODEL_NAME,
        )
        vision_provider_name = "local"
        logger.info("Vision Provider: LOCAL ({} @ {})", LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL)
    else:
        image_analyzer = GeminiImageAnalyzer(api_key=GEMINI_API_KEY, model_name=VISION_MODEL_NAME)
        vision_provider_name = "gemini"
        logger.info("Vision Provider: GEMINI ({})", VISION_MODEL_NAME)

    vision = Vision(
        screen_capture=MssScreenCapture(),
        image_analyzer=image_analyzer,
        default_ttl=VISION_DEFAULT_TTL,
        provider_name=vision_provider_name,
    )

    performance_tracker = PerformanceTracker()

    # v2.0 Step 9 — Provider Selection & Default Decision. Default SEKARANG
    # "local" (config/settings.py) — diputuskan resmi setelah Step 7 Full
    # Regression selesai & diterima Teacher, bukan cuma karena gratis. Gemini
    # TIDAK dihapus — override AI_PROVIDER=gemini di .env kalau mau pakai itu.
    # System prompt dibangun sekali di sini lewat pipeline yang SAMA
    # (load_prompts + build_system_prompt) yang dipakai Companion untuk
    # provider default-nya sendiri — tidak ada logic persona kedua.
    #
    # TIDAK ADA try/except di sini yang menangkap kegagalan provider lalu
    # diam-diam ganti ke provider lain (No Silent Fallback, spec v2.0 Step 9
    # §15) — kalau Local/Gemini gagal, errornya muncul natural lewat
    # Companion.chat()/check_autonomous_opportunity() (ProviderError ->
    # CompanionError) ke GUI, BUKAN di-tangani diam-diam di sini.
    if AI_PROVIDER == "local":
        prompts = load_prompts()
        system_prompt = build_system_prompt(prompts)
        provider = LocalProvider(
            system_prompt=system_prompt,
            model_name=LOCAL_PROVIDER_MODEL_NAME,
            base_url=LOCAL_PROVIDER_BASE_URL,
        )
        logger.info("AI Provider: LOCAL ({} @ {})", LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL)
    else:
        provider = None  # Companion akan membuat GeminiProvider default-nya sendiri
        logger.info("AI Provider: GEMINI ({})", MODEL_NAME)

    # v2.2 — Local Memory Extraction Provider Selection. KEPUTUSAN TERPISAH
    # dari AI_PROVIDER di atas (§27) — sengaja dua blok if/else yang berdiri
    # sendiri, BUKAN "kalau AI_PROVIDER local maka MEMORY_PROVIDER ikut
    # local". `system_prompt` di sini adalah EXTRACTION_SYSTEM_PROMPT (dari
    # ai/memory_extractor.py, TIDAK diubah sedikit pun) — BUKAN system_prompt
    # chat di atas. `base_url`/`model_name` SENGAJA reuse LOCAL_PROVIDER_*
    # yang sama dengan chat (§20/§30: implementasi pertama TIDAK membuat
    # server LM Studio kedua secara otomatis — Memory Local & Chat Local,
    # kalau dua-duanya aktif, bicara ke server & model YANG SAMA).
    # temperature/frequency_penalty/presence_penalty = 0.0 (BUKAN default
    # 0.85/0.4/0.4 milik `provider` chat di atas) — §13: ekstraksi memori
    # butuh deterministic & conservative, BUKAN kreatif. TIDAK ADA try/except
    # yang diam-diam fallback ke Gemini di sini juga (No Silent Fallback,
    # sama seperti AI_PROVIDER di atas) — kalau Local Memory gagal jalan,
    # errornya muncul natural lewat MemoryExtractionWorker (sudah menangkap
    # & mencatatnya per task, v2.1) TANPA mengganti provider diam-diam.
    if MEMORY_PROVIDER == "local":
        memory_provider = LocalProvider(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            model_name=LOCAL_PROVIDER_MODEL_NAME,
            base_url=LOCAL_PROVIDER_BASE_URL,
            temperature=0.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )
        logger.info(
            "Memory Extraction Provider: LOCAL ({} @ {})", LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL
        )
    else:
        memory_provider = None  # Companion akan membuat GeminiProvider extraction default-nya sendiri
        logger.info("Memory Extraction Provider: GEMINI ({})", MODEL_NAME)

    companion = Companion(
        vision=vision,
        performance_tracker=performance_tracker,
        provider=provider,
        memory_provider=memory_provider,
    )

    logger.info("Companion backend ready.")

    # v1.5.2: `vision` diteruskan LANGSUNG ke MainWindow (bukan cuma lewat
    # Companion) supaya VisionPage bisa memanggil vision.set_mode()/
    # get_mode() untuk kontrol OFF/MANUAL/AUTO (spec §4: "Vision GUI ->
    # Vision Service" langsung) TANPA menyentuh ai/companion.py yang beku
    # (Architecture Freeze Policy) — ini instance Vision yang SAMA persis
    # dengan yang dipakai Companion di atas, tidak ada instance kedua.
    window = MainWindow(companion, vision, performance_tracker=performance_tracker)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()