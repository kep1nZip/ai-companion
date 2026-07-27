from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from behavior.behavior_state import BehaviorState
from initiative.initiative_decision import DecisionResult, decide
from initiative.initiative_engine import InitiativeEngine
from initiative.initiative_history import InitiativeHistory
from initiative.initiative_rules import DecisionRule, DEFAULT_THRESHOLD
from routine.routine_event import RoutineEvent
from vision.vision_context import VisionContext
from database.memory_manager import MemoryManager
from config.logger import logger


class Initiative:
    """Public API Autonomous/Initiative System. Satu-satunya titik masuk yang
    boleh dipanggil Companion (Autonomous Independence Policy). Final output
    SELALU YES/NO (should_start) — TIDAK PERNAH menghasilkan teks balasan."""

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        timezone_name: str = "Asia/Jakarta",
        threshold: float = DEFAULT_THRESHOLD,
        rules: Optional[list[DecisionRule]] = None,
        max_per_hour: int = 3,
        max_per_day: int = 10,
        cooldown_minutes: float = 45.0,
    ):
        self._timezone_name = timezone_name
        self._history = InitiativeHistory(
            memory_manager=memory_manager,
            max_per_hour=max_per_hour,
            max_per_day=max_per_day,
            cooldown=timedelta(minutes=cooldown_minutes),
        )
        self._engine = InitiativeEngine(timezone_name=timezone_name, rules=rules, threshold=threshold)
        self._last_result: Optional[DecisionResult] = None

    def _now(self) -> datetime:
        return datetime.now(ZoneInfo(self._timezone_name))

    def update(
        self,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
        routine_event: Optional[RoutineEvent] = None,
        is_voice_active: bool = False,
        is_actively_typing: bool = False,
    ) -> DecisionResult:
        """Hitung ulang decision. Cooldown & Budget dicek SEBAGAI HARD GATE
        (sama level dengan Suppression) SEBELUM scoring — Conversation Budget
        (rekomendasi GPT #3) mencegah Arona terlalu sering 'minta' memulai obrolan."""
        now = self._now()

        if self._history.in_cooldown(now):
            result = decide(0.0, self._engine.threshold, [], suppressed=True,
                             suppression_reason="Masih dalam cooldown percakapan otonom")
        elif self._history.budget_exceeded(now):
            result = decide(0.0, self._engine.threshold, [], suppressed=True,
                             suppression_reason="Budget percakapan otonom hari ini/jam ini sudah habis")
        else:
            result = self._engine.compute(
                behavior_state, vision_context, routine_event, is_voice_active, is_actively_typing,
            )

        self._last_result = result
        return result

    def evaluate(self, *args, **kwargs) -> DecisionResult:
        """Alias eksplisit sesuai Public API spec — sama seperti update()."""
        return self.update(*args, **kwargs)

    def should_start(self) -> bool:
        return self._last_result.should_start if self._last_result else False

    def mark_started(self) -> None:
        self._history.record_start(self._now())

    def get_last_score(self) -> float:
        return self._last_result.score if self._last_result else 0.0

    # ---------- Developer Metrics API (rekomendasi GPT #4, backend-only, siap v0.9.5) ----------

    def get_current_score(self) -> float:
        return self.get_last_score()

    def get_last_result(self) -> Optional[DecisionResult]:
        return self._last_result

    def get_active_suppressions(self) -> list[str]:
        if self._last_result and self._last_result.suppressed and self._last_result.suppression_reason:
            return [self._last_result.suppression_reason]
        return []

    def get_remaining_budget(self) -> dict[str, int]:
        return self._history.remaining_budget(self._now())

    def get_cooldowns(self) -> dict[str, Optional[timedelta]]:
        return {"autonomous_conversation": self._history.cooldown_remaining(self._now())}