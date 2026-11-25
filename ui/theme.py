"""Single source styling untuk seluruh GUI. Siap diperluas jadi multi-theme di masa depan.

Palet resmi Arona (Blue Archive) — SATU-SATUNYA tempat warna didefinisikan.
Semua QSS di bawah memakai token `@NAMA@` yang diganti saat modul di-load,
jadi mengubah warna cukup edit dict PALETTE ini.

    Sky Blue       #7AC5F8  rambut & mata kanan  -> aksen utama / teks highlight
    Pure White     #F4F7FA  seragam sailor & pita -> teks utama
    Soft Violet    #A394E8  ujung rambut & mata kiri -> aksen sekunder (section, focus)
    Electric Blue  #2898FF  halo & garis seragam  -> aksi utama / item aktif
"""

PALETTE = {
    # ---- warna karakter (resmi) ----
    "SKY": "#7AC5F8",
    "WHITE": "#F4F7FA",
    "VIOLET": "#A394E8",
    "ELECTRIC": "#2898FF",
    # ---- netral gelap bernuansa navy, diturunkan dari Sky/Electric ----
    "BG": "#0D1420",          # background utama
    "BG_DEEP": "#0A101A",     # sidebar, menu, status bar, input row
    "SURFACE": "#152033",     # card / bubble Arona / input
    "SURFACE_HI": "#1C2B42",  # hover / item aktif
    "BORDER": "#223249",
    "BORDER_HI": "#33496A",
    # ---- teks ----
    "TEXT_MUTED": "#9DB2CC",
    "TEXT_DIM": "#66809F",
    "ON_ACCENT": "#06121F",   # teks di atas tombol/bubble berwarna terang
    # ---- status ----
    "OK": "#86E0B0",
    "WARN": "#F0CB86",
    "ERROR": "#F59BAA",
}

