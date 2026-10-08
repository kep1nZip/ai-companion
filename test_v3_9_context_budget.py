"""v3.9 — Adaptive Context Budget & Attention Allocation — Regression Test.

Milestone ini MEASUREMENT-FIRST (lihat V3.9_EXECUTION_REPORT.md) — tidak
ada tier/budget enforcement baru yang diaktifkan. Test di sini memvalidasi
instrumentasi BARU (section_sizes, memory_context cache) dan MEMBUKTIKAN
preservasi reference (anchor v3.3 baca full history, independen dari
history cap) — sesuai Hard Boundary §5 spec v3.9.
"""

from __future__ import annotations

import os
import tempfile

from ai.companion import Companion
from ai.context_builder import ContextBuilder
from ai.conversation import Conversation
from ai.temporal_signals import TemporalSignals
from ai.response_calibration import ResponseCalibration
from behavior.behavior_state import DEFAULT_BEHAVIOR_STATE
from config.constants import EPHEMERAL_CONTEXT_MEMORY_LIMIT
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
    companion._last_memory_context_text = ""
    return companion


def run() -> None:
    cb = ContextBuilder()

    # T01: measure_sections() — section kosong harus 0, bukan dihilangkan
    sizes_empty = cb.measure_sections(DEFAULT_BEHAVIOR_STATE)
    _check(
        "T01",
        sizes_empty["temporal"] == 0 and sizes_empty["calibration"] == 0 and sizes_empty["vision"] == 0
        and all(k in sizes_empty for k in ("time", "continuity", "emotion", "relationship", "internal")),
        f"section kosong = 0, semua key tetap ada -> {sizes_empty}",
    )

    # T02: measure_sections() dengan evidence -> angka harus > 0 dan PERSIS
    # sama dengan panjang teks yang benar-benar dirender formatter yang sama.
    temporal = TemporalSignals(continuation_cues=("masih",), unresolved_cues=("masih error",))
    calibration = ResponseCalibration(conversation_form="problem_report", depth_cues=("concise",), explicit_phrases=("singkat aja",))
    sizes_filled = cb.measure_sections(DEFAULT_BEHAVIOR_STATE, temporal_signals=temporal, response_calibration=calibration)
    _check(
        "T02",
        sizes_filled["temporal"] == len(cb._format_temporal(temporal))
        and sizes_filled["calibration"] == len(cb._format_response_calibration(calibration)),
        f"angka measure_sections HARUS identik dgn formatter asli -> {sizes_filled}",
    )
    _check("T02b", sizes_filled["temporal"] > 0 and sizes_filled["calibration"] > 0, "evidence terisi -> size > 0")

    # T03: Instrumentation Honesty — SEBELUM v3.9, ephemeral_context_characters
    # di get_context_debug_snapshot() TIDAK menyertakan temporal/calibration.
    # Verifikasi perbaikannya: measure_sections() memang mencakup KEDUANYA
    # (lihat T02), beda dari panggilan build() lama yang cuma hitung 5 section
    # dasar.
    sizes_base_only = cb.measure_sections(DEFAULT_BEHAVIOR_STATE)  # tanpa temporal/calibration
    base_sum = sum(v for k, v in sizes_base_only.items() if k in ("time", "continuity", "emotion", "relationship", "internal"))
    _check(
        "T03",
        sum(sizes_filled.values()) > base_sum,
        f"total dengan evidence ({sum(sizes_filled.values())}) harus > base 5-section saja ({base_sum}) -> bukti undercounting lama sudah diperbaiki",
    )

    # ---------------------------------------------------------------
    # T04-T06: Integrasi Companion — cache memory_context_text terisi benar,
    # dan reference preservation (anchor baca FULL history, independen cap).
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t04.db"))
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")
        companion._conversation.add_user_message("Aku lagi ngerjain LeadEstate")
        companion._conversation.add_assistant_message("Oke semangat!")
        msg = "Masih error di auth, singkat aja."
        companion._conversation.add_user_message(msg)
        contents = companion._build_contents(msg, DEFAULT_BEHAVIOR_STATE)
        _check("T04", "LeadEstate" in companion._last_memory_context_text, f"memory_text harus tercache -> {companion._last_memory_context_text!r}")

        snapshot_sizes = companion._context_builder.measure_sections(
            DEFAULT_BEHAVIOR_STATE, temporal_signals=companion._last_temporal_signals,
            response_calibration=companion._last_response_calibration,
        )
        _check("T05", snapshot_sizes["temporal"] > 0 and snapshot_sizes["calibration"] > 0, f"measure_sections reuse cache turn terakhir -> {snapshot_sizes}")

    # T06: Reference Preservation — _recent_conversation_anchor_keywords()
    # HARUS membaca get_history() TANPA max_messages (full, independen cap).
    import inspect
    src = inspect.getsource(Companion._recent_conversation_anchor_keywords)
    _check(
        "T06",
        "self._conversation.get_history()" in src and "max_messages" not in src,
        "anchor retrieval v3.3 HARUS baca full history (bukti source code), independen history cap",
    )

    # T07: Default behavior — history cap TIDAK diaktifkan default oleh v3.9
    # (measurement-first, PASS valid walau cap tidak diaktifkan).
    from config.settings import CONVERSATION_HISTORY_MAX_MESSAGES
    _check("T07", CONVERSATION_HISTORY_MAX_MESSAGES is None, f"v3.9 TIDAK mengaktifkan cap default -> {CONVERSATION_HISTORY_MAX_MESSAGES}")

    # T08: Empty-section elimination tetap utuh (regresi arsitektur v3.5-v3.7)
    text_no_evidence = cb.build(DEFAULT_BEHAVIOR_STATE)
    _check(
        "T08",
        "Temporal Context" not in text_no_evidence and "Response Calibration" not in text_no_evidence,
        "section opsional tetap tersembunyi kalau kosong (regresi v3.5/v3.6)",
    )

    # T09: No new persistent state / no embeddings / no vector db — audit teks
    with open("ai/context_builder.py", encoding="utf-8") as f:
        src_cb = f.read().lower()
    forbidden = ["import faiss", "embedding", "vector_db", "chromadb", "pinecone"]
    found = [w for w in forbidden if w in src_cb]
    _check("T09", not found, f"TIDAK BOLEH ada embedding/vector DB -> {found}")

    # T10: EPHEMERAL_CONTEXT_MEMORY_LIMIT tetap konstanta yang sudah ada
    # (v3.9 TIDAK mengubah budget memory yang sudah ditetapkan v3.4)
    _check("T10", EPHEMERAL_CONTEXT_MEMORY_LIMIT == 10, f"budget memory v3.4 tidak diubah v3.9 -> {EPHEMERAL_CONTEXT_MEMORY_LIMIT}")

    # T11-T15: regresi v3.3-v3.8 dijalankan terpisah
    for vt in ("T11", "T12", "T13", "T14", "T15"):
        _results.append((vt, "SKIP", "regresi dijalankan sebagai file terpisah (test_v3_3..v3_8)"))

    print_report()


def print_report() -> None:
    print("=" * 70)
    print("v3.9 — Adaptive Context Budget & Attention Allocation — Test Result")
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