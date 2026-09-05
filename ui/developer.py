from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QTabWidget,
    QLineEdit,
    QComboBox,
    QPlainTextEdit,
    QFileDialog,
    QMessageBox,
)

from developer.developer import DeveloperService, DeveloperSnapshot
from config.logger import logger

_DISPLAY_TIMEZONE = ZoneInfo("Asia/Jakarta")
_POLL_INTERVAL_MS = 2000  # v1.7 §19: presentation-only refresh, TIDAK memicu logic apa pun


def _yes_no(value) -> str:
    if value is None:
        return "Not available"
    return "YES" if value else "NO"


def _ready_down(value) -> str:
    if value is None:
        return "Not available"
    return "● Ready" if value else "● Down"


def _fmt(value, suffix: str = "") -> str:
    if value is None:
        return "Not available"
    return f"{value}{suffix}"


class DeveloperDashboard(QDialog):
    """v1.7 — Developer Dashboard. Observability MURNI di atas
    DeveloperService (v0.9.5) yang SUDAH ADA — satu snapshot per render
    (DeveloperService.get_snapshot(), §17-18), TIDAK PERNAH memanggil apa pun
    yang memicu runtime behavior (Vision.refresh(), Routine.update()/
    evaluate(), Initiative.evaluate(), Avatar action, Voice action, Memory
    write, Gemini). Ini "mata", bukan "tangan" — tidak ada satu pun tombol
    kontrol di sini, cuma Refresh (re-render presentation-only) dan Export
    (menulis file lokal dari data yang SAMA persis dengan yang sudah
    ditampilkan, tidak menghitung ulang apa pun).

    Dibuka lewat tombol di Settings page (bukan item sidebar permanen) —
    DEVELOPER_MODE TIDAK ADA di config manapun (dikonfirmasi ulang saat
    inspeksi v1.7, konsisten dengan catatan v1.4 di ui/settings.py), jadi
    TIDAK diciptakan persistence/toggle baru apa pun untuk visibility ini
    (spec §9/§29) — dialog ini murni dipanggil langsung, seperti dialog
    About/Version yang sudah ada di menu Help.

    Live refresh: QTimer polling (§19: 'A presentation-only GUI refresh is
    allowed... The refresh callback MUST NOT trigger application logic').
    Setiap tick cuma memanggil DeveloperService.get_snapshot() ulang (semua
    method di dalamnya murni pembacaan state yang sudah ada — dikonfirmasi
    lewat inspeksi developer/developer.py: get_behavior/get_vision/
    get_routine/get_initiative/get_memory/get_avatar/get_performance/
    get_health semuanya read-only) lalu re-render label. TIDAK ADA
    scheduler/thread baru — timer ini murni GUI-thread, mati saat dialog
    ditutup."""

    def __init__(self, developer_service: DeveloperService, parent=None):
        super().__init__(parent)
        self._service = developer_service
        self.setObjectName("developerDashboard")
        self.setWindowTitle("Developer Dashboard")
        self.setMinimumSize(560, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Developer Dashboard")
        title.setObjectName("developerPageTitle")
        header_row.addWidget(title)
        header_row.addStretch()

        self._timestamp_label = QLabel("")
        self._timestamp_label.setObjectName("developerTimestampLabel")
        header_row.addWidget(self._timestamp_label)
        root.addLayout(header_row)

        self._error_label = QLabel("")
        self._error_label.setObjectName("developerErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        root.addWidget(self._error_label)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, stretch=1)

        self._overview_tab = self._build_overview_tab()
        self._tabs.addTab(self._overview_tab, "Overview")

        self._logs_tab = self._build_logs_tab()
        self._tabs.addTab(self._logs_tab, "Logs")

        button_row = QHBoxLayout()
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("developerSecondaryButton")
        refresh_button.clicked.connect(self._handle_refresh)
        button_row.addWidget(refresh_button)

        export_json_button = QPushButton("Export JSON")
        export_json_button.setObjectName("developerSecondaryButton")
        export_json_button.clicked.connect(self._handle_export_json)
        button_row.addWidget(export_json_button)

        export_md_button = QPushButton("Export Markdown")
        export_md_button.setObjectName("developerSecondaryButton")
        export_md_button.clicked.connect(self._handle_export_markdown)
        button_row.addWidget(export_md_button)

        button_row.addStretch()
        root.addLayout(button_row)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._render)
        self._poll_timer.start()

        self._render()
        logger.info("Developer Dashboard Opened")

    # ---------- Overview tab construction ----------

    def _build_overview_tab(self) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("developerScrollArea")
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        self._overview_layout = QVBoxLayout(content)
        self._overview_layout.setContentsMargins(4, 4, 4, 4)
        self._overview_layout.setSpacing(12)

        self._health_card = self._add_section("System Health")
        self._behavior_card = self._add_section("Behavior")
        self._vision_card = self._add_section("Vision")
        self._routine_card = self._add_section("Routine")
        self._initiative_card = self._add_section("Initiative")
        self._memory_card = self._add_section("Memory")
        self._memory_worker_card = self._add_section("Memory Extraction (Async)")
        self._avatar_card = self._add_section("Avatar")
        self._performance_card = self._add_section("Performance")

        self._overview_layout.addStretch()
        scroll.setWidget(content)
        return container

    def _add_section(self, title: str) -> QFrame:
        label = QLabel(title)
        label.setObjectName("developerSectionLabel")
        self._overview_layout.addWidget(label)

        frame = QFrame()
        frame.setObjectName("developerCard")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)

        content_label = QLabel("")
        content_label.setObjectName("developerCardContent")
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        frame_layout.addWidget(content_label)

        frame._content_label = content_label  # type: ignore[attr-defined]
        self._overview_layout.addWidget(frame)
        return frame

    def _set_card(self, card: QFrame, text: str) -> None:
        card._content_label.setText(text)  # type: ignore[attr-defined]

    # ---------- Logs tab construction ----------

    def _build_logs_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self._log_search_box = QLineEdit()
        self._log_search_box.setPlaceholderText("Search logs...")
        self._log_search_box.returnPressed.connect(self._handle_log_refresh)
        filter_row.addWidget(self._log_search_box, stretch=1)

        self._log_level_combo = QComboBox()
        self._log_level_combo.addItems(["ALL", "INFO", "WARNING", "ERROR"])
        filter_row.addWidget(self._log_level_combo)

        log_refresh_button = QPushButton("Search")
        log_refresh_button.setObjectName("developerSecondaryButton")
        log_refresh_button.clicked.connect(self._handle_log_refresh)
        filter_row.addWidget(log_refresh_button)

        layout.addLayout(filter_row)

        self._log_view = QPlainTextEdit()
        self._log_view.setObjectName("developerLogView")
        self._log_view.setReadOnly(True)
        self._log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self._log_view, stretch=1)

        return container

    def _handle_log_refresh(self) -> None:
        level = self._log_level_combo.currentText()
        level_filter = None if level == "ALL" else level
        search = self._log_search_box.text().strip() or None

        try:
            # v1.7 §24: read-only murni via DeveloperService.get_logs() yang
            # sudah ada — TIDAK PERNAH menulis ke file log dari sini.
            entries = self._service.get_logs(limit=300, level=level_filter, search=search)
        except Exception as e:
            self._log_view.setPlainText(f"Failed to read logs: {e}")
            return

        if not entries:
            self._log_view.setPlainText("No log entries match.")
            return

        lines = [f"{e.timestamp} | {e.level} | {e.module} | {e.message}" for e in entries]
        self._log_view.setPlainText("\n".join(lines))

    # ---------- Actions ----------

    def _handle_refresh(self) -> None:
        logger.info("Developer Dashboard Refresh")
        self._render()

    def _handle_export_json(self) -> None:
        self._export(self._service.export_json, "json", "JSON Files (*.json)")

    def _handle_export_markdown(self) -> None:
        self._export(self._service.export_markdown, "md", "Markdown Files (*.md)")

    def _export(self, export_fn, extension: str, file_filter: str) -> None:
        # v1.7 §25-26: reuse export_json()/export_markdown() yang SUDAH ADA
        # apa adanya — TIDAK mengubah schema, TIDAK menambah field apa pun
        # di jalur export ini. QFileDialog cuma menulis file lokal biasa,
        # BUKAN persistence/config system baru.
        default_name = f"arona_developer_snapshot.{extension}"
        path, _ = QFileDialog.getSaveFileName(self, "Export Developer Snapshot", default_name, file_filter)
        if not path:
            return
        try:
            content = export_fn()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Developer Dashboard Export: {}", path)
            QMessageBox.information(self, "Export Complete", f"Saved to:\n{path}")
        except Exception as e:
            logger.warning("Developer Dashboard export gagal: {}", e)
            QMessageBox.warning(self, "Export Failed", f"Could not save file:\n{e}")

    # ---------- Rendering ----------

    def _render(self) -> None:
        try:
            snapshot = self._service.get_snapshot()
        except Exception as e:
            logger.warning("Developer Dashboard: gagal ambil snapshot: {}", e)
            self._error_label.setText("Developer Tools Unavailable.\n\nPlease Try Again.")
            self._error_label.show()
            return

        self._error_label.hide()
        local_ts = snapshot.timestamp.astimezone(_DISPLAY_TIMEZONE)
        self._timestamp_label.setText(f"Last updated: {local_ts.strftime('%H:%M:%S')}")

        self._render_health(snapshot)
        self._render_behavior(snapshot)
        self._render_vision(snapshot)
        self._render_routine(snapshot)
        self._render_initiative(snapshot)
        self._render_memory(snapshot)
        self._render_memory_worker(snapshot)
        self._render_avatar(snapshot)
        self._render_performance(snapshot)

    def _render_health(self, snapshot: DeveloperSnapshot) -> None:
        h = snapshot.health
        vision_state = snapshot.vision.mode.upper() if snapshot.vision.mode else _ready_down(h.vision)
        routine_state = (
            ("● Enabled" if snapshot.routine.enabled else "● Disabled")
            if snapshot.routine is not None else _ready_down(h.routine)
        )
        avatar_state = snapshot.avatar.connection_state or _ready_down(h.avatar)
        voice_state = snapshot.avatar.voice_state or "Not available"

        lines = [
            f"Gemini: {_ready_down(h.gemini)}",
            f"Behavior: {_ready_down(h.behavior)}",
            f"Memory: {_ready_down(h.memory)}",
            f"Voice: {voice_state}",
            f"Avatar: {avatar_state}",
            f"Vision: {vision_state}",
            f"Routine: {routine_state}",
            f"Initiative: {_ready_down(h.initiative)}",
        ]
        self._set_card(self._health_card, "\n".join(lines))

    def _render_behavior(self, snapshot: DeveloperSnapshot) -> None:
        b = snapshot.behavior
        if b is None:
            self._set_card(self._behavior_card, "Not available")
            return
        lines = [
            f"Emotion: {b.emotion} (intensity {b.emotion_intensity:.2f})",
            f"Mood: {b.mood}",
            f"Energy: {b.energy}",
            f"Curiosity: {b.curiosity}",
            f"Initiative: {b.initiative}",
            "",
            f"Trust: {b.trust}   Comfort: {b.comfort}   Affection: {b.affection}",
            f"Respect: {b.respect}   Familiarity: {b.familiarity}",
        ]
        self._set_card(self._behavior_card, "\n".join(lines))

    def _render_vision(self, snapshot: DeveloperSnapshot) -> None:
        v = snapshot.vision
        lines = [
            # v2.3 §18: baris provider paling atas — Teacher paling sering
            # ingin tahu "yang aktif sekarang Local atau Gemini?" duluan
            # sebelum status mode/freshness (pola sama dengan card Memory
            # Extraction v2.1/v2.2).
            f"Provider: {(v.provider or 'unknown').capitalize()}",
            f"Mode: {v.mode.upper() if v.mode else 'Not available'}",
            f"Fresh: {_yes_no(v.is_fresh)}",
            f"Age: {_fmt(round(v.age_seconds, 1) if v.age_seconds is not None else None, ' s')}",
            f"TTL: {_fmt(v.ttl, ' s')}",
            f"Last Capture: {v.captured_at or 'Not available'}",
            f"Summary available: {_yes_no(v.summary is not None)}",
        ]
        self._set_card(self._vision_card, "\n".join(lines))

    def _render_routine(self, snapshot: DeveloperSnapshot) -> None:
        r = snapshot.routine
        if r is None:
            self._set_card(self._routine_card, "Not available")
            return

        # Next Eligible: sama seperti RoutinePage (v1.6) — timestamp PALING
        # AWAL di antara next_schedule dict, presentation-only, TIDAK
        # menduplikasi kondisi trigger apa pun.
        next_eligible = "Not Available"
        if r.next_schedule:
            earliest_type, earliest_str = min(r.next_schedule.items(), key=lambda kv: kv[1])
            next_eligible = f"{earliest_type} ({earliest_str})"

        suppression = "None"
        if r.last_suppression_type:
            suppression = f"{r.last_suppression_type} ({r.last_suppression_level})"

        lines = [
            f"Enabled: {_yes_no(r.enabled)}",
            f"Current Routine: {r.pending_event_type or 'None'}",
            f"Next Eligible: {next_eligible}",
            f"Cooldown Count: {len(r.next_schedule)}",
            f"Last Suppression: {suppression}",
            f"Recent History Count: {r.recent_history_count}",
        ]
        self._set_card(self._routine_card, "\n".join(lines))

    def _render_initiative(self, snapshot: DeveloperSnapshot) -> None:
        i = snapshot.initiative
        if i is None:
            self._set_card(self._initiative_card, "Not available")
            return
        reasons = ", ".join(i.reasons) if i.reasons else "None"
        lines = [
            f"Score: {i.score:.1f}",
            f"Threshold: {i.threshold:.1f}",
            f"Should Start: {_yes_no(i.should_start)}",
            f"Suppressed: {_yes_no(i.suppressed)}"
            + (f" ({i.suppression_reason})" if i.suppression_reason else ""),
            f"Cooldown Remaining: {_fmt(round(i.cooldown_remaining_seconds, 1) if i.cooldown_remaining_seconds is not None else None, ' s')}",
            f"Budget: {i.hourly_remaining}/hour, {i.daily_remaining}/day remaining",
            f"Reasons: {reasons}",
        ]
        self._set_card(self._initiative_card, "\n".join(lines))

    def _render_memory(self, snapshot: DeveloperSnapshot) -> None:
        m = snapshot.memory
        if m is None:
            self._set_card(self._memory_card, "Not available")
            return
        categories = ", ".join(f"{k}: {v}" for k, v in m.category_counts.items()) or "None"
        lines = [
            f"Total Count: {m.total_count}",
            f"Categories: {categories}",
            f"Internal Bookkeeping Entries (hidden from list): {m.internal_marker_count}",
        ]
        self._set_card(self._memory_card, "\n".join(lines))

    def _render_memory_worker(self, snapshot: DeveloperSnapshot) -> None:
        w = snapshot.memory_worker
        if w is None:
            self._set_card(self._memory_worker_card, "Not available")
            return
        lines = [
            # v2.2: baris provider paling atas — Teacher paling sering ingin
            # tahu "yang aktif sekarang Local atau Gemini?" duluan sebelum
            # angka statistik.
            f"Provider: {(snapshot.memory_provider_name or 'unknown').capitalize()}",
            f"Pending: {w.pending}",
            f"Completed: {w.total_completed}",
            f"Failed: {w.total_failed}",
            f"Last Success: {w.last_success_at or 'None'}",
            f"Last Failure: {w.last_failure_at or 'None'}",
        ]
        self._set_card(self._memory_worker_card, "\n".join(lines))

    def _render_avatar(self, snapshot: DeveloperSnapshot) -> None:
        a = snapshot.avatar
        layers = ", ".join(a.active_animation_layers) if a.active_animation_layers else "None"
        lines = [
            f"Connection: {a.connection_state or 'Not available'}",
            f"Voice State: {a.voice_state or 'Not available'}",
            f"Active Layers: {layers}",
        ]
        self._set_card(self._avatar_card, "\n".join(lines))

    def _render_performance(self, snapshot: DeveloperSnapshot) -> None:
        perf = snapshot.performance
        if not perf:
            self._set_card(self._performance_card, "No performance data yet.")
            return
        lines = []
        for name, m in sorted(perf.items()):
            lines.append(
                f"{name}: last={m.last_ms:.1f}ms  avg={m.avg_ms:.1f}ms  "
                f"min={m.min_ms:.1f}ms  max={m.max_ms:.1f}ms  (n={m.count})"
            )
        self._set_card(self._performance_card, "\n".join(lines))

    # ---------- Lifecycle ----------

    def closeEvent(self, event) -> None:
        self._poll_timer.stop()
        logger.info("Developer Dashboard Closed")
        super().closeEvent(event)