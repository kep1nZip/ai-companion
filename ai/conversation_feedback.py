from __future__ import annotations

import re
from dataclasses import dataclass

# v3.7 — Conversational Feedback & Repair Intelligence
# (spec V3_7_CONVERSATIONAL_FEEDBACK_REPAIR_INTELLIGENCE_DESIGN_SPEC.md) —
# modul BARU, pola IDENTIK `ai/response_calibration.py` (v3.6)/`ai/temporal_
# signals.py` (v3.5): pure/deterministic, TIDAK ADA LLM call, TIDAK ADA
# network call, TIDAK ADA state/database baru. Modul ini HANYA melaporkan
# APA YANG TEACHER KATAKAN tentang interaksi sebelumnya — TIDAK PERNAH
# menilai kualitas balasan Arona sendiri (Hard Boundary spec §4.1/§4.2:
# "No Self-Evaluation LLM", "No Hidden 'Arona Was Wrong' State"). LLM
# percakapan yang sudah ada TETAP satu-satunya yang memperbaiki/
# menyesuaikan jawabannya — modul ini cuma menyediakan fakta tekstual.
#
# Phase 0 Audit (ringkasan, detail lengkap di V3.7_EXECUTION_REPORT.md):
# - `ai/conversation_signals.py::detect_closure()` (v2.8) SUDAH mendeteksi
#   pola "oke makasih"/"udah ngerti"/"sip" — TAPI dipakai untuk keputusan
#   Initiative/Routine ("bolehkah Arona bicara proaktif", bukan evidence ke
#   LLM), berupa SATU boolean tunggal, TIDAK membedakan "sekadar paham"
#   vs "menutup topik". DI-REUSE LANGSUNG (import) sebagai salah satu
#   komponen `closure_detected` di bawah — TIDAK direimplementasi, TIDAK
#   diubah (zero risk terhadap Initiative/Routine yang sudah stabil sejak
#   v2.8). Pola TAMBAHAN ("udah cukup", dst) yang belum dicakup
#   `detect_closure()` ditambah LOKAL di modul ini, BUKAN dengan mengubah
#   `ai/conversation_signals.py` (spec §29 TIDAK melarang itu secara
#   eksplisit, TAPI mengubah fungsi yang dipakai subsystem lain yang sudah
#   stabil berisiko regresi yang tidak perlu — smallest safe change).
# - `behavior/emotion_analyzer.py::_BAD_NEWS_PATTERNS` TIDAK mencakup
#   "bingung" sama sekali — confusion TIDAK ADA detector di manapun
#   sebelum v3.7, gap nyata.
# - confusion/correction/length-feedback/complexity-feedback/repeat/
#   simplification/expansion — NOL detector ada di codebase manapun
#   sebelum v3.7, semua gap nyata, dibangun di sini.
# - `Conversation` (v1.x) SUDAH mengirim balasan Arona SEBELUMNYA sebagai
#   bagian riwayat (`role="model"`) setiap turn — LLM SUDAH melihat apa
#   yang baru saja dia katakan tanpa perlu mekanisme tambahan apa pun;
#   v3.7 TIDAK membuat "riwayat percakapan kedua" (Hard Boundary §4.3/§4.4).


# ---------------------------------------------------------------------------
# Phase 1/3 — Feedback Cue Detection (tiap kategori independen, SEMUA bisa
# muncul bersamaan dalam satu pesan — spec §8 "Multi-Cue Feedback", TIDAK
# dipaksa jadi satu pemenang)
# ---------------------------------------------------------------------------

_CONFUSION_PATTERNS = [
    r"\b(?:nggak|ga|gak)\s+ngerti\b",
    r"\bmasih\s+bingung\b",
    r"\bbingung\b",
    r"\bkurang\s+paham\b",
    r"\bbelum\s+paham\b",
    r"\bkurang\s+ngerti\b",
]

# SENGAJA tidak termasuk kata "salah" berdiri sendiri — terlalu ambigu
# (bisa berarti "kode saya salah di baris X", problem_report biasa, BUKAN
# koreksi terhadap interpretasi Arona). Hanya frasa yang SECARA SPESIFIK
# menunjuk ke kesalahpahaman Arona yang dimasukkan (spec §9: konservatif).
_CORRECTION_PATTERNS = [
    r"\bbukan\s+itu\s+maksudku\b",
    # "bukan yang tadi itu"/"bukan yang itu" — izinkan SATU kata sisipan
    # opsional antara "yang" dan "itu" (mis. "tadi") supaya tetap match
    # pola percakapan natural tanpa jadi terlalu longgar (bukan wildcard
    # bebas — tetap dibatasi SATU kata, bukan `.*`).
    r"\bbukan\s+(?:yang\s+(?:\w+\s+)?)?itu\b",
    r"\bmaksudku\s+bukan\s+begitu\b",
    r"\bbukan\s+maksudku\b",
    r"\bbukan\s+gitu\b",
    r"\bsalah\s+paham\b",
]

