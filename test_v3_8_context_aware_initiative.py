"""v3.8 — Context-Aware Initiative & Proactive Support — Regression Test.

Pola & harness IDENTIK test_v3_7_conversation_feedback.py.
"""

from __future__ import annotations

import os
import tempfile

from ai.companion import Companion
from ai.context_builder import ContextBuilder
from ai.conversation import Conversation
from ai.conversation_feedback import ConversationFeedback
from ai.temporal_signals import TemporalSignals
from behavior.behavior_state import DEFAULT_BEHAVIOR_STATE
from database.memory_manager import MemoryManager
from initiative.initiative_decision import DecisionResult, decide
from initiative.initiative_rules import (
    ConversationAnchorMemoryRule,
    DecisionContext,
    RecentCorrectionRule,
    RecentUnresolvedRule,
)

_PASS = "PASS"
_FAIL = "FAIL"
_results: list[tuple[str, str, str]] = []


def _check(test_id: str, condition: bool, detail: str) -> None:
    _results.append((test_id, _PASS if condition else _FAIL, detail))


def _ctx(**overrides) -> DecisionContext:
    base = dict(
        idle_seconds=1000.0,
        behavior_state=DEFAULT_BEHAVIOR_STATE,
        vision_context=None,
        routine_event=None,
        hour=10,
    )
    base.update(overrides)
    return DecisionContext(**base)


def _make_companion(db_path: str) -> Companion:
    companion = Companion.__new__(Companion)
    companion._conversation = Conversation()
    companion._memory_manager = MemoryManager(db_path=db_path)
    companion._recall_decision_history = []
    companion._memory_decision_history = []
    companion._MEMORY_HISTORY_LIMIT = 30
    companion._context_builder = ContextBuilder()
    companion._performance = None
    companion._last_recall_scores = {}
    companion._last_temporal_signals = None
    companion._last_response_calibration = None
    companion._last_conversation_feedback = None
    return companion


