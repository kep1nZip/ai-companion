"""v3.4 — Memory Relevance Ranking & Context Quality — Regression Test.

Menguji `ai/memory_ranking.py` (pure/deterministic) dan integrasinya di
`Companion._search_memories_by_keywords()`/`_select_relevant_memories()`.
Pola & harness IDENTIK `test_v3_3_reference_recall.py` — `Companion.__new__`
+ atribut minimal, `MemoryManager` dengan db_path sementara, TIDAK ADA
network call/provider sungguhan sama sekali.

Dijalankan manual: `python test_v3_4_memory_ranking.py`
Untuk regresi penuh (termasuk v3.3): jalankan juga `test_v3_3_reference_recall.py`.
"""

from __future__ import annotations

import os
import tempfile

from ai.companion import Companion
from ai.context_builder import ContextBuilder
from ai.conversation import Conversation
from ai.memory_ranking import rank_memories, score_memory
from database.memory_manager import MemoryManager
from vision.vision_context import VisionContext

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
    return companion


def run() -> None:
    # ---------------------------------------------------------------
    # T01-T05: score_memory()/rank_memories() murni — tanpa Companion
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        mm = MemoryManager(db_path=os.path.join(tmp, "pure.db"))
        m_specific = mm.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")
        m_generic = mm.save_memory("preference", "Teacher suka programming")
        keywords = ["debugging", "backend", "leadestate"]

        score_specific = score_memory(m_specific, keywords)
        score_generic = score_memory(m_generic, keywords)
        _check(
            "T01",
            score_specific > score_generic,
            f"exact topic match ({score_specific}) harus > generic ({score_generic})",
        )

        m_multi = mm.save_memory("project", "Teacher sedang mengerjakan project Arona")
        m_single = mm.save_memory("preference", "Teacher suka project lama")
        kws_ambiguous = ["project", "arona"]
        score_multi = score_memory(m_multi, kws_ambiguous)
        score_single = score_memory(m_single, kws_ambiguous)
        _check(
            "T02",
            score_multi > score_single,
            f"match 2 keyword ({score_multi}) harus > match 1 keyword ({score_single})",
        )

        m_java = mm.save_memory("preference", "Teacher pernah memakai Java")
        score_java = score_memory(m_java, keywords)
        _check(
            "T03",
            score_specific > score_java,
            f"kandidat LeadEstate spesifik ({score_specific}) TIDAK boleh dikalahkan kandidat generik ({score_java})",
        )

    # T04: recency tie-break — dua memory dengan match_count/coverage IDENTIK
    # (sama-sama nol match, mis. dipakai di skenario recency) -> yang lebih
    # baru harus menang lewat recency_component.
    with tempfile.TemporaryDirectory() as tmp:
        mm = MemoryManager(db_path=os.path.join(tmp, "tie.db"))
        m_old = mm.save_memory("general", "Teacher cerita soal masa kecil")
        m_new = mm.save_memory("general", "Teacher cerita soal masa kuliah")
        ranked = rank_memories([m_old, m_new], keywords=["takterkait"])
        _check(
            "T04",
            ranked[0].id == m_new.id,
            f"tie-break recency: memory lebih baru ({m_new.id}) harus menang saat skor lain identik -> urutan {[m.id for m in ranked]}",
        )

    # T05: memory LAMA yang sangat relevan harus tetap mengalahkan memory
    # BARU yang cuma cocok lemah (generic) — recency TIDAK BOLEH overpower
    # relevansi topikal (spec §5.5).
    with tempfile.TemporaryDirectory() as tmp:
        mm = MemoryManager(db_path=os.path.join(tmp, "old_relevant.db"))
        m_old_relevant = mm.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")
        m_new_weak = mm.save_memory("preference", "Teacher suka ngoding")
        ranked = rank_memories([m_new_weak, m_old_relevant], keywords=["backend", "leadestate"])
        _check(
            "T05",
            ranked[0].id == m_old_relevant.id,
            f"memory LAMA relevan harus mengalahkan memory BARU tapi lemah -> urutan {[m.id for m in ranked]}",
        )

    # ---------------------------------------------------------------
    # T06: Duplicate Removal — lewat Companion penuh (search_memory per kata,
    # 1 memory match >1 keyword sekaligus -> harus dihitung sbg duplicate,
    # bukan muncul 2x).
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "dedup.db"))
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")
        result = companion._select_relevant_memories("Aku lagi debugging backend LeadEstate")
        ids = [m.id for m in result]
        recall_log = companion._recall_decision_history[-1]
        _check(
            "T06",
            len(ids) == len(set(ids)) and recall_log["duplicates_removed"] >= 1,
            f"memory yang match >1 keyword ('backend' & 'leadestate') HARUS cuma muncul sekali, "
            f"duplicates_removed harus tercatat -> ids={ids}, log={recall_log}",
        )

    # ---------------------------------------------------------------
    # T07: Stable Ordering — input identik dipanggil berkali-kali -> urutan
    # output harus identik persis setiap kali (tidak ada randomness).
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "stable.db"))
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan LeadEstate")
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan project Arona")
        orders = []
        for _ in range(5):
            result = companion._select_relevant_memories("Aku lagi ngerjain LeadEstate dan project Arona")
            orders.append(tuple(m.id for m in result))
        _check("T07", len(set(orders)) == 1, f"urutan hasil HARUS identik di setiap pemanggilan berulang -> {orders}")

    # ---------------------------------------------------------------
    # T08-T11: Regresi tier v3.3 (current_message / anchor / vision /
    # ambiguous) tetap bekerja setelah ranking masuk.
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t08.db"))
        companion._memory_manager.save_memory("preference", "Teacher suka kopi americano")
        result = companion._select_relevant_memories("Aku suka kopi americano juga")
        recall_log = companion._recall_decision_history[-1]
        _check("T08", recall_log["query_source"] == "current_message" and len(result) == 1, f"current_message tier -> {recall_log}")

    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t09.db"))
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")
        companion._conversation.add_user_message("Aku lagi debugging backend LeadEstate.")
        companion._conversation.add_assistant_message("Semangat, Teacher.")
        companion._conversation.add_user_message("lanjut yang tadi")
        result = companion._select_relevant_memories("lanjut yang tadi")
        recall_log = companion._recall_decision_history[-1]
        _check(
            "T09",
            recall_log["query_source"] == "conversation_anchor" and any("LeadEstate" in m.content for m in result),
            f"conversation_anchor tier -> {recall_log}",
        )

    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t10.db"))
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan VTuber avatar Arona")
        companion._conversation.add_user_message("yang ini kenapa error ya")
        vision_context = VisionContext(summary="Error dialog muncul.", application="VTuber Arona editor")
        result = companion._select_relevant_memories("yang ini kenapa error ya", vision_context)
        recall_log = companion._recall_decision_history[-1]
        _check(
            "T10",
            recall_log["query_source"] in {"vision_context", "recency_fallback"},
            f"vision_context tier fallback -> {recall_log}",
        )

    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t11.db"))
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan LeadEstate")
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan project Arona")
        companion._conversation.add_user_message("Aku lagi ngerjain LeadEstate dan project Arona.")
        companion._conversation.add_assistant_message("Oke, semangat Teacher!")
        companion._conversation.add_user_message("lanjut yang tadi")
        result = companion._select_relevant_memories("lanjut yang tadi")
        contents = [m.content for m in result]
        _check(
            "T11",
            any("LeadEstate" in c for c in contents) and any("Arona" in c for c in contents),
            f"KEDUA kandidat ambigu harus tetap ada setelah ranking (tidak boleh ada 'pemenang' tunggal dipaksakan) -> {contents}",
        )

    # ---------------------------------------------------------------
    # T12: Unrelated Topic Guard — memory tidak terkait yang kebetulan
    # mengandung kata umum TIDAK boleh mendominasi topik baru yang spesifik.
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t12.db"))
        companion._memory_manager.save_memory("general", "Teacher pernah cerita soal project kuliahnya dulu")
        companion._memory_manager.save_memory("project", "Teacher sedang mengerjakan backend LeadEstate")
        result = companion._select_relevant_memories("Aku lagi debugging backend LeadEstate")
        _check(
            "T12",
            result and "LeadEstate" in result[0].content,
            f"memory LeadEstate spesifik HARUS peringkat #1, bukan memory 'project kuliah' yang cuma kebetulan match -> {[m.content for m in result]}",
        )

    # ---------------------------------------------------------------
    # T13: Active vs Superseded — memory yang sudah di-supersede TIDAK BOLEH
    # ikut nongol lagi lewat ranking (regresi v2.5/v2.6, bukan fitur baru).
    # ---------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        companion = _make_companion(os.path.join(tmp, "t13.db"))
        old = companion._memory_manager.save_memory("preference", "Teacher suka americano")
        companion._memory_manager.supersede_memory(old.id, "preference", "Teacher tidak suka americano lagi")
        result = companion._select_relevant_memories("Amerika americano gimana ya")
        contents = [m.content for m in result]
        _check(
            "T13",
            "Teacher suka americano" not in contents,
            f"memory yang SUDAH di-supersede TIDAK BOLEH muncul lagi di hasil ranking -> {contents}",
        )

    # ---------------------------------------------------------------
    # T14: Provider Independence — ranking murni fungsi atas data, TIDAK
    # ADA cabang provider apa pun. Dibuktikan (a) tidak ada string
    # "gemini"/"local" dicek di modul ranking, (b) output deterministik utk
    # input sama dipanggil ulang.
    # ---------------------------------------------------------------
    with open("ai/memory_ranking.py", encoding="utf-8") as f:
        ranking_source = f.read().lower()
    _check(
        "T14",
        "provider ==" not in ranking_source and '"local"' not in ranking_source and '"gemini"' not in ranking_source,
        "ai/memory_ranking.py TIDAK BOLEH mengandung cabang logic spesifik provider apa pun",
    )

    print_report()


def print_report() -> None:
    print("=" * 70)
    print("v3.4 — Memory Relevance Ranking & Context Quality — Test Result")
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