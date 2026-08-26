from __future__ import annotations
from pathlib import Path  # <-- Tambahan Import

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QLabel,  # <-- Tambahan Import QLabel
    QStackedWidget,  # <-- v1.1: page switching (Chat / Memory)
)

from ui.chat import ChatArea
from ui.chat_worker import ChatWorker
from ui.voice_worker import VoiceWorker
from ui.speak_worker import SpeakWorker
from ui.avatar_worker import AvatarWorker  # <-- Tambahan Import Avatar
from ui.navigation import Sidebar
from ui.memory_service import MemoryService  # <-- v1.1
from ui.memory import MemoryPage  # <-- v1.1
from ui.voice import VoicePage  # <-- v1.2
from ui.avatar import AvatarPage  # <-- v1.3
from ui.settings_service import SettingsService  # <-- v1.4
from ui.settings import SettingsPage  # <-- v1.4
from ui.vision import VisionPage  # <-- v1.5
from ui.routine import RoutinePage  # <-- v1.6
from ui.developer import DeveloperDashboard  # <-- v1.7
from ai.companion import Companion
from vision.vision import Vision  # <-- v1.5.2: diteruskan langsung, lihat main_gui.py
from ai.commands import is_command, run_command
from speech.voice_manager import VoiceManager, VoiceState
from avatar.avatar_manager import AvatarManager  # <-- Tambahan Import Avatar
from avatar.vtube import VTubeStudioClient  # <-- Tambahan Import Avatar
from avatar.expression import HaloMapper  # <-- Tambahan Import Avatar
from avatar.parameter_mapper import ParameterMapper  # <-- Tambahan Import Avatar
from config.constants import (
    APP_NAME, VERSION, MODEL_NAME, TTS_MODEL_NAME, TTS_VOICE_NAME, STT_MODEL_SIZE,
    VTUBE_STUDIO_URL, VTUBE_PLUGIN_NAME, VTUBE_PLUGIN_DEVELOPER,
    VTUBE_TOKEN_PATH, VTUBE_MODEL_CONFIG_PATH, VTUBE_RECONNECT_INTERVAL,  # <-- Tambahan Konstanta VTube
)
from config.settings import GEMINI_API_KEY
from config.logger import logger
from developer.performance_debug import PerformanceTracker
from developer.developer import DeveloperService


