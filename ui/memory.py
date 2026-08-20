from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QFrame,
    QStackedWidget,
    QSizePolicy,
)

from database.memory_manager import Memory
from ui.memory_service import MemoryService, MemoryReadError
from config.logger import logger


def _format_timestamp(raw: str) -> str:
    """Best-effort format ISO timestamp jadi '17 August 2026'. Kalau parsing
    gagal (format tak terduga), tampilkan apa adanya daripada crash GUI."""
    try:
        return datetime.fromisoformat(raw).strftime("%d %B %Y")
    except Exception:
        return raw


class MemoryCard(QFrame):
    """Satu baris ringkasan memori di list, bisa diklik untuk buka detail."""

    def __init__(self, memory: Memory, on_click: Callable[[Memory], None]):
        super().__init__()
        self.setObjectName("memoryCard")
        self.setCursor(Qt.PointingHandCursor)
        self._memory = memory
        self._on_click = on_click

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        snippet = memory.content if len(memory.content) <= 140 else memory.content[:140] + "…"
        content_label = QLabel(snippet)
        content_label.setObjectName("memoryCardContent")
        content_label.setWordWrap(True)

        meta_label = QLabel(f"{memory.category}  ·  {_format_timestamp(memory.updated_at)}")
        meta_label.setObjectName("memoryCardMeta")

        layout.addWidget(content_label)
        layout.addWidget(meta_label)

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._on_click(self._memory)
        super().mousePressEvent(event)


class MemoryDetailView(QWidget):
    """Tampilan penuh satu memori. Read-only murni — tidak ada tombol edit/hapus
    (Memory GUI Read-Only Policy v1.1)."""

    def __init__(self, on_back: Callable[[], None]):
        super().__init__()
        self.setObjectName("memoryDetail")
        self._on_back = on_back

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        back_button = QPushButton("← Back")
        back_button.setObjectName("memoryBackButton")
        back_button.clicked.connect(self._on_back)
        layout.addWidget(back_button, alignment=Qt.AlignLeft)

        self._category_label = QLabel()
        self._category_label.setObjectName("memoryDetailCategory")
        layout.addWidget(self._category_label)

        self._content_label = QLabel()
        self._content_label.setObjectName("memoryDetailContent")
        self._content_label.setWordWrap(True)
        self._content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._content_label)

        self._meta_label = QLabel()
        self._meta_label.setObjectName("memoryDetailMeta")
        layout.addWidget(self._meta_label)

        layout.addStretch()

    def show_memory(self, memory: Memory) -> None:
        self._category_label.setText(memory.category.capitalize())
        self._content_label.setText(memory.content)
        self._meta_label.setText(
            f"Created: {_format_timestamp(memory.created_at)}   "
            f"Updated: {_format_timestamp(memory.updated_at)}"
        )


class MemoryListView(QWidget):
    """Search bar + refresh + daftar kartu memori + state (loading/empty/error)."""

    def __init__(self, on_select: Callable[[Memory], None]):
        super().__init__()
        self._on_select = on_select

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Memory")
        title.setObjectName("memoryPageTitle")
        layout.addWidget(title)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Cari memori...")
        search_row.addWidget(self._search_box, stretch=1)

        self._search_button = QPushButton("Search")
        search_row.addWidget(self._search_button)

        self._refresh_button = QPushButton("Refresh")
        search_row.addWidget(self._refresh_button)

        layout.addLayout(search_row)

        self._state_label = QLabel("")
        self._state_label.setObjectName("memoryStateLabel")
        self._state_label.setAlignment(Qt.AlignCenter)
        self._state_label.hide()
        layout.addWidget(self._state_label)

        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("memoryListArea")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._list_layout.setSpacing(8)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_area.setWidget(self._list_container)

        layout.addWidget(self._scroll_area, stretch=1)

    # ---------- Wiring exposed to MemoryPage ----------

    def connect_search(self, handler: Callable[[], None]) -> None:
        self._search_button.clicked.connect(handler)
        self._search_box.returnPressed.connect(handler)

    def connect_refresh(self, handler: Callable[[], None]) -> None:
        self._refresh_button.clicked.connect(handler)

    def current_query(self) -> str:
        return self._search_box.text()

    # ---------- Rendering ----------

    def show_loading(self) -> None:
        self._clear_cards()
        self._state_label.setText("Memuat memori...")
        self._state_label.show()

    def show_error(self, message: str) -> None:
        self._clear_cards()
        self._state_label.setText(message)
        self._state_label.show()

    def show_memories(self, memories: list[Memory]) -> None:
        self._clear_cards()
        if not memories:
            self._state_label.setText("Belum ada memori yang tersimpan.")
            self._state_label.show()
            return

        self._state_label.hide()
        for memory in memories:
            self._list_layout.addWidget(MemoryCard(memory, self._on_select))

    def _clear_cards(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


class MemoryPage(QWidget):
    """Halaman Memory — read-only murni. Baca sinkron di GUI thread (SQLite lokal,
    dataset kecil, tanpa bukti butuh worker terpisah — lih. keputusan desain
    v1.1). Tidak pernah memanggil write API MemoryManager/Companion."""

    def __init__(self, memory_service: MemoryService):
        super().__init__()
        self.setObjectName("memoryPage")
        self._service = memory_service
        self._loaded_once = False

        self._stack = QStackedWidget()
        self._list_view = MemoryListView(on_select=self._show_detail)
        self._detail_view = MemoryDetailView(on_back=self._show_list)
        self._stack.addWidget(self._list_view)
        self._stack.addWidget(self._detail_view)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._list_view.connect_search(self._handle_search)
        self._list_view.connect_refresh(self._handle_refresh)

    # ---------- Navigation from window.py ----------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self._load_recent()

    # ---------- Actions ----------

    def _load_recent(self) -> None:
        self._list_view.show_loading()
        try:
            memories = self._service.list_recent()
        except MemoryReadError as e:
            self._list_view.show_error(str(e))
            return
        self._list_view.show_memories(memories)
        logger.info("Memory GUI: {} memori dimuat.", len(memories))

    def _handle_search(self) -> None:
        query = self._list_view.current_query()
        self._list_view.show_loading()
        try:
            memories = self._service.search(query)
        except MemoryReadError as e:
            self._list_view.show_error(str(e))
            return
        self._list_view.show_memories(memories)
        logger.info("Memory GUI: pencarian '{}' -> {} hasil.", query, len(memories))

    def _handle_refresh(self) -> None:
        query = self._list_view.current_query().strip()
        if query:
            self._handle_search()
        else:
            self._load_recent()

    def _show_detail(self, memory: Memory) -> None:
        self._detail_view.show_memory(memory)
        self._stack.setCurrentWidget(self._detail_view)

    def _show_list(self) -> None:
        self._stack.setCurrentWidget(self._list_view)