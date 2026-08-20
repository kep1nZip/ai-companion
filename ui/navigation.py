from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel


class Sidebar(QWidget):
    """Sidebar navigasi permanen. Chat dan Memory sekarang fungsional (v1.1);
    Voice/Avatar/Settings tetap placeholder non-fungsional sampai fiturnya
    benar-benar diimplementasikan sebagai halaman terpisah."""

    navigate_requested = Signal(str)  # "chat" | "memory"

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

        layout.addWidget(self._chat_button)
        layout.addWidget(self._memory_button)
        layout.addWidget(self._make_item("Voice", coming_soon=True))
        layout.addWidget(self._make_item("Avatar", coming_soon=True))

        layout.addStretch()

        layout.addWidget(self._make_item("Settings", coming_soon=True))

        self._chat_button.clicked.connect(lambda: self._select("chat"))
        self._memory_button.clicked.connect(lambda: self._select("memory"))

    def _select(self, page_name: str) -> None:
        self._set_active(self._chat_button if page_name == "chat" else self._memory_button)
        self.navigate_requested.emit(page_name)

    def _set_active(self, active_button: QPushButton) -> None:
        for button in (self._chat_button, self._memory_button):
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