"""v3.6 — Adaptive Response Calibration & Conversational Pacing — Regression Test.

Pola & harness IDENTIK test_v3_5_temporal_awareness.py — `Companion.__new__`,
MemoryManager db_path sementara, TIDAK ADA network call/provider sungguhan.
"""

from __future__ import annotations

import os
import tempfile

from ai.companion import Companion
from ai.context_builder import ContextBuilder
from ai.conversation import Conversation
from ai.reference_signals import detect_reference_signal
from ai.response_calibration import (
    ResponseCalibration,
    build_response_calibration,
    detect_conversation_form,
    detect_depth_cues,
)
from ai.temporal_signals import detect_temporal_signals
from behavior.behavior_state import DEFAULT_BEHAVIOR_STATE
from database.memory_manager import MemoryManager

_PASS = "PASS"
_FAIL = "FAIL"
_results: list[tuple[str, str, str]] = []


def _check(test_id: str, condition: bool, detail: str) -> None:
    _results.append((test_id, _PASS if condition else _FAIL, detail))


def _calibrate(text: str) -> ResponseCalibration:
    """Helper test: panggil build_response_calibration() dengan reuse
    evidence v3.3/v3.5 PERSIS seperti Companion._build_contents()."""
    temporal = detect_temporal_signals(text)
    return build_response_calibration(
        text,
        reference_signal=detect_reference_signal(text),
        unresolved_cues=temporal.unresolved_cues,
        completion_cues=temporal.completion_cues,
    )


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
    return companion


