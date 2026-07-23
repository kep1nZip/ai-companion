import sys

from PySide6.QtWidgets import QApplication

from ai.companion import Companion
from ui.window import MainWindow
from ui.theme import DARK_STYLESHEET
from config.constants import APP_NAME, VERSION, MODEL_NAME
from config.logger import logger


def main() -> None:
    logger.info("GUI application starting. {} v{}", APP_NAME, VERSION)

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)

    companion = Companion()
    logger.info("Companion backend ready. Model: {}", MODEL_NAME)

    window = MainWindow(companion)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()