from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# v3.6 — Adaptive Response Calibration & Conversational Pacing
# (spec V3_6_ADAPTIVE_RESPONSE_CALIBRATION_CONVERSATIONAL_PACING_DESIGN_SPEC.md)
# — modul BARU, pola IDENTIK `ai/reference_signals.py` (v3.3)/`ai/temporal_
# signals.py` (v3.5): pure/deterministic, TIDAK ADA LLM call, TIDAK ADA
# network call, TIDAK ADA state/database baru. Modul ini HANYA
# mengembalikan EVIDENCE (sinyal leksikal + bentuk percakapan dangkal) —
# TIDAK PERNAH menyusun/memaksa teks jawaban Arona (Hard Boundary spec
# §4.1/§4.2: "No Second LLM", "No Response Template Engine"). LLM
# percakapan yang sudah ada TETAP satu-satunya yang memutuskan kata-kata,
# panjang, dan nada jawaban — modul ini cuma menyediakan fakta "apa yang
# Teacher baru saja katakan", persis prinsip inti spec §2.
#
# Phase 0 Audit (ringkasan, detail lengkap di V3.6_EXECUTION_REPORT.md):
# - `ai/conversation_signals.py::detect_style_preference()` (v3.0) SUDAH
#   mendeteksi concise/detailed, TAPI murni observasional untuk Dashboard
#   (TIDAK PERNAH masuk ke `contents` yang dikirim ke provider — lihat
#   docstring fungsi itu sendiri), dan COLLAPSE jadi SATU nilai (kalau ada
#   dua cue kontradiktif dalam satu pesan, salah satu hilang begitu saja).
#   TIDAK disentuh (Hard Boundary §25: tidak ada bug konkret di situ) —
#   v3.6 membangun detector SENDIRI yang lebih lengkap (depth_cues berupa
#   TUPLE, bisa lebih dari satu sekaligus) tanpa mengubah fungsi v3.0 itu.
# - `prompts/system_rules.txt` SUDAH punya instruksi umum "Keep answers
#   concise by default, unless Teacher explicitly asks for more detail" —
#   ALREADY SATISFIED untuk KEBIJAKAN DEFAULT, TIDAK disentuh. Gap
#   sebenarnya: instruksi itu general/statis di awal prompt, BUKAN evidence
#   KONKRET per-pesan di dekat titik generasi (persis pola yang sudah
#   terbukti perlu diperkuat di v3.3 round 2 — konkret mengalahkan
#   abstrak untuk model yang lebih lemah). ContextBuilder section baru
#   di bawah (dipasang lewat `ai/context_builder.py`) yang mengisi gap ini.
# - `behavior/emotion_analyzer.py` SUDAH menangkap "capek"/"lelah" sebagai
#   sinyal emosi yang masuk ke Behavior Engine (sudah ada di context lewat
#   "Current Emotion"/"Internal State") — ALREADY SATISFIED, v3.6 TIDAK
#   membuat detector emosi baru (Hard Boundary spec §10 Phase 5).
# - `ai/reference_signals.py::detect_reference_signal()` (v3.3) dan
#   `ai/temporal_signals.py::detect_completion_cues()`/`detect_unresolved_
#   cues()` (v3.5) DI-REUSE LANGSUNG (import, bukan reimplementasi) untuk
#   mendeteksi form "reference_followup"/"completion_statement"/
#   "problem_report" — spec §16 eksplisit: evidence v3.3/v3.5/v3.6 HARUS
#   koeksis, bukan saling menduplikasi.


# ---------------------------------------------------------------------------
# Phase 1 — Explicit User Pacing Cues (depth_cues + explicit_phrases)
# ---------------------------------------------------------------------------