_QSS_TEMPLATE = """
/* ---------- Base ---------- */

QWidget {
    font-family: "Segoe UI", "Inter", "Noto Sans", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: @BG@;
}

QToolTip {
    background-color: @SURFACE_HI@;
    color: @WHITE@;
    border: 1px solid @BORDER_HI@;
    padding: 4px 8px;
}

QMenuBar {
    background-color: @BG_DEEP@;
    color: @TEXT_MUTED@;
    border-bottom: 1px solid @BORDER@;
    padding: 2px 4px;
}

QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 6px;
}

QMenuBar::item:selected {
    background-color: @SURFACE_HI@;
    color: @WHITE@;
}

QMenu {
    background-color: @SURFACE@;
    color: @WHITE@;
    border: 1px solid @BORDER_HI@;
    border-radius: 8px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 22px;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: @ELECTRIC@;
    color: @ON_ACCENT@;
}

QMessageBox {
    background-color: @BG@;
}

QMessageBox QLabel {
    color: @WHITE@;
}

/* ---------- Scrollbars ---------- */

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: @BORDER_HI@;
    border-radius: 3px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background: @SKY@;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    background: @BORDER_HI@;
    border-radius: 3px;
    min-width: 32px;
}

QScrollBar::handle:horizontal:hover {
    background: @SKY@;
}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
    border: none;
    width: 0px;
    height: 0px;
}

/* ---------- Sidebar ---------- */

QWidget#sidebar {
    background-color: @BG_DEEP@;
    border-right: 1px solid @BORDER@;
}

QLabel#sidebarTitle {
    color: @SKY@;
    font-size: 18px;
    font-weight: 800;
    padding: 2px 8px 0px 8px;
}

QLabel#sidebarSubtitle {
    color: @VIOLET@;
    font-size: 11px;
    padding: 0px 8px 4px 8px;
}

QPushButton#sidebarItem,
QPushButton#sidebarItemActive {
    text-align: left;
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#sidebarItem {
    color: @TEXT_MUTED@;
}

QPushButton#sidebarItem:hover {
    background-color: @SURFACE@;
    color: @WHITE@;
}

QPushButton#sidebarItemActive {
    background-color: rgba(40, 152, 255, 0.16);
    border-left: 3px solid @ELECTRIC@;
    color: @WHITE@;
    font-weight: 700;
}

/* ---------- Chat ---------- */

QScrollArea#chatArea,
QScrollArea#pageScroll {
    background-color: @BG@;
    border: none;
}

QWidget#pageScrollBody,
QWidget#chatContainer {
    background-color: @BG@;
}

QFrame#userBubble {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                      stop:0 @ELECTRIC@, stop:1 @SKY@);
    border-radius: 14px;
    border-bottom-right-radius: 4px;
}

QFrame#userBubble QLabel {
    color: @ON_ACCENT@;
    font-size: 13px;
    background: transparent;
}

QFrame#aronaBubble {
    background-color: @SURFACE@;
    border: 1px solid @BORDER@;
    border-radius: 14px;
    border-bottom-left-radius: 4px;
}

QFrame#aronaBubble QLabel {
    color: @WHITE@;
    font-size: 13px;
    background: transparent;
}

QWidget#inputRow {
    background-color: @BG_DEEP@;
    border-top: 1px solid @BORDER@;
}

/* ---------- Inputs ---------- */

QLineEdit {
    background-color: @SURFACE@;
    color: @WHITE@;
    border: 1px solid @BORDER@;
    border-radius: 10px;
    padding: 8px 14px;
    min-height: 20px;
    font-size: 13px;
    selection-background-color: @ELECTRIC@;
    selection-color: @ON_ACCENT@;
}

QLineEdit:hover {
    border: 1px solid @BORDER_HI@;
}

QLineEdit:focus {
    border: 1px solid @SKY@;
}

QLineEdit:disabled {
    color: @TEXT_DIM@;
    background-color: @BG_DEEP@;
}

QComboBox {
    background-color: @SURFACE@;
    color: @WHITE@;
    border: 1px solid @BORDER@;
    border-radius: 10px;
    padding: 6px 12px;
    min-height: 22px;
    font-size: 13px;
}

QComboBox:hover {
    border: 1px solid @BORDER_HI@;
}

QComboBox:focus {
    border: 1px solid @SKY@;
}

QComboBox QAbstractItemView {
    background-color: @SURFACE@;
    color: @WHITE@;
    border: 1px solid @BORDER_HI@;
    selection-background-color: @ELECTRIC@;
    selection-color: @ON_ACCENT@;
    outline: none;
}

/* ---------- Buttons ---------- */

QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                      stop:0 @ELECTRIC@, stop:1 @SKY@);
    color: @ON_ACCENT@;
    border: none;
    border-radius: 10px;
    padding: 8px 20px;
    min-height: 20px;
    font-weight: 700;
}

QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                      stop:0 #4AAEFF, stop:1 #A2D8FB);
}

QPushButton:pressed {
    background-color: @ELECTRIC@;
}

QPushButton:disabled {
    background-color: @SURFACE_HI@;
    color: @TEXT_DIM@;
}

QPushButton#micButton {
    background-color: @SURFACE@;
    color: @WHITE@;
    border: 1px solid @BORDER_HI@;
    padding: 8px 0px;
    font-size: 15px;
}

QPushButton#micButton:hover {
    border: 1px solid @SKY@;
    background-color: @SURFACE_HI@;
}

QPushButton#micButton:disabled {
    background-color: @BG_DEEP@;
    border: 1px solid @BORDER@;
    color: @TEXT_DIM@;
}

QPushButton#micButtonRecording {
    background-color: @ERROR@;
    color: @ON_ACCENT@;
    border: 1px solid @ERROR@;
    padding: 8px 0px;
    font-size: 15px;
}

/* ---------- Status bar ---------- */

QStatusBar {
    background-color: @BG_DEEP@;
    color: @TEXT_MUTED@;
    border-top: 1px solid @BORDER@;
}

QStatusBar::item {
    border: none;
}

QLabel#statusPill,
QLabel#statusPillOk,
QLabel#statusPillWarn,
QLabel#statusPillBad {
    font-size: 12px;
    font-weight: 600;
    padding: 1px 12px 1px 6px;
    background: transparent;
}

QLabel#statusPill     { color: @TEXT_MUTED@; }
QLabel#statusPillOk   { color: @OK@; }
QLabel#statusPillWarn { color: @WARN@; }
QLabel#statusPillBad  { color: @TEXT_DIM@; }

/* ---------- Radio / generic ---------- */

QRadioButton {
    color: @WHITE@;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 12px;
    height: 12px;
    border-radius: 8px;
    border: 2px solid @BORDER_HI@;
    background: transparent;
}

QRadioButton::indicator:hover {
    border: 2px solid @SKY@;
}

QRadioButton::indicator:checked {
    border: 2px solid @SKY@;
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                      stop:0 @ELECTRIC@, stop:0.55 @ELECTRIC@,
                                      stop:0.6 @BG@, stop:1 @BG@);
}

QTabWidget::pane {
    border: 1px solid @BORDER@;
    border-radius: 10px;
    background-color: @BG@;
    top: -1px;
}

QTabBar::tab {
    background: transparent;
    color: @TEXT_MUTED@;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}

QTabBar::tab:hover {
    color: @WHITE@;
}

QTabBar::tab:selected {
    color: @SKY@;
    border-bottom: 2px solid @ELECTRIC@;
}

/* ---------- Shared page chrome ----------
   Page title / section label / card dipakai sama oleh semua halaman —
   objectName per-halaman dipertahankan (kode UI tidak diubah). */

QLabel#memoryPageTitle, QLabel#voicePageTitle, QLabel#avatarPageTitle,
QLabel#settingsPageTitle, QLabel#visionPageTitle, QLabel#routinePageTitle,
QLabel#developerPageTitle {
    color: @WHITE@;
    font-size: 22px;
    font-weight: 800;
    padding-bottom: 2px;
}

QLabel#voiceSectionLabel, QLabel#avatarSectionLabel, QLabel#settingsSectionLabel,
QLabel#visionSectionLabel, QLabel#routineSectionLabel, QLabel#developerSectionLabel {
    color: @VIOLET@;
    font-size: 11px;
    font-weight: 700;
    padding-top: 10px;
    border-bottom: 1px solid @BORDER@;
    padding-bottom: 4px;
}

QFrame#memoryCard, QFrame#voiceTranscriptBox, QFrame#avatarStateCard,
QFrame#visionCard, QFrame#routineCard, QFrame#developerCard {
    background-color: @SURFACE@;
    border: 1px solid @BORDER@;
    border-radius: 12px;
}

QFrame#memoryCard:hover {
    border: 1px solid @SKY@;
    background-color: @SURFACE_HI@;
}

QFrame#voiceTranscriptBox { min-height: 48px; }
QFrame#avatarStateCard    { min-height: 32px; }
QFrame#visionCard         { min-height: 40px; }
QFrame#routineCard        { min-height: 40px; }
QFrame#developerCard      { min-height: 32px; }

QLabel#memoryCardContent, QLabel#voiceTranscriptContent, QLabel#avatarStateCardContent,
QLabel#visionCardContent, QLabel#routineCardContent {
    color: @WHITE@;
    font-size: 13px;
    background: transparent;
}

QLabel#developerCardContent {
    color: @WHITE@;
    font-size: 12px;
    background: transparent;
}

QPushButton#settingsSecondaryButton, QPushButton#visionSecondaryButton,
QPushButton#routineSecondaryButton, QPushButton#developerSecondaryButton {
    background-color: transparent;
    color: @WHITE@;
    border: 1px solid @BORDER_HI@;
    font-weight: 600;
}

QPushButton#settingsSecondaryButton:hover, QPushButton#visionSecondaryButton:hover,
QPushButton#routineSecondaryButton:hover, QPushButton#developerSecondaryButton:hover {
    background-color: @SURFACE_HI@;
    border: 1px solid @SKY@;
}

QPushButton#settingsSecondaryButton:disabled, QPushButton#visionSecondaryButton:disabled,
QPushButton#routineSecondaryButton:disabled, QPushButton#developerSecondaryButton:disabled {
    background-color: transparent;
    color: @TEXT_DIM@;
    border: 1px solid @BORDER@;
}

QLabel#voiceErrorLabel, QLabel#settingsErrorLabel, QLabel#visionErrorLabel,
QLabel#routineErrorLabel, QLabel#developerErrorLabel {
    color: @ERROR@;
    font-size: 13px;
}

QLabel#avatarErrorLabel, QLabel#settingsHintLabel {
    color: @WARN@;
    font-size: 12px;
}

/* ---------- Memory GUI (v1.1) ---------- */

QWidget#memoryPage, QWidget#memoryDetail, QWidget#voicePage, QWidget#avatarPage,
QWidget#settingsPage, QWidget#visionPage, QWidget#routinePage {
    background-color: @BG@;
}

QScrollArea#memoryListArea, QScrollArea#developerScrollArea {
    background-color: @BG@;
    border: none;
}

QLabel#memoryCardMeta {
    color: @TEXT_MUTED@;
    font-size: 11px;
}

QLabel#memoryStateLabel {
    color: @TEXT_DIM@;
    font-size: 13px;
    padding: 24px;
}

QPushButton#memoryBackButton {
    background-color: transparent;
    color: @SKY@;
    font-weight: 600;
    padding: 4px 8px;
}

QPushButton#memoryBackButton:hover {
    background-color: @SURFACE@;
}

QLabel#memoryDetailCategory {
    color: @VIOLET@;
    font-size: 12px;
    font-weight: 700;
}

QLabel#memoryDetailContent {
    color: @WHITE@;
    font-size: 15px;
    padding: 12px 0;
}

QLabel#memoryDetailMeta {
    color: @TEXT_DIM@;
    font-size: 12px;
}

/* ---------- Voice GUI (v1.2) ---------- */

QLabel#voiceStatusLabel {
    color: @WHITE@;
    font-size: 13px;
}

QPushButton#voiceRecordButton {
    padding: 10px 24px;
}

/* ---------- Avatar GUI (v1.3) ---------- */

QLabel#avatarStatusLabel {
    color: @WHITE@;
    font-size: 13px;
}

QPushButton#avatarControlButton {
    padding: 8px 20px;
}

/* ---------- Settings GUI (v1.4) ---------- */

QLabel#settingsFieldLabel {
    color: @WHITE@;
    font-size: 13px;
    min-height: 22px;
}

QLabel#settingsFieldValue {
    color: @SKY@;
    font-size: 13px;
    min-height: 22px;
}

/* ---------- Vision GUI (v1.5) ---------- */

QLabel#visionStatusLabel {
    color: @WHITE@;
    font-size: 15px;
    font-weight: 600;
}

QLabel#visionFieldValue {
    color: @TEXT_MUTED@;
    font-size: 13px;
}

QRadioButton#visionModeRadio {
    color: @WHITE@;
    font-size: 13px;
    padding: 3px 0px;
    spacing: 8px;
}

QLabel#visionStatusLabelAuto {
    color: @OK@;
    font-size: 15px;
    font-weight: 700;
}

/* ---------- Routine GUI (v1.6) ---------- */

QLabel#routineStatusLabel {
    color: @OK@;
    font-size: 15px;
    font-weight: 700;
}

QLabel#routineStatusLabelDisabled {
    color: @TEXT_MUTED@;
    font-size: 15px;
    font-weight: 700;
}

/* ---------- Developer Dashboard (v1.7) ---------- */

QLabel#developerTimestampLabel {
    color: @TEXT_DIM@;
    font-size: 11px;
}

QPlainTextEdit#developerLogView {
    background-color: @BG_DEEP@;
    color: @OK@;
    border: 1px solid @BORDER@;
    border-radius: 10px;
    font-family: "Cascadia Mono", "Consolas", "Menlo", monospace;
    font-size: 11px;
    selection-background-color: @ELECTRIC@;
    selection-color: @ON_ACCENT@;
}
"""


def _build_stylesheet(template: str, palette: dict[str, str]) -> str:
    qss = template
    for key, value in palette.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


DARK_STYLESHEET = _build_stylesheet(_QSS_TEMPLATE, PALETTE)
