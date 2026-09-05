from __future__ import annotations

import threading
from typing import Optional

from PIL import Image

from vision.screen_capture import ScreenCapture
from vision.image_analyzer import ImageAnalyzer
from vision.vision_context import VisionContext, parse_vision_context
from vision.vision_mode import VisionMode
from vision.auto_scheduler import VisionAutoScheduler
from config.constants import VISION_AUTO_INTERVAL
from config.logger import logger


class Vision:
    """Public API Vision System. Satu-satunya titik masuk yang boleh dipanggil
    Companion untuk urusan visual (Vision Independence Policy) — Vision TIDAK
    PERNAH tahu Behavior/Avatar/Voice/GUI/Memory/PromptBuilder ada.

    v1.5.2: Vision sekarang memiliki mode lifecycle sendiri (OFF/MANUAL/AUTO,
    spec §6-7) alih-alih ON/OFF yang murni GUI-side seperti v1.5.1. Ini
    menyelesaikan known limitation v1.5.1: dulu toggle OFF di GUI tidak
    menghapus VisionContext lama yang masih fresh, jadi chat() masih bisa
    memakainya lewat get_context(). Sekarang OFF adalah state BACKEND —
    get_context() mengembalikan None secara eksplisit saat mode OFF, dan
    context lama langsung dibuang (bukan cuma dibiarkan kadaluarsa oleh TTL).

    Auto Vision (mode AUTO) menyalakan satu VisionAutoScheduler internal yang
    memanggil refresh_if_needed() secara berkala — scheduler TIDAK PERNAH
    membuat instance Vision/ScreenCapture/ImageAnalyzer baru (spec §16), dan
    TIDAK PERNAH memanggil apa pun di luar Vision Public API (khususnya
    TIDAK PERNAH Companion.chat() — Auto Vision Independence dari Autonomous
    Chat, spec §24)."""

    def __init__(self, screen_capture: ScreenCapture, image_analyzer: ImageAnalyzer, default_ttl: float = 30.0,
                 provider_name: str = "gemini"):
        self._screen_capture = screen_capture
        self._image_analyzer = image_analyzer
        self._default_ttl = default_ttl
        # v2.3 §18: MURNI label observability untuk Developer Dashboard —
        # TIDAK memengaruhi analyze()/refresh() sama sekali (image_analyzer
        # yang disuntik sudah menentukan provider mana yang SUNGGUHAN
        # dipakai). Pola sama dengan Companion._memory_provider_name (v2.2)
        # — dicatat eksplisit saat construction, BUKAN ditebak lewat
        # type(self._image_analyzer).__name__ (§18: Dashboard membaca label
        # yang eksplisit diset, tidak melakukan introspeksi/pemanggilan apa
        # pun ke VisionAnalyzer — "Eyes, not hands").
        self._provider_name = provider_name
        self._current_context: Optional[VisionContext] = None
        self._last_captured_image: Optional[Image.Image] = None

        # v1.5.2: default startup mode HARUS OFF (Default Privacy Policy §7)
        # — Auto Vision melakukan screen capture otomatis, jadi Teacher wajib
        # opt-in eksplisit tiap sesi, tidak pernah persist sebagai AUTO.
        self._mode: VisionMode = VisionMode.OFF

        # _state_lock melindungi _mode dan baca/tulis _current_context —
        # dipegang SINGKAT saja (spec §50: "Do not hold a lock longer than
        # needed", "Do not block get_context() unnecessarily during a
        # network request"). _capture_lock men-serialisasi kerja capture+
        # analyze itu sendiri (network-bound) supaya Manual Capture dan Auto
        # Scheduler tidak pernah menjalankan dua request Gemini bersamaan
        # (spec §17).
        self._state_lock = threading.Lock()
        self._capture_lock = threading.Lock()

        self._auto_scheduler: Optional[VisionAutoScheduler] = None

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
            with self._state_lock:
                # v1.5.2 Context Clear Policy §21: kalau mode berubah jadi
                # OFF SELAGI network call ini masih berjalan (race antara
                # analyze() network-bound dan Teacher menekan OFF), context
                # yang baru selesai dianalisis TIDAK BOLEH menyelinap masuk
                # setelah OFF — dibuang, bukan disimpan.
                if self._mode == VisionMode.OFF:
                    logger.info("Vision OFF saat analisis selesai — context dibuang.")
                    self._current_context = None
                    return None
                self._current_context = context
            logger.info("Context Generated")
            return context
        except Exception as e:
            logger.warning("Vision analysis gagal, context dikosongkan: {}", e)
            with self._state_lock:
                self._current_context = None   # Error Handling Policy: Gemini failure -> Empty Vision Context
            return None

    def get_context(self) -> Optional[VisionContext]:
        """Reuse context yang masih fresh (TTL belum lewat) — Freshness Policy:
        'If context is still valid, Vision must reuse it. Do NOT capture again
        unnecessarily.' TIDAK memicu capture baru sama sekali.

        v1.5.2 §20: kalau mode OFF, SELALU None — ini yang menyelesaikan known
        limitation v1.5.1 (context lama tidak lagi bisa "menyelinap" ke chat
        setelah OFF, terlepas dari TTL-nya masih berapa lama lagi)."""
        with self._state_lock:
            if self._mode == VisionMode.OFF:
                return None
            context = self._current_context
        if context is not None and context.is_fresh():
            logger.info("Context Reused")
            return context
        return None

    def refresh(self, source: str = "screen") -> Optional[VisionContext]:
        """Paksa capture + analyze baru — dipakai tombol 'Capture Now' (Manual
        maupun Auto mode, spec §12/§31). SELALU capture ulang walau context
        lama masih fresh; Teacher sengaja minta kondisi TERBARU.

        v1.5.2: diabaikan (return None) kalau mode OFF — pertahanan tambahan
        di level backend, di luar tombol GUI yang sudah di-disable saat OFF
        (spec §53 'Capture Now disabled in OFF')."""
        with self._state_lock:
            if self._mode == VisionMode.OFF:
                logger.info("Vision refresh diabaikan — mode OFF.")
                return None

        with self._capture_lock:
            return self._do_refresh(source)

    def refresh_if_needed(self, source: str = "screen") -> Optional[VisionContext]:
        """Dipakai HANYA oleh VisionAutoScheduler (spec §19). Beda dengan
        refresh(): reuse context yang masih fresh alih-alih selalu memaksa
        capture baru (Freshness Policy §11 — 'Scheduler tidak boleh capture
        setiap interval secara buta jika context masih valid').

        Kalau capture lain (manual atau auto lain) sedang berjalan, siklus
        auto ini di-SKIP (non-blocking) alih-alih mengantre (spec §18) —
        supaya tidak ada dua request Gemini bersamaan dan tidak ada backlog."""
        with self._state_lock:
            if self._mode == VisionMode.OFF:
                return None
            existing = self._current_context

        if existing is not None and existing.is_fresh():
            logger.info("Context Reused")
            return existing

        acquired = self._capture_lock.acquire(blocking=False)
        if not acquired:
            logger.info("Auto Vision capture skipped (capture already in progress)")
            return self._current_context
        try:
            return self._do_refresh(source)
        finally:
            self._capture_lock.release()

    def _do_refresh(self, source: str = "screen") -> Optional[VisionContext]:
        """Kerja capture+analyze aktual — HARUS dipanggil dalam _capture_lock
        (lihat refresh()/refresh_if_needed()), supaya Manual Capture dan Auto
        Scheduler tidak pernah tumpang tindih menjalankan network request."""
        logger.info("Context Refreshed")
        try:
            image = self.capture()
        except Exception as e:
            logger.warning("Capture gagal, pakai context sebelumnya: {}", e)
            return self._current_context

        return self.analyze(image, source=source)

    # ---------- Mode Lifecycle (v1.5.2) ----------

    def get_mode(self) -> VisionMode:
        with self._state_lock:
            return self._mode

    def get_provider_name(self) -> str:
        """v2.3 §18: read-only murni, untuk Developer Dashboard — "local" |
        "gemini", provider yang BENAR-BENAR dipakai (ditentukan sekali saat
        construction, restart wajib untuk ganti — sama seperti Language/
        Memory Provider)."""
        return self._provider_name

    def set_mode(self, mode: VisionMode) -> None:
        """Transisi mode sesuai tabel spec §22:
        OFF->MANUAL: scheduler tetap berhenti.
        OFF->AUTO / MANUAL->AUTO: scheduler start.
        AUTO->MANUAL / AUTO->OFF: scheduler stop.
        AUTO->OFF: context juga di-clear (Context Clear Policy §21)."""
        with self._state_lock:
            if mode == self._mode:
                return  # idempotent — tidak perlu restart scheduler untuk mode yang sama
            previous_mode = self._mode
            self._mode = mode

            if mode == VisionMode.OFF:
                self._current_context = None
                logger.info("Vision OFF")
            elif mode == VisionMode.MANUAL:
                logger.info("Vision MANUAL")
            elif mode == VisionMode.AUTO:
                logger.info("Vision AUTO")

        # Start/stop scheduler DI LUAR _state_lock — thread.join() di dalam
        # stop() bisa memakan waktu (menunggu siklus capture in-flight
        # selesai), dan kita tidak mau menahan lock selama itu (spec §50).
        if previous_mode == VisionMode.AUTO and mode != VisionMode.AUTO:
            self._stop_auto_scheduler()
        if mode == VisionMode.AUTO and previous_mode != VisionMode.AUTO:
            self._start_auto_scheduler()

    def _start_auto_scheduler(self) -> None:
        if self._auto_scheduler is None:
            self._auto_scheduler = VisionAutoScheduler(
                refresh_callback=self.refresh_if_needed,
                interval_seconds=VISION_AUTO_INTERVAL,
            )
        logger.info("Auto Vision enabled")
        self._auto_scheduler.start()

    def _stop_auto_scheduler(self) -> None:
        if self._auto_scheduler is not None:
            self._auto_scheduler.stop()

    def shutdown(self) -> None:
        """Dipanggil saat aplikasi ditutup (MainWindow.closeEvent) — memastikan
        tidak ada thread scheduler yang bertahan setelah proses exit (spec §34
        'No timer/thread may survive application shutdown')."""
        self._stop_auto_scheduler()