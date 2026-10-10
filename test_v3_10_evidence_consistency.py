"""v3.10 — Evidence Consistency & Conflict Resolution — Regression Test.

Harness IDENTIK test_v3_9_context_budget.py (Companion.__new__, DB sementara,
tanpa GUI/provider/network). Hanya meng-assert apa yang APLIKASI kendalikan;
perilaku bebas LLM TIDAK di-assert (lihat checklist manual di execution report).

Dua bug terreproduksi pada audit Phase 0 (R01/R02) diuji sebelum+sesudah fix.
"""

from __future__ import annotations

import inspect
import os
import tempfile

from ai.companion import Companion
from ai.context_builder import ContextBuilder
from ai.conversation import Conversation
from ai.conversation_feedback import build_conversation_feedback
from ai.reference_signals import detect_reference_signal
from ai.response_calibration import build_response_calibration
from ai.temporal_signals import detect_temporal_signals
from behavior.behavior_state import DEFAULT_BEHAVIOR_STATE
from config.constants import EPHEMERAL_CONTEXT_MEMORY_LIMIT
from database.memory_manager import MemoryManager

_results: list[tuple[str, str, str]] = []


def _check(test_id: str, condition: bool, detail: str) -> None:
    _results.append((test_id, "PASS" if condition else "FAIL", detail))


def _make_companion(db_path: str) -> Companion:
    c = Companion.__new__(Companion)
    c._conversation = Conversation()
    c._memory_manager = MemoryManager(db_path=db_path)
    c._recall_decision_history = []
    c._memory_decision_history = []
    c._MEMORY_HISTORY_LIMIT = 30
    c._context_builder = ContextBuilder()
    c._performance = None
    c._last_recall_scores = {}
    c._last_temporal_signals = None
    c._last_response_calibration = None
    c._last_conversation_feedback = None
    c._last_memory_context_text = ""
    return c


def _turn(c: Companion, user: str, reply: str) -> None:
    c._conversation.add_user_message(user)
    c._conversation.add_assistant_message(reply)


def _build(c: Companion, msg: str):
    c._conversation.add_user_message(msg)
    return c._build_contents(msg, DEFAULT_BEHAVIOR_STATE)


def _texts(contents) -> list[str]:
    return [ct.parts[0].text for ct in contents]