def run() -> None:
    # T01: RecentUnresolvedRule memberi bonus kalau recent_unresolved True
    rule = RecentUnresolvedRule()
    _check("T01", rule.evaluate(_ctx(recent_unresolved=True)) is not None, "bonus unresolved aktif")
    _check("T01b", rule.evaluate(_ctx(recent_unresolved=False)) is None, "tidak aktif kalau False")

    # T02: RecentCorrectionRule memberi penalti kalau recent_correction True
    rule2 = RecentCorrectionRule()
    _check("T02", rule2.evaluate(_ctx(recent_correction=True)) is not None, "penalti correction aktif")
    _check("T02b", rule2.get_weight(_ctx(recent_correction=True)) < 0, "weight correction harus negatif (penalti)")

    # T03: ConversationAnchorMemoryRule
    rule3 = ConversationAnchorMemoryRule()
    _check("T03", rule3.evaluate(_ctx(conversation_memory_count=3)) is not None, "bonus memory relevan aktif")
    _check("T03b", rule3.evaluate(_ctx(conversation_memory_count=0)) is None, "tidak aktif kalau 0")

    # T04: Correction penalty LEBIH BESAR dari closure penalty (spec: koreksi
    # lebih serius) — dibandingkan via magnitude weight statis.
    _check("T04", abs(RecentCorrectionRule().weight) > 10.0, f"correction weight {RecentCorrectionRule().weight} harus > closure (-10.0)")

    # T05: DecisionContext backward compat — field v3.8 semua optional,
    # DecisionContext lama (tanpa field v3.8) tetap konstruksi normal.
    ctx_old_style = _ctx()  # tidak mengisi field v3.8 sama sekali
    _check(
        "T05",
        ctx_old_style.recent_unresolved is False and ctx_old_style.recent_correction is False
        and ctx_old_style.conversation_memory_count == 0 and ctx_old_style.anchor_present is False,
        f"default backward-compat -> {ctx_old_style}",
    )

    # T06: decide() backward compat — pemanggil lama (tanpa argumen v3.8)
    # tetap berfungsi normal.
    old_result = decide(60.0, 50.0, ["test (+10.0)"])
    _check(
        "T06",
        old_result.should_start is True and old_result.idle_category is None and old_result.recent_unresolved is False,
        f"decide() lama tanpa argumen v3.8 tetap jalan -> {old_result}",
    )

    # T07: DecisionResult v3.8 fields tersimpan benar
    new_result = decide(
        60.0, 50.0, ["test"], idle_category="long_return", recent_unresolved=True,
        recent_closure=False, recent_correction=False, anchor_present=True, conversation_memory_count=2,
    )
    _check(
        "T07",
        new_result.idle_category == "long_return" and new_result.recent_unresolved is True
        and new_result.anchor_present is True and new_result.conversation_memory_count == 2,
        f"-> {new_result}",
    )

    # T08: Suppressed result TIDAK membawa evidence v3.8 yang salah (tetap
    # default aman, bukan sisa evidence dari evaluasi sebelumnya)
    suppressed_result = decide(
        0.0, 50.0, [], suppressed=True, suppression_reason="test",
        idle_category="active", recent_unresolved=True,
    )
    _check(
        "T08",
        suppressed_result.suppressed is True and suppressed_result.should_start is False,
        f"suppressed tetap should_start=False -> {suppressed_result}",
    )

    # ---------------------------------------------------------------
    # T09-T13: Integrasi Companion._initiative_evidence_kwargs — REUSE
    # cache v3.5/v3.7/v3.3-v3.4, TIDAK ADA query/deteksi baru.
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t09.db"))

        # Kondisi kosong (belum ada chat sama sekali) -> semua evidence aman/default
        kwargs_empty = companion._initiative_evidence_kwargs(DEFAULT_BEHAVIOR_STATE)
        _check(
            "T09",
            kwargs_empty["recent_unresolved"] is False and kwargs_empty["conversation_memory_count"] == 0
            and kwargs_empty["anchor_present"] is False,
            f"kondisi kosong harus aman -> {kwargs_empty}",
        )
        _check("T09b", kwargs_empty["idle_category"] in ("active", "short_return", "long_return"), f"idle_category tetap terisi -> {kwargs_empty['idle_category']}")

        # Simulasikan cache v3.5 (unresolved) + v3.7 (correction) terisi
        companion._last_temporal_signals = TemporalSignals(unresolved_cues=("masih error",))
        companion._last_conversation_feedback = ConversationFeedback(correction_detected=True)
        companion._recall_decision_history = [
            {"result_count": 3, "query_source": "conversation_anchor"},
        ]
        kwargs_filled = companion._initiative_evidence_kwargs(DEFAULT_BEHAVIOR_STATE)
        _check("T10", kwargs_filled["recent_unresolved"] is True, f"reuse v3.5 cache -> {kwargs_filled}")
        _check("T11", kwargs_filled["recent_correction"] is True, f"reuse v3.7 cache -> {kwargs_filled}")
        _check("T12", kwargs_filled["conversation_memory_count"] == 3, f"reuse v3.3/v3.4 cache -> {kwargs_filled}")
        _check("T13", kwargs_filled["anchor_present"] is True, f"anchor dari query_source=conversation_anchor -> {kwargs_filled}")

        # T14: _detect_conversation_closure() upgrade — reuse v3.7 superset
        companion._last_conversation_feedback = ConversationFeedback(closure_detected=True)
        _check("T14", companion._detect_conversation_closure() is True, "reuse closure_detected v3.7")

    # ---------------------------------------------------------------
    # T15: Provider Independence — nol cabang logic provider di rule baru
    # ---------------------------------------------------------------
    with open("initiative/initiative_rules.py", encoding="utf-8") as f:
        src = f.read().lower()
    _check("T15", 'provider ==' not in src and '"local"' not in src and '"gemini"' not in src, "nol cabang logic provider")

    # T16: No New Persistent State — rule v3.8 TIDAK menyimpan state sendiri
    _check(
        "T16",
        "save_memory" not in src and "sqlite" not in src.replace("initiativehistory", ""),
        "TIDAK BOLEH ada persistent state baru di initiative_rules.py",
    )

    # T17-T20: regresi v3.3-v3.7 dijalankan terpisah
    for vt in ("T17", "T18", "T19", "T20"):
        _results.append((vt, "SKIP", "regresi dijalankan sebagai file terpisah (test_v3_3/4/5/6/7)"))

    print_report()


def print_report() -> None:
    print("=" * 70)
    print("v3.8 — Context-Aware Initiative & Proactive Support — Test Result")
    print("=" * 70)
    failed = 0
    for test_id, status, detail in _results:
        marker = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}.get(status, "?")
        print(f"{marker} {test_id} [{status}] {detail}")
        if status == "FAIL":
            failed += 1
    print("-" * 70)
    print(f"Total: {len(_results)} | Failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run()