_LENGTH_FEEDBACK_PATTERNS = [
    r"\bkepanjangan\b",
    r"\bterlalu\s+panjang\b",
    r"\bpanjang\s+banget\b",
    r"\bkebanyakan\b",
]

_COMPLEXITY_FEEDBACK_PATTERNS = [
    r"\bterlalu\s+ribet\b",
    r"\bsusah\s+dipahami\b",
    r"\bterlalu\s+teknis\b",
]

_REPEAT_REQUEST_PATTERNS = [
    r"\bulang\s+dari\s+awal\b",
    r"\bcoba\s+jelasin\s+lagi\b",
    r"\bjelasin\s+lagi\b",
    r"\bulang\s+dong\b",
    r"\bcoba\s+lagi\b",
    r"\bulangin\b",
    r"\bsekali\s+lagi\b",
]

_SIMPLIFICATION_REQUEST_PATTERNS = [
    r"\bjelasin\s+dengan\s+bahasa\s+gampang\b",
    r"\bjelasin\s+kayak\s+pemula\b",
    r"\bjelasin\s+lebih\s+gampang\b",
    r"\blebih\s+gampang\s+dong\b",
    r"\blebih\s+sederhana\b",
    r"\byang\s+(?:lebih\s+)?gampang\b",
]

# SENGAJA TIDAK termasuk kata "lanjut" berdiri sendiri — terlalu umum &
# ambigu (bentrok dengan "lanjut yang tadi" di v3.3, akan mendominasi
# false-positive). Hanya frasa yang SECARA SPESIFIK minta perluasan
# jawaban yang dimasukkan.
_EXPANSION_REQUEST_PATTERNS = [
    r"\bjelasin\s+lebih\s+lengkap\b",
    r"\bbahas\s+lebih\s+dalam\b",
    r"\blebih\s+detail\b",
]

# Lebih RINGAN dari `detect_closure()` (v2.8) — sekadar mengonfirmasi
# paham, BELUM TENTU menutup topik/percakapan.
_ACKNOWLEDGEMENT_PATTERNS = [
    r"\boke\s+ngerti\b",
    r"\budah\s+ngerti\b",
    r"\bohh?\s+ngerti\b",
    r"\bpaham\b",
    r"\bngerti\b",
    r"\bsip\b",
]

# TAMBAHAN di luar `detect_closure()` (v2.8) — frasa penutup topik yang
# BELUM dicakup pola v2.8 (yang fokus ke "mengakhiri SESI/percakapan",
# bukan "menutup SATU topik/pertanyaan").
_CLOSURE_SUPPLEMENT_PATTERNS = [
    r"\budah\s+cukup\b",
    r"\bcukup,?\s*makasih\b",
    r"\bmakasih,?\s*(?:udah\s+)?ngerti\b",
]


def _collect(text_lower: str, patterns: list[str], phrases: list[str]) -> bool:
    """Scan SEMUA pola dalam satu kategori — return True kalau ADA yang
    match (minimal satu), dan kumpulkan teks VERBATIM yang match ke
    `phrases` (dipakai utuh di ContextBuilder, bukan label abstrak —
    pelajaran dari hotfix v3.3 round 2: konkret > abstrak untuk model
    yang lebih lemah). TIDAK melakukan non-overlap bookkeeping antar
    kategori BEDA (beda dari `ai/temporal_signals.py`/`ai/response_
    calibration.py`) — kategori di modul ini saling independen by design
    (spec §8: semua cue valid harus tetap ada), overlap antar kategori
    justru DIHARAPKAN (mis. "masih bingung" & kalimat lanjutannya "ulang
    dong" sah-sah saja dua-duanya terdeteksi)."""
    found = False
    for p in patterns:
        m = re.search(p, text_lower)
        if m:
            found = True
            phrase = m.group(0)
            if phrase not in phrases:
                phrases.append(phrase)
    return found


def detect_confusion_cues(text: str) -> bool:
    return bool(re.search("|".join(_CONFUSION_PATTERNS), (text or "").lower()))


def detect_correction_cues(text: str) -> bool:
    return bool(re.search("|".join(_CORRECTION_PATTERNS), (text or "").lower()))


def detect_repeat_requests(text: str) -> bool:
    return bool(re.search("|".join(_REPEAT_REQUEST_PATTERNS), (text or "").lower()))


def detect_acknowledgement(text: str) -> bool:
    return bool(re.search("|".join(_ACKNOWLEDGEMENT_PATTERNS), (text or "").lower()))


