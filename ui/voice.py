from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)

from speech.voice_manager import VoiceManager, VoiceState
from ui.voice_worker import VoiceWorker
from config.logger import logger


class VoicePage(QWidget):
    """Halaman Voice — presentation layer murni di atas VoiceManager yang SUDAH
    ADA (dipakai bersama dengan mic button di Chat page, sesuai Shared
    Companion Path v1.2 §14). TIDAK membuat VoiceManager/Recorder/STT/TTS/
    AudioPlayer baru, TIDAK memanggil Gemini langsung, TIDAK memanggil
    Recorder/STT/TTS/Player secara langsung — semua lewat VoiceManager +
    VoiceWorker yang sudah dipakai Chat page (v1.1/v0.4).

    Reuse `ui/voice_worker.py::VoiceWorker` apa adanya (bukan worker baru) —
    ini memanggil `voice_manager.stop_recording_and_respond()`, yang di dalam
    backend SUDAH mencakup STT + Companion.chat() + TTS + playback dalam satu
    blocking call. Karena itu 'You said' dan 'Arona:' di halaman ini baru
    terisi SETELAH audio balasan selesai diputar — ini kontrak asli backend,
    bukan desain ulang di sisi GUI.

    Tidak ada tombol Stop Playback: AudioPlayer (speech/player.py) tidak
    menyediakan API stop, jadi tidak diciptakan di sini (v1.2 §19)."""

    def __init__(self, voice_manager: VoiceManager):
        super().__init__()
        self.setObjectName("voicePage")
        self._voice_manager = voice_manager
        self._voice_worker: VoiceWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel("Voice")
        title.setObjectName("voicePageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Voice System")
        subtitle.setObjectName("voiceSectionLabel")
        layout.addWidget(subtitle)

        self._status_label = QLabel(f"Status: {self._voice_manager.state.value}")
        self._status_label.setObjectName("voiceStatusLabel")
        layout.addWidget(self._status_label)

        self._error_label = QLabel("")
        self._error_label.setObjectName("voiceErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._record_button = QPushButton("🎙 Start Recording")
        self._record_button.setObjectName("voiceRecordButton")
        self._record_button.clicked.connect(self._handle_record_click)
        layout.addWidget(self._record_button, alignment=Qt.AlignLeft)

        layout.addWidget(self._make_section_label("You said:"))
        self._user_text_box = self._make_transcript_box()
        layout.addWidget(self._user_text_box)

        layout.addWidget(self._make_section_label("Arona:"))
        self._reply_text_box = self._make_transcript_box()
        layout.addWidget(self._reply_text_box)

        layout.addStretch()

    # ---------- UI helpers ----------

    def _make_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("voiceSectionLabel")
        return label

    def _make_transcript_box(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("voiceTranscriptBox")
        inner_layout = QVBoxLayout(frame)
        inner_layout.setContentsMargins(12, 10, 12, 10)

        label = QLabel("")
        label.setObjectName("voiceTranscriptContent")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        inner_layout.addWidget(label)

        frame._content_label = label  # type: ignore[attr-defined]
        return frame

    def _set_transcript(self, box: QFrame, text: str) -> None:
        box._content_label.setText(text)  # type: ignore[attr-defined]

    # ---------- Actions ----------

    def _handle_record_click(self) -> None:
        if self._voice_manager.state == VoiceState.IDLE:
            self._start_recording()
        elif self._voice_manager.state == VoiceState.RECORDING:
            self._stop_and_process()

    def _start_recording(self) -> None:
        self._error_label.hide()
        try:
            self._voice_manager.start_recording()
        except Exception as e:
            logger.warning("Voice GUI: gagal memulai rekaman: {}", e)
            self._show_error("Microphone unavailable. Please check your microphone.")
            return

        self._record_button.setText("⏹ Stop Recording")
        self._status_label.setText(f"Status: {VoiceState.RECORDING.value}")

    def _stop_and_process(self) -> None:
        self._record_button.setEnabled(False)
        self._error_label.hide()

        self._voice_worker = VoiceWorker(self._voice_manager)
        self._voice_worker.state_changed.connect(self._on_state_changed)
        self._voice_worker.reply_ready.connect(self._on_reply_ready)
        self._voice_worker.error_occurred.connect(self._on_error)
        self._voice_worker.start()

    def _on_state_changed(self, status_text: str) -> None:
        self._status_label.setText(f"Status: {status_text}")

    def _on_reply_ready(self, user_text: str, reply: str) -> None:
        self._set_transcript(self._user_text_box, user_text)
        self._set_transcript(self._reply_text_box, reply)
        logger.info("Voice GUI: interaksi selesai.")
        self._reset_record_button()

    def _on_error(self, message: str) -> None:
        self._show_error(message)
        self._reset_record_button()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _reset_record_button(self) -> None:
        self._record_button.setText("🎙 Start Recording")
        self._record_button.setEnabled(True)
        self._status_label.setText(f"Status: {VoiceState.IDLE.value}")