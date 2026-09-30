"""v3.5 — Temporal Awareness & Task Continuity — Regression Test.

Menguji `ai/temporal_signals.py` (pure/deterministic) dan integrasinya di
`ai/context_builder.py` (section "Temporal Context", assembly-only) serta
`Companion._build_contents()`/`get_temporal_debug_snapshot()`. Pola &
harness IDENTIK `test_v3_3_reference_recall.py`/`test_v3_4_memory_
ranking.py` — `Companion.__new__`, `MemoryManager` db_path sementara,
TIDAK ADA network call/provider sungguhan sama sekali.

Dijalankan manual: `python test_v3_5_temporal_awareness.py`
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from ai.companion import Companion
from ai.context_builder import ContextBuilder
from ai.conversation import Conversation
from ai.temporal_signals import (
    TemporalSignals,
    detect_completion_cues,
    detect_continuation_cues,
    detect_relative_time_terms,
    detect_temporal_signals,
    detect_unresolved_cues,
    format_memory_age,
    normalize_relative_dates,
)
from behavior.behavior_state import DEFAULT_BEHAVIOR_STATE
from config.constants import ROUTINE_TIMEZONE
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
    return companion


def run() -> None:
    # ---------------------------------------------------------------
    # T01-T04: normalisasi tanggal — HANYA istilah tidak ambigu
    # ---------------------------------------------------------------
    now = datetime(2026, 9, 30, 10, 30, tzinfo=ZoneInfo(ROUTINE_TIMEZONE))  # Rabu

    besok = normalize_relative_dates("aku ada meeting besok", now)
    _check("T01", besok.get("besok") == "Kamis, 1 Oktober 2026", f"'besok' dari 30 Sep 2026 -> {besok}")

    kemarin = normalize_relative_dates("kemarin aku ngerjain LeadEstate", now)
    _check("T02", kemarin.get("kemarin") == "Selasa, 29 September 2026", f"'kemarin' -> {kemarin}")

    lusa = normalize_relative_dates("lusa aku ada deadline", now)
    _check("T03", lusa.get("lusa") == "Jumat, 2 Oktober 2026", f"'lusa' -> {lusa}")

    ambigu = normalize_relative_dates("minggu depan aku libur, nanti kabari ya", now)
    _check(
        "T04",
        "minggu depan" not in ambigu and "nanti" not in ambigu,
        f"istilah AMBIGU ('minggu depan'/'nanti') TIDAK BOLEH dinormalisasi jadi tanggal pasti -> {ambigu}",
    )
    relative_terms = detect_relative_time_terms("minggu depan aku libur, nanti kabari ya")
    _check(
        "T04b",
        "minggu depan" in relative_terms and "nanti" in relative_terms,
        f"tapi TETAP dilaporkan sebagai raw cue (bukan dihilangkan sama sekali) -> {relative_terms}",
    )

    # ---------------------------------------------------------------
    # T05-T06: continuation cues
    # ---------------------------------------------------------------
    cues = detect_continuation_cues("aku masih ngerjain backend LeadEstate")
    _check("T05", cues == ("masih ngerjain",), f"'masih ngerjain' harus terdeteksi SATU kali (bukan dobel 'masih') -> {cues}")

    cues2 = detect_continuation_cues("oke lanjutin yang tadi ya")
    _check("T06", "lanjutin" in cues2, f"'lanjutin' harus terdeteksi -> {cues2}")

    # ---------------------------------------------------------------
    # T07-T08: completion cues + No False Completion
    # ---------------------------------------------------------------
    done = detect_completion_cues("akhirnya sudah selesai semua!")
    _check("T07", "sudah selesai" in done, f"'sudah selesai' harus terdeteksi -> {done}")

    imperative = detect_completion_cues("Tolong selesaikan tugas ini nanti ya")
    _check(
        "T08",
        "selesai" not in imperative and not imperative,
        f"'selesaikan' (perintah, BUKAN pernyataan sudah selesai) TIDAK BOLEH memicu completion cue -> {imperative}",
    )

    # ---------------------------------------------------------------
    # T09-T10: unresolved cues + dual-category "belum selesai"
    # ---------------------------------------------------------------
    unresolved = detect_unresolved_cues("masih error nih di bagian auth")
    _check("T09", "masih error" in unresolved, f"'masih error' harus terdeteksi -> {unresolved}")

    dual_continuation = detect_continuation_cues("backend-nya belum selesai")
    dual_unresolved = detect_unresolved_cues("backend-nya belum selesai")
    _check(
        "T10",
        "belum selesai" in dual_continuation and "belum selesai" in dual_unresolved,
        f"'belum selesai' SENGAJA muncul di continuation DAN unresolved -> {dual_continuation}, {dual_unresolved}",
    )

    # ---------------------------------------------------------------
    # T11: Hard Boundary — TIDAK ADA field/kata task_status/deadline/priority
    # di modul ini sama sekali (spec §4.2/§4.3)
    # ---------------------------------------------------------------
    with open("ai/temporal_signals.py", encoding="utf-8") as f:
        source_lower = f.read().lower()
    # Cek pola FIELD/KEY sungguhan (dataclass field ':' atau dict key '"..."'),
    # BUKAN substring bebas — kata-kata ini SENGAJA disebut di komentar/
    # docstring untuk MENJELASKAN Hard Boundary (mis. "TIDAK ADA field
    # task_status di sini"), jadi substring check naif akan false-positive.
    forbidden_patterns = [
        '"task_status"', "task_status:", "task_status =",
        '"deadline"', "deadline:", "deadline =",
        '"priority"', "priority:", "priority =",
        '"is_active"', "is_active:", "is_active =",
        '"task_complete"', "task_complete:", "task_complete =",
    ]
    found_forbidden = [w for w in forbidden_patterns if w in source_lower]
    _check("T11", not found_forbidden, f"TIDAK BOLEH ada field/key task_status/deadline/priority sungguhan di temporal_signals.py -> {found_forbidden}")

    # ---------------------------------------------------------------
    # T12: TemporalSignals.is_empty()
    # ---------------------------------------------------------------
    empty = TemporalSignals()
    _check("T12", empty.is_empty() is True, "TemporalSignals kosong harus is_empty()==True")
    nonempty = detect_temporal_signals("aku masih ngerjain LeadEstate")
    _check("T12b", nonempty.is_empty() is False, "TemporalSignals dengan continuation cue harus is_empty()==False")

    # ---------------------------------------------------------------
    # T13: format_memory_age — murni tampilan, None kalau invalid
    # ---------------------------------------------------------------
    from datetime import timezone as _tz
    two_hours_ago = (datetime.now(_tz.utc).replace(microsecond=0) - __import__("datetime").timedelta(hours=2)).isoformat()
    age = format_memory_age(two_hours_ago, datetime.now(_tz.utc))
    _check("T13", age is not None and "jam" in age, f"memory 2 jam lalu harus dapat label '~2 jam lalu' -> {age}")
    _check("T13b", format_memory_age("", datetime.now(_tz.utc)) is None, "updated_at kosong harus return None (bukan error)")
    _check("T13c", format_memory_age("bukan-tanggal-valid", datetime.now(_tz.utc)) is None, "string tidak valid harus return None (bukan meledak)")

    # ---------------------------------------------------------------
    # T14: ContextBuilder — section "Temporal Context" HANYA muncul kalau
    # ADA sinyal, dan assembly-only (Companion yang deteksi, bukan
    # ContextBuilder)
    # ---------------------------------------------------------------
    cb = ContextBuilder()
    text_with_signal = cb.build(DEFAULT_BEHAVIOR_STATE, temporal_signals=detect_temporal_signals("aku masih ngerjain LeadEstate"))
    _check("T14", "Temporal Context" in text_with_signal, "section Temporal Context HARUS muncul kalau ada sinyal")

    text_without_signal = cb.build(DEFAULT_BEHAVIOR_STATE, temporal_signals=TemporalSignals())
    _check("T14b", "Temporal Context" not in text_without_signal, "section Temporal Context TIDAK BOLEH muncul kalau kosong")

    text_default_none = cb.build(DEFAULT_BEHAVIOR_STATE)
    _check("T14c", "Temporal Context" not in text_default_none, "tanpa parameter temporal_signals sama sekali, section tidak muncul (backward-compat)")

    # ---------------------------------------------------------------
    # T15: Integrasi Companion._build_contents — temporal signal dari pesan
    # SAAT INI harus tersalur ke contents, dan tercache di
    # get_temporal_debug_snapshot()
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t15.db"))
        companion._conversation.add_user_message("aku masih debugging backend LeadEstate")
        contents = companion._build_contents("aku masih debugging backend LeadEstate", DEFAULT_BEHAVIOR_STATE)
        all_text = "\n".join(part.text or "" for c in contents for part in (c.parts or []))
        _check("T15", "Temporal Context" in all_text and "masih debugging" in all_text, "sinyal continuation harus masuk ke contents")

        snapshot = companion.get_temporal_debug_snapshot()
        _check(
            "T15b",
            "masih debugging" in snapshot["continuation_cues"],
            f"get_temporal_debug_snapshot() harus mencerminkan sinyal yang sama -> {snapshot}",
        )

    # ---------------------------------------------------------------
    # T16: pesan biasa tanpa sinyal apa pun -> tidak ada Temporal Context,
    # snapshot semua kosong
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t16.db"))
        companion._conversation.add_user_message("Aku suka kopi americano")
        contents = companion._build_contents("Aku suka kopi americano", DEFAULT_BEHAVIOR_STATE)
        all_text = "\n".join(part.text or "" for c in contents for part in (c.parts or []))
        _check("T16", "Temporal Context" not in all_text, "pesan tanpa sinyal temporal apa pun TIDAK BOLEH memunculkan section")

    # ---------------------------------------------------------------
    # T17: get_temporal_debug_snapshot() sebelum ada chat sama sekali ->
    # semua field kosong, TIDAK error
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t17.db"))
        snapshot = companion.get_temporal_debug_snapshot()
        _check(
            "T17",
            snapshot["relative_terms"] == () and snapshot["anchor_preview"] is None,
            f"snapshot sebelum ada chat harus semua kosong, bukan error -> {snapshot}",
        )

    print_report()


def print_report() -> None:
    print("=" * 70)
    print("v3.5 — Temporal Awareness & Task Continuity — Test Result")
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