class MainWindow(QMainWindow):
    def __init__(self, companion: Companion, vision: Vision, performance_tracker: PerformanceTracker):
        super().__init__()
        self._companion = companion
        self._vision = vision  # <-- v1.5.2: instance yang SAMA dengan milik Companion, lihat main_gui.py
        self._performance_tracker = performance_tracker
        self._worker: ChatWorker | None = None
        self._voice_worker: VoiceWorker | None = None
        self._speak_worker: SpeakWorker | None = None
        self._developer_dashboard: DeveloperDashboard | None = None  # <-- v1.7: dibuat lazy, reused kalau sudah terbuka

        # ---------- VTube Studio / Avatar Initialization (sebelum VoiceManager) ----------
        vtube_client = VTubeStudioClient(
            url=VTUBE_STUDIO_URL,
            plugin_name=VTUBE_PLUGIN_NAME,
            plugin_developer=VTUBE_PLUGIN_DEVELOPER,
            token_path=Path(VTUBE_TOKEN_PATH),
        )
        self._avatar_manager = AvatarManager(
            vtube_client=vtube_client,
            halo_mapper=HaloMapper(),
            parameter_mapper=ParameterMapper(config_path=Path(VTUBE_MODEL_CONFIG_PATH)),
            reconnect_interval=VTUBE_RECONNECT_INTERVAL,
        )
        self._avatar_worker = AvatarWorker(self._avatar_manager)
        self._avatar_worker.state_changed.connect(self._on_avatar_state_changed)
        self._avatar_worker.start()
        # -----------------------------------------------------------

        self._voice_manager = VoiceManager(
            companion=companion,
            api_key=GEMINI_API_KEY,
            stt_model_size=STT_MODEL_SIZE,
            tts_model_name=TTS_MODEL_NAME,
            voice_name=TTS_VOICE_NAME,
            on_audio_ready=self._avatar_worker.animate_lipsync,
        )

        self._developer_service = DeveloperService(
            companion=self._companion,
            avatar_manager=self._avatar_manager,
            voice_manager=self._voice_manager,
            performance_tracker=performance_tracker,
        )

        # ---------- Memory GUI (v1.1) — read-only boundary di atas Companion ----------
        self._memory_service = MemoryService(companion)
        # -----------------------------------------------------------

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)

        self._build_menu_bar()
        self._build_central_widget()

        self.statusBar().showMessage("Ready")

        self._avatar_status_label = QLabel("Avatar: Disconnected")
        self.statusBar().addPermanentWidget(self._avatar_status_label)

        logger.info("Window opened.")

    # ---------- UI Construction ----------

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        conversation_menu = menu_bar.addMenu("Conversation")
        clear_action = QAction("Clear Chat", self)
        clear_action.triggered.connect(self._handle_clear_chat)
        conversation_menu.addAction(clear_action)

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        version_action = QAction("Version", self)
        version_action.triggered.connect(self._show_version)
        help_menu.addAction(version_action)

    def _build_central_widget(self) -> None:
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.navigate_requested.connect(self._on_navigate)
        root_layout.addWidget(self._sidebar)

        # ---------- v1.1: QStackedWidget menggantikan single content widget,
        # supaya sidebar bisa switch antar halaman (Chat / Memory) ----------
        self._pages = QStackedWidget()

        self._chat_page = self._build_chat_page()
        self._memory_page = MemoryPage(self._memory_service)
        # v1.2: VoicePage reuses the SAME VoiceManager instance already created
        # above for the Chat page's mic button — no second VoiceManager, no
        # second Recorder/STT/TTS/AudioPlayer (Shared Companion Path §14).
        self._voice_page = VoicePage(self._voice_manager)
        # v1.3: AvatarPage reuses the SAME AvatarManager + AvatarWorker instances
        # already created above (VTube Studio / Avatar Initialization block) —
        # no second AvatarManager, no second VTube Studio connection.
        self._avatar_page = AvatarPage(self._avatar_manager, self._avatar_worker)
        # v1.4: SettingsService needs NO reference to Companion/any manager —
        # it only reads config/constants.py + config/settings.py + local file
        # checks, and writes GEMINI_API_KEY to .env. Settings is not a
        # SettingsManager that reaches into subsystems (Companion Rules §31).
        self._settings_service = SettingsService()
        self._settings_page = SettingsPage(self._settings_service)
        self._settings_page.open_developer_dashboard_requested.connect(self._handle_open_developer_dashboard)
        # v1.5: VisionPage reuses self._companion directly — Vision.capture()/
        # analyze() already live inside Companion via capture_vision()/
        # current_vision_context(), no second Vision/ScreenCapture/ImageAnalyzer.
        # v1.5.2: VisionPage juga menerima self._vision langsung (instance yang
        # SAMA, lihat main_gui.py) khusus untuk kontrol mode OFF/MANUAL/AUTO
        # (set_mode/get_mode) — capture Manual/Auto tetap lewat Companion.
        self._vision_page = VisionPage(self._companion, self._vision)

        # v1.6: RoutinePage reuses self._companion directly — semua akses ke
        # Routine System (v0.8) lewat passthrough Companion yang SUDAH ADA
        # (get_pending_routine_events/get_last_routine_event/
        # get_next_routine_schedule/get_routine_history/get_routine_suppression/
        # is_routine_enabled/enable_routine/disable_routine). TIDAK ADA
        # RoutineEngine/RoutineScheduler kedua, TIDAK ada instance Routine baru.
        self._routine_page = RoutinePage(self._companion)

        self._pages.addWidget(self._chat_page)
        self._pages.addWidget(self._memory_page)
        self._pages.addWidget(self._voice_page)
        self._pages.addWidget(self._avatar_page)
        self._pages.addWidget(self._settings_page)
        self._pages.addWidget(self._vision_page)
        self._pages.addWidget(self._routine_page)

        root_layout.addWidget(self._pages, stretch=1)

        self.setCentralWidget(central)

    def _build_chat_page(self) -> QWidget:
        """Sama persis dengan content widget v1.0 sebelumnya — cuma dipindah
        jadi method terpisah supaya bisa dipasang sebagai satu page di
        QStackedWidget. Tidak ada perubahan logic chat/voice/avatar sama sekali."""
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._chat_area = ChatArea()
        content_layout.addWidget(self._chat_area, stretch=1)

        input_row = QWidget()
        input_row.setObjectName("inputRow")
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(8)

        self._input_box = QLineEdit()
        self._input_box.setPlaceholderText("Ketik pesan atau perintah (/help)...")
        self._input_box.returnPressed.connect(self._handle_send)

        self._mic_button = QPushButton("🎤")
        self._mic_button.setFixedWidth(44)
        self._mic_button.clicked.connect(self._handle_mic_click)

        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._handle_send)

        input_layout.addWidget(self._input_box, stretch=1)
        input_layout.addWidget(self._mic_button)
        input_layout.addWidget(self._send_button)

        content_layout.addWidget(input_row)

        return content

    # ---------- Navigation (v1.1) ----------

    def _on_navigate(self, page_name: str) -> None:
        if page_name == "chat":
            self._pages.setCurrentWidget(self._chat_page)
        elif page_name == "memory":
            self._pages.setCurrentWidget(self._memory_page)
        elif page_name == "voice":
            self._pages.setCurrentWidget(self._voice_page)
        elif page_name == "avatar":
            self._pages.setCurrentWidget(self._avatar_page)
        elif page_name == "settings":
            self._pages.setCurrentWidget(self._settings_page)
        elif page_name == "vision":
            self._pages.setCurrentWidget(self._vision_page)
        elif page_name == "routine":
            self._pages.setCurrentWidget(self._routine_page)

    # ---------- Text Chat Actions ----------

    def _handle_send(self) -> None:
        text = self._input_box.text().strip()
        if not text:
            return

        self._input_box.clear()

        if is_command(text):
            self._handle_command(text)
            return

        self._chat_area.add_message(text, is_user=True)
        logger.info("Message sent from GUI: {}", text)

        self._set_text_input_enabled(False)
        self.statusBar().showMessage("Thinking...")

        self._worker = ChatWorker(self._companion, text)
        self._worker.result_ready.connect(self._on_reply_received)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _handle_command(self, text: str) -> None:
        result = run_command(text, self._companion)

        if text.strip().lower() == "/clear":
            self._chat_area.clear_messages()
        else:
            self._chat_area.add_message(result.message, is_user=False)

        if result.should_exit:
            logger.info("Application exiting via /exit command (GUI).")
            self.close()

    def _handle_clear_chat(self) -> None:
        self._companion.clear_history()
        self._chat_area.clear_messages()
        self.statusBar().showMessage("Conversation cleared", 3000)
        logger.info("Conversation cleared from menu.")

    def _on_reply_received(self, reply: str) -> None:
        self._chat_area.add_message(reply, is_user=False)
        self.statusBar().showMessage("Connected", 3000)
        self._set_text_input_enabled(True)
        logger.info("Message received in GUI.")
        self._speak_text(reply)
        self._avatar_worker.request_reaction(reply)  # <-- Tambahan baris reaksi avatar

        behavior_state = self._companion.current_behavior_state()
        self._avatar_worker.apply_mood(behavior_state.internal.mood.value)

    def _speak_text(self, text: str) -> None:
        self._mic_button.setEnabled(False)
        self._speak_worker = SpeakWorker(self._voice_manager, text)
        self._speak_worker.state_changed.connect(self._on_voice_state_changed)
        self._speak_worker.finished_speaking.connect(self._on_speak_finished)
        self._speak_worker.start()

    def _on_speak_finished(self) -> None:
        self._mic_button.setEnabled(True)
        self.statusBar().showMessage("Ready", 2000)

    def _on_error(self, message: str, is_rate_limit: bool) -> None:
        self._chat_area.add_message(message, is_user=False)
        self.statusBar().showMessage("Error", 3000)
        self._set_text_input_enabled(True)

    def _set_text_input_enabled(self, enabled: bool) -> None:
        self._input_box.setEnabled(enabled)
        self._send_button.setEnabled(enabled)
        if enabled:
            self._input_box.setFocus()

    # ---------- Voice Actions ----------

    def _handle_mic_click(self) -> None:
        if self._voice_manager.state == VoiceState.IDLE:
            self._voice_manager.start_recording()
            self._mic_button.setText("⏹")
            self.statusBar().showMessage(VoiceState.RECORDING.value)
            logger.info("Recording started from GUI.")
            return

        if self._voice_manager.state == VoiceState.RECORDING:
            self._mic_button.setEnabled(False)
            self._set_text_input_enabled(False)

            self._voice_worker = VoiceWorker(self._voice_manager)
            self._voice_worker.state_changed.connect(self._on_voice_state_changed)
            self._voice_worker.reply_ready.connect(self._on_voice_reply)
            self._voice_worker.error_occurred.connect(self._on_voice_error)
            self._voice_worker.start()

    def _on_voice_state_changed(self, status_text: str) -> None:
        self.statusBar().showMessage(status_text)

    def _on_voice_reply(self, user_text: str, reply: str) -> None:
        self._chat_area.add_message(user_text, is_user=True)
        self._chat_area.add_message(reply, is_user=False)
        self.statusBar().showMessage("Completed", 3000)
        self._reset_voice_ui()
        logger.info("Voice interaction completed.")
        self._avatar_worker.request_reaction(reply)  # <-- Tambahan baris reaksi avatar

        behavior_state = self._companion.current_behavior_state()
        self._avatar_worker.apply_mood(behavior_state.internal.mood.value)
        
    def _on_voice_error(self, message: str) -> None:
        self._chat_area.add_message(message, is_user=False)
        self.statusBar().showMessage("Error", 3000)
        self._reset_voice_ui()

    def _reset_voice_ui(self) -> None:
        self._mic_button.setText("🎤")
        self._mic_button.setEnabled(True)
        self._set_text_input_enabled(True)

    # ---------- Avatar Handlers ----------

    def _on_avatar_state_changed(self, state_text: str) -> None:  # <-- Handler baru
        self._avatar_status_label.setText(f"Avatar: {state_text}")

    # ---------- Dialogs ----------

    def _handle_open_developer_dashboard(self) -> None:
        # v1.7: dialog non-modal, reused kalau sudah terbuka (bukan
        # menumpuk instance baru tiap klik). DeveloperDashboard SUDAH
        # menerima self._developer_service yang sudah ada sejak awal
        # (dibuat di __init__ MainWindow) — TIDAK ada instance
        # DeveloperService kedua.
        if self._developer_dashboard is None:
            self._developer_dashboard = DeveloperDashboard(self._developer_service, parent=self)
        self._developer_dashboard.show()
        self._developer_dashboard.raise_()
        self._developer_dashboard.activateWindow()

    def _show_about(self) -> None:
        QMessageBox.information(
            self, "About", f"{APP_NAME} — AI Desktop Companion\nDitenagai oleh Gemini API."
        )

    def _show_version(self) -> None:
        QMessageBox.information(self, "Version", f"{APP_NAME} v{VERSION}")

    # ---------- Shutdown ----------

    def closeEvent(self, event) -> None:
        self._avatar_worker.stop_avatar()  # <-- Menghentikan worker avatar sebelum keluar
        # v1.5.2 spec §34/§48: scheduler Auto Vision (kalau sedang jalan)
        # TIDAK BOLEH bertahan setelah aplikasi ditutup — shutdown() men-stop
        # thread-nya secara bersih (join dengan timeout).
        self._vision.shutdown()
        # v1.7: pastikan QTimer polling Developer Dashboard (kalau sedang
        # terbuka) ikut berhenti — closeEvent dialog TIDAK otomatis
        # terpanggil hanya karena parent window ditutup.
        if self._developer_dashboard is not None:
            self._developer_dashboard.close()
        logger.info("Application closed.")
        event.accept()