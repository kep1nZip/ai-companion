from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from ui.settings_service import SettingsService, SettingsSaveError
from config.logger import logger


class SettingsPage(QWidget):
    """Halaman Settings — presentation + configuration layer murni di atas
    SettingsService. TIDAK ada Configuration System baru, TIDAK ada
    SettingsManagerV2, TIDAK menyentuh Companion/Behavior/Vision/Avatar/Voice
    backend sama sekali.

    Hasil inspeksi (config/constants.py, config/settings.py) menunjukkan
    HANYA SATU field yang benar-benar punya mekanisme persistence/runtime
    yang nyata: GEMINI_API_KEY (lewat .env). Semua field lain di halaman ini
    Read Only — bukan karena belum sempat dibuat editable, tapi karena
    memang tidak ada setter/persistence contract untuk field itu di source
    aktual (Model, TTS Model/Voice, STT Model Size, VTube Studio URL, Model
    Config Path semuanya konstanta murni di constants.py, dipakai sekali saat
    construct object masing-masing subsystem, tanpa reload mechanism).

    Developer category SENGAJA tidak ada di halaman ini — DEVELOPER_MODE
    tidak ada di constants.py sama sekali (sudah dicek), sesuai kebijakan
    v1.0 yang menyebut definisi toggle itu belum punya spec jelas."""

    def __init__(self, settings_service: SettingsService):
        super().__init__()
        self.setObjectName("settingsPage")
        self._service = settings_service
        self._is_revealed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("settingsPageTitle")
        layout.addWidget(title)

        self._error_label = QLabel("")
        self._error_label.setObjectName("settingsErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._restart_label = QLabel("Some changes require restarting Arona.")
        self._restart_label.setObjectName("settingsHintLabel")
        self._restart_label.hide()
        layout.addWidget(self._restart_label)

        # ---------- General ----------
        layout.addWidget(self._section_label("General"))
        self._version_value = self._add_readonly_row(layout, "Version")
        self._theme_value = self._add_readonly_row(layout, "Theme")

        # ---------- AI ----------
        layout.addWidget(self._section_label("AI"))
        self._model_value = self._add_readonly_row(layout, "Model")

        api_key_row = QHBoxLayout()
        api_key_label = QLabel("API Key")
        api_key_label.setObjectName("settingsFieldLabel")
        api_key_row.addWidget(api_key_label)

        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.Password)
        self._api_key_input.textEdited.connect(self._on_api_key_edited)
        api_key_row.addWidget(self._api_key_input, stretch=1)

        self._show_button = QPushButton("Show")
        self._show_button.setObjectName("settingsSecondaryButton")
        self._show_button.clicked.connect(self._toggle_show_api_key)
        api_key_row.addWidget(self._show_button)

        layout.addLayout(api_key_row)

        # ---------- Voice ----------
        layout.addWidget(self._section_label("Voice"))
        self._tts_model_value = self._add_readonly_row(layout, "TTS Model")
        self._tts_voice_value = self._add_readonly_row(layout, "TTS Voice")
        self._stt_size_value = self._add_readonly_row(layout, "STT Model Size")

        # ---------- Avatar ----------
        layout.addWidget(self._section_label("Avatar"))
        self._vtube_url_value = self._add_readonly_row(layout, "VTube Studio URL")
        self._vtube_config_value = self._add_readonly_row(layout, "Model Config Path")
        self._vtube_token_value = self._add_readonly_row(layout, "VTube Studio Token")

        layout.addStretch()

        # ---------- Footer ----------
        footer = QHBoxLayout()
        footer.addStretch()

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setObjectName("settingsSecondaryButton")
        self._cancel_button.clicked.connect(self._handle_cancel)
        self._cancel_button.setEnabled(False)
        footer.addWidget(self._cancel_button)

        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self._handle_apply)
        self._apply_button.setEnabled(False)
        footer.addWidget(self._apply_button)

        layout.addLayout(footer)

        self._load_snapshot()

    # ---------- UI helpers ----------

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsSectionLabel")
        return label

    def _add_readonly_row(self, layout: QVBoxLayout, name: str) -> QLabel:
        row = QHBoxLayout()

        name_label = QLabel(name)
        name_label.setObjectName("settingsFieldLabel")
        row.addWidget(name_label)

        value_label = QLabel("")
        value_label.setObjectName("settingsFieldValue")
        value_label.setAlignment(Qt.AlignRight)
        row.addWidget(value_label, stretch=1)

        layout.addLayout(row)
        return value_label

    # ---------- Load / refresh ----------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        snapshot = self._service.get_snapshot()

        self._version_value.setText(snapshot.version)
        self._theme_value.setText(f"{snapshot.theme} (only theme currently available)")
        self._model_value.setText(snapshot.model_name)
        self._tts_model_value.setText(snapshot.tts_model_name)
        self._tts_voice_value.setText(snapshot.tts_voice_name)
        self._stt_size_value.setText(snapshot.stt_model_size)
        self._vtube_url_value.setText(snapshot.vtube_studio_url)
        self._vtube_config_value.setText(snapshot.vtube_model_config_path)
        self._vtube_token_value.setText("Present" if snapshot.vtube_token_present else "Not found")

        # Re-mask setiap kali halaman dibuka/di-reset — jangan biarkan API key
        # yang pernah di-reveal tetap kelihatan kalau user kembali ke halaman ini.
        self._is_revealed = False
        self._show_button.setText("Show")
        self._api_key_input.setEchoMode(QLineEdit.Password)
        self._api_key_input.clear()
        self._api_key_input.setPlaceholderText(
            "•" * 16 if snapshot.api_key_configured else "Not configured"
        )

        self._error_label.hide()
        self._set_dirty(False)

    # ---------- API Key actions ----------

    def _toggle_show_api_key(self) -> None:
        if self._is_revealed:
            self._api_key_input.setEchoMode(QLineEdit.Password)
            self._show_button.setText("Show")
            self._is_revealed = False
            return

        if not self._api_key_input.text():
            self._api_key_input.setText(self._service.reveal_api_key())

        self._api_key_input.setEchoMode(QLineEdit.Normal)
        self._show_button.setText("Hide")
        self._is_revealed = True

    def _on_api_key_edited(self, _text: str) -> None:
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._apply_button.setEnabled(dirty)
        self._cancel_button.setEnabled(dirty)
        self._restart_label.setVisible(dirty)

    # ---------- Apply / Cancel ----------

    def _handle_cancel(self) -> None:
        self._load_snapshot()

    def _handle_apply(self) -> None:
        new_value = self._api_key_input.text()
        try:
            self._service.save_api_key(new_value)
        except SettingsSaveError as e:
            self._show_error(str(e))
            return

        logger.info("Settings GUI: API key diperbarui, restart dibutuhkan.")
        self._load_snapshot()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()