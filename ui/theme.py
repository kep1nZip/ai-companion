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
"""