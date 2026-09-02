from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json

from developer.avatar_debug import AvatarSnapshot, build_avatar_snapshot
from developer.behavior_debug import BehaviorSnapshot, build_behavior_snapshot
from developer.initiative_debug import InitiativeSnapshot, build_initiative_snapshot
from developer.log_viewer import LogEntry, read_logs
from developer.memory_debug import MemorySnapshot, build_memory_snapshot
from developer.performance_debug import MetricSnapshot, PerformanceTracker
from developer.routine_debug import RoutineSnapshot, build_routine_snapshot
from developer.vision_debug import VisionSnapshot, build_vision_snapshot
from ai.memory_worker import MemoryWorkerStatus
from config.constants import LOG_DIR, LOG_FILE
from config.logger import logger

from avatar.avatar_manager import AvatarState

@dataclass(frozen=True)
class HealthStatus:
    """System Health (rekomendasi GPT #2)."""

    behavior: bool
    vision: bool
    routine: bool
    initiative: bool
    memory: bool
    avatar: bool
    gemini: bool


@dataclass(frozen=True)
class DeveloperSnapshot:
    """Facade result (rekomendasi GPT #3) — SATU object gabungan, dibangun sekali
    oleh get_snapshot(), bukan GUI manggil 8 method satu-satu."""

    behavior: Optional[BehaviorSnapshot]
    vision: VisionSnapshot
    routine: Optional[RoutineSnapshot]
    initiative: Optional[InitiativeSnapshot]
    memory: Optional[MemorySnapshot]
    memory_worker: Optional[MemoryWorkerStatus]
    memory_provider_name: Optional[str]
    avatar: AvatarSnapshot
    performance: dict
    health: HealthStatus
    timestamp: datetime


class DeveloperService:
    """Public API Developer Tools — Observability Layer (rekomendasi GPT). READ-ONLY
    MURNI: tidak pernah memanggil method yang memodifikasi state subsystem apa pun
    (mis. clear_routine_queue(), manual_override(), dsb TIDAK PERNAH dipanggil di sini).
    Semua data lewat public API Companion, plus AvatarManager/VoiceManager yang
    di-inject read-only dari ui/ (Avatar Independence Policy: keduanya bukan milik
    Companion)."""

    def __init__(
        self,
        companion,
        avatar_manager=None,
        voice_manager=None,
        performance_tracker: Optional[PerformanceTracker] = None,
    ):
        self._companion = companion
        self._avatar_manager = avatar_manager
        self._voice_manager = voice_manager
        self._performance_tracker = performance_tracker or PerformanceTracker()

    # ---------- Public API (sesuai spec) ----------

    def get_behavior(self) -> Optional[BehaviorSnapshot]:
        try:
            return build_behavior_snapshot(self._companion.current_behavior_state())
        except Exception as e:
            logger.warning("Developer: gagal ambil behavior snapshot: {}", e)
            return None

    def get_vision(self) -> VisionSnapshot:
        try:
            mode = self._companion.get_vision_mode()
            return build_vision_snapshot(self._companion.current_vision_context(), mode=mode)
        except Exception as e:
            logger.warning("Developer: gagal ambil vision snapshot: {}", e)
            return build_vision_snapshot(None)

    def get_routine(self) -> Optional[RoutineSnapshot]:
        try:
            pending = self._companion.get_pending_routine_events()
            last = self._companion.get_last_routine_event()
            schedule = self._companion.get_next_routine_schedule()
            enabled = self._companion.is_routine_enabled()
            suppression = self._companion.get_routine_suppression()
            history_count = len(self._companion.get_routine_history())
            return build_routine_snapshot(
                pending, last, schedule,
                enabled=enabled,
                last_suppression=suppression,
                recent_history_count=history_count,
            )
        except Exception as e:
            logger.warning("Developer: gagal ambil routine snapshot: {}", e)
            return None

    def get_initiative(self) -> Optional[InitiativeSnapshot]:
        try:
            last_result = self._companion.get_last_initiative_result()
            budget = self._companion.get_initiative_budget()
            cooldowns = self._companion.get_initiative_cooldowns()
            return build_initiative_snapshot(last_result, budget, cooldowns)
        except Exception as e:
            logger.warning("Developer: gagal ambil initiative snapshot: {}", e)
            return None

    def get_memory(self, limit: int = 50) -> Optional[MemorySnapshot]:
        try:
            memories = self._companion.list_memories(limit=limit)
            return build_memory_snapshot(memories)
        except Exception as e:
            logger.warning("Developer: gagal ambil memory snapshot: {}", e)
            return None

    def get_memory_worker(self) -> Optional[MemoryWorkerStatus]:
        """v2.1 §21: read-only murni — cuma memanggil
        Companion.get_memory_worker_status() (yang sendiri cuma baca angka
        dari MemoryExtractionWorker), TIDAK PERNAH memicu extraction/
        submit apa pun."""
        try:
            return self._companion.get_memory_worker_status()
        except Exception as e:
            logger.warning("Developer: gagal ambil status memory worker: {}", e)
            return None

    def get_memory_provider_name(self) -> Optional[str]:
        """v2.2 §21: read-only murni — "local" | "gemini" | None (kalau
        gagal ambil)."""
        try:
            return self._companion.get_memory_provider_name()
        except Exception as e:
            logger.warning("Developer: gagal ambil nama memory provider: {}", e)
            return None

    def get_avatar(self) -> AvatarSnapshot:
        try:
            return build_avatar_snapshot(self._avatar_manager, self._voice_manager)
        except Exception as e:
            logger.warning("Developer: gagal ambil avatar snapshot: {}", e)
            return build_avatar_snapshot(None, None)

    def get_performance(self) -> dict:
        return self._performance_tracker.snapshot()

    def get_logs(self, limit: int = 200, level: Optional[str] = None, search: Optional[str] = None) -> list[LogEntry]:
        return read_logs(Path(LOG_DIR) / LOG_FILE, limit=limit, level_filter=level, search=search)

    # ---------- System Health (rekomendasi GPT #2) ----------

    def get_health(self) -> HealthStatus:
        """System Health — best-effort read-only check, bukan live probe. `gemini`
        di sini adalah PROXY (disamakan dengan behavior_ok), bukan pengecekan
        langsung ke Gemini API, karena Developer Tools dilarang mengirim request
        Gemini sungguhan (Read-Only Policy)."""
        behavior_snapshot = self.get_behavior()
        memory_snapshot = self.get_memory(limit=1)
        avatar_snapshot = self.get_avatar()

        return HealthStatus(
            behavior=behavior_snapshot is not None,
            vision=self._companion is not None,
            routine=self.get_routine() is not None,
            initiative=self.get_initiative() is not None,
            memory=memory_snapshot is not None,
            avatar=avatar_snapshot.connection_state == AvatarState.READY.value,
            gemini=behavior_snapshot is not None,
        )

    # ---------- Facade (rekomendasi GPT #3) ----------

    def get_snapshot(self) -> DeveloperSnapshot:
        return DeveloperSnapshot(
            behavior=self.get_behavior(),
            vision=self.get_vision(),
            routine=self.get_routine(),
            initiative=self.get_initiative(),
            memory=self.get_memory(),
            memory_worker=self.get_memory_worker(),
            memory_provider_name=self.get_memory_provider_name(),
            avatar=self.get_avatar(),
            performance=self.get_performance(),
            health=self.get_health(),
            timestamp=datetime.now(timezone.utc),
        )

    # ---------- Export (rekomendasi GPT #4) ----------

    def export_json(self) -> str:
        return json.dumps(asdict(self.get_snapshot()), indent=2, default=str, ensure_ascii=False)

    def export_markdown(self) -> str:
        s = self.get_snapshot()
        lines = [f"# Arona Developer Snapshot — {s.timestamp.isoformat()}", "", "## System Health"]
        lines += [f"- {k.capitalize()}: {'✓ OK' if v else '✗ DOWN'}" for k, v in asdict(s.health).items()]

        for title, obj in [
            ("Behavior", s.behavior), ("Vision", s.vision), ("Routine", s.routine),
            ("Initiative", s.initiative), ("Memory", s.memory),
            ("Memory Worker", s.memory_worker), ("Avatar", s.avatar),
        ]:
            if obj is None:
                continue
            lines += ["", f"## {title}"] + [f"- {k}: {v}" for k, v in asdict(obj).items()]
            if title == "Memory Worker" and s.memory_provider_name is not None:
                # v2.2: memory_provider_name adalah str biasa (bukan
                # dataclass) — tidak bisa lewat asdict() seperti field lain
                # di loop ini, jadi ditambahkan sebagai baris terpisah,
                # tetap di bawah section "Memory Worker" yang sama.
                lines += [f"- provider: {s.memory_provider_name}"]

        lines += ["", "## Performance"]
        lines += [
            f"- {name}: avg={m.avg_ms:.1f}ms min={m.min_ms:.1f}ms max={m.max_ms:.1f}ms count={m.count}"
            for name, m in s.performance.items()
        ]

        return "\n".join(lines)