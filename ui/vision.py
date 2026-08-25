from __future__ import annotations

from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QRadioButton,
    QButtonGroup,
    QMessageBox,
)

from ai.companion import Companion
from vision.vision import Vision
from vision.vision_mode import VisionMode
from vision.vision_context import VisionContext
from ui.vision_worker import VisionWorker
from config.logger import logger

_DISPLAY_TIMEZONE = ZoneInfo("Asia/Jakarta")  # konsisten dengan ContextBuilder._format_time()

# v1.5.2 §35: GUI TIDAK PERNAH disentuh langsung dari thread VisionAutoScheduler
# (yang murni threading.Thread, bukan Qt). Alih-alih worker/signal yang
# menyeberang dari thread background itu, VisionPage memakai QTimer POLLING
# ringan yang hidup sepenuhnya di GUI thread sendiri — ia hanya MEMBACA state
# thread-safe milik Vision (get_mode()/get_context(), sudah dilindungi lock
# di vision.py) secara berkala selagi halaman ini terlihat. Scheduler sendiri
# tidak pernah tahu GUI ada sama sekali (Vision Independence Policy tetap utuh).
_POLL_INTERVAL_MS = 1000


class VisionPage(QWidget):
    """Halaman Vision — presentation/control layer murni di atas Vision System
    (v0.7) yang SUDAH ADA. TIDAK ADA Vision System baru, TIDAK ADA
    ScreenCapture/ImageAnalyzer kedua, TIDAK memanggil Gemini langsung dari GUI.

    v1.5.2 (Auto Vision): mode ON/OFF GUI-side v1.5.1 diganti tiga mode
    BACKEND asli — OFF / MANUAL / AUTO (vision.get_mode()/set_mode()).
    VisionPage menerima `vision` secara terpisah dari `companion` (lihat
    main_gui.py -> ui/window.py) supaya bisa mengontrol mode TANPA menyentuh
    ai/companion.py yang beku (Architecture Freeze Policy) — ini instance
    Vision yang SAMA persis dengan yang dipakai Companion untuk chat(), bukan
    instance kedua.

    Capture Manual ('Capture Now') TETAP lewat Companion.capture_vision()
    (VisionWorker, tidak berubah dari v1.5.1) — VisionPage hanya menambah
    jalur baru vision.set_mode()/get_mode() untuk kontrol mode, tidak
    menggantikan jalur capture yang sudah ada.

    Auto Vision adalah BACKGROUND CONTEXT REFRESH, BUKAN autonomous chat
    (spec v1.5.2 §3): scheduler (vision/auto_scheduler.py) hanya memanggil
    Vision.refresh_if_needed() secara berkala di dalam Vision sendiri — tidak
    pernah memanggil Companion.chat(), tidak pernah membuat Arona bicara
    sendiri. VisionPage di sini pun tidak pernah memicu chat apa pun.

    Privacy (Context Clear Policy, spec §20-21): begitu mode diset ke OFF,
    vision.set_mode(OFF) LANGSUNG menghapus VisionContext yang mungkin masih
    fresh (bukan cuma berhenti menampilkannya) dan get_context() sesudahnya
    SELALU None — tidak ada lagi context lama yang bisa 'menyelinap' ke
    chat() setelah OFF (ini known limitation v1.5.1 yang sudah diperbaiki)."""

    def __init__(self, companion: Companion, vision: Vision):
        super().__init__()
        self.setObjectName("visionPage")
        self._companion = companion
        self._vision = vision
        self._is_capturing = False  # state in-flight tombol Capture Now, terpisah dari mode
        self._worker: VisionWorker | None = None
        self._auto_confirmed_this_session = False  # spec §41: konfirmasi cukup sekali per sesi

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
        layout.addWidget(self._status_label)

        # ---------- Mode (v1.5.2) ----------
        layout.addWidget(self._section_label("Mode"))

        self._radio_off = QRadioButton("Off")
        self._radio_manual = QRadioButton("Manual")
        self._radio_auto = QRadioButton("Auto")
        for radio in (self._radio_off, self._radio_manual, self._radio_auto):
            radio.setObjectName("visionModeRadio")
            layout.addWidget(radio)

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._radio_off)
        self._mode_group.addButton(self._radio_manual)
        self._mode_group.addButton(self._radio_auto)
        # v1.5.2 §7: default startup mode = OFF, sesuai state awal Vision itu
        # sendiri (vision.get_mode() baru dibuat = VisionMode.OFF).
        self._radio_off.setChecked(True)
        self._mode_group.buttonClicked.connect(self._handle_mode_clicked)

        layout.addWidget(self._section_label("Status"))
        self._mode_status_label = QLabel("")
        self._mode_status_label.setObjectName("visionFieldValue")
        self._mode_status_label.setWordWrap(True)
        layout.addWidget(self._mode_status_label)

        # v1.5.2 §31: Capture Now HARUS tetap tersedia di mode AUTO — tombol
        # ini satu-satunya jalur force-refresh (vision.refresh(), lewat
        # Companion.capture_vision()) terlepas dari mode MANUAL atau AUTO.
        self._capture_button = QPushButton("Capture Now")
        self._capture_button.clicked.connect(self._handle_capture)
        layout.addWidget(self._capture_button, alignment=Qt.AlignLeft)

        layout.addWidget(self._section_label("Last Capture"))
        self._last_capture_card = self._make_card()
        layout.addWidget(self._last_capture_card)

        layout.addWidget(self._section_label("Freshness"))
        self._freshness_card = self._make_card()
        layout.addWidget(self._freshness_card)

        layout.addWidget(self._section_label("Vision Context"))
        self._context_card = self._make_card()
        layout.addWidget(self._context_card)

        layout.addStretch()

        # Polling timer (lihat catatan _POLL_INTERVAL_MS di atas) — dibuat di
        # sini tapi baru start/stop lewat showEvent/hideEvent, supaya tidak
        # jalan sia-sia saat halaman ini tidak sedang dilihat Teacher.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._render)

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
        # (Freshness Policy). _render() juga menghormati _is_capturing, jadi
        # kalau Teacher pindah halaman lalu balik lagi SAAT capture masih
        # berjalan di background, tombol tidak akan salah ke-enable.
        self._render()
        self._poll_timer.start()

    def hideEvent(self, event) -> None:
        # Hentikan polling saat halaman tidak terlihat (mis. Teacher pindah
        # ke Chat/Memory page) — Auto Scheduler di backend TETAP jalan
        # independen dari ini, cuma GUI-nya saja yang berhenti me-refresh
        # dirinya sendiri untuk hemat resource.
        self._poll_timer.stop()
        super().hideEvent(event)

    # ---------- Mode ----------

    def _handle_mode_clicked(self, button) -> None:
        if button is self._radio_off:
            target_mode = VisionMode.OFF
        elif button is self._radio_manual:
            target_mode = VisionMode.MANUAL
        else:
            target_mode = VisionMode.AUTO

        if target_mode == VisionMode.AUTO and not self._auto_confirmed_this_session:
            if not self._confirm_auto_activation():
                # Teacher batal -> kembalikan radio ke mode yang sebenarnya
                # aktif di backend (bukan asumsi OFF), supaya UI tidak
                # berbohong soal state.
                self._sync_radio_to_mode(self._vision.get_mode())
                return
            self._auto_confirmed_this_session = True

        self._error_label.hide()
        self._vision.set_mode(target_mode)
        self._render()
        logger.info("Vision GUI: mode diubah ke {}", target_mode.value)

    def _confirm_auto_activation(self) -> bool:
        # v1.5.2 §41: konfirmasi direkomendasikan untuk aktivasi AUTO
        # pertama kali di sesi ini — TIDAK ditanyakan ulang tiap 30 detik.
        answer = QMessageBox.question(
            self,
            "Vision Auto Mode",
            "Arona will periodically analyze your screen while Auto Vision "
            "is enabled.\n\nNo screenshots are permanently stored.\n\n"
            "Enable Auto Vision?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Yes

    def _sync_radio_to_mode(self, mode: VisionMode) -> None:
        radio = {
            VisionMode.OFF: self._radio_off,
            VisionMode.MANUAL: self._radio_manual,
            VisionMode.AUTO: self._radio_auto,
        }[mode]
        # blockSignals supaya set ini tidak memicu _handle_mode_clicked lagi
        self._mode_group.blockSignals(True)
        radio.setChecked(True)
        self._mode_group.blockSignals(False)

    # ---------- Capture ----------

    def _handle_capture(self) -> None:
        mode = self._vision.get_mode()
        # v1.5.2 §53: Capture Now disabled di OFF (dan cegah klik ganda
        # memicu beberapa capture bersamaan, sama seperti v1.5.1).
        if mode == VisionMode.OFF or self._is_capturing:
            return

        # Capture Now SELALU paksa refresh baru (vision.refresh()), TIDAK
        # PERNAH cek dulu apakah context masih fresh — beda dengan Auto
        # Scheduler yang pakai refresh_if_needed() (spec §12/§19).
        self._is_capturing = True
        self._error_label.hide()
        self._render()

        self._worker = VisionWorker(self._companion)
        self._worker.result_ready.connect(self._on_capture_result)
        self._worker.error_occurred.connect(self._on_capture_error)
        self._worker.start()

    def _on_capture_result(self, context: VisionContext | None) -> None:
        self._is_capturing = False

        if context is None:
            # Vision.refresh() sudah membungkus SEMUA kegagalan (capture
            # ataupun analysis) jadi None secara internal — tidak bisa
            # dibedakan dari sini mana yang gagal, jadi satu pesan generik
            # (bukan mengarang presisi diagnostik yang tidak tersedia).
            self._render()
            self._show_error("Vision capture failed. Please try again.")
            return

        self._render()
        logger.info("Vision GUI: capture selesai.")

    def _on_capture_error(self, message: str) -> None:
        self._is_capturing = False
        self._render()
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    # ---------- Rendering ----------

    def _render(self) -> None:
        # Mode adalah sumber kebenaran dari BACKEND (vision.get_mode()),
        # bukan diasumsikan dari radio yang dicentang — kalau ada perubahan
        # dari luar (mis. shutdown), tampilan tetap konsisten dengan state asli.
        mode = self._vision.get_mode()
        self._sync_radio_to_mode(mode)

        if self._is_capturing:
            self._status_label.setText(self._status_text(mode))
            self._mode_status_label.setText("Capturing...")
            self._capture_button.setText("Capturing...")
            self._capture_button.setEnabled(False)
            self._set_radios_enabled(True)
            return

        self._status_label.setText(self._status_text(mode))
        self._set_radios_enabled(True)

        if mode == VisionMode.OFF:
            self._mode_status_label.setText("Vision is off. No capture, no context is used by chat.")
            self._capture_button.setText("Capture Now")
            self._capture_button.setEnabled(False)
            self._set_card_text(self._last_capture_card, "—")
            self._set_card_text(self._freshness_card, "Vision is off. No new capture will be taken.")
            self._set_card_text(self._context_card, "—")
            return

        self._capture_button.setText("Capture Now")
        self._capture_button.setEnabled(True)

        if mode == VisionMode.MANUAL:
            self._mode_status_label.setText("Manual mode. Use Capture Now to update Vision Context.")
        else:  # AUTO
            self._mode_status_label.setText("Auto Vision active — refreshing in the background.")

        context = self._companion.current_vision_context()
        self._render_context(context)

    def _status_text(self, mode: VisionMode) -> str:
        if mode == VisionMode.AUTO:
            return "👁 Vision: AUTO"
        if mode == VisionMode.MANUAL:
            return "👁 Vision: MANUAL"
        return "👁 Vision: OFF"

    def _set_radios_enabled(self, enabled: bool) -> None:
        # Mode tetap boleh diganti walau sedang capture (mis. Teacher ingin
        # langsung matikan Vision di tengah proses) — parameter ini disiapkan
        # untuk konsistensi kalau kebijakan berubah nanti, saat ini selalu True.
        for radio in (self._radio_off, self._radio_manual, self._radio_auto):
            radio.setEnabled(enabled)

    def _render_context(self, context: VisionContext | None) -> None:
        if context is None:
            self._set_card_text(self._last_capture_card, "—")
            self._set_card_text(self._freshness_card, "No Vision Context")
            self._set_card_text(self._context_card, "—")
            return

        age = int(context.age_seconds())
        # Wording eksplisit Fresh/Stale, bukan cuma "Fresh: YES/NO" (v1.5.1).
        freshness_line = f"Fresh — {age} seconds old" if context.is_fresh() else f"Stale — {age} seconds old"
        captured_at = context.timestamp.astimezone(_DISPLAY_TIMEZONE).strftime("%d %B %Y, %H:%M:%S")

        self._set_card_text(self._last_capture_card, captured_at)
        self._set_card_text(self._freshness_card, f"{freshness_line}\n\nTTL: {context.ttl:.0f} seconds")

        app_line = f"Application: {context.application}\n\n" if context.application else ""
        self._set_card_text(self._context_card, f"{app_line}{context.summary}")