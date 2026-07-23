from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ai.companion import Companion, RateLimitError, CompanionError


class ChatWorker(QThread):
    """Jalanin companion.chat() di background thread supaya GUI tidak freeze."""

    result_ready = Signal(str)
    error_occurred = Signal(str, bool)  # (pesan, is_rate_limit)

    def __init__(self, companion: Companion, user_input: str):
        super().__init__()
        self._companion = companion
        self._user_input = user_input

    def run(self) -> None:
        try:
            reply = self._companion.chat(self._user_input)
            self.result_ready.emit(reply)

        except RateLimitError:
            self.error_occurred.emit(
                "(Dark Blue Dripping Halo) Maaf Teacher, Arona sedang lelah karena "
                "terlalu banyak berpikir... Tolong tunggu sebentar lagi ya...",
                True,
            )

        except CompanionError as e:
            self.error_occurred.emit(
                f"(Eh?) Ada masalah sistem, Teacher... Error: {e}", False
            )