def detect_feedback_cues(text: str) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    """Entry point utama Phase 1/3/8 — scan SEMUA 9 kategori sekaligus.
    Return `(feedback_cues, explicit_phrases, closure_detected)`:

    - `feedback_cues`: tuple kategori yang terdeteksi (urutan tetap: confusion,
      correction, negative_length_feedback, negative_complexity_feedback,
      repeat_request, simplification_request, expansion_request,
      positive_acknowledgement) — BISA lebih dari satu sekaligus (spec §8),
      TIDAK PERNAH dipaksa jadi satu pemenang.
    - `explicit_phrases`: potongan teks verbatim gabungan semua kategori
      yang match (urutan kemunculan pertama).
    - `closure_detected`: DIPISAH dari `feedback_cues` (bukan masuk tuple
      itu) karena nilainya BENAR-BENAR reuse `detect_closure()` (v2.8,
      import langsung) DIGABUNG `or` dengan `_CLOSURE_SUPPLEMENT_PATTERNS`
      lokal — bukan pattern baru murni milik modul ini sendiri."""
    from ai.conversation_signals import detect_closure  # import lokal: hindari import siklik modul v2.8<->v3.7

    t = (text or "").lower()
    cues: list[str] = []
    phrases: list[str] = []

    if _collect(t, _CONFUSION_PATTERNS, phrases):
        cues.append("confusion")
    if _collect(t, _CORRECTION_PATTERNS, phrases):
        cues.append("correction")
    if _collect(t, _LENGTH_FEEDBACK_PATTERNS, phrases):
        cues.append("negative_length_feedback")
    if _collect(t, _COMPLEXITY_FEEDBACK_PATTERNS, phrases):
        cues.append("negative_complexity_feedback")
    if _collect(t, _REPEAT_REQUEST_PATTERNS, phrases):
        cues.append("repeat_request")
    if _collect(t, _SIMPLIFICATION_REQUEST_PATTERNS, phrases):
        cues.append("simplification_request")
    if _collect(t, _EXPANSION_REQUEST_PATTERNS, phrases):
        cues.append("expansion_request")
    if _collect(t, _ACKNOWLEDGEMENT_PATTERNS, phrases):
        cues.append("positive_acknowledgement")

    closure_supplement = _collect(t, _CLOSURE_SUPPLEMENT_PATTERNS, phrases)
    closure_detected = bool(detect_closure(text)) or closure_supplement
    if closure_detected:
        cues.append("closure")

    return tuple(cues), tuple(phrases), closure_detected


# ---------------------------------------------------------------------------
# Struktur hasil + entrypoint gabungan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversationFeedback:
    """Wadah EVIDENCE murni (spec §23/§28) — SETIAP field adalah OBSERVASI
    tekstual, BUKAN kesimpulan/penilaian. TIDAK ADA field
    `previous_response_quality`/`misunderstanding_score`/`assistant_error_
    score` di sini SAMA SEKALI (Hard Boundary §4.2), TIDAK ADA angka
    confidence buatan (spec §28: "No fabricated confidence")."""
    feedback_cues: tuple[str, ...] = ()
    explicit_phrases: tuple[str, ...] = ()
    correction_detected: bool = False
    repeat_requested: bool = False
    closure_detected: bool = False
    conflicting_feedback: bool = False

    def is_empty(self) -> bool:
        """True kalau TIDAK ADA evidence feedback apa pun — dipakai
        `ai/context_builder.py` untuk memutuskan apakah section
        "Conversation Feedback" perlu ditulis sama sekali (spec §15:
        "Only show the section when meaningful feedback evidence
        exists")."""
        return not (self.feedback_cues or self.explicit_phrases)


def build_conversation_feedback(text: str) -> ConversationFeedback:
    """SATU-SATUNYA entrypoint dipakai `Companion` — menghitung seluruh
    evidence feedback dari `text` (pesan Teacher yang SEDANG diproses turn
    ini). `conflicting_feedback` True kalau ada kombinasi yang secara
    alami bertentangan (spec §8, pola IDENTIK `conflicting_cues` di
    `ai/response_calibration.py` v3.6 — ditandai, TIDAK pernah diresolusi
    aplikasi): simplification_request BERSAMAAN expansion_request (minta
    lebih sederhana SEKALIGUS lebih lengkap), atau confusion BERSAMAAN
    positive_acknowledgement (bingung SEKALIGUS mengaku paham)."""
    feedback_cues, explicit_phrases, closure_detected = detect_feedback_cues(text)
    cue_set = set(feedback_cues)

    conflicting = bool(
        {"simplification_request", "expansion_request"} <= cue_set
        or {"confusion", "positive_acknowledgement"} <= cue_set
    )

    return ConversationFeedback(
        feedback_cues=feedback_cues,
        explicit_phrases=explicit_phrases,
        correction_detected="correction" in cue_set,
        repeat_requested="repeat_request" in cue_set,
        closure_detected=closure_detected,
        conflicting_feedback=conflicting,
    )