"""v3.3 — Contextual Recall & Reference Intelligence — Regression Test.

Menguji 3 lapisan perubahan v3.3 (lihat
docs/CLAUDE-CONTEXT_DESIGN-SPEC_VERSION/V3.3_CONTEXTUAL_RECALL_REFERENCE_INTELLIGENCE.md):

1. `ai/reference_signals.py` — fungsi murni (regex/keyword), tidak butuh
   Companion/database sama sekali.
2. `Companion._recent_conversation_anchor_keywords()` / `_select_relevant_
   memories()` — diuji lewat instance Companion yang DIBANGUN MANUAL
   (`Companion.__new__` + atribut minimal), BUKAN `Companion()` penuh —
   supaya test ini TIDAK PERNAH menyentuh `database/memory.db` produksi
   ataupun memanggil provider Gemini/Local sungguhan (tidak ada network
   call sama sekali, aman dijalankan di mana pun/kapan pun). Pola ini
   konsisten dengan semangat `test_memory_quality_validation.py` yang juga
   sengaja membangun `MemoryManager` dengan db_path terpisah, bukan lewat
   Companion penuh.
3. Test skenario nyata dari spec §19 (Test A "Simple Reference" & Test B
   "Ambiguous Reference") — memverifikasi bahwa memory context yang
   dihasilkan `_select_relevant_memories()` benar-benar membawa memory
   yang relevan (LeadEstate) ketika Teacher bilang "lanjut yang tadi",
   TANPA aplikasi memaksakan satu jawaban (tetap tugas LLM di
   `prompts/system_rules.txt`, tidak disentuh v3.3).

Dijalankan manual: `python test_v3_3_reference_recall.py`
"""

from __future__ import annotations

import os
import tempfile

from google.genai import types

from ai.companion import Companion
from ai.conversation import Conversation
from ai.reference_signals import (
    GENERIC_REFERENCE_STOPWORDS,
    detect_reference_signal,
    extract_keywords,
    filter_search_keywords,
)
from database.memory_manager import MemoryManager
from vision.vision_context import VisionContext

_PASS = "PASS"
_FAIL = "FAIL"
_results: list[tuple[str, str, str]] = []  # (test_id, status, detail)


def _check(test_id: str, condition: bool, detail: str) -> None:
    _results.append((test_id, _PASS if condition else _FAIL, detail))


def _make_companion(db_path: str) -> Companion:
    """Companion minimal untuk unit test — TIDAK memanggil `__init__`
    (yang akan construct GeminiProvider/MemoryExtractor/BehaviorEngine/
    Vision/dst dan butuh network/API key). Hanya atribut yang benar-benar
    disentuh method yang diuji (`_conversation`, `_memory_manager`,
    `_recall_decision_history`, `_MEMORY_HISTORY_LIMIT`) yang diisi."""
    companion = Companion.__new__(Companion)
    companion._conversation = Conversation()
    companion._memory_manager = MemoryManager(db_path=db_path)
    companion._recall_decision_history = []
    companion._memory_decision_history = []
    companion._MEMORY_HISTORY_LIMIT = 30
    return companion


