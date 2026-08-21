from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel


class Sidebar(QWidget):
    """Sidebar navigasi permanen. Chat/Memory/Voice/Avatar sekarang fungsional
    (v1.1-v1.3); Settings tetap placeholder non-fungsional sampai fiturnya
    benar-benar diimplementasikan sebagai halaman terpisah."""

    navigate_requested = Signal(str)  # "chat" | "memory" | "voice" | "avatar"

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(170)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("ARONA")
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)
        layout.addSpacing(12)

        self._chat_button = self._make_item("Chat", active=True)
        self._memory_button = self._make_item("Memory")
        self._voice_button = self._make_item("Voice")
        self._avatar_button = self._make_item("Avatar")

        layout.addWidget(self._chat_button)
        layout.addWidget(self._memory_button)
        layout.addWidget(self._voice_button)
        layout.addWidget(self._avatar_button)

        layout.addStretch()

        layout.addWidget(self._make_item("Settings", coming_soon=True))

        self._chat_button.clicked.connect(lambda: self._select("chat"))
        self._memory_button.clicked.connect(lambda: self._select("memory"))
        self._voice_button.clicked.connect(lambda: self._select("voice"))
        self._avatar_button.clicked.connect(lambda: self._select("avatar"))

    def _select(self, page_name: str) -> None:
        self._set_active(self._button_for(page_name))
        self.navigate_requested.emit(page_name)

    def _button_for(self, page_name: str) -> QPushButton:
        return {
            "chat": self._chat_button,
            "memory": self._memory_button,
            "voice": self._voice_button,
            "avatar": self._avatar_button,
        }[page_name]

    def _set_active(self, active_button: QPushButton) -> None:
        for button in (self._chat_button, self._memory_button, self._voice_button, self._avatar_button):
            is_active = button is active_button
            button.setObjectName("sidebarItemActive" if is_active else "sidebarItem")
            button.style().unpolish(button)
            button.style().polish(button)

    def _make_item(self, label: str, active: bool = False, coming_soon: bool = False) -> QPushButton:
        text = f"{label}  ·  Coming Soon" if coming_soon else label
        button = QPushButton(text)
        button.setObjectName("sidebarItemActive" if active else "sidebarItem")

        if coming_soon:
            button.setEnabled(False)
            button.setCursor(Qt.ArrowCursor)
        else:
            button.setCursor(Qt.PointingHandCursor)

        return button