def run() -> None:
    # T01-T03: explicit depth cues
    cues, phrases = detect_depth_cues("singkat aja ya")
    _check("T01", cues == ("concise",) and "singkat aja" in phrases, f"'singkat aja' -> {cues}, {phrases}")

    cues, phrases = detect_depth_cues("jelasin detail dong")
    _check("T02", "detailed" in cues, f"'jelasin detail' -> {cues}, {phrases}")

    cues, phrases = detect_depth_cues("jelasin step by step ya")
    _check("T03", "step_by_step" in cues, f"'step by step' -> {cues}, {phrases}")

    # T04: no explicit cue -> normal question tidak otomatis concise/detailed
    calib = _calibrate("kenapa JWT expired?")
    _check("T04", calib.depth_cues == (), f"pertanyaan biasa TIDAK BOLEH otomatis dapat depth cue -> {calib.depth_cues}")

    # T05-T09: conversation form
    _check("T05", detect_conversation_form("masih error nih", unresolved_cues=("masih error",)) == "problem_report", "problem_report")
    _check("T06", detect_conversation_form("kenapa JWT expired?") == "question", "question")
    _check("T07", detect_conversation_form("jelasin JWT dong") == "request", "request")
    _check("T08", detect_conversation_form("aku lagi ngerjain backend LeadEstate") == "progress_update", "progress_update")
    _check("T09", detect_conversation_form("sudah selesai", completion_cues=("sudah selesai",)) == "completion_statement", "completion_statement")

    # T10-T11: contradictory & priority
    calib10 = _calibrate("jelasin detail tapi singkat aja")
    _check("T10", set(calib10.depth_cues) == {"detailed", "concise"} and calib10.conflicting_cues, f"kedua cue harus tetap ada -> {calib10}")

    calib11 = _calibrate("kenapa API error? singkat aja")
    _check("T11", calib11.conversation_form == "question" and "concise" in calib11.depth_cues, f"-> {calib11}")

    # T12: Reference + Temporal + Calibration coexist
    temporal12 = detect_temporal_signals("balik ke API tadi, masih error. Singkat aja.")
    calib12 = build_response_calibration(
        "balik ke API tadi, masih error. Singkat aja.",
        reference_signal=detect_reference_signal("balik ke API tadi, masih error. Singkat aja."),
        unresolved_cues=temporal12.unresolved_cues,
        completion_cues=temporal12.completion_cues,
    )
    _check(
        "T12",
        "masih error" in temporal12.unresolved_cues and "concise" in calib12.depth_cues,
        f"v3.5 evidence tetap utuh DAN v3.6 concise terdeteksi -> temporal={temporal12.unresolved_cues}, calib={calib12.depth_cues}",
    )

    # T13: False positive protection
    cues13, _ = detect_depth_cues("aku lagi baca buku yang singkatnya bagus banget")
    _check("T13", "concise" not in cues13, f"'singkatnya' (bagian kata lain) TIDAK BOLEH memicu cue 'singkat aja' -> {cues13}")

    # T14: No new persistent state — ResponseCalibration cuma dataclass biasa,
    # TIDAK ada mekanisme simpan-permanen di modul ini sama sekali.
    with open("ai/response_calibration.py", encoding="utf-8") as f:
        src = f.read().lower()
    _check(
        "T14",
        "save_memory" not in src and "memory_manager" not in src and "sqlite" not in src,
        "ai/response_calibration.py TIDAK BOLEH menyimpan state permanen apa pun",
    )

    # T15: ContextBuilder assembly only
    cb = ContextBuilder()
    with_evidence = cb.build(DEFAULT_BEHAVIOR_STATE, response_calibration=_calibrate("singkat aja ya"))
    _check("T15", "Response Calibration" in with_evidence, "section HARUS muncul kalau ada evidence")
    without_evidence = cb.build(DEFAULT_BEHAVIOR_STATE, response_calibration=ResponseCalibration())
    _check("T15b", "Response Calibration" not in without_evidence, "section TIDAK BOLEH muncul kalau kosong")
    default_none = cb.build(DEFAULT_BEHAVIOR_STATE)
    _check("T15c", "Response Calibration" not in default_none, "tanpa parameter sama sekali, section tidak muncul (backward-compat)")

    # T16/T17: integrasi Companion (chat vs autonomous)
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t16.db"))
        companion._conversation.add_user_message("jelasin detail kenapa JWT expired")
        contents = companion._build_contents("jelasin detail kenapa JWT expired", DEFAULT_BEHAVIOR_STATE)
        all_text = "\n".join(part.text or "" for c in contents for part in (c.parts or []))
        _check("T16", "Response Calibration" in all_text and "jelasin detail" in all_text, "evidence harus masuk ke contents jalur chat()")

        snapshot = companion.get_response_calibration_debug_snapshot()
        _check("T16b", "detailed" in snapshot["depth_cues"], f"snapshot dashboard harus mencerminkan evidence -> {snapshot}")

        # T17: autonomous TIDAK membuat response_calibration dari apa pun
        # (method tidak disentuh sama sekali oleh v3.6 — cek source tidak
        # mereferensikan response_calibration di body method itu).
        import inspect
        autonomous_src = inspect.getsource(Companion._build_autonomous_contents)
        _check("T17", "response_calibration" not in autonomous_src, "_build_autonomous_contents TIDAK BOLEH menghitung response_calibration")

    # T18: Provider Independence — nol referensi provider di modul
    with open("ai/response_calibration.py", encoding="utf-8") as f:
        src2 = f.read().lower()
    _check("T18", 'provider ==' not in src2 and '"local"' not in src2 and '"gemini"' not in src2, "nol cabang logic spesifik provider")

    # T19-T21: regresi v3.3/v3.4/v3.5 — dijalankan terpisah sebagai file
    # sendiri (test_v3_3_reference_recall.py / test_v3_4_memory_ranking.py /
    # test_v3_5_temporal_awareness.py), BUKAN diimpor-ulang di sini supaya
    # tidak menduplikasi ~60 test yang sudah ada. Dicatat di laporan
    # eksekusi sebagai run terpisah.
    _results.append(("T19", "SKIP", "jalankan python test_v3_3_reference_recall.py terpisah"))
    _results.append(("T20", "SKIP", "jalankan python test_v3_4_memory_ranking.py terpisah"))
    _results.append(("T21", "SKIP", "jalankan python test_v3_5_temporal_awareness.py terpisah"))

    print_report()


def print_report() -> None:
    print("=" * 70)
    print("v3.6 — Adaptive Response Calibration & Conversational Pacing — Test Result")
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