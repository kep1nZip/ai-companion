from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal

from ai.companion import Companion
from vision.vision_context import VisionContext


class VisionWorker(QThread):
    """Menjalankan Companion.capture_vision() di background thread — ini
    memicu screen capture + Gemini Vision analysis (network-bound, sama
    kelasnya dengan Companion.chat()), jadi tidak boleh dipanggil di GUI
    thread langsung. Tidak ada logic Vision di sini, cuma pass-through.

    Companion.capture_vision() -> Vision.refresh() SUDAH membungkus semua
    kegagalan (capture gagal maupun analysis gagal) secara internal dan
    tidak pernah raise — selalu return Optional[VisionContext]. try/except
    di sini murni defensif (pola sama dengan worker lain di project),
    bukan karena ada exception spesifik yang diharapkan."""

    result_ready = Signal(object)  # Optional[VisionContext]
    error_occurred = Signal(str)

    def __init__(self, companion: Companion):
        super().__init__()
        self._companion = companion

    def run(self) -> None:
        try:
            context: Optional[VisionContext] = self._companion.capture_vision()
            self.result_ready.emit(context)
        except Exception:
            self.error_occurred.emit("Vision capture failed. Please try again.")