import sys

from PySide6.QtWidgets import QApplication

from ai.companion import Companion
from ai.personality import load_prompts
from ai.prompt_builder import build_system_prompt
from ai.providers.gemini_provider import GeminiProvider
from ai.providers.local_provider import LocalProvider
from config.settings import GEMINI_API_KEY, AI_PROVIDER, LOCAL_PROVIDER_BASE_URL, LOCAL_PROVIDER_MODEL_NAME
from ui.window import MainWindow
from ui.theme import DARK_STYLESHEET
from config.constants import APP_NAME, VERSION, MODEL_NAME
from config.logger import logger

from vision.vision import Vision
from vision.screen_capture import MssScreenCapture
from vision.image_analyzer import ImageAnalyzer
from config.constants import VISION_MODEL_NAME, VISION_DEFAULT_TTL

from developer.performance_debug import PerformanceTracker
from developer.developer import DeveloperService

def main() -> None:
    logger.info("GUI application starting. {} v{}", APP_NAME, VERSION)

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)

    vision = Vision(
        screen_capture=MssScreenCapture(),
        image_analyzer=ImageAnalyzer(api_key=GEMINI_API_KEY, model_name=VISION_MODEL_NAME),
        default_ttl=VISION_DEFAULT_TTL,
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

    companion = Companion(
        vision=vision,
        performance_tracker=performance_tracker,
        provider=provider,
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