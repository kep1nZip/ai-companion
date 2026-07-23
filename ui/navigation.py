from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel


class Sidebar(QWidget):
    """Sidebar navigasi permanen. Item masih placeholder (non-fungsional) sesuai spec revisi.
    Nanti tinggal aktifkan tiap item saat fiturnya benar-benar diimplementasikan."""

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

        layout.addWidget(self._make_item("Chat", active=True))
        layout.addWidget(self._make_item("Memory", coming_soon=True))
        layout.addWidget(self._make_item("Voice", coming_soon=True))
        layout.addWidget(self._make_item("Avatar", coming_soon=True))

        layout.addStretch()

        layout.addWidget(self._make_item("Settings", coming_soon=True))

    def _make_item(self, label: str, active: bool = False, coming_soon: bool = False) -> QPushButton:
        text = f"{label}  ·  Coming Soon" if coming_soon else label
        button = QPushButton(text)
        button.setObjectName("sidebarItemActive" if active else "sidebarItem")
        button.setEnabled(False)  # placeholder — belum fungsional
        button.setCursor(Qt.ArrowCursor)
        return button