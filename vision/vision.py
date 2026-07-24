from __future__ import annotations

from typing import Optional

from PIL import Image

from vision.screen_capture import ScreenCapture
from vision.image_analyzer import ImageAnalyzer
from vision.vision_context import VisionContext, parse_vision_context
from config.logger import logger


class Vision:
    """Public API Vision System. Satu-satunya titik masuk yang boleh dipanggil
    Companion untuk urusan visual (Vision Independence Policy) — Vision TIDAK
    PERNAH tahu Behavior/Avatar/Voice/GUI/Memory/PromptBuilder ada."""

    def __init__(self, screen_capture: ScreenCapture, image_analyzer: ImageAnalyzer, default_ttl: float = 30.0):
        self._screen_capture = screen_capture
        self._image_analyzer = image_analyzer
        self._default_ttl = default_ttl
        self._current_context: Optional[VisionContext] = None
        self._last_captured_image: Optional[Image.Image] = None

    def capture(self) -> Image.Image:
        """Manual capture SAJA (Capture Policy) — tidak ada polling/automatic capture."""
        logger.info("Capture Started")
        image = self._screen_capture.capture()
        self._last_captured_image = image
        logger.info("Capture Finished")
        return image

    def analyze(self, image: Optional[Image.Image] = None, source: str = "screen") -> Optional[VisionContext]:
        """Generic multimodal entrypoint (rekomendasi GPT #3): terima gambar APA
        PUN (screenshot sekarang; webcam/upload di masa depan tanpa ubah arsitektur),
        BUKAN analyze_screen(). Kalau image=None, analisis capture TERAKHIR (sesuai
        Public API spec: 'Vision.analyze() - Analyze current capture')."""
        target_image = image if image is not None else self._last_captured_image

        if target_image is None:
            logger.warning("Tidak ada gambar untuk dianalisis.")
            return None

        try:
            raw_text = self._image_analyzer.analyze(target_image)
            context = parse_vision_context(raw_text, source=source, ttl=self._default_ttl)
            self._current_context = context
            logger.info("Context Generated")
            return context
        except Exception as e:
            logger.warning("Vision analysis gagal, context dikosongkan: {}", e)
            self._current_context = None   # Error Handling Policy: Gemini failure -> Empty Vision Context
            return None

    def get_context(self) -> Optional[VisionContext]:
        """Reuse context yang masih fresh (TTL belum lewat) — Freshness Policy:
        'If context is still valid, Vision must reuse it. Do NOT capture again
        unnecessarily.' TIDAK memicu capture baru sama sekali."""
        if self._current_context is not None and self._current_context.is_fresh():
            logger.info("Context Reused")
            return self._current_context
        return None

    def refresh(self, source: str = "screen") -> Optional[VisionContext]:
        """Paksa capture + analyze baru. Kalau capture gagal, pertahankan context
        LAMA (Error Handling Policy: 'Capture failure -> Previous Vision Context')."""
        logger.info("Context Refreshed")
        try:
            image = self.capture()
        except Exception as e:
            logger.warning("Capture gagal, pakai context sebelumnya: {}", e)
            return self._current_context

        return self.analyze(image, source=source)