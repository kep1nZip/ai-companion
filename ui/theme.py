"""Single source styling untuk seluruh GUI. Siap diperluas jadi multi-theme di masa depan."""

DARK_STYLESHEET = """
QMainWindow {
    background-color: #1e1f26;
}

QMenuBar {
    background-color: #23252e;
    color: #e6e6e6;
}

QMenuBar::item:selected {
    background-color: #3a3d4a;
}

QMenu {
    background-color: #23252e;
    color: #e6e6e6;
    border: 1px solid #33343f;
}

QMenu::item:selected {
    background-color: #4a90e2;
}

QWidget#sidebar {
    background-color: #23252e;
    border-right: 1px solid #33343f;
}

QLabel#sidebarTitle {
    color: #4a90e2;
    font-size: 15px;
    font-weight: 700;
    padding: 4px 8px;
}

QPushButton#sidebarItem,
QPushButton#sidebarItemActive {
    text-align: left;
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 12px;
}

QPushButton#sidebarItemActive {
    background-color: #2c2e38;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#sidebarItem {
    color: #6b6e7a;
}

QScrollArea#chatArea {
    background-color: #1e1f26;
    border: none;
}

QFrame#userBubble {
    background-color: #4a90e2;
    border-radius: 12px;
}

QFrame#userBubble QLabel {
    color: #ffffff;
    font-size: 13px;
}

QFrame#aronaBubble {
    background-color: #2c2e38;
    border-radius: 12px;
}

QFrame#aronaBubble QLabel {
    color: #e6e6e6;
    font-size: 13px;
}

QWidget#inputRow {
    background-color: #23252e;
    border-top: 1px solid #33343f;
}

QLineEdit {
    background-color: #2c2e38;
    color: #e6e6e6;
    border: 1px solid #3a3d4a;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}

QLineEdit:focus {
    border: 1px solid #4a90e2;
}

QPushButton {
    background-color: #4a90e2;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #5b9ee8;
}

QPushButton:disabled {
    background-color: #3a3d4a;
    color: #7a7d8a;
}

QStatusBar {
    background-color: #23252e;
    color: #a0a3b0;
}

/* ---------- Memory GUI (v1.1) ---------- */

QWidget#memoryPage {
    background-color: #1e1f26;
}

QLabel#memoryPageTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}

QScrollArea#memoryListArea {
    background-color: #1e1f26;
    border: none;
}

QFrame#memoryCard {
    background-color: #2c2e38;
    border: 1px solid #33343f;
    border-radius: 10px;
}

QFrame#memoryCard:hover {
    border: 1px solid #4a90e2;
}

QLabel#memoryCardContent {
    color: #e6e6e6;
    font-size: 13px;
}

QLabel#memoryCardMeta {
    color: #a0a3b0;
    font-size: 11px;
}

QLabel#memoryStateLabel {
    color: #6b6e7a;
    font-size: 13px;
    padding: 24px;
}

QWidget#memoryDetail {
    background-color: #1e1f26;
}

QPushButton#memoryBackButton {
    background-color: transparent;
    color: #4a90e2;
    font-weight: 600;
    padding: 4px 8px;
}

QPushButton#memoryBackButton:hover {
    background-color: #2c2e38;
}

QLabel#memoryDetailCategory {
    color: #4a90e2;
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
}

QLabel#memoryDetailContent {
    color: #e6e6e6;
    font-size: 15px;
    padding: 12px 0;
}

QLabel#memoryDetailMeta {
    color: #6b6e7a;
    font-size: 12px;
}

/* ---------- Voice GUI (v1.2) ---------- */

QWidget#voicePage {
    background-color: #1e1f26;
}

QLabel#voicePageTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}

QLabel#voiceSectionLabel {
    color: #a0a3b0;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
}

QLabel#voiceStatusLabel {
    color: #e6e6e6;
    font-size: 13px;
}

QLabel#voiceErrorLabel {
    color: #e88a8a;
    font-size: 13px;
}

QPushButton#voiceRecordButton {
    padding: 10px 24px;
}

QFrame#voiceTranscriptBox {
    background-color: #2c2e38;
    border: 1px solid #33343f;
    border-radius: 10px;
    min-height: 48px;
}

QLabel#voiceTranscriptContent {
    color: #e6e6e6;
    font-size: 13px;
}

/* ---------- Avatar GUI (v1.3) ---------- */

QWidget#avatarPage {
    background-color: #1e1f26;
}

QLabel#avatarPageTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}

QLabel#avatarSectionLabel {
    color: #a0a3b0;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
}

QLabel#avatarStatusLabel {
    color: #e6e6e6;
    font-size: 13px;
}

QLabel#avatarErrorLabel {
    color: #e0b054;
    font-size: 13px;
}

QFrame#avatarStateCard {
    background-color: #2c2e38;
    border: 1px solid #33343f;
    border-radius: 10px;
    min-height: 32px;
}

QLabel#avatarStateCardContent {
    color: #e6e6e6;
    font-size: 13px;
}

QPushButton#avatarControlButton {
    padding: 8px 20px;
}

/* ---------- Settings GUI (v1.4) ---------- */

QWidget#settingsPage {
    background-color: #1e1f26;
}

QLabel#settingsPageTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}

QLabel#settingsSectionLabel {
    color: #a0a3b0;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    padding-top: 4px;
}

QLabel#settingsFieldLabel {
    color: #e6e6e6;
    font-size: 13px;
}

QLabel#settingsFieldValue {
    color: #a0a3b0;
    font-size: 13px;
}

QLabel#settingsHintLabel {
    color: #e0b054;
    font-size: 12px;
}

QLabel#settingsErrorLabel {
    color: #e88a8a;
    font-size: 13px;
}

QPushButton#settingsSecondaryButton {
    background-color: transparent;
    color: #e6e6e6;
    border: 1px solid #3a3d4a;
}

QPushButton#settingsSecondaryButton:hover {
    background-color: #2c2e38;
}

/* ---------- Vision GUI (v1.5) ---------- */

QWidget#visionPage {
    background-color: #1e1f26;
}

QLabel#visionPageTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}

QLabel#visionSectionLabel {
    color: #a0a3b0;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    padding-top: 4px;
}

QLabel#visionStatusLabel {
    color: #e6e6e6;
    font-size: 15px;
    font-weight: 600;
}

QLabel#visionFieldValue {
    color: #a0a3b0;
    font-size: 13px;
}

QLabel#visionErrorLabel {
    color: #e88a8a;
    font-size: 13px;
}

QFrame#visionCard {
    background-color: #2c2e38;
    border: 1px solid #33343f;
    border-radius: 10px;
    min-height: 40px;
}

QLabel#visionCardContent {
    color: #e6e6e6;
    font-size: 13px;
}

QPushButton#visionSecondaryButton {
    background-color: transparent;
    color: #e6e6e6;
    border: 1px solid #3a3d4a;
}

QPushButton#visionSecondaryButton:hover {
    background-color: #2c2e38;
}

/* ---------- Vision GUI (v1.5.2 — Mode radio buttons) ---------- */

QRadioButton#visionModeRadio {
    color: #e6e6e6;
    font-size: 13px;
    padding: 2px 0px;
    spacing: 8px;
}

QRadioButton#visionModeRadio::indicator {
    width: 14px;
    height: 14px;
}

QLabel#visionStatusLabelAuto {
    color: #7fd48a;
    font-size: 15px;
    font-weight: 700;
}

/* ---------- Routine GUI (v1.6) ---------- */

QWidget#routinePage {
    background-color: #1e1f26;
}

QLabel#routinePageTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}

QLabel#routineSectionLabel {
    color: #a0a3b0;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    padding-top: 4px;
}

QLabel#routineStatusLabel {
    color: #7fd48a;
    font-size: 15px;
    font-weight: 700;
}

QLabel#routineStatusLabelDisabled {
    color: #a0a3b0;
    font-size: 15px;
    font-weight: 700;
}

QLabel#routineErrorLabel {
    color: #e88a8a;
    font-size: 13px;
}

QFrame#routineCard {
    background-color: #2c2e38;
    border: 1px solid #33343f;
    border-radius: 10px;
    min-height: 40px;
}

QLabel#routineCardContent {
    color: #e6e6e6;
    font-size: 13px;
}

QPushButton#routineSecondaryButton {
    background-color: transparent;
    color: #e6e6e6;
    border: 1px solid #3a3d4a;
}

QPushButton#routineSecondaryButton:hover {
    background-color: #2c2e38;
}

/* ---------- Developer Dashboard (v1.7) ---------- */

QDialog#developerDashboard {
    background-color: #1e1f26;
}

QLabel#developerPageTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
}

QLabel#developerTimestampLabel {
    color: #6b6e7a;
    font-size: 11px;
}

QLabel#developerSectionLabel {
    color: #a0a3b0;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    padding-top: 4px;
}

QLabel#developerErrorLabel {
    color: #e88a8a;
    font-size: 13px;
}

QFrame#developerCard {
    background-color: #2c2e38;
    border: 1px solid #33343f;
    border-radius: 10px;
    min-height: 32px;
}

QLabel#developerCardContent {
    color: #e6e6e6;
    font-size: 12px;
}

QPushButton#developerSecondaryButton {
    background-color: transparent;
    color: #e6e6e6;
    border: 1px solid #3a3d4a;
}

QPushButton#developerSecondaryButton:hover {
    background-color: #2c2e38;
}

QScrollArea#developerScrollArea {
    background-color: #1e1f26;
    border: none;
}

QPlainTextEdit#developerLogView {
    background-color: #16171c;
    color: #a0e6a0;
    border: 1px solid #33343f;
    border-radius: 8px;
    font-family: "Consolas", "Menlo", monospace;
    font-size: 11px;
}
"""