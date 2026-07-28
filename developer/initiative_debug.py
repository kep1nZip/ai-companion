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
    )