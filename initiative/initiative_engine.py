from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from behavior.behavior_state import BehaviorState
from initiative.initiative_decision import DecisionResult, decide
from initiative.initiative_rules import (
    DecisionContext, DecisionRule, DEFAULT_RULES, DEFAULT_THRESHOLD, check_suppression,
)
from routine.routine_event import RoutineEvent
from vision.vision_context import VisionContext
from config.logger import logger


class InitiativeEngine:
    """Mengumpulkan BehaviorState+VisionContext+RoutineEvent+waktu -> DecisionScore.
    TIDAK PERNAH memanggil Gemini. TIDAK PERNAH memodifikasi BehaviorState/Vision/
    Routine — read-only murni."""

    def __init__(
        self,
        timezone_name: str = "Asia/Jakarta",
        rules: Optional[list[DecisionRule]] = None,
        threshold: float = DEFAULT_THRESHOLD,
    ):
        self._timezone_name = timezone_name
        self._rules = rules or DEFAULT_RULES
        self.threshold = threshold

    def compute(
        self,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
        routine_event: Optional[RoutineEvent] = None,
        is_voice_active: bool = False,
        is_actively_typing: bool = False,
        relevant_memory_count: int = 0,
        conversation_closed: bool = False,
    ) -> DecisionResult:
        suppressed, suppression_reason = check_suppression(vision_context, is_voice_active, is_actively_typing)

        if suppressed:
            logger.info("Suppression: {}", suppression_reason)
            return decide(0.0, self.threshold, [], suppressed=True, suppression_reason=suppression_reason)

        now = datetime.now(ZoneInfo(self._timezone_name))
        ctx = DecisionContext(
            idle_seconds=behavior_state.internal.elapsed_seconds(),
            behavior_state=behavior_state,
            vision_context=vision_context,
            routine_event=routine_event,
            hour=now.hour,
            relevant_memory_count=relevant_memory_count,
            conversation_closed=conversation_closed,
        )

        score = 0.0
        reasons: list[str] = []
        for rule in self._rules:
            reason = rule.evaluate(ctx)
            if reason is not None:
                # v2.7 Phase 3: `get_weight(ctx)` menggantikan `.weight` statis
                # langsung — untuk 6 dari 7 rule di DEFAULT_RULES hasilnya
                # IDENTIK (default `get_weight()` cuma return `self.weight`,
                # lihat DecisionRule di initiative_rules.py). Hanya
                # RoutinePendingRule yang sekarang mengembalikan nilai
                # bervariasi sesuai EventPriority.
                weight = rule.get_weight(ctx)
                score += weight
                sign = "+" if weight >= 0 else ""
                reasons.append(f"{reason} ({sign}{weight:.1f})")

        result = decide(score, self.threshold, reasons)
        logger.info("Decision Score: {:.0f} / threshold {:.0f}", score, self.threshold)
        return result