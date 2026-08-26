from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)

from ai.companion import Companion
from routine.routine_event import RoutineEvent, RoutineEventType
from routine.routine_rules import SuppressionLevel
from config.logger import logger

_DISPLAY_TIMEZONE = ZoneInfo("Asia/Jakarta")  # konsisten dengan ContextBuilder/Vision GUI
_POLL_INTERVAL_MS = 1000  # v1.6 §28: lightweight polling, cuma untuk re-render (lihat catatan di bawah)


def _readable_event_type(event_type: RoutineEventType) -> str:
    return event_type.value.replace("_", " ").title()


def _readable_suppression_level(level: SuppressionLevel) -> str:
    if level == SuppressionLevel.ALL_NON_CRITICAL:
        return "All non-critical routines paused"
    if level == SuppressionLevel.NON_CASUAL:
        return "Non-casual routines paused"
    return level.value


class RoutinePage(QWidget):
    """Halaman Routine — presentation/control layer murni di atas Routine
    System (v0.8) yang SUDAH ADA lewat Companion.get_pending_routine_events()/
    get_last_routine_event()/get_next_routine_schedule()/get_routine_history()/
    get_routine_suppression()/is_routine_enabled()/enable_routine()/
    disable_routine(). TIDAK ADA RoutineEngine/RoutineScheduler kedua, TIDAK
    memanggil Gemini langsung dari GUI, TIDAK PERNAH memutuskan apakah Arona
    bicara (Routine Decision Policy §21 — itu tetap 100% jalur Behavior/
    Initiative/Companion yang sudah ada, RoutinePage cuma observer read-only
    + satu kontrol lifecycle enable/disable).

    Live update: Routine TIDAK memiliki scheduler thread/Qt signal apa pun
    (Routine Independence Policy §4 — backend modules TIDAK PERNAH import Qt).
    Routine.update()/evaluate() HANYA dipanggil reaktif dari Companion.chat()
    (lewat Chat/Voice), bukan dari timer background. Jadi QTimer polling di
    sini (§28: 'lightweight polling' diperbolehkan untuk 'countdown displays'
    dan 'status refreshes') PURELY re-render tampilan dari data yang SUDAH
    ada di backend — TIDAK PERNAH memanggil update()/evaluate() atau logic
    Routine apa pun (§28: 'Polling must never execute Routine logic'). Ini
    murni supaya: (1) countdown cooldown presentation-only tetap jalan real-time
    (§17), dan (2) kalau Teacher chat lewat Chat/Voice page sementara halaman
    Routine ini terbuka, hasilnya ikut terlihat tanpa perlu klik Refresh manual.

    KETERBATASAN DATA YANG DISADARI (bukan disembunyikan, sesuai §19 'do not
    fabricate'):
    - Recent History HANYA berisi event yang benar-benar SELESAI dipakai
      (RoutineHistory.record() cuma dipanggil dari mark_completed()) — backend
      TIDAK menyimpan entri 'Suppressed'/'Skipped' di history sama sekali,
      cuma log teks di logger.info(). Jadi Recent History di sini HANYA
      menampilkan routine yang selesai (✓), bukan mix seperti contoh mockup
      spec yang menyertakan '⏸ Idle Chat Suppressed' — data itu tidak ada di
      backend untuk ditampilkan secara jujur.
    - 'Next Eligible' BUKAN 'jadwal masa depan' bergaya kalender — Routine
      System ini murni reaktif/opportunistic (evaluate() cuma mengecek
      kondisi SAAT DIPANGGIL), tidak ada konsep 'akan trigger jam sekian'.
      Yang ditampilkan adalah kapan tiap event type LEPAS dari cooldown
      (get_next_routine_schedule()) — waktu paling awal di antara semua tipe
      dipilih untuk ditampilkan sebagai 'Next Eligible', TIDAK menjamin
      routine itu benar-benar akan trigger saat itu (masih tergantung time
      window/idle time/suppression saat momen itu tiba — logic itu TETAP
      100% di RoutineEngine, GUI cuma mengurutkan timestamp yang backend
      sudah kembalikan, bukan menduplikasi kondisi trigger)."""

    def __init__(self, companion: Companion):
        super().__init__()
        self.setObjectName("routinePage")
        self._companion = companion

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel("Routine")
        title.setObjectName("routinePageTitle")
        layout.addWidget(title)

        self._error_label = QLabel("")
        self._error_label.setObjectName("routineErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._status_label = QLabel("")
        self._status_label.setObjectName("routineStatusLabel")
        layout.addWidget(self._status_label)

        self._toggle_button = QPushButton("")
        self._toggle_button.setObjectName("routineSecondaryButton")
        self._toggle_button.clicked.connect(self._handle_toggle)
        layout.addWidget(self._toggle_button, alignment=Qt.AlignLeft)

        layout.addWidget(self._section_label("Current Routine"))
        self._current_card = self._make_card()
        layout.addWidget(self._current_card)

        layout.addWidget(self._section_label("Next Eligible"))
        self._next_card = self._make_card()
        layout.addWidget(self._next_card)

        layout.addWidget(self._section_label("Cooldowns"))
        self._cooldown_card = self._make_card()
        layout.addWidget(self._cooldown_card)

        layout.addWidget(self._section_label("Recent History"))
        self._history_card = self._make_card()
        layout.addWidget(self._history_card)

        refresh_row = QPushButton("Refresh")
        refresh_row.setObjectName("routineSecondaryButton")
        refresh_row.clicked.connect(self._handle_refresh)
        layout.addWidget(refresh_row, alignment=Qt.AlignRight)

        layout.addStretch()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._render)

        self._render()

    # ---------- UI helpers ----------

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("routineSectionLabel")
        return label

    def _make_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("routineCard")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)

        label = QLabel("")
        label.setObjectName("routineCardContent")
        label.setWordWrap(True)
        frame_layout.addWidget(label)

        frame._content_label = label  # type: ignore[attr-defined]
        return frame

    def _set_card_text(self, card: QFrame, text: str) -> None:
        card._content_label.setText(text)  # type: ignore[attr-defined]

    # ---------- Lifecycle ----------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._render()
        self._poll_timer.start()
        logger.info("Routine GUI: Routine Page Opened")

    def hideEvent(self, event) -> None:
        self._poll_timer.stop()
        super().hideEvent(event)

    # ---------- Enable / Disable ----------

    def _handle_toggle(self) -> None:
        try:
            if self._companion.is_routine_enabled():
                self._companion.disable_routine()
                logger.info("Routine Disabled")
            else:
                self._companion.enable_routine()
                logger.info("Routine Enabled")
            self._error_label.hide()
        except Exception:
            self._show_error("Routine Unavailable.\n\nPlease Try Again.")
        self._render()

    def _handle_refresh(self) -> None:
        logger.info("Routine GUI: Routine Refresh")
        self._error_label.hide()
        self._render()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    # ---------- Rendering ----------

    def _render(self) -> None:
        try:
            enabled = self._companion.is_routine_enabled()
        except Exception:
            self._show_error("Routine Unavailable.\n\nPlease Try Again.")
            return

        self._status_label.setText("● Enabled" if enabled else "○ Disabled")
        self._status_label.setObjectName("routineStatusLabel" if enabled else "routineStatusLabelDisabled")
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self._toggle_button.setText("Disable Routine" if enabled else "Enable Routine")

        self._render_current(enabled)
        self._render_next_eligible()
        self._render_cooldowns()
        self._render_history()

    def _render_current(self, enabled: bool) -> None:
        if not enabled:
            # v1.6: pending event lama (kalau ada) TIDAK ditampilkan sebagai
            # 'Current' selagi disabled — Companion.chat() tidak akan pernah
            # memakainya selama disabled, jadi menampilkannya di sini
            # berpotensi menyesatkan Teacher (lihat docstring class).
            self._set_card_text(self._current_card, "Routine is disabled. No routine is currently pending.")
            return

        try:
            pending = self._companion.get_pending_routine_events()
        except Exception:
            self._set_card_text(self._current_card, "Routine Unavailable.")
            return

        if not pending:
            self._set_card_text(self._current_card, "No routine currently pending.")
            return

        event = pending[0]
        lines = [
            _readable_event_type(event.event_type),
            f"Priority: {event.priority.name.title()}",
        ]

        try:
            suppression = self._companion.get_routine_suppression()
        except Exception:
            suppression = None
        if suppression is not None:
            sup_type, sup_level = suppression
            lines.append(f"\nLast Suppressed: {_readable_event_type(sup_type)}")
            lines.append(f"Status: Suppressed ({_readable_suppression_level(sup_level)})")

        self._set_card_text(self._current_card, "\n".join(lines))

    def _render_next_eligible(self) -> None:
        try:
            schedule = self._companion.get_next_routine_schedule()
        except Exception:
            self._set_card_text(self._next_card, "Routine Unavailable.")
            return

        if not schedule:
            self._set_card_text(self._next_card, "Not Available")
            return

        # Presentation-only: pilih timestamp PALING AWAL di antara data yang
        # backend kembalikan — TIDAK menghitung/menduplikasi kondisi trigger
        # apa pun (lihat docstring class §15).
        event_type, when = min(schedule.items(), key=lambda item: item[1])
        when_local = when.astimezone(_DISPLAY_TIMEZONE)
        now = datetime.now(_DISPLAY_TIMEZONE)

        if when <= datetime.now(when.tzinfo):
            status = "Ready now (once other conditions are met)"
        else:
            status = when_local.strftime("%d %B %Y, %H:%M:%S")

        self._set_card_text(
            self._next_card,
            f"{_readable_event_type(event_type)}\n{status}",
        )

    def _render_cooldowns(self) -> None:
        try:
            schedule = self._companion.get_next_routine_schedule()
        except Exception:
            self._set_card_text(self._cooldown_card, "Routine Unavailable.")
            return

        if not schedule:
            self._set_card_text(self._cooldown_card, "No cooldown data yet — no routine has triggered this session.")
            return

        now = datetime.now(next(iter(schedule.values())).tzinfo)
        lines = []
        for event_type, cooldown_until in sorted(schedule.items(), key=lambda item: item[1]):
            remaining = cooldown_until - now
            if remaining.total_seconds() <= 0:
                lines.append(f"{_readable_event_type(event_type)}: Ready")
            else:
                total_minutes = int(remaining.total_seconds() // 60)
                hours, minutes = divmod(total_minutes, 60)
                if hours > 0:
                    remaining_text = f"{hours}h {minutes}min remaining"
                else:
                    remaining_text = f"{minutes} min remaining"
                lines.append(f"{_readable_event_type(event_type)}: {remaining_text}")

        self._set_card_text(self._cooldown_card, "\n".join(lines))

    def _render_history(self) -> None:
        try:
            history: list[RoutineEvent] = self._companion.get_routine_history(limit=10)
        except Exception:
            self._set_card_text(self._history_card, "Routine Unavailable.")
            return

        if not history:
            self._set_card_text(self._history_card, "No routine history yet.")
            return

        # Terbaru di atas. SEMUA entri di sini adalah routine yang SELESAI
        # dipakai (✓) — backend tidak menyimpan entri suppressed/skipped di
        # history (lihat docstring class), jadi tidak ada ikon lain yang jujur
        # untuk ditampilkan di sini.
        lines = []
        for event in reversed(history):
            time_str = event.created_at.astimezone(_DISPLAY_TIMEZONE).strftime("%d %b, %H:%M")
            lines.append(f"✓ {_readable_event_type(event.event_type)} — {time_str}")

        self._set_card_text(self._history_card, "\n".join(lines))