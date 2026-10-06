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
        idle_category: Optional[str] = None,
        recent_unresolved: bool = False,
        recent_correction: bool = False,
        conversation_memory_count: int = 0,
        anchor_present: bool = False,
    ) -> DecisionResult:
        """v3.8 Phase 1/2 — 5 parameter BARU di akhir, SEMUA opsional dengan
        default backward-compat (pemanggil lama tanpa v3.8 TIDAK PERLU
        diubah). `idle_category` MURNI informasional untuk observability
        (lihat `DecisionContext.anchor_present` docstring — pola IDENTIK
        field `hour` yang sudah ada sejak awal dan tidak dikonsumsi rule
        apa pun) — scoring idle TETAP berbasis `idle_seconds` detik seperti
        sebelumnya (`IdleRule`/`RecentInteractionPenaltyRule`/
        `ReturningAfterGapRule`, TIDAK diubah), `idle_category` dihitung
        Companion lewat `categorize_continuity()` (v3.1, `ai/context_
        builder.py`) yang SUDAH ADA — Initiative TIDAK mengimpor ulang/
        menduplikasi kalkulator idle itu sendiri."""
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
            recent_unresolved=recent_unresolved,
            recent_correction=recent_correction,
            conversation_memory_count=conversation_memory_count,
            anchor_present=anchor_present,
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

        result = decide(
            score, self.threshold, reasons,
            idle_category=idle_category,
            recent_unresolved=recent_unresolved,
            recent_closure=conversation_closed,
            recent_correction=recent_correction,
            anchor_present=anchor_present,
            conversation_memory_count=conversation_memory_count,
        )
        logger.info("Decision Score: {:.0f} / threshold {:.0f}", score, self.threshold)
        return result