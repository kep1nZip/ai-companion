from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

# v3.5 — Temporal Awareness & Task Continuity
# (spec V3_5_TEMPORAL_AWARENESS_TASK_CONTINUITY.md) — modul BARU, pola
# IDENTIK `ai/reference_signals.py` (v3.3) dan `ai/memory_ranking.py`
# (v3.4): pure/deterministic, TIDAK ADA LLM call, TIDAK ADA network call,
# TIDAK ADA state/database baru. Modul ini HANYA mengembalikan EVIDENCE
# (sinyal leksikal + aritmatika tanggal biasa) — TIDAK PERNAH menyimpulkan
# task_status/deadline/priority (Hard Boundary spec §4.2/§4.3). Interpretasi
# semantik ("apakah task ini masih aktif", "apa prioritasnya") TETAP jadi
# tanggung jawab LLM percakapan yang sudah ada, persis prinsip inti spec §2:
# "v3.5 should provide evidence, not make semantic decisions."
#
# Perbedaan dengan `ai/reference_signals.py::detect_reference_signal()`:
# fungsi itu (v3.3) mendeteksi pesan yang MENUNJUK BALIK ke sesuatu yang
# sudah dibicarakan ("yang tadi", "itu") — dipakai untuk memutuskan APAKAH
# perlu mencoba conversation anchor saat mencari memory. Fungsi-fungsi di
# modul INI mendeteksi sinyal waktu & kelanjutan aktivitas yang BERBEDA
# tujuannya (evidence untuk LLM, bukan trigger pencarian memory) — beberapa
# kata baku (mis. "tadi", "kemarin", "barusan") memang tumpang tindih
# secara leksikal karena keduanya bahasa Indonesia sehari-hari yang sama,
# TAPI dipakai untuk keputusan yang sama sekali berbeda (spec §8 Phase 3:
# "v3.5 MUST NOT replace v3.3 reference resolution... both can be supplied
# to the LLM"). TIDAK ADA import silang antar modul ini dengan
# `reference_signals.py` — keduanya independen, sengaja tidak saling
# bergantung supaya masing-masing tetap gampang diuji sendiri-sendiri.


def _add_first_match(
    text_lower: str, pattern: str, label: str, found: list[str], covered_spans: list[tuple[int, int]]
) -> None:
    """Helper internal dipakai SEMUA detector di bawah — mencari SATU match
    pertama untuk `pattern`, dan HANYA menambahkannya ke `found` kalau
    rentang teks yang di-match belum "diklaim" oleh pola LAIN yang lebih
    spesifik (`covered_spans`). Pola dicek berurutan dari yang PALING
    SPESIFIK ke yang PALING GENERIK di tiap fungsi `detect_*` di bawah
    (mis. "masih ngerjain" dicek sebelum "masih" polos) — supaya kalimat
    seperti "aku masih ngerjain LeadEstate" tidak melaporkan DUA sinyal
    tumpang-tindih ("masih ngerjain" DAN "masih" terpisah) yang sebetulnya
    merujuk kata yang sama persis. TIDAK ada kesimpulan semantik apa pun di
    sini — murni non-overlapping regex match bookkeeping."""
    m = re.search(pattern, text_lower)
    if not m:
        return
    span = m.span()
    for s0, s1 in covered_spans:
        if s0 <= span[0] < s1 or span[0] <= s0 < span[1]:
            return
    found.append(label)
    covered_spans.append(span)


# ---------------------------------------------------------------------------
# Phase 1 — Temporal Signal Detection (relative time terms, murni leksikal)
# ---------------------------------------------------------------------------

_RELATIVE_TIME_PATTERNS: list[tuple[str, str]] = [
    (r"\bhari\s+ini\b", "hari ini"),
    (r"\bbaru\s+saja\b", "baru saja"),
    (r"\bsebentar\s+lagi\b", "sebentar lagi"),
    (r"\bminggu\s+depan\b", "minggu depan"),
    (r"\bminggu\s+lalu\b", "minggu lalu"),
    (r"\bbulan\s+depan\b", "bulan depan"),
    (r"\bbulan\s+lalu\b", "bulan lalu"),
    (r"\bsekarang\b", "sekarang"),
    (r"\btadi\b", "tadi"),
    (r"\bbarusan\b", "barusan"),
    (r"\bkemarin\b", "kemarin"),
    (r"\bbesok\b", "besok"),
    (r"\blusa\b", "lusa"),
    (r"\bnanti\b", "nanti"),
]


