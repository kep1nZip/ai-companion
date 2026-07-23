from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
)

AVATAR_DIR = Path(__file__).resolve().parent.parent / "assets" / "avatar"
AVATAR_SIZE = 40

_USER_ICON_PATH = AVATAR_DIR / "icon-user.jpg"
_ARONA_ICON_PATH = AVATAR_DIR / "icon-arona.jpg"


def _load_circular_avatar(path: Path, size: int = AVATAR_SIZE) -> QPixmap:
    """Load gambar dan crop jadi bulat. Fallback ke placeholder abu-abu kalau file tidak ada."""
    source = QPixmap(str(path))

    if source.isNull():
        placeholder = QPixmap(size, size)
        placeholder.fill(Qt.transparent)
        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.gray)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.end()
        return placeholder

    scaled = source.scaled(
        size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )

    x_offset = (scaled.width() - size) // 2
    y_offset = (scaled.height() - size) // 2
    cropped = scaled.copy(x_offset, y_offset, size, size)

    rounded = QPixmap(size, size)
    rounded.fill(Qt.transparent)

    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)

    path_clip = QPainterPath()
    path_clip.addEllipse(0, 0, size, size)
    painter.setClipPath(path_clip)
    painter.drawPixmap(0, 0, cropped)
    painter.end()

    return rounded


class AvatarLabel(QLabel):
    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self.setPixmap(pixmap)
        self.setFixedSize(QSize(AVATAR_SIZE, AVATAR_SIZE))
        self.setAlignment(Qt.AlignTop)


class ChatBubble(QFrame):
    """Satu gelembung pesan, milik Teacher atau Arona."""

    def __init__(self, text: str, is_user: bool):
        super().__init__()
        self.setObjectName("userBubble" if is_user else "aronaBubble")

        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("bubbleLabel")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(label)

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.setMaximumWidth(500)


class ChatArea(QScrollArea):
    """Area chat yang bisa di-scroll, auto-scroll ke pesan terbaru."""

    def __init__(self):
        super().__init__()
        self.setObjectName("chatArea")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.setSpacing(10)
        self._layout.setContentsMargins(16, 16, 16, 16)

        self.setWidget(self._container)

        self._user_avatar = _load_circular_avatar(_USER_ICON_PATH)
        self._arona_avatar = _load_circular_avatar(_ARONA_ICON_PATH)

    def add_message(self, text: str, is_user: bool) -> None:
        bubble = ChatBubble(text, is_user)
        avatar = AvatarLabel(self._user_avatar if is_user else self._arona_avatar)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        if is_user:
            row.addStretch()
            row.addWidget(bubble)
            row.addWidget(avatar)
        else:
            row.addWidget(avatar)
            row.addWidget(bubble)
            row.addStretch()

        row_widget = QWidget()
        row_widget.setLayout(row)
        self._layout.addWidget(row_widget)

        QTimer.singleShot(0, self._scroll_to_bottom)

    def clear_messages(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())