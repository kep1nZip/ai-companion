from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class DecisionResult:
    """DecisionReason (rekomendasi GPT #1) — bukan cuma True/False, tapi skor,
    threshold, dan daftar alasan yang bisa langsung dipakai Developer Panel (v0.9.5)
    tanpa perlu rekonstruksi ulang dari log.

    v3.8 Phase 15 (Initiative Decision Explanation) — 6 field evidence BARU
    di bawah, SEMUA default backward-compat (`None`/`False`/`0`). Spec:
    "If the current Initiative architecture already exposes a decision
    snapshot, extend it rather than creating a new system" — `DecisionResult`
    SUDAH jadi "decision snapshot" itu sejak awal (dipakai Developer
    Dashboard lewat `developer/initiative_debug.py`), jadi diperluas DI
    SINI, bukan bikin struktur observability baru. SEMUA field murni echo
    evidence deterministik dari `DecisionContext` (`initiative_rules.py`)
    yang SUDAH dihitung `InitiativeEngine.compute()` — TIDAK ADA skor
    confidence buatan (spec §19: "Good: Relevant Memories: 3. Bad: Arona
    is 86% confident...")."""

    should_start: bool
    score: float
    threshold: float
    reasons: list[str] = field(default_factory=list)
    suppressed: bool = False
    suppression_reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # v3.8 — echo `DecisionContext` evidence fields (lihat initiative_rules.py)
    idle_category: str | None = None
    recent_unresolved: bool = False
    recent_closure: bool = False
    recent_correction: bool = False
    anchor_present: bool = False
    conversation_memory_count: int = 0


def decide(
    score: float,
    threshold: float,
    reasons: list[str],
    suppressed: bool = False,
    suppression_reason: str | None = None,
    idle_category: str | None = None,
    recent_unresolved: bool = False,
    recent_closure: bool = False,
    recent_correction: bool = False,
    anchor_present: bool = False,
    conversation_memory_count: int = 0,
) -> DecisionResult:
    if suppressed:
        return DecisionResult(
            should_start=False, score=0.0, threshold=threshold,
            reasons=[], suppressed=True, suppression_reason=suppression_reason,
            idle_category=idle_category, recent_unresolved=recent_unresolved,
            recent_closure=recent_closure, recent_correction=recent_correction,
            anchor_present=anchor_present, conversation_memory_count=conversation_memory_count,
        )
    return DecisionResult(
        should_start=score >= threshold, score=score, threshold=threshold, reasons=reasons,
        idle_category=idle_category, recent_unresolved=recent_unresolved,
        recent_closure=recent_closure, recent_correction=recent_correction,
        anchor_present=anchor_present, conversation_memory_count=conversation_memory_count,
    )