def detect_relative_time_terms(text: str) -> tuple[str, ...]:
    """Kata/frasa waktu RELATIF yang muncul di `text` — murni deteksi
    leksikal, TIDAK menyimpulkan tanggal apa pun di sini (lihat
    `normalize_relative_dates()` terpisah di bawah untuk yang bisa
    dihitung, spec §7). Termasuk istilah SAMAR ("nanti", "sebentar lagi")
    yang SENGAJA TIDAK PERNAH dinormalisasi jadi tanggal pasti (spec §23
    Ambiguity Rule) — tetap dilaporkan sebagai raw signal supaya LLM tahu
    ADA rujukan waktu, tanpa aplikasi mengarang kapan persisnya."""
    t = (text or "").lower()
    found: list[str] = []
    covered: list[tuple[int, int]] = []
    for pattern, label in _RELATIVE_TIME_PATTERNS:
        _add_first_match(t, pattern, label, found, covered)
    return tuple(found)


# ---------------------------------------------------------------------------
# Phase 2 — Relative Date Normalization (HANYA istilah yang benar-benar
# tidak ambigu — spec §7/§23)
# ---------------------------------------------------------------------------

_INDO_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_INDO_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# HANYA 4 istilah ini (spec §7 contoh eksplisit) — SENGAJA TIDAK termasuk
# "minggu depan"/"bulan depan"/dst: istilah itu butuh keputusan tambahan
# (hari apa dalam minggu itu? tanggal berapa dalam bulan itu?) yang BUKAN
# aritmatika kalender biasa lagi, jadi TETAP diperlakukan sebagai raw cue
# (lewat `detect_relative_time_terms()` di atas), TIDAK dinormalisasi
# (spec §23: "may be normalized only if the phrase is unambiguous enough
# for ordinary calendar arithmetic" — 4 istilah ini SATU-SATUNYA yang
# memenuhi syarat itu, offset harinya baku & tidak berubah-ubah artinya).
_UNAMBIGUOUS_DATE_OFFSETS: dict[str, int] = {
    "hari ini": 0,
    "besok": 1,
    "lusa": 2,
    "kemarin": -1,
}


def _format_indo_date(dt: datetime) -> str:
    return f"{_INDO_HARI[dt.weekday()]}, {dt.day} {_INDO_BULAN[dt.month - 1]} {dt.year}"


def normalize_relative_dates(text: str, now: datetime) -> dict[str, str]:
    """Hitung tanggal kalender KONKRET untuk istilah relatif yang BENAR-
    BENAR tidak ambigu ("hari ini"/"besok"/"lusa"/"kemarin") — ini
    aritmatika tanggal BIASA (`now + timedelta(days=offset)`), BUKAN
    LLM/semantic parsing apa pun (spec §7: "This is acceptable because it
    is ordinary date arithmetic"). `now` WAJIB diteruskan pemanggil (biasa
    `datetime.now(ZoneInfo(...))` dari timezone yang SUDAH dikonfigurasi
    project, lihat `config.constants.ROUTINE_TIMEZONE` — modul ini TIDAK
    membuat/menyimpan timezone sendiri, murni fungsi kalkulasi).

    Return dict kosong `{}` kalau tidak ada istilah yang cocok — TIDAK
    PERNAH mengarang tanggal untuk istilah SAMAR seperti "nanti"/"sebentar
    lagi"/"minggu depan" (spec §23), istilah itu HANYA muncul lewat
    `detect_relative_time_terms()` sebagai raw signal, tidak pernah masuk
    ke sini."""
    t = (text or "").lower()
    result: dict[str, str] = {}
    for term, offset in _UNAMBIGUOUS_DATE_OFFSETS.items():
        if re.search(rf"\b{re.escape(term)}\b", t):
            result[term] = _format_indo_date(now + timedelta(days=offset))
    return result


# ---------------------------------------------------------------------------
# Phase 4 — Task Continuity Cues (continuation / completion / unresolved)
# ---------------------------------------------------------------------------

