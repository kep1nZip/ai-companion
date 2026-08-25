import sys

from PySide6.QtWidgets import QApplication

from ai.companion import Companion
from config.settings import GEMINI_API_KEY
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

    companion = Companion(
        vision=vision,
        performance_tracker=performance_tracker,
    )

    logger.info("Companion backend ready. Model: {}", MODEL_NAME)

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