def _ephemeral(contents) -> str:
    return _texts(contents)[0]


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        def fresh(name: str) -> Companion:
            return _make_companion(os.path.join(tmp, f"{name}.db"))

        # T01: audit precedence path nyata — evidence dikirim lewat _build_contents
        src = inspect.getsource(Companion._build_contents)
        _check("T01", all(k in src for k in (
            "detect_temporal_signals", "build_response_calibration",
            "build_conversation_feedback", "_select_relevant_memories")),
            "_build_contents memang merakit temporal/calibration/memory/feedback")

        # T02: preferensi singkat + "jelaskan detail" -> permintaan eksplisit turn ini terkirim
        c = fresh("t02")
        c._memory_manager.save_memory("preference", "Teacher lebih suka jawaban singkat")
        msg = "Untuk topik ini, jelaskan detail dan beri contoh."
        ct = _build(c, msg)
        eph = _ephemeral(ct)
        _check("T02", "jelaskan detail" in eph and msg in _texts(ct), "calibration memuat frasa eksplisit + pesan asli utuh")

        # T03: preferensi stabil tanpa override tetap tersedia lewat retrieval existing
        c = fresh("t03")
        c._memory_manager.save_memory("preference", "Teacher lebih suka jawaban singkat")
        ct = _build(c, "gimana cara kerja jawaban singkat itu")
        _check("T03", "jawaban singkat" in c._last_memory_context_text, "memory preferensi tetap dipakai tanpa override")

        # T04: "kali ini singkat aja" tidak menulis memory (tidak ada jalur tulis di build)
        c = fresh("t04")
        before = len(c._memory_manager.load_memories(limit=50, include_superseded=True))
        _build(c, "kali ini singkat aja")
        after = len(c._memory_manager.load_memories(limit=50, include_superseded=True))
        eph04 = _ephemeral(c._build_contents("kali ini singkat aja", DEFAULT_BEHAVIOR_STATE))
        _check("T04", before == after == 0 and "singkat aja" in eph04,
               "instruksi sekali pakai: evidence turn ini ada, memory DB tidak berubah")

        # T05: repair signal v3.7 tetap di akhir contents
        c = fresh("t05")
        ct = _build(c, "masih bingung, jelasin lebih gampang")
        _check("T05", "Conversation Feedback" in _texts(ct)[-1] and "lebih sederhana" in _texts(ct)[-1],
               "feedback repair di posisi akhir")

        # T06: koreksi langsung -> correction tercatat + tidak menulis memory
        c = fresh("t06")
        ct = _build(c, "bukan itu maksudku, yang kumaksud proyek Flask")
        fb = c._last_conversation_feedback
        _check("T06", fb.correction_detected and "bukan yang dimaksud" in _texts(ct)[-1]
               and not c._memory_manager.load_memories(limit=10), "correction ada, nol memory tertulis")

        # T07: fakta eksplisit saat ini vs memory lama -> pesan saat ini tidak dihapus/diubah,
        #      memory berlabel 'bukan pesan langsung Teacher' & berada SEBELUM pesan saat ini
        c = fresh("t07")
        c._memory_manager.save_memory("project", "Teacher memakai Flask untuk backend")
        msg = "Sekarang backend aku pakai FastAPI, bukan Flask lagi"
        ct = _build(c, msg)
        t = _texts(ct)
        mem_idx = next(i for i, x in enumerate(t) if "Konteks memori" in x)
        msg_idx = t.index(msg)
        _check("T07", mem_idx < msg_idx and "bukan pesan langsung dari Teacher" in t[mem_idx],
               "memory lama tidak menimpa; pesan Teacher saat ini tetap utuh & paling belakang")

        # T08: memory relevan tanpa konflik tetap muncul
        c = fresh("t08")
        c._memory_manager.save_memory("project", "Teacher membangun backend LeadEstate")
        _build(c, "bantu aku debug LeadEstate")
        _check("T08", "LeadEstate" in c._last_memory_context_text, "tidak over-filter")

        # T09: A -> B -> C -> "balik ke A tadi" (A punya memory, disebut eksplisit)
        c = fresh("t09")
        c._memory_manager.save_memory("project", "Teacher membangun backend LeadEstate dengan Laravel")
        _turn(c, "aku lagi ngerjain backend LeadEstate", "oke")
        _turn(c, "btw aku suka kopi americano", "wah")
        _turn(c, "semalam main Valorant", "hm")
        _build(c, "balik ke LeadEstate yang tadi")
        _check("T09", "LeadEstate" in c._last_memory_context_text, "topik lama ter-resolve")

        # T10 / R01: target eksplisit hanya ada di riwayat; B/C punya memory
        c = fresh("t10")
        for cat, txt in (("preference", "Teacher suka kopi americano tanpa gula"),
                         ("general", "Teacher sering main game Valorant di malam hari"),
                         ("project", "Teacher sedang main game Minecraft bareng teman")):
            c._memory_manager.save_memory(cat, txt)
        _turn(c, "aku lagi debugging parser JSON di tool kecilku", "oke")
        _turn(c, "btw aku suka banget kopi americano tanpa gula", "wah")
        _turn(c, "semalam main Valorant sampai pagi, terus Minecraft juga", "hm")
        ct = _build(c, "balik ke parser JSON yang tadi dong")
        last = _texts(ct)[-1]
        _check("T10", "WAJIB tanya klarifikasi" not in last and "ADA LEBIH DARI SATU" not in last,
               "R01: target eksplisit tidak dikalahkan recency -> tidak ada note klarifikasi B/C palsu")
        anchor = c._recent_conversation_anchor_keywords(target_keywords=["parser", "json"])
        _check("R01", "parser" in anchor and "valorant" not in anchor,
               f"anchor berasal dari turn yang disebut eksplisit -> {anchor}")

        # T10b: tanpa target cocok, perilaku v3.3 TIDAK berubah (recency anchor)
        legacy = c._recent_conversation_anchor_keywords()
        with_nomatch = c._recent_conversation_anchor_keywords(target_keywords=["zzzxyz"])
        _check("T10b", legacy == with_nomatch and "valorant" in legacy, "fallback legacy utuh")

        # T11: tanggal eksplisit tetap utuh di pesan; normalisasi hanya tambahan berlabel 'dihitung'
        c = fresh("t11")
        msg = "Besok tanggal 15 Oktober ada ujian jam 3 sore"
        ct = _build(c, msg)
        _check("T11", msg in _texts(ct) and "dihitung dari kalender" in _ephemeral(ct), "pesan eksplisit tidak diganti")

        # T12: frasa samar tidak dinormalisasi
        sig = detect_temporal_signals("nanti aku kabarin, mungkin minggu depan", now=__import__("datetime").datetime(2026, 10, 10))
        _check("T12", not sig.normalized_dates and "nanti" in sig.relative_terms, "raw cue saja")

        # T13 / R02: self-correction jelas -> bukan 'bertentangan', maksud akhir dilaporkan
        cal = build_response_calibration("jelaskan detail—eh, cukup ringkas saja")
        c = fresh("t13")
        eph = _ephemeral(_build(c, "jelaskan detail—eh, cukup ringkas saja"))
        _check("T13", cal.self_correction_final == "concise" and not cal.conflicting_cues
               and "maksud akhirnya" in eph and "saling bertentangan" not in eph,
               "R02: maksud akhir = ringkas")
        cal2 = build_response_calibration("singkat aja, eh jelasin detail ya")
        _check("T13b", cal2.self_correction_final == "detailed", "arah sebaliknya juga benar (bukan 'klausa terakhir selalu menang' buta)")
        cal3 = build_response_calibration("jelasin detail tapi singkat aja")
        _check("T13c", cal3.conflicting_cues and cal3.self_correction_final is None, "tanpa marker koreksi tetap ditandai bertentangan (v3.6)")

        # T14: konflik asli: ditandai bila terdeteksi; klarifikasi bebas = ranah LLM (tidak ada kontrol aplikasi)
        _results.append(("T14", "SKIP", "klarifikasi konflik asli ranah LLM, bukan kendali aplikasi (lihat report, manual F)"))

        # T15: tidak ada jalur tulis memory dari modul evidence
        import ai.response_calibration as rc, ai.conversation_feedback as cf, ai.temporal_signals as ts
        srcs = "".join(inspect.getsource(m) for m in (rc, cf, ts))
        _check("T15", "save_memory" not in srcs and "supersede_memory" not in srcs and "MemoryManager" not in srcs,
               "modul evidence tidak punya akses tulis memory")

        # T16: empty-section tetap hilang
        c = fresh("t16")
        eph = _ephemeral(_build(c, "halo"))
        _check("T16", "Temporal Context" not in eph and "Response Calibration" not in eph, "section kosong tidak muncul")

        # T17: budget memory v3.4
        c = fresh("t17")
        for i in range(25):
            c._memory_manager.save_memory("general", f"Teacher punya proyek robot nomor {i}")
        _build(c, "ceritakan proyek robot")
        _check("T17", c._last_memory_context_text.count("\n- ") <= EPHEMERAL_CONTEXT_MEMORY_LIMIT, "limit v3.4 utuh")

        # T18: supersession semantics
        c = fresh("t18")
        old = c._memory_manager.save_memory("preference", "Teacher suka americano")
        c._memory_manager.supersede_memory(old.id, "preference", "Teacher tidak suka americano lagi")
        active = [m.content for m in c._memory_manager.load_memories(limit=10)]
        _check("T18", active == ["Teacher tidak suka americano lagi"], f"superseded tersaring -> {active}")

        # T19: provider-independent
        c = fresh("t19")
        import ast, textwrap
        tree = ast.parse(textwrap.dedent(inspect.getsource(Companion._build_contents)))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        _check("T19", not ({"_ai_provider_name", "_gemini", "GeminiProvider", "LocalProvider", "_memory_provider_name"} & names),
               "tidak ada cabang/akses provider di kode _build_contents (AST)")

        # T20: autonomous tidak menyentuh logic v3.10
        asrc = inspect.getsource(Companion._build_autonomous_contents)
        _check("T20", "target_keywords" not in asrc and "self_correction_final" not in asrc, "autonomous tak tersentuh")

        # T21: initiative tetap decision-only
        from initiative import initiative as ini
        _check("T21", "generate(" not in inspect.getsource(ini), "initiative tidak generate bahasa")

        # T22: vision freshness path tak diubah (hanya diteruskan)
        _check("T22", "vision_context" in inspect.getsource(Companion._select_relevant_memories), "jalur vision tetap ada sebagai fallback terakhir")

        # T23: measure_sections == formatter asli
        cal = build_response_calibration("jelaskan detail—eh, cukup ringkas saja")
        cb = ContextBuilder()
        sizes = cb.measure_sections(DEFAULT_BEHAVIOR_STATE, response_calibration=cal)
        _check("T23", sizes["calibration"] == len(cb._format_response_calibration(cal)) > 0, "tidak ada drift pengukuran")

        # T24: v3.3 reference preservation: anchor tetap baca full history
        _check("T24", "get_history(max_messages" not in inspect.getsource(Companion._recent_conversation_anchor_keywords),
               "anchor tidak bergantung cap")

        # T25: history cap tetap None default
        from config.settings import CONVERSATION_HISTORY_MAX_MESSAGES
        _check("T25", CONVERSATION_HISTORY_MAX_MESSAGES is None, "cap tidak diaktifkan")

        # tambahan: reference signal v3.3 tidak berubah untuk pola balik-ke
        _check("T26", detect_reference_signal("balik ke parser JSON yang tadi dong"), "reference signal tetap terdeteksi")
        _check("T27", build_conversation_feedback("bukan itu maksudku").correction_detected, "detektor koreksi v3.7 utuh")

    print_report()


def print_report() -> None:
    print("=" * 70)
    print("v3.10 — Evidence Consistency & Conflict Resolution — Test Result")
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