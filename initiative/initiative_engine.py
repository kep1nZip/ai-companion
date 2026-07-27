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
        )

        score = 0.0
        reasons: list[str] = []
        for rule in self._rules:
            reason = rule.evaluate(ctx)
            if reason is not None:
                score += rule.weight
                sign = "+" if rule.weight >= 0 else ""
                reasons.append(f"{reason} ({sign}{rule.weight:.0f})")

        result = decide(score, self.threshold, reasons)
        logger.info("Decision Score: {:.0f} / threshold {:.0f}", score, self.threshold)
        return result