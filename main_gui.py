import sys

from PySide6.QtWidgets import QApplication

from ai.companion import Companion
from ai.providers.factory import build_language_provider, build_memory_provider
from config.settings import (
    GEMINI_API_KEY,
    LOCAL_PROVIDER_BASE_URL,
    LOCAL_PROVIDER_MODEL_NAME,
    VISION_PROVIDER,
)
from ui.window import MainWindow
from ui.theme import DARK_STYLESHEET
from config.constants import APP_NAME, VERSION
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
        vision_model_name = LOCAL_PROVIDER_MODEL_NAME
        logger.info("Vision Provider: LOCAL ({} @ {})", LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL)
    else:
        image_analyzer = GeminiImageAnalyzer(api_key=GEMINI_API_KEY, model_name=VISION_MODEL_NAME)
        vision_provider_name = "gemini"
        vision_model_name = VISION_MODEL_NAME
        logger.info("Vision Provider: GEMINI ({})", VISION_MODEL_NAME)

    # v2.4 Phase 2 — Runtime Observability: `model_name` ditambahkan di sini
    # (pola IDENTIK `provider_name` yang sudah ada sejak v2.3) supaya
    # Developer Dashboard bisa menampilkan "Vision Model" — SEBELUMNYA cuma
    # provider yang bisa diobservasi, model name-nya tidak pernah sampai ke
    # Vision sama sekali (Provider Map v2.4 Phase 0 §8).
    vision = Vision(
        screen_capture=MssScreenCapture(),
        image_analyzer=image_analyzer,
        default_ttl=VISION_DEFAULT_TTL,
        provider_name=vision_provider_name,
        model_name=vision_model_name,
    )

    performance_tracker = PerformanceTracker()

    # v2.4 Phase 1 — Configuration Cleanup: logic pemilihan provider (baca
    # AI_PROVIDER/MEMORY_PROVIDER, construct LocalProvider, dsb — SEBELUMNYA
    # inline di sini) sekarang dipusatkan di ai/providers/factory.py, supaya
    # main.py (CLI) bisa reuse PERSIS logic yang sama alih-alih diam-diam
    # selalu Gemini seperti sebelumnya (Provider Map v2.4 Phase 0 §7).
    # Behavior TIDAK BERUBAH SAMA SEKALI di jalur GUI ini — No Silent
    # Fallback (v2.0 §15) tetap berlaku persis seperti sebelumnya, cuma
    # baris if/else-nya sekarang tinggal di satu tempat.
    provider, ai_model_name = build_language_provider()
    memory_provider, memory_model_name = build_memory_provider()

    companion = Companion(
        vision=vision,
        performance_tracker=performance_tracker,
        provider=provider,
        memory_provider=memory_provider,
        ai_model_name=ai_model_name,
        memory_model_name=memory_model_name,
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