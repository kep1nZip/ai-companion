"""v3.7 — Conversational Feedback & Repair Intelligence — Regression Test.

Pola & harness IDENTIK test_v3_6_response_calibration.py.
"""

from __future__ import annotations

import inspect
import os
import tempfile

from ai.companion import Companion
from ai.context_builder import ContextBuilder
from ai.conversation import Conversation
from ai.conversation_feedback import (
    ConversationFeedback,
    build_conversation_feedback,
    detect_acknowledgement,
    detect_confusion_cues,
    detect_correction_cues,
    detect_repeat_requests,
)
from behavior.behavior_state import DEFAULT_BEHAVIOR_STATE
from database.memory_manager import MemoryManager

_PASS = "PASS"
_FAIL = "FAIL"
_results: list[tuple[str, str, str]] = []


def _check(test_id: str, condition: bool, detail: str) -> None:
    _results.append((test_id, _PASS if condition else _FAIL, detail))


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
    _check("T01", detect_confusion_cues("masih bingung"), "confusion")
    _check("T02", detect_correction_cues("bukan itu maksudku"), "correction")

    fb03 = build_conversation_feedback("kepanjangan")
    _check("T03", "negative_length_feedback" in fb03.feedback_cues, f"-> {fb03.feedback_cues}")

    fb04 = build_conversation_feedback("terlalu teknis")
    _check("T04", "negative_complexity_feedback" in fb04.feedback_cues, f"-> {fb04.feedback_cues}")

    _check("T05", detect_repeat_requests("jelasin lagi"), "repeat")

    fb06 = build_conversation_feedback("jelasin lebih gampang")
    _check("T06", "simplification_request" in fb06.feedback_cues, f"-> {fb06.feedback_cues}")

    fb07 = build_conversation_feedback("jelasin lebih detail")
    _check("T07", "expansion_request" in fb07.feedback_cues, f"-> {fb07.feedback_cues}")

    _check("T08", detect_acknowledgement("oke ngerti"), "acknowledgement")

    fb09 = build_conversation_feedback("udah cukup, makasih")
    _check("T09", fb09.closure_detected, f"-> {fb09}")

    # T10: Multi-Cue Feedback — semua cue tetap ada
    fb10 = build_conversation_feedback("masih bingung, tadi kepanjangan, ulang dari awal yang lebih gampang")
    expected10 = {"confusion", "negative_length_feedback", "repeat_request", "simplification_request"}
    _check("T10", expected10 <= set(fb10.feedback_cues), f"-> {fb10.feedback_cues}")

    # T11: Correction + New Request (new request bukan tanggung jawab modul ini,
    # cukup pastikan correction tetap terdeteksi tanpa menghalangi apa pun)
    fb11 = build_conversation_feedback("bukan itu, coba kasih contoh login JWT")
    _check("T11", fb11.correction_detected, f"-> {fb11}")

    # T12: Feedback vs Current Instruction — dua-duanya tetap terdeteksi independen
    fb12 = build_conversation_feedback("tadi kepanjangan, sekarang singkat aja")
    _check("T12", "negative_length_feedback" in fb12.feedback_cues, f"v3.7 length feedback -> {fb12.feedback_cues}")

    # T13: V3.6 Integration
    from ai.response_calibration import build_response_calibration
    text13 = "masih bingung. jelasin lebih gampang dan singkat aja."
    fb13 = build_conversation_feedback(text13)
    calib13 = build_response_calibration(text13)
    _check(
        "T13",
        "confusion" in fb13.feedback_cues and "concise" in calib13.depth_cues,
        f"v3.7={fb13.feedback_cues}, v3.6={calib13.depth_cues}",
    )

    # T14: V3.3 Integration
    from ai.reference_signals import detect_reference_signal
    text14 = "bukan yang tadi itu, maksudku API."
    fb14 = build_conversation_feedback(text14)
    _check(
        "T14",
        fb14.correction_detected and detect_reference_signal(text14),
        f"v3.7 correction={fb14.correction_detected}, v3.3 reference={detect_reference_signal(text14)}",
    )

    # T15: V3.5 Integration
    from ai.temporal_signals import detect_temporal_signals
    text15 = "masih bingung soal yang kemarin"
    fb15 = build_conversation_feedback(text15)
    temporal15 = detect_temporal_signals(text15)
    _check(
        "T15",
        "confusion" in fb15.feedback_cues and "kemarin" in temporal15.relative_terms,
        f"v3.7={fb15.feedback_cues}, v3.5={temporal15.relative_terms}",
    )

    # T16: False Positive Protection
    fb16 = build_conversation_feedback("budgetnya cukup besar untuk project ini")
    _check("T16", not fb16.closure_detected, f"'cukup' dalam kalimat biasa TIDAK BOLEH jadi closure -> {fb16}")

    # T17: No Persistent Feedback State
    with open("ai/conversation_feedback.py", encoding="utf-8") as f:
        src = f.read().lower()
    _check(
        "T17",
        "save_memory" not in src and "memorymanager" not in src.replace("_", "") and "sqlite" not in src,
        "TIDAK BOLEH ada persistent state di modul ini",
    )

    # T18: ContextBuilder Assembly Only
    cb = ContextBuilder()
    section_with = cb.build_feedback_section(build_conversation_feedback("masih bingung"))
    _check("T18", "Conversation Feedback" in section_with, "section muncul kalau ada evidence")
    section_without = cb.build_feedback_section(ConversationFeedback())
    _check("T18b", section_without == "", "section kosong kalau tidak ada evidence")

    # T19: Autonomous Safety
    autonomous_src = inspect.getsource(Companion._build_autonomous_contents)
    _check("T19", "conversation_feedback" not in autonomous_src, "_build_autonomous_contents TIDAK BOLEH menghitung conversation_feedback")

    # T20: Provider Independence
    _check("T20", 'provider ==' not in src and '"local"' not in src and '"gemini"' not in src, "nol cabang logic provider")

    # Integrasi penuh Companion._build_contents
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t_integration.db"))
        companion._conversation.add_user_message("masih bingung")
        contents = companion._build_contents("masih bingung", DEFAULT_BEHAVIOR_STATE)
        all_text = "\n".join(part.text or "" for c in contents for part in (c.parts or []))
        _check("T_INTEGRATION", "Conversation Feedback" in all_text and "belum memahami" in all_text, "evidence masuk ke contents")

        snapshot = companion.get_conversation_feedback_debug_snapshot()
        _check("T_INTEGRATION_SNAPSHOT", "confusion" in snapshot["feedback_cues"], f"-> {snapshot}")

    # T22-T25: regresi v3.3-v3.6 dijalankan terpisah
    for vt in ("T22", "T23", "T24", "T25"):
        _results.append((vt, "SKIP", "regresi dijalankan sebagai file terpisah (test_v3_3/4/5/6)"))

    print_report()


def print_report() -> None:
    print("=" * 70)
    print("v3.7 — Conversational Feedback & Repair Intelligence — Test Result")
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