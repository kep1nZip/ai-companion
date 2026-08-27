from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ai.companion import Companion
from config.logger import logger


class AutonomousWorker(QThread):
    """v1.8 — menjalankan Companion.check_autonomous_opportunity() di
    background thread, persis pola ChatWorker (GUI TIDAK PERNAH memanggil
    Companion langsung di main thread). Kegagalan (Gemini error/rate limit)
    SENGAJA tidak ditampilkan ke Teacher (spec §30: log, tetap diam, tunggu
    kesempatan berikutnya) — cuma di-log, tidak ada Signal error yang
    memunculkan bubble chat."""

    result_ready = Signal(str)  # "" berarti Arona tetap diam (hasil valid)

    def __init__(self, companion: Companion, is_voice_active: bool, is_actively_typing: bool):
        super().__init__()
        self._companion = companion
        self._is_voice_active = is_voice_active
        self._is_actively_typing = is_actively_typing

    def run(self) -> None:
        try:
            reply = self._companion.check_autonomous_opportunity(
                is_voice_active=self._is_voice_active,
                is_actively_typing=self._is_actively_typing,
            )
            self.result_ready.emit(reply or "")
        except Exception as e:
            logger.warning("Autonomous check gagal total, tetap diam: {}", e)
            self.result_ready.emit("")