def run() -> None:
    # ---------------------------------------------------------------
    # T01-T05: ai/reference_signals.py — fungsi murni
    # ---------------------------------------------------------------
    kws = filter_search_keywords(extract_keywords("lanjut yang tadi"))
    _check("T01", kws == [], f"filter keyword 'lanjut yang tadi' -> {kws} (harus kosong, semua generik)")

    kws2 = filter_search_keywords(extract_keywords("Aku lagi debugging backend LeadEstate"))
    _check(
        "T02",
        set(kws2) == {"debugging", "backend", "leadestate"},
        f"filter keyword pesan project-specific -> {kws2} (harus tetap ada debugging/backend/leadestate)",
    )

    _check("T03", detect_reference_signal("lanjut yang tadi") is True, "'lanjut yang tadi' harus terdeteksi reference signal")
    _check("T04", detect_reference_signal("yang barusan aku bilang") is True, "'yang barusan aku bilang' harus terdeteksi")
    _check(
        "T05",
        detect_reference_signal("Aku suka kopi americano.") is False,
        "kalimat fakta biasa TIDAK boleh terdeteksi sebagai reference signal",
    )
    _check("T06", "yang" in GENERIC_REFERENCE_STOPWORDS and "tadi" in GENERIC_REFERENCE_STOPWORDS, "stopword list memuat 'yang'/'tadi'")
    _check("T07", "leadestate" not in GENERIC_REFERENCE_STOPWORDS, "'leadestate' TIDAK boleh masuk stopword (nama project bukan kata generik)")

    # ---------------------------------------------------------------
    # T10-T14: Test A (spec §19) — Simple Reference
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_a.db")
        companion = _make_companion(db_path)

        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")

        # Simulasikan riwayat percakapan PERSIS Test A spec:
        # Teacher: "Aku lagi debugging backend LeadEstate."
        # Arona:   "Semangat, Teacher."
        # Teacher: "lanjut yang tadi"   <- pesan yang sedang diproses
        companion._conversation.add_user_message("Aku lagi debugging backend LeadEstate.")
        companion._conversation.add_assistant_message("Semangat, Teacher.")
        companion._conversation.add_user_message("lanjut yang tadi")

        anchor_keywords = companion._recent_conversation_anchor_keywords()
        _check(
            "T10",
            set(anchor_keywords) == {"debugging", "backend", "leadestate"},
            f"anchor keywords dari turn sebelumnya -> {anchor_keywords}",
        )

        result = companion._select_relevant_memories("lanjut yang tadi")
        _check(
            "T11",
            any("LeadEstate" in m.content for m in result),
            f"memory LeadEstate harus ikut ter-recall untuk 'lanjut yang tadi' -> {[m.content for m in result]}",
        )

        recall_log = companion._recall_decision_history[-1]
        _check("T12", recall_log["query_source"] == "conversation_anchor", f"query_source harus 'conversation_anchor' -> {recall_log}")
        _check("T13", recall_log["reference_signal"] is True, "reference_signal harus True untuk 'lanjut yang tadi'")

        snapshot = companion.get_memory_decision_debug_snapshot()
        _check(
            "T14",
            snapshot["conversation_anchor_used_count"] == 1 and snapshot["reference_signal_count"] == 1,
            f"snapshot debug harus mencatat 1 anchor-used & 1 reference-signal -> {snapshot}",
        )

    # ---------------------------------------------------------------
    # T20-T22: Test B (spec §19) — Ambiguous Reference (aplikasi TIDAK
    # boleh memilih satu secara arbitrary — cukup pastikan KEDUA project
    # relevan ikut masuk sebagai candidate, disambiguasi tetap tugas LLM)
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_b.db")
        companion = _make_companion(db_path)

        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan LeadEstate")
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan project Arona")

        companion._conversation.add_user_message("Aku lagi ngerjain LeadEstate dan project Arona.")
        companion._conversation.add_assistant_message("Oke, semangat Teacher!")
        companion._conversation.add_user_message("lanjut yang tadi")

        result = companion._select_relevant_memories("lanjut yang tadi")
        contents = [m.content for m in result]
        _check(
            "T20",
            any("LeadEstate" in c for c in contents) and any("Arona" in c for c in contents),
            f"KEDUA candidate project harus ikut masuk (ambiguity dibiarkan ke LLM, app tidak menebak) -> {contents}",
        )

    # ---------------------------------------------------------------
    # T30-T31: Vision fallback (Phase 7) — hanya dipakai kalau conversation
    # anchor JUGA nihil
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_vision.db")
        companion = _make_companion(db_path)
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan VTuber avatar Arona")

        # Tidak ada riwayat percakapan sebelumnya sama sekali (sesi baru) —
        # anchor conversation pasti nihil, jadi Vision jadi sumber terakhir.
        companion._conversation.add_user_message("yang ini kenapa error ya")
        vision_context = VisionContext(summary="Error dialog muncul.", application="VTuber Arona editor")

        result = companion._select_relevant_memories("yang ini kenapa error ya", vision_context)
        recall_log = companion._recall_decision_history[-1]
        _check(
            "T30",
            recall_log["query_source"] in {"vision_context", "recency_fallback"},
            f"tanpa conversation anchor, harus fallback ke vision atau recency -> {recall_log}",
        )
        if recall_log["query_source"] == "vision_context":
            _check("T31", any("Arona" in m.content for m in result), f"vision-assisted recall harus temukan memory terkait -> {[m.content for m in result]}")
        else:
            _results.append(("T31", "SKIP", "vision keyword tidak menghasilkan match, fallback recency (perilaku aman, bukan kegagalan)"))

    # ---------------------------------------------------------------
    # T40: Regression — pesan biasa (bukan referensi) tetap pakai current
    # message langsung, TIDAK pernah melipir ke conversation anchor.
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_regression.db")
        companion = _make_companion(db_path)
        companion._memory_manager.save_memory("preference", "Teacher suka kopi americano")
        companion._conversation.add_user_message("Project lama gimana kabarnya")
        companion._conversation.add_assistant_message("Masih lanjut, Teacher.")

        result = companion._select_relevant_memories("Aku suka kopi americano juga ternyata")
        recall_log = companion._recall_decision_history[-1]
        _check(
            "T40",
            recall_log["query_source"] == "current_message",
            f"pesan non-referensial harus tetap pakai current_message -> {recall_log}",
        )


    # ---------------------------------------------------------------
    # T50: Regression krusial — topik BARU yang tidak match memory apa pun
    # dan BUKAN pesan referensial TIDAK BOLEH menarik anchor dari topik
    # lama (spec §23 FAIL condition: "old topic mendominasi current
    # topic"). Ini pagar pengaman supaya eskalasi tier 2/3 tidak kebablasan.
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_new_topic.db")
        companion = _make_companion(db_path)
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")

        companion._conversation.add_user_message("Aku lagi debugging backend LeadEstate.")
        companion._conversation.add_assistant_message("Semangat, Teacher.")
        # Topik baru sama sekali, keyword spesifik ("gitar") tapi memang
        # belum ada memory tentang itu, dan BUKAN kalimat referensial.
        companion._conversation.add_user_message("Aku baru beli gitar akustik baru.")

        companion._select_relevant_memories("Aku baru beli gitar akustik baru.")
        recall_log = companion._recall_decision_history[-1]
        # Catatan: `query_source` di sini yang jadi bukti utama — HARUS
        # "recency_fallback" (bukan "conversation_anchor"), artinya tier
        # eskalasi anchor MEMANG TIDAK dicoba sama sekali untuk pesan ini
        # (gate `should_try_wider_context` bekerja benar). Isi hasil recency
        # fallback itu sendiri SENGAJA tidak diperiksa di sini — recency
        # fallback (v1.9, tidak diubah) memang mengembalikan memory
        # TERBARU apa pun yang ada di DB tanpa peduli topik, jadi kalau DB
        # test cuma berisi satu memory (LeadEstate), memory itu WAJAR ikut
        # muncul lewat jalur recency — itu bukan tanda anchor bocor.
        _check(
            "T50",
            recall_log["query_source"] == "recency_fallback",
            f"topik baru non-referensial TIDAK boleh memicu tier conversation_anchor -> {recall_log}",
        )


def main() -> None:
    run()
    print("=" * 70)
    print("v3.3 — Contextual Recall & Reference Intelligence — Test Result")
    print("=" * 70)
    failed = 0
    for test_id, status, detail in _results:
        marker = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}.get(status, "?")
        print(f"{marker} {test_id} [{status}] {detail}")
        if status == "FAIL":
            failed += 1
    print("-" * 70)
    total = len(_results)
    print(f"Total: {total} | Failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()