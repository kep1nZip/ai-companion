from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)

from avatar.avatar_manager import AvatarManager, AvatarState
from ui.avatar_worker import AvatarWorker


class AvatarPage(QWidget):
    """Halaman Avatar — presentation/status layer murni di atas AvatarManager +
    AvatarWorker (v0.5/v0.6) yang SUDAH ADA. TIDAK ada AvatarManager kedua,
    TIDAK ada backend VTube Studio baru.

    Kenapa TIDAK ada tombol Connect/Reconnect/Disconnect/Trigger Expression
    (beda dari mockup awal) — hasil inspeksi source langsung:

    - AvatarManager tidak punya connect()/disconnect() manual. Koneksi +
      auto-reconnect sepenuhnya di dalam run_forever() (sudah berjalan sejak
      MainWindow.__init__, sebelum halaman ini pernah dibuka).
    - AvatarManager.stop() BUKAN "Disconnect" yang aman untuk tombol GUI —
      itu permanent shutdown yang dipakai closeEvent aplikasi. Memakainya di
      sini akan mematikan idle animation (blink/breathing) secara permanen
      dan menghentikan AvatarWorker thread tanpa cara restart selain restart
      aplikasi (melanggar kebijakan "jangan merusak idle animation").
    - Tidak ada trigger_expression()/trigger_hotkey() publik yang aman
      dipanggil manual — satu-satunya jalur ke ekspresi (react_to_reply)
      mem-parsing teks balasan asli, memanggilnya manual berarti mensimulasi
      balasan Companion palsu, bukan kontrol GUI.
    - AvatarManager tidak menyimpan "expression/halo terakhir" atau
      "nama model VTS saat ini" sebagai state yang bisa dibaca — jadi baris
      "Emotion"/"Halo"/"Model" di mockup awal tidak ditampilkan (data itu
      tidak ada, menampilkannya berarti mengarang).

    Yang ditampilkan HANYA data yang benar-benar ada: connection state
    (AvatarState) dan animation layers yang sedang aktif (AnimationState),
    keduanya read-only snapshot yang sudah dipakai developer/avatar_debug.py
    sejak v1.0."""

    def __init__(self, avatar_manager: AvatarManager, avatar_worker: AvatarWorker):
        super().__init__()
        self.setObjectName("avatarPage")
        self._avatar_manager = avatar_manager
        self._avatar_worker = avatar_worker

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel("Avatar")
        title.setObjectName("avatarPageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Avatar System")
        subtitle.setObjectName("avatarSectionLabel")
        layout.addWidget(subtitle)

        self._status_label = QLabel("")
        self._status_label.setObjectName("avatarStatusLabel")
        layout.addWidget(self._status_label)

        self._hint_label = QLabel(
            "If Avatar shows Disconnected, please check whether VTube Studio is running."
        )
        self._hint_label.setObjectName("avatarErrorLabel")
        self._hint_label.setWordWrap(True)
        self._hint_label.hide()
        layout.addWidget(self._hint_label)

        layout.addWidget(self._make_section_label("Animation Layers"))
        self._layers_card = self._make_state_card()
        layout.addWidget(self._layers_card)

        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.setObjectName("avatarControlButton")
        self._refresh_button.clicked.connect(self._refresh)
        layout.addWidget(self._refresh_button, alignment=Qt.AlignLeft)

        note = QLabel("No manual avatar controls are currently supported by the backend.")
        note.setObjectName("avatarSectionLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch()

        # Live update: subscribe ke AvatarWorker.state_changed (Qt Signal,
        # multi-subscriber-friendly) — BUKAN avatar_manager.set_state_listener()
        # langsung, karena slot itu sudah dipakai AvatarWorker sendiri sejak
        # __init__. Mendaftar ulang di situ akan membajak listener dan merusak
        # status bar yang sudah ada di MainWindow.
        self._avatar_worker.state_changed.connect(self._on_state_changed)

        self._refresh()

    # ---------- UI helpers ----------

    def _make_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("avatarSectionLabel")
        return label

    def _make_state_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("avatarStateCard")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)

        label = QLabel("")
        label.setObjectName("avatarStateCardContent")
        label.setWordWrap(True)
        frame_layout.addWidget(label)

        frame._content_label = label  # type: ignore[attr-defined]
        return frame

    # ---------- Actions ----------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        """Baca sinkron dari AvatarManager — property read biasa (state,
        animation_state), sama seperti developer/avatar_debug.py sudah
        lakukan sejak v1.0. Tidak ada I/O blocking, tidak perlu worker."""
        self._render_state(self._avatar_manager.state.value)

        layers = sorted(self._avatar_manager.animation_state.active_layers)
        text = ", ".join(layers) if layers else "None"
        self._layers_card._content_label.setText(text)  # type: ignore[attr-defined]

    def _on_state_changed(self, status_text: str) -> None:
        self._render_state(status_text)

    def _render_state(self, status_text: str) -> None:
        self._status_label.setText(f"Status: {status_text}")
        self._hint_label.setVisible(status_text == AvatarState.DISCONNECTED.value)