# Spesifik dulu ("jelasin pelan-pelan" sebagai DETAILED) supaya bare
# "pelan-pelan" (STEP_BY_STEP) di bawah tidak dobel-match span yang sama —
# pola non-overlap yang sama dipakai `ai/temporal_signals.py`.
_DETAILED_PATTERNS = [
    r"\bjelasin\s+pelan-pelan\b",
    r"\bjelasin\s+detail\b",
    r"\bjelaskan\s+(?:secara\s+)?(?:detail|lengkap|rinci)\b",
    r"\bdetail(?:kan)?\s+(?:dong|ya|donk)\b",
    r"\bbahas\s+lengkap\b",
    r"\blebih\s+(?:rinci|detail|lengkap|dalam)\b",
]
_STEP_BY_STEP_PATTERNS = [
    r"\bsatu-satu\b",
    r"\bstep\s*by\s*step\b",
    r"\blangkah\s+demi\s+langkah\b",
    r"\bpelan-pelan\b",  # kalau belum diklaim "jelasin pelan-pelan" di atas
    r"\bdari\s+awal\b",
]
_CONCISE_PATTERNS = [
    r"\b(?:ga|gak|nggak)\s+usah\s+(?:terlalu\s+)?panjang\b",
    r"\bjangan\s+(?:terlalu\s+)?panjang\b",
    r"\btidak\s+usah\s+(?:terlalu\s+)?panjang\b",
    r"\bsingkat\s+(?:aja|saja)\b",
    r"\byang\s+singkat\b",
    r"\bjawab\s+pendek\b",
    r"\blangsung\s+jawab\b",
    r"\blangsung\s+aja\b",
    r"\blangsung\s+inti\b",
    r"\bto\s+the\s+point\b",
    r"\bringkas\s+(?:aja|saja)\b",
    r"\bintinya\s+aja\b",
]


