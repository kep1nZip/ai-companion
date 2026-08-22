from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)

from ai.companion import Companion
from vision.vision_context import VisionContext
from ui.vision_worker import VisionWorker
from config.logger import logger

_DISPLAY_TIMEZONE = ZoneInfo("Asia/Jakarta")  # konsisten dengan ContextBuilder._format_time()


class VisionPage(QWidget):
    """Halaman Vision — presentation/control layer murni di atas Vision System
    (v0.7) yang SUDAH ADA lewat Companion.capture_vision()/current_vision_context().
    TIDAK ADA Vision System baru, TIDAK ADA ScreenCapture/ImageAnalyzer kedua,
    TIDAK memanggil Gemini langsung dari GUI.

    ON/OFF: Vision class TIDAK punya enable()/disable() sama sekali (sudah
    diverifikasi baca source langsung) — jadi toggle ini MURNI GUI-side,
    in-memory, TIDAK PERSISTEN (reset ke ON setiap app start, sama seperti
    perilaku Vision sebelum v1.5 yang selalu aktif). Mekanismenya: capture
    BARU (Vision.refresh()) HANYA PERNAH dipanggil lewat satu jalur —tombol
    'Capture Screen' di halaman ini. chat() TIDAK PERNAH memicu capture baru
    (Capture Policy sejak v0.7). Karena itu men-disable tombol saat OFF sudah
    CUKUP untuk menjamin 'tidak ada capture baru' tanpa perlu API baru di
    Vision/Companion.

    KETERBATASAN YANG DISADARI (didokumentasikan, bukan disembunyikan):
    toggle OFF tidak menghapus VisionContext yang MASIH FRESH dari capture
    sebelumnya di dalam Companion — kalau Teacher chat lewat teks dalam
    beberapa detik setelah OFF, Companion.chat() (tidak disentuh di v1.5)
    tetap bisa memakai context lama itu lewat get_context()-nya sendiri.
    Ini bukan regresi v1.5 — TTL default cuma 30 detik, dan context akan
    otomatis kadaluarsa dengan sendirinya (Freshness Policy v0.7)."""

    def __init__(self, companion: Companion):
        super().__init__()
        self.setObjectName("visionPage")
        self._companion = companion
        self._enabled = True  # default ON — sama seperti perilaku sebelum v1.5
        self._worker: VisionWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel("Vision")
        title.setObjectName("visionPageTitle")
        layout.addWidget(title)

        self._error_label = QLabel("")
        self._error_label.setObjectName("visionErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._status_label = QLabel("")
        self._status_label.setObjectName("visionStatusLabel")
        layout.addWidget(self._status_label)

        self._toggle_button = QPushButton("")
        self._toggle_button.setObjectName("visionSecondaryButton")
        self._toggle_button.clicked.connect(self._handle_toggle)
        layout.addWidget(self._toggle_button, alignment=Qt.AlignLeft)

        layout.addWidget(self._section_label("Mode"))
        mode_label = QLabel("Manual (only mode currently available)")
        mode_label.setObjectName("visionFieldValue")
        layout.addWidget(mode_label)

        self._capture_button = QPushButton("📷 Capture Screen")
        self._capture_button.clicked.connect(self._handle_capture)
        layout.addWidget(self._capture_button, alignment=Qt.AlignLeft)

        layout.addWidget(self._section_label("Freshness"))
        self._freshness_card = self._make_card()
        layout.addWidget(self._freshness_card)

        layout.addWidget(self._section_label("Vision Context"))
        self._context_card = self._make_card()
        layout.addWidget(self._context_card)

        layout.addStretch()

        self._render()

    # ---------- UI helpers ----------

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("visionSectionLabel")
        return label

    def _make_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("visionCard")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)

        label = QLabel("")
        label.setObjectName("visionCardContent")
        label.setWordWrap(True)
        frame_layout.addWidget(label)

        frame._content_label = label  # type: ignore[attr-defined]
        return frame

    def _set_card_text(self, card: QFrame, text: str) -> None:
        card._content_label.setText(text)  # type: ignore[attr-defined]

    # ---------- Lifecycle ----------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Baca CACHE saja (current_vision_context -> Vision.get_context()) —
        # TIDAK PERNAH memicu capture baru hanya karena halaman dibuka
        # (Freshness Policy §10: jangan capture kalau tidak perlu).
        self._render()

    # ---------- Toggle ----------

    def _handle_toggle(self) -> None:
        self._enabled = not self._enabled
        self._error_label.hide()
        self._render()
        logger.info("Vision GUI: {}", "Vision Enabled" if self._enabled else "Vision Disabled")

    # ---------- Capture ----------

    def _handle_capture(self) -> None:
        if not self._enabled:
            return

        self._capture_button.setEnabled(False)
        self._error_label.hide()

        self._worker = VisionWorker(self._companion)
        self._worker.result_ready.connect(self._on_capture_result)
        self._worker.error_occurred.connect(self._on_capture_error)
        self._worker.start()

    def _on_capture_result(self, context: VisionContext | None) -> None:
        self._capture_button.setEnabled(self._enabled)

        if context is None:
            # Vision.refresh() sudah membungkus SEMUA kegagalan (capture
            # ataupun analysis) jadi None secara internal — tidak bisa
            # dibedakan dari sini mana yang gagal, jadi satu pesan generik
            # (bukan mengarang presisi diagnostik yang tidak tersedia).
            self._show_error("Vision capture failed. Please try again.")
            return

        self._render_context(context)
        logger.info("Vision GUI: capture selesai.")

    def _on_capture_error(self, message: str) -> None:
        self._capture_button.setEnabled(self._enabled)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    # ---------- Rendering ----------

    def _render(self) -> None:
        if self._enabled:
            self._status_label.setText("👁 Vision: ● ON")
            self._toggle_button.setText("Turn Vision OFF")
            self._capture_button.setEnabled(True)

            context = self._companion.current_vision_context()
            self._render_context(context)
        else:
            self._status_label.setText("👁 Vision: ○ OFF")
            self._toggle_button.setText("Turn Vision ON")
            self._capture_button.setEnabled(False)

            self._set_card_text(self._freshness_card, "Vision is off. No capture will be taken.")
            self._set_card_text(self._context_card, "—")

    def _render_context(self, context: VisionContext | None) -> None:
        if context is None:
            self._set_card_text(self._freshness_card, "No capture yet.")
            self._set_card_text(self._context_card, "—")
            return

        captured_at = context.timestamp.astimezone(_DISPLAY_TIMEZONE).strftime("%d %B %Y, %H:%M:%S")
        age = int(context.age_seconds())
        fresh = "YES" if context.is_fresh() else "NO"

        self._set_card_text(
            self._freshness_card,
            f"Captured: {captured_at}\nAge: {age} seconds\nTTL: {context.ttl:.0f} seconds\nFresh: {fresh}",
        )

        app_line = f"Application: {context.application}\n\n" if context.application else ""
        self._set_card_text(self._context_card, f"{app_line}{context.summary}")