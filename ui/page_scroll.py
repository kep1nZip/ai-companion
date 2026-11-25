from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget


def make_scrollable(page: QWidget) -> QScrollArea:
    """Bungkus satu halaman supaya BISA di-scroll kalau window terlalu kecil.

    Sebelumnya halaman dengan banyak baris (Settings, Vision, Routine) cuma
    "diperas" oleh layout ketika window di-restore ke ukuran kecil — teks
    kepotong, combo box kosong, tombol gepeng. Dengan wrapper ini halaman
    selalu mendapat tinggi minimumnya sendiri; kalau tidak muat, muncul
    scrollbar (bukan kepotong). Halaman aslinya TIDAK diubah sama sekali —
    objek yang sama, signal/slot yang sama, cuma dipasang di dalam QScrollArea.
    """
    scroll = QScrollArea()
    scroll.setObjectName("pageScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    page.setAttribute(Qt.WA_StyledBackground, True)
    scroll.setWidget(page)
    return scroll
