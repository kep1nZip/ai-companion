from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InitiativeSnapshot:
    score: float
    threshold: float
    should_start: bool
    reasons: list
    suppressed: bool
    suppression_reason: Optional[str]
    hourly_remaining: int
    daily_remaining: int
    cooldown_remaining_seconds: Optional[float]
    # v3.8 Phase 15 (Context-Aware Initiative) — "extend yang sudah ada,
    # bukan bikin sistem observability baru" (spec eksplisit). SEMUA field
    # di bawah murni echo `DecisionResult` (`initiative/initiative_decision.py`,
    # sudah diperluas v3.8) — card Dashboard "Initiative" yang SUDAH ADA
    # sejak awal yang menampilkannya, bukan card/dashboard baru.
    idle_category: Optional[str] = None
    recent_unresolved: bool = False
    recent_closure: bool = False
    recent_correction: bool = False
    anchor_present: bool = False
    conversation_memory_count: int = 0


def build_initiative_snapshot(last_result, budget: dict, cooldowns: dict) -> InitiativeSnapshot:
    cooldown = cooldowns.get("autonomous_conversation")
    return InitiativeSnapshot(
        score=last_result.score if last_result else 0.0,
        threshold=last_result.threshold if last_result else 0.0,
        should_start=last_result.should_start if last_result else False,
        reasons=last_result.reasons if last_result else [],
        suppressed=last_result.suppressed if last_result else False,
        suppression_reason=last_result.suppression_reason if last_result else None,
        hourly_remaining=budget.get("hourly_remaining", 0),
        daily_remaining=budget.get("daily_remaining", 0),
        cooldown_remaining_seconds=cooldown.total_seconds() if cooldown else None,
        idle_category=getattr(last_result, "idle_category", None) if last_result else None,
        recent_unresolved=getattr(last_result, "recent_unresolved", False) if last_result else False,
        recent_closure=getattr(last_result, "recent_closure", False) if last_result else False,
        recent_correction=getattr(last_result, "recent_correction", False) if last_result else False,
        anchor_present=getattr(last_result, "anchor_present", False) if last_result else False,
        conversation_memory_count=(
            getattr(last_result, "conversation_memory_count", 0) if last_result else 0
        ),
    )