def detect_depth_cues(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Deteksi cue kedalaman jawaban yang DIUCAPKAN EKSPLISIT Teacher — spec
    §6 (Phase 1). Return `(depth_cues, explicit_phrases)`:

    - `depth_cues`: kategori yang terdeteksi, SETIAP kategori MAKSIMAL
      sekali ("concise"/"detailed"/"step_by_step"), BISA LEBIH DARI SATU
      sekaligus kalau pesan memang mengandung cue yang bertentangan (spec
      §12 Phase 7 "Contradictory Explicit Cues" — mis. "jelasin detail
      tapi singkat aja" -> `("detailed", "concise")`). TIDAK PERNAH
      di-resolve jadi satu nilai di sini — itu keputusan LLM, bukan
      aplikasi (spec: "Let the LLM interpret the natural tradeoff").
    - `explicit_phrases`: potongan teks VERBATIM yang match (mis.
      `("jelasin detail", "singkat aja")`) — dipakai utuh di ContextBuilder
      supaya evidence yang dikirim ke LLM konkret, BUKAN meta-label
      abstrak (pelajaran dari v3.3 round 2 hotfix: konkret > abstrak untuk
      model yang lebih lemah).

    Deteksi SENGAJA konservatif (word-boundary ketat, frasa utuh) — TIDAK
    PERNAH menyimpulkan "Teacher selalu suka jawaban pendek" dari satu
    kalimat (spec §6 eksplisit melarang itu); hasil fungsi ini HANYA
    berlaku untuk PESAN INI, pemanggil tidak menyimpannya sebagai
    preferensi permanen (itu tetap wewenang `MemoryExtractor` yang sudah
    ada, kalau memang messagenya eksplisit jangka panjang)."""
    depth_cues, explicit_phrases, _spans = _scan_depth_cues(text)
    return depth_cues, explicit_phrases


def _scan_depth_cues(
    text: str,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, tuple[int, int]]]:
    """v3.10 — badan asli `detect_depth_cues()` (v3.6, logic TIDAK berubah)
    dipindah ke sini supaya posisi (span) match tiap kategori ikut
    dikembalikan — dibutuhkan `_resolve_self_correction()` di bawah untuk
    tahu URUTAN cue dalam kalimat. `detect_depth_cues()` publik tetap
    mengembalikan 2 nilai persis seperti sebelumnya (backward-compat)."""
    t = (text or "").lower()
    depth_cues: list[str] = []
    explicit_phrases: list[str] = []
    covered: list[tuple[int, int]] = []
    cue_spans: dict[str, tuple[int, int]] = {}

    def check(patterns: list[str], category: str) -> bool:
        matched_any = False
        for p in patterns:
            m = re.search(p, t)
            if not m:
                continue
            span = m.span()
            if any(s0 <= span[0] < s1 or span[0] <= s0 < span[1] for s0, s1 in covered):
                continue
            covered.append(span)
            explicit_phrases.append(m.group(0))
            if category not in cue_spans or span[0] < cue_spans[category][0]:
                cue_spans[category] = span
            matched_any = True
        return matched_any

    if check(_DETAILED_PATTERNS, "detailed"):
        depth_cues.append("detailed")
    if check(_STEP_BY_STEP_PATTERNS, "step_by_step"):
        depth_cues.append("step_by_step")
    if check(_CONCISE_PATTERNS, "concise"):
        depth_cues.append("concise")

    return tuple(depth_cues), tuple(explicit_phrases), cue_spans


# v3.10 — Self-correction dalam SATU pesan (spec v3.10 §4.4: "jelaskan
# detail—eh, cukup ringkas saja" -> ikuti maksud akhir untuk turn ini).
# SENGAJA sempit: marker koreksi EKSPLISIT harus ada di antara dua cue yang
# bertentangan. Tanpa marker ("jelasin detail tapi singkat aja") tetap
# dianggap bertentangan seperti v3.6 — BUKAN aturan "klausa terakhir selalu
# menang" (spec §4.4 melarang aturan rapuh itu).
_SELF_CORRECTION_MARKERS = re.compile(
    r"(?:\beh\b|\bralat\b|\bkoreksi\b|\bmaksudku\b|\bmaksud\s+aku\b"
    r"|\b(?:ga|gak|nggak|tidak)\s+jadi\b|\bmaaf\s+salah\b)"
)


def _resolve_self_correction(
    text: str, cue_spans: dict[str, tuple[int, int]]
) -> Optional[str]:
    """Return kategori cue AKHIR ("concise"/"detailed") kalau ada marker
    koreksi eksplisit di ANTARA cue concise dan detailed; selain itu None.
    Pure/deterministic, tidak ada skor/confidence."""
    if "concise" not in cue_spans or "detailed" not in cue_spans:
        return None
    c, d = cue_spans["concise"], cue_spans["detailed"]
    if c[0] < d[0]:
        first_end, last_start, last_cat = c[1], d[0], "detailed"
    else:
        first_end, last_start, last_cat = d[1], c[0], "concise"
    between = (text or "").lower()[first_end:last_start]
    if _SELF_CORRECTION_MARKERS.search(between):
        return last_cat
    return None


# ---------------------------------------------------------------------------
# Phase 2/4 — Conversational Form Evidence (lightweight, bukan klasifikasi
# semantik penuh — "unknown"/None kalau bukti leksikal tidak cukup)
# ---------------------------------------------------------------------------

_REQUEST_MARKERS = [
    r"\bjelasin\b", r"\bjelaskan\b", r"\bajarin\b", r"\bajari\b",
    r"\btolong\b", r"\bbisa(?:kah)?\s", r"\bcoba(?:kan)?\s+jelasin\b",
]
_PROGRESS_MARKERS = [
    r"\b(?:lagi|sedang)\s+(?:ngerjain|mengerjakan|debugging|develop|bikin|develop(?:ing)?)\b",
]
_PROBLEM_WORD_MARKERS = [
    r"\berror\b", r"\bgagal\b", r"\brusak\b", r"\bbug\b",
    r"\b(?:nggak|ga|gak)\s+jalan\b", r"\bstuck\b", r"\bcrash\b",
]
_ACKNOWLEDGEMENT_PATTERNS = [
    r"^\s*(?:ohh?\s+iya|oh\s+gitu|ohh?|oke|ok|iya|ya|hmm|wah|oalah)\s*[.!]*\s*$",
]


def detect_conversation_form(
    text: str,
    *,
    reference_signal: bool = False,
    unresolved_cues: tuple[str, ...] = (),
    completion_cues: tuple[str, ...] = (),
) -> Optional[str]:
    """Deteksi bentuk percakapan DANGKAL (spec §7 Phase 2) — SATU label per
    pesan (beda dari `detect_depth_cues()` yang bisa multi-kategori), atau
    `None` ("unknown") kalau tidak ada bukti leksikal yang cukup kuat
    (spec: "Prefer form = unknown over a false hard classification").

    REUSE langsung (parameter opsional, dihitung PEMANGGIL lewat fungsi
    v3.3/v3.5 yang SUDAH ADA — modul ini TIDAK memanggil ulang/reimport
    detector itu sendiri supaya TIDAK ADA logic yang terhitung dua kali,
    spec §16): `reference_signal` dari `detect_reference_signal()`
    (`ai/reference_signals.py`), `unresolved_cues`/`completion_cues` dari
    `detect_temporal_signals()` (`ai/temporal_signals.py`).

    Urutan prioritas (lexical, bukan skor numerik — spec §11 "Do not
    invent numeric confidence scores. Prefer categorical evidence."):
    question -> problem_report -> completion_statement -> progress_update
    -> request -> acknowledgement -> reference_followup (fallback paling
    akhir, HANYA kalau tidak ada bukti lain apa pun selain pesan ini
    memang menunjuk balik ke sesuatu — spec §16 contoh: pesan yang JUGA
    mengandung bukti problem_report tetap diberi label problem_report,
    BUKAN reference_followup, walau sama-sama mengandung referensi)."""
    stripped = (text or "").strip()
    t = stripped.lower()
    if not t:
        return None

    # Cek "?" di MANA PUN di pesan (bukan cuma di akhir) — pesan Teacher
    # sering multi-kalimat ("kenapa API error? singkat aja", spec §20 T11),
    # tanda tanya bisa ada di tengah, bukan cuma di penghujung kalimat
    # terakhir. Tanda tanya tetap sinyal yang sangat kuat & jarang false-
    # positive di Bahasa Indonesia sehari-hari, aman dipakai longgar begini.
    if "?" in stripped:
        return "question"

    if unresolved_cues or any(re.search(p, t) for p in _PROBLEM_WORD_MARKERS):
        return "problem_report"

    if completion_cues:
        return "completion_statement"

    if any(re.search(p, t) for p in _PROGRESS_MARKERS):
        return "progress_update"

    if any(re.search(p, t) for p in _REQUEST_MARKERS):
        return "request"

    if any(re.search(p, t.rstrip(".!?, ")) for p in _ACKNOWLEDGEMENT_PATTERNS):
        return "acknowledgement"

    if reference_signal:
        return "reference_followup"

    return None


# ---------------------------------------------------------------------------
# Struktur hasil + entrypoint gabungan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResponseCalibration:
    """Wadah EVIDENCE murni (spec §23/§26) — SETIAP field adalah OBSERVASI
    leksikal, BUKAN kesimpulan/instruksi. TIDAK ADA field
    "response_quality"/"confidence"/"best_style" di sini SAMA SEKALI (Hard
    Boundary §19: dashboard/evidence tidak boleh memuat angka confidence
    yang dikarang)."""
    conversation_form: Optional[str] = None
    depth_cues: tuple[str, ...] = ()
    explicit_phrases: tuple[str, ...] = ()
    step_by_step_requested: bool = False
    conflicting_cues: bool = False
    # v3.10: kategori maksud AKHIR ("concise"/"detailed") kalau Teacher
    # mengoreksi dirinya sendiri secara eksplisit dalam pesan yang sama;
    # None = tidak ada self-correction terdeteksi.
    self_correction_final: Optional[str] = None

    def is_empty(self) -> bool:
        """True kalau TIDAK ADA evidence kalibrasi apa pun — dipakai
        `ai/context_builder.py` untuk memutuskan apakah section "Response
        Calibration" perlu ditulis sama sekali (spec §13: section
        OPSIONAL, jangan muncul kosong)."""
        return not (self.conversation_form or self.depth_cues or self.explicit_phrases)


def build_response_calibration(
    text: str,
    *,
    reference_signal: bool = False,
    unresolved_cues: tuple[str, ...] = (),
    completion_cues: tuple[str, ...] = (),
) -> ResponseCalibration:
    """SATU-SATUNYA entrypoint gabungan dipakai `Companion` — menghitung
    `depth_cues`/`explicit_phrases` (Phase 1) + `conversation_form`
    (Phase 2), lalu `conflicting_cues` (Phase 7: True kalau `depth_cues`
    memuat "concise" DAN "detailed" sekaligus — kombinasi bertentangan
    yang SENGAJA TIDAK diresolusi di sini, cuma ditandai supaya LLM tahu
    keduanya ada).

    Parameter `reference_signal`/`unresolved_cues`/`completion_cues`
    OPSIONAL — kalau pemanggil tidak meneruskannya (mis. test unit
    terisolasi), fungsi ini TETAP jalan normal, cuma form detection jadi
    sedikit lebih sempit (reference_followup/problem_report/completion_
    statement yang bergantung pada sinyal reuse itu tidak akan
    terdeteksi lewat jalur itu — tapi `_PROBLEM_WORD_MARKERS` sendiri
    tetap independen jalan)."""
    depth_cues, explicit_phrases, cue_spans = _scan_depth_cues(text)
    conversation_form = detect_conversation_form(
        text,
        reference_signal=reference_signal,
        unresolved_cues=unresolved_cues,
        completion_cues=completion_cues,
    )
    conflicting_cues = "concise" in depth_cues and "detailed" in depth_cues
    # v3.10: self-correction eksplisit BUKAN konflik — maksud akhir jelas.
    self_correction_final = _resolve_self_correction(text, cue_spans) if conflicting_cues else None
    if self_correction_final:
        conflicting_cues = False

    return ResponseCalibration(
        conversation_form=conversation_form,
        depth_cues=depth_cues,
        explicit_phrases=explicit_phrases,
        step_by_step_requested="step_by_step" in depth_cues,
        conflicting_cues=conflicting_cues,
        self_correction_final=self_correction_final,
    )