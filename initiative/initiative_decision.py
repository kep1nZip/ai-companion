from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class DecisionResult:
    """DecisionReason (rekomendasi GPT #1) — bukan cuma True/False, tapi skor,
    threshold, dan daftar alasan yang bisa langsung dipakai Developer Panel (v0.9.5)
    tanpa perlu rekonstruksi ulang dari log."""

    should_start: bool
    score: float
    threshold: float
    reasons: list[str] = field(default_factory=list)
    suppressed: bool = False
    suppression_reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def decide(
    score: float,
    threshold: float,
    reasons: list[str],
    suppressed: bool = False,
    suppression_reason: str | None = None,
) -> DecisionResult:
    if suppressed:
        return DecisionResult(
            should_start=False, score=0.0, threshold=threshold,
            reasons=[], suppressed=True, suppression_reason=suppression_reason,
        )
    return DecisionResult(
        should_start=score >= threshold, score=score, threshold=threshold, reasons=reasons,
    )