# Diurutkan SPESIFIK -> GENERIK (lihat `_add_first_match` di atas) supaya
# "masih ngerjain" tidak dilaporkan dobel sebagai "masih ngerjain" + "masih".
_CONTINUATION_PATTERNS: list[tuple[str, str]] = [
    (r"\bmasih\s+ngerjain\b", "masih ngerjain"),
    (r"\bmasih\s+debugging\b", "masih debugging"),
    (r"\bbelum\s+selesai\b", "belum selesai"),
    (r"\bbalik\s+lagi\s+ke\b", "balik lagi ke"),
    (r"\bsekarang\s+balik\s+ke\b", "sekarang balik ke"),
    (r"\bbalik\s+ke\b", "balik ke"),
    (r"\bkembali\s+ke\b", "kembali ke"),
    (r"\bkita\s+lanjut\b", "kita lanjut"),
    (r"\blanjut\s+lagi\b", "lanjut lagi"),
    (r"\blanjutin\b", "lanjutin"),
    (r"\bterusin\b", "terusin"),
    (r"\blanjut\b", "lanjut"),
    (r"\bmasih\b", "masih"),
]

_COMPLETION_PATTERNS: list[tuple[str, str]] = [
    (r"\bsudah\s+selesai\b", "sudah selesai"),
    (r"\budah\s+selesai\b", "udah selesai"),
    (r"\bsudah\s+kelar\b", "sudah kelar"),
    (r"\budah\s+kelar\b", "udah kelar"),
    (r"\bsudah\s+fix\b", "sudah fix"),
    (r"\budah\s+fix\b", "udah fix"),
    (r"\bsudah\s+beres\b", "sudah beres"),
    (r"\budah\s+beres\b", "udah beres"),
    (r"\bberes\b", "beres"),
    (r"\bselesai\b", "selesai"),
    (r"\bdone\b", "done"),
]

_UNRESOLVED_PATTERNS: list[tuple[str, str]] = [
    (r"\bmasih\s+error\b", "masih error"),
    (r"\bmasih\s+stuck\b", "masih stuck"),
    (r"\bmasih\s+gagal\b", "masih gagal"),
    (r"\bbelum\s+bisa\b", "belum bisa"),
    (r"\bbelum\s+selesai\b", "belum selesai"),
]


def detect_continuation_cues(text: str) -> tuple[str, ...]:
    """Frasa yang menunjukkan Teacher SEDANG/MASIH melanjutkan sesuatu
    ("masih", "lanjut", "balik ke", dst — spec §9). Murni leksikal —
    TIDAK menyimpulkan status task apa pun."""
    t = (text or "").lower()
    found: list[str] = []
    covered: list[tuple[int, int]] = []
    for pattern, label in _CONTINUATION_PATTERNS:
        _add_first_match(t, pattern, label, found, covered)
    return tuple(found)


def detect_completion_cues(text: str) -> tuple[str, ...]:
    """Frasa yang menunjukkan sesuatu DIUCAPKAN sudah selesai ("sudah
    selesai", "beres", "done", dst — spec §9). Regex pakai word-boundary
    ketat (`\\bselesai\\b`) — SENGAJA tidak match "selesaikan" (kata
    perintah "tolong selesaikan" BUKAN pernyataan sudah selesai, beda
    makna gramatikal total; spec §21 T08 "No False Completion" eksplisit
    minta detector tetap konservatif untuk kasus semacam ini)."""
    t = (text or "").lower()
    found: list[str] = []
    covered: list[tuple[int, int]] = []
    for pattern, label in _COMPLETION_PATTERNS:
        _add_first_match(t, pattern, label, found, covered)
    return tuple(found)


def detect_unresolved_cues(text: str) -> tuple[str, ...]:
    """Frasa yang menunjukkan sesuatu MASIH BERMASALAH/BELUM KELAR ("masih
    error", "belum bisa", dst — spec §9). "belum selesai" SENGAJA muncul
    di sini DAN di `detect_continuation_cues()` — spec §9 sendiri
    mencantumkannya di kedua kategori (frasa itu memang secara alami
    menyiratkan pekerjaan lanjut BERSAMAAN DENGAN belum tuntas, dua sinyal
    berbeda yang kebetulan dari frasa yang sama, bukan bug duplikasi)."""
    t = (text or "").lower()
    found: list[str] = []
    covered: list[tuple[int, int]] = []
    for pattern, label in _UNRESOLVED_PATTERNS:
        _add_first_match(t, pattern, label, found, covered)
    return tuple(found)


# ---------------------------------------------------------------------------
# Struktur hasil + entrypoint gabungan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemporalSignals:
    """Wadah EVIDENCE murni (spec §6/§26) — SETIAP field adalah OBSERVASI
    tekstual/aritmatika, BUKAN kesimpulan. Tidak ada field `task_status`,
    `deadline`, `priority` di sini SAMA SEKALI (Hard Boundary §4.2/§4.3) —
    kalau suatu hari ada kebutuhan begitu, itu keputusan produk terpisah di
    luar v3.5, BUKAN sesuatu yang "keceplosan" masuk lewat struktur ini."""
    relative_terms: tuple[str, ...] = ()
    normalized_dates: tuple[str, ...] = ()  # format "istilah -> tanggal", cuma untuk istilah TIDAK ambigu
    continuation_cues: tuple[str, ...] = ()
    completion_cues: tuple[str, ...] = ()
    unresolved_cues: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        """True kalau TIDAK ADA sinyal temporal apa pun terdeteksi — dipakai
        pemanggil (`ai/context_builder.py`) untuk memutuskan apakah section
        "Temporal Context" perlu ditulis sama sekali (spec §15: section
        ini OPSIONAL, jangan muncul kosong tanpa isi)."""
        return not (
            self.relative_terms or self.normalized_dates
            or self.continuation_cues or self.completion_cues or self.unresolved_cues
        )


def detect_temporal_signals(text: str, now: Optional[datetime] = None) -> TemporalSignals:
    """SATU-SATUNYA entrypoint gabungan dipakai `Companion` — memanggil
    ke-4 detector di atas sekali, plus `normalize_relative_dates()` KALAU
    `now` diteruskan (opsional — dibiarkan `None` supaya fungsi ini tetap
    bisa dipanggil/diuji tanpa perlu menyuntik waktu, spec §26 contoh
    `detect_temporal_signals(text)` tanpa parameter `now` sama sekali).
    Kalau `now` tidak diisi, `normalized_dates` otomatis kosong — TIDAK
    ADA tanggal yang dikarang tanpa referensi waktu nyata."""
    normalized_dates: tuple[str, ...] = ()
    if now is not None:
        normalized_map = normalize_relative_dates(text, now)
        normalized_dates = tuple(f"{term} -> {date_str}" for term, date_str in normalized_map.items())

    return TemporalSignals(
        relative_terms=detect_relative_time_terms(text),
        normalized_dates=normalized_dates,
        continuation_cues=detect_continuation_cues(text),
        completion_cues=detect_completion_cues(text),
        unresolved_cues=detect_unresolved_cues(text),
    )


# ---------------------------------------------------------------------------
# Phase 8 — Memory Freshness Awareness (TAMPILAN usia, BUKAN validitas)
# ---------------------------------------------------------------------------

def format_memory_age(updated_at: str, now: datetime) -> Optional[str]:
    """Terjemahkan `Memory.updated_at` (string ISO 8601 UTC, lihat
    `database/memory_manager.py`) jadi label usia ringkas ("~2 jam lalu")
    untuk ditampilkan berdampingan dengan isi memory di context (spec §13:
    "expose a lightweight freshness/age signal"). MURNI tampilan — TIDAK
    PERNAH mengubah `status`/menghapus/men-supersede memory apa pun di
    sini (spec §13 eksplisit: "Old ≠ false... Do not automatically
    invalidate old memories"). Memory lama TETAP dikirim ke LLM apa
    adanya, cuma sekarang disertai info "sudah berapa lama" supaya LLM
    (bukan aplikasi) yang menimbang relevansinya terhadap percakapan
    sekarang.

    Return `None` kalau `updated_at` kosong/tidak valid — pemanggil harus
    menangani ini dengan TIDAK menampilkan info usia sama sekali (bukan
    label error apapun) untuk baris memory itu, TIDAK meledak."""
    if not updated_at:
        return None
    try:
        ts = datetime.fromisoformat(updated_at)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        return None
    delta_seconds = max((now - ts).total_seconds(), 0.0)
    minutes = delta_seconds / 60
    if minutes < 1:
        return "baru saja"
    if minutes < 60:
        return f"~{int(minutes)} menit lalu"
    hours = minutes / 60
    if hours < 24:
        return f"~{int(hours)} jam lalu"
    days = hours / 24
    return f"~{int(days)} hari lalu"