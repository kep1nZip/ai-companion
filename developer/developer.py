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
from config.constants import LOG_DIR, LOG_FILE, TTS_MODEL_NAME
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
    # v2.4 Phase 2 (Runtime Observability) — target Provider Map §8 yang
    # SEBELUMNYA belum ada sama sekali (6 dari 8 field): AI Provider/Model,
    # Memory Model, Vision Model, TTS Provider/Model. `vision.provider` dan
    # `vision.model` sudah ikut lewat `vision` di atas (v2.3/v2.4), jadi
    # TIDAK diduplikasi jadi field terpisah di sini.
    ai_provider_name: Optional[str]
    ai_model_name: Optional[str]
    memory_model_name: Optional[str]
    tts_provider_name: str
    tts_model_name: str
    # v2.6 Phase 10 (Observability) — Optional[dict] karena
    # `get_context_debug_snapshot()` (ai/companion.py) tidak selalu ada di
    # versi Companion lama/test yang belum diupdate; None ditangani sama
    # seperti field observability lain di file ini (tampil "unknown"/"N/A").
    context_debug: Optional[dict]
    # v3.0 Phase 10 (Item F) — pola IDENTIK context_debug (Optional[dict]
    # generik, nol perubahan skema besar diperlukan untuk field baru di
    # dalamnya nanti).
    personalization_debug: Optional[dict]
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
            provider = self._companion.get_vision_provider_name()
            model = self._companion.get_vision_model_name()
            return build_vision_snapshot(
                self._companion.current_vision_context(), mode=mode, provider=provider, model=model
            )
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

    def get_ai_provider_name(self) -> Optional[str]:
        """v2.4 Phase 2: read-only murni — pola IDENTIK
        get_memory_provider_name() di atas."""
        try:
            return self._companion.get_ai_provider_name()
        except Exception as e:
            logger.warning("Developer: gagal ambil nama AI provider: {}", e)
            return None

    def get_ai_model_name(self) -> Optional[str]:
        try:
            return self._companion.get_ai_model_name()
        except Exception as e:
            logger.warning("Developer: gagal ambil nama AI model: {}", e)
            return None

    def get_memory_model_name(self) -> Optional[str]:
        try:
            return self._companion.get_memory_model_name()
        except Exception as e:
            logger.warning("Developer: gagal ambil nama memory model: {}", e)
            return None

    def get_tts_provider_name(self) -> str:
        """v2.4 Phase 2: TTS TIDAK PUNYA provider selection (§16 spec v2.4 —
        tetap Gemini, tidak dipindah ke Local dalam v2.4) — jadi ini BUKAN
        passthrough ke Companion (Companion sama sekali tidak tahu soal TTS,
        Avatar Independence Policy), melainkan literal tetap "gemini", untuk
        kelengkapan Dashboard sesuai target Provider Map §8."""
        return "gemini"

    def get_tts_model_name(self) -> str:
        """v2.4 Phase 2: baca langsung dari constant yang sudah ada
        (config/constants.py::TTS_MODEL_NAME) — TIDAK ada konfigurasi baru."""
        return TTS_MODEL_NAME

    def get_context_debug(self) -> Optional[dict]:
        """v2.6 Phase 10: read-only passthrough ke
        Companion.get_context_debug_snapshot(). Pola try/except IDENTIK
        getter observability lain di file ini."""
        try:
            return self._companion.get_context_debug_snapshot()
        except Exception as e:
            logger.warning("Developer: gagal ambil context debug snapshot: {}", e)
            return None

    def get_personalization_debug(self) -> Optional[dict]:
        """v3.0 Phase 10 (Item F): read-only passthrough ke
        Companion.get_personalization_debug_snapshot(). Pola try/except
        IDENTIK get_context_debug() di atas."""
        try:
            return self._companion.get_personalization_debug_snapshot()
        except Exception as e:
            logger.warning("Developer: gagal ambil personalization debug snapshot: {}", e)
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
            ai_provider_name=self.get_ai_provider_name(),
            ai_model_name=self.get_ai_model_name(),
            memory_model_name=self.get_memory_model_name(),
            tts_provider_name=self.get_tts_provider_name(),
            tts_model_name=self.get_tts_model_name(),
            context_debug=self.get_context_debug(),
            personalization_debug=self.get_personalization_debug(),
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

        # v2.4 Phase 2: section "Providers" baru — satu tempat gabungan
        # untuk 8 field target Provider Map §8 (AI/Memory/Vision/TTS x
        # Provider/Model). Vision Provider/Model TETAP juga tampil di
        # section "Vision" di bawah (tidak dihapus dari sana) — section ini
        # murni ringkasan tambahan, bukan pengganti.
        lines += [
            "", "## Providers",
            f"- Language Provider: {(s.ai_provider_name or 'unknown').capitalize()}",
            f"- Language Model: {s.ai_model_name or 'unknown'}",
            f"- Memory Provider: {(s.memory_provider_name or 'unknown').capitalize()}",
            f"- Memory Model: {s.memory_model_name or 'unknown'}",
            f"- Vision Provider: {(s.vision.provider or 'unknown').capitalize()}",
            f"- Vision Model: {s.vision.model or 'unknown'}",
            f"- TTS Provider: {s.tts_provider_name.capitalize()}",
            f"- TTS Model: {s.tts_model_name}",
        ]

        # v2.6 Phase 10 — section "Context" baru. `context_debug` bisa None
        # (Companion lama/test yang belum punya get_context_debug_snapshot())
        # — ditangani sama seperti field observability lain di file ini.
        cd = s.context_debug
        cap_text = "unbounded (default)" if not cd or cd.get("history_cap") is None else str(cd["history_cap"])
        lines += [
            "", "## Context",
            f"- History Messages: {cd['history_message_count'] if cd else 'unknown'} (cap: {cap_text})",
            f"- Vision: {'Fresh' if cd and cd.get('vision_fresh') else 'Not available'}",
            f"- Active Memory Count (total di DB): {cd['active_memory_count'] if cd and cd.get('active_memory_count') is not None else 'unknown'}",
            f"- Recent Turns Used: {cd['recent_turns_used'] if cd and cd.get('recent_turns_used') is not None else 'unknown'}",
            f"- History Filtered: {cd['history_filtered'] if cd and cd.get('history_filtered') is not None else 'unknown'}",
            f"- Conversation Closure: {'Yes' if cd and cd.get('conversation_closed') else 'No'}",
            f"- History Characters: {cd['history_characters'] if cd and cd.get('history_characters') is not None else 'unknown'}",
            f"- Estimated Context Size: ~{cd['estimated_context_tokens']} tokens ({cd['estimated_total_characters']} chars, KASAR — bukan tokenizer sungguhan)" if cd and cd.get('estimated_total_characters') is not None else "- Estimated Context Size: unknown",
            f"- Context Assembly Latency: {cd['context_assembly_latency_ms']:.1f} ms (avg)" if cd and cd.get('context_assembly_latency_ms') is not None else "- Context Assembly Latency: belum ada data (belum pernah chat sejak app dibuka)",
            f"- Provider Generation Latency: {cd['llm_latency_ms']:.1f} ms (avg)" if cd and cd.get('llm_latency_ms') is not None else "- Provider Generation Latency: belum ada data",
        ]

        # v3.0 Phase 10 (Item F) — SEMUA field di bawah "sinyal yang
        # TERSEDIA", BUKAN "diterapkan" (§7 Audit v3.0: klaim "applied"
        # berisiko fabricated telemetry karena kita tidak pernah tahu pasti
        # LLM benar-benar memakainya).
        pd = s.personalization_debug
        lines += [
            "", "## Personalization",
            f"- Relationship: Trust {pd['relationship_trust']} / Comfort {pd['relationship_comfort']} / Affection {pd['relationship_affection']} / Respect {pd['relationship_respect']} / Familiarity {pd['relationship_familiarity']} (avg {pd['relationship_average']})" if pd else "- Relationship: unknown",
            f"- Emotion: {pd['emotion_current']}" if pd else "- Emotion: unknown",
            f"- Energy: {pd['energy_current']}" if pd else "- Energy: unknown",
            f"- Relevant Preference Count: {pd['relevant_preference_count']}" if pd else "- Relevant Preference Count: unknown",
            f"- Response Style Signal: {pd['response_style_signal'] or 'None detected'}" if pd else "- Response Style Signal: unknown",
            f"- Personalization Signal Available: {'Yes' if pd and pd.get('personalization_signal_available') else 'No'}",
        ]

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