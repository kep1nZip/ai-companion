from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
)

from ui.settings_service import SettingsService, SettingsSaveError
from config.logger import logger


class SettingsPage(QWidget):
    """Halaman Settings — presentation + configuration layer murni di atas
    SettingsService. TIDAK ada Configuration System baru, TIDAK ada
    SettingsManagerV2, TIDAK menyentuh Companion/Behavior/Vision/Avatar/Voice
    backend sama sekali.

    Hasil inspeksi (config/constants.py, config/settings.py) menunjukkan
    HANYA field yang benar-benar punya mekanisme persistence/runtime nyata
    yang editable: GEMINI_API_KEY, dan (v2.0 Step 9) AI_PROVIDER +
    LOCAL_PROVIDER_MODEL_NAME — semuanya lewat .env. Semua field lain di
    halaman ini Read Only — bukan karena belum sempat dibuat editable, tapi
    karena memang tidak ada setter/persistence contract untuk field itu di
    source aktual (TTS Model/Voice, STT Model Size, VTube Studio URL, Model
    Config Path semuanya konstanta murni di constants.py, dipakai sekali saat
    construct object masing-masing subsystem, tanpa reload mechanism).

    v2.0 Step 9 §10-11: provider di-construct SEKALI saat startup
    (main_gui.py) — TIDAK ADA hot-swap. Mengubah 'Language Provider' di sini
    cuma menyimpan ke .env dan WAJIB restart untuk berlaku, sama persis
    seperti API Key sudah bekerja sejak v1.4. §7: UI mengikuti mockup resmi
    spec (Provider dropdown, Model, Status) — TIDAK menambah Base URL atau
    field lain yang tidak diminta.

    Dirty-state DIPISAH per section (API Key vs Provider) — supaya klik
    Apply karena ganti Provider saja TIDAK ikut mencoba nyimpen API Key
    kosong (dan sebaliknya). Kedua section tetap berbagi SATU tombol
    Apply/Cancel (spec: 'Do not redesign Settings' — bukan bikin footer per
    section), tapi _handle_apply() cuma menyimpan section yang benar2
    diubah.

    DEVELOPER_MODE TIDAK ADA di constants.py sama sekali (dikonfirmasi ulang
    saat inspeksi v1.7) — jadi tombol 'Open Developer Dashboard' di bawah
    BUKAN gated oleh mode/toggle/persistence apa pun (spec v1.7 §9/§29: 'Do
    not invent a Developer Mode just to hide/show a page'). Tombol ini cuma
    memancarkan Signal (open_developer_dashboard_requested) — SettingsPage
    TIDAK menyimpan referensi ke DeveloperService/Companion sama sekali
    (menjaga prinsip 'SettingsService needs NO reference to Companion/any
    manager' tetap utuh); ui/window.py (yang sudah memegang
    self._developer_service) yang membuka dialog-nya."""

    open_developer_dashboard_requested = Signal()  # v1.7

    def __init__(self, settings_service: SettingsService):
        super().__init__()
        self.setObjectName("settingsPage")
        self._service = settings_service
        self._is_revealed = False
        self._api_key_dirty = False
        self._provider_dirty = False
        self._memory_provider_dirty = False  # v2.2: dipisah dari _provider_dirty (Language Provider)

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

        provider_row = QHBoxLayout()
        provider_label = QLabel("Language Provider")
        provider_label.setObjectName("settingsFieldLabel")
        provider_row.addWidget(provider_label)

        self._provider_combo = QComboBox()
        # v2.0 Step 9 §8: cuma provider yang BENERAN diimplementasikan.
        self._provider_combo.addItems(["Local", "Gemini"])
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_row.addWidget(self._provider_combo, stretch=1)
        layout.addLayout(provider_row)

        self._local_model_row_label = QLabel("Local Model")
        self._local_model_row_label.setObjectName("settingsFieldLabel")
        local_model_row = QHBoxLayout()
        local_model_row.addWidget(self._local_model_row_label)
        self._local_model_input = QLineEdit()
        self._local_model_input.textEdited.connect(self._on_provider_field_edited)
        local_model_row.addWidget(self._local_model_input, stretch=1)
        layout.addLayout(local_model_row)

        self._provider_status_value = self._add_readonly_row(layout, "Status")

        self._model_value = self._add_readonly_row(layout, "Gemini Model")

        # v2.2: Memory Extraction Provider — dropdown TERPISAH dari Language
        # Provider di atas (§27: dua keputusan independen). TIDAK ADA field
        # "Local Model" kedua di sini — Local Memory Extraction reuse
        # LOCAL_PROVIDER_MODEL_NAME yang sama dipakai Language Provider
        # (§20/§30), jadi tidak ada apa pun untuk diedit selain provider-nya
        # sendiri.
        memory_provider_row = QHBoxLayout()
        memory_provider_label = QLabel("Memory Extraction Provider")
        memory_provider_label.setObjectName("settingsFieldLabel")
        memory_provider_row.addWidget(memory_provider_label)

        self._memory_provider_combo = QComboBox()
        self._memory_provider_combo.addItems(["Local", "Gemini"])
        self._memory_provider_combo.currentIndexChanged.connect(self._on_memory_provider_changed)
        memory_provider_row.addWidget(self._memory_provider_combo, stretch=1)
        layout.addLayout(memory_provider_row)

        self._memory_provider_status_value = self._add_readonly_row(layout, "Memory Status")

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

        # ---------- Developer Tools (v1.7) ----------
        layout.addWidget(self._section_label("Developer Tools"))
        self._developer_button = QPushButton("Open Developer Dashboard")
        self._developer_button.setObjectName("settingsSecondaryButton")
        self._developer_button.clicked.connect(self.open_developer_dashboard_requested.emit)
        layout.addWidget(self._developer_button, alignment=Qt.AlignLeft)

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

        # v2.0 Step 9: reset tampilan provider dari snapshot (bukan dari state
        # UI lama) setiap kali halaman ini dibuka — konsisten dengan pola
        # re-masking API key di atas.
        self._provider_combo.blockSignals(True)
        self._provider_combo.setCurrentText(snapshot.ai_provider.capitalize())
        self._provider_combo.blockSignals(False)
        self._local_model_input.blockSignals(True)
        self._local_model_input.setText(snapshot.local_provider_model_name)
        self._local_model_input.blockSignals(False)
        self._update_provider_field_visibility(snapshot.ai_provider)
        self._update_provider_status(snapshot.ai_provider)

        # v2.2: reset tampilan Memory Provider dari snapshot, pola sama
        # dengan Language Provider di atas.
        self._memory_provider_combo.blockSignals(True)
        self._memory_provider_combo.setCurrentText(snapshot.memory_provider.capitalize())
        self._memory_provider_combo.blockSignals(False)
        self._update_memory_provider_status(snapshot.memory_provider)

        self._error_label.hide()
        self._api_key_dirty = False
        self._provider_dirty = False
        self._memory_provider_dirty = False
        self._sync_dirty_ui()

    def _update_provider_field_visibility(self, provider: str) -> None:
        is_local = provider.strip().lower() == "local"
        self._local_model_row_label.setVisible(is_local)
        self._local_model_input.setVisible(is_local)

    def _update_provider_status(self, provider: str) -> None:
        # v2.0 Step 9 §27/§12: status ini murni "config-nya kelihatan masuk
        # akal" (non-empty), BUKAN klaim koneksi live tervalidasi — TIDAK ada
        # health-check subsystem baru dibuat untuk ini.
        if provider.strip().lower() == "local":
            self._provider_status_value.setText("● Local provider configured")
        else:
            self._provider_status_value.setText("● Gemini provider configured")

    def _update_memory_provider_status(self, provider: str) -> None:
        # v2.2: pola IDENTIK dengan _update_provider_status di atas — config-
        # sane check, bukan live health-check (spec §12 yang sama berlaku
        # untuk Memory Provider).
        if provider.strip().lower() == "local":
            self._memory_provider_status_value.setText("● Local memory provider configured")
        else:
            self._memory_provider_status_value.setText("● Gemini memory provider configured")

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
        self._api_key_dirty = True
        self._sync_dirty_ui()

    # ---------- Provider actions (v2.0 Step 9) ----------

    def _on_provider_changed(self, _index: int) -> None:
        self._update_provider_field_visibility(self._provider_combo.currentText())
        self._provider_dirty = True
        self._sync_dirty_ui()

    def _on_provider_field_edited(self, _text: str) -> None:
        self._provider_dirty = True
        self._sync_dirty_ui()

    # ---------- Memory Provider actions (v2.2) ----------

    def _on_memory_provider_changed(self, _index: int) -> None:
        self._memory_provider_dirty = True
        self._sync_dirty_ui()

    # ---------- Shared dirty state ----------

    def _sync_dirty_ui(self) -> None:
        dirty = self._api_key_dirty or self._provider_dirty or self._memory_provider_dirty
        self._apply_button.setEnabled(dirty)
        self._cancel_button.setEnabled(dirty)
        self._restart_label.setVisible(dirty)

    # ---------- Apply / Cancel ----------

    def _handle_cancel(self) -> None:
        self._load_snapshot()

    def _handle_apply(self) -> None:
        # v2.0 Step 9: cuma simpan section yang BENERAN diubah — supaya ganti
        # Provider saja tidak ikut mencoba nyimpen API Key kosong, dan
        # sebaliknya (lihat catatan dirty-state terpisah di docstring class).
        if self._api_key_dirty:
            try:
                self._service.save_api_key(self._api_key_input.text())
            except SettingsSaveError as e:
                self._show_error(str(e))
                return

        if self._provider_dirty:
            try:
                self._service.save_provider_settings(
                    provider=self._provider_combo.currentText(),
                    local_model_name=self._local_model_input.text(),
                )
            except SettingsSaveError as e:
                self._show_error(str(e))
                return
            logger.info("Settings GUI: AI provider diperbarui, restart dibutuhkan.")

        # v2.2: dipisah dari _provider_dirty (Language Provider) — pola sama
        # dengan blok api_key_dirty/provider_dirty di atas.
        if self._memory_provider_dirty:
            try:
                self._service.save_memory_provider_settings(
                    memory_provider=self._memory_provider_combo.currentText(),
                )
            except SettingsSaveError as e:
                self._show_error(str(e))
                return
            logger.info("Settings GUI: Memory Extraction provider diperbarui, restart dibutuhkan.")

        logger.info("Settings GUI: perubahan disimpan.")
        self._load_snapshot()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()