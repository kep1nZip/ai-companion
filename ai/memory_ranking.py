from __future__ import annotations

from datetime import datetime
from typing import NamedTuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from database.memory_manager import Memory

# v3.4 — Memory Relevance Ranking & Context Quality
# (spec V3_4_MEMORY_RELEVANCE_RANKING_CONTEXT_QUALITY.md) — modul BARU,
# terpisah dari `ai/companion.py` (pola IDENTIK `ai/reference_signals.py`
# v3.3): pure/deterministic, TIDAK ADA LLM call, TIDAK ADA network call,
# TIDAK ADA import GUI, TIDAK ADA import MemoryManager/database write apa
# pun — hanya beroperasi di atas objek `Memory` yang SUDAH diambil
# pemanggil lewat `search_memory()` yang sudah ada. File terpisah supaya
# gampang diuji unit-test murni (spec §20: "pure/deterministic, easy to
# unit test, provider-agnostic, database-agnostic, free of GUI imports,
# free of LLM calls").
#
# Hard Boundary spec §3 EKSPLISIT melarang: vector DB, embeddings, RAG,
# second LLM, second classifier, MemoryManager baru, provider-specific
# ranking. Modul ini murni fungsi skor mekanis atas string (substring
# match + panjang kata) + tie-break eksplisit atas timestamp — tidak ada
# "kecerdasan" semantik apa pun, semata operasi aritmatika/perbandingan di
# atas data yang sudah ada.


class RetrievalOutcome(NamedTuple):
    """Hasil satu kali `search+rank+select` untuk satu tier query (current
    message / conversation anchor / vision context). SATU-SATUNYA bentuk
    return `Companion._search_memories_by_keywords()` sejak v3.4 (SEBELUMNYA
    cuma `tuple[list[Memory], Optional[str]]`) — diperluas jadi NamedTuple
    supaya metadata ranking (candidate_count, duplicates_removed, top_score,
    keyword_frequency) ikut terbawa ke observability & ke `_build_contents()`
    (note klarifikasi ambiguity, "round 3" — lihat `Companion.__init__`)
    TANPA menghitung ulang apa pun di tempat lain (spec §16 Performance:
    "avoid ranking the same candidate multiple times")."""
    memories: list  # list["Memory"], SUDAH diranking & dipangkas ke budget akhir
    candidate_count: int  # jumlah kandidat MENTAH unik sebelum dipangkas (setelah dedup)
    duplicates_removed: int  # berapa match diskip karena id sudah pernah muncul (keyword lain, tier sama)
    top_score: Optional[float]  # skor kandidat #1 (None kalau candidate_count == 0)
    keyword_frequency: dict  # {kata: jumlah memory yang di-match kata itu} — lihat catatan hotfix di bawah


# v3.4 hotfix (temuan Teacher lewat testing `main_gui.py`, real database
# production): kata seperti "Arona" (nama companion sendiri) bisa jadi
# SANGAT sering muncul di database MEMORY NYATA (banyak memory afeksi/
# romantis menyebut "Arona") — bukan stopword bahasa (masih kata yang sah
# jadi nama project di skenario lain, spec §5.3/Test B sendiri memakai
# "project Arona" sebagai kandidat legit), tapi TERLALU UMUM di database
# ITU SPESIFIK untuk jadi keyword pencarian yang diskriminatif. Ini bug
# yang SAMA JENISNYA dengan "yang"/"tadi" di v3.3 (kata generik mendominasi
# substring match), tapi domain-specific — tidak bisa diselesaikan dengan
# stopword list statis (blacklist "arona" akan merusak Test B canonical
# yang justru butuh "arona" sebagai keyword topik yang sah).
#
# Solusi: berapa BANYAK memory yang di-match SATU keyword saat pencarian
# (`keyword_frequency`, dihitung Companion dari hasil `search_memory()`
# yang SUDAH dipanggil — TIDAK ADA query tambahan) dipakai sebagai sinyal
# "seberapa umum/tidak-diskriminatif kata ini DI DATABASE INI SEKARANG" —
# analog IDF (inverse document frequency) dari pencarian teks klasik, TAPI
# murni hitungan integer, BUKAN embedding/statistik semantik apa pun. Ini
# mengoreksi SKOR MENTAH (`score_memory()`) — filter kandidat mana yang
# layak disebut di note klarifikasi TETAP jadi tanggung jawab mekanisme
# ratio-threshold ("round 3", `Companion._last_recall_scores` +
# `_REFERENCE_NOTE_SCORE_RATIO`), yang SEKARANG bekerja di atas skor yang
# sudah benar (bukan mekanisme kedua yang bersaing).


def _parse_timestamp(value) -> float:
    """`Memory.updated_at` disimpan sebagai STRING ISO 8601
    (`datetime.now(timezone.utc).isoformat()`, lihat `database/
    memory_manager.py`) — BUKAN objek `datetime`. Helper ini mem-parsing
    string itu jadi Unix timestamp (float) buat dibandingkan sebagai tie-
    breaker. Return `0.0` kalau `value` kosong/tidak bisa di-parse (memory
    tanpa timestamp valid dianggap paling lama, TIDAK meledak jadi
    exception yang mengganggu ranking kandidat lain)."""
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError, OSError, OverflowError):
        return 0.0


def _matched_keywords(memory: "Memory", keywords: list[str]) -> list[str]:
    """Daftar keyword (dari `keywords`) yang benar-benar muncul sebagai
    substring di `memory.content` — SATU-SATUNYA definisi "match" dipakai
    `score_memory()`, supaya tidak ada definisi "match" ganda yang bisa
    berbeda diam-diam."""
    content_lower = (memory.content or "").lower()
    return [kw for kw in keywords if kw and kw in content_lower]


def score_memory(
    memory: "Memory",
    keywords: list[str],
    raw_query_text: str = "",
    keyword_frequency: Optional[dict] = None,
) -> float:
    """Skor relevansi DETERMINISTIK murni — bukan "AI confidence", cuma
    aritmatika di atas substring match + panjang kata + (opsional) frekuensi
    kemunculan keyword di database saat ini. Bobot (didokumentasikan di
    sini sesuai spec §6: "weighting must be documented in code comments"):

    - `50.0 * exact_phrase` — BONUS TERKUAT, kalau seluruh `raw_query_text`
      (bukan cuma satu kata) muncul verbatim sebagai substring di memory
      (spec §5.3 "Phrase/Project Name Match").
    - `4.0 * match_weight_sum` — total bobot SPESIFISITAS semua keyword
      yang match. Tiap keyword diberi bobot `panjang_kata / document_
      frequency` kalau `keyword_frequency` disediakan (v3.4 hotfix, lihat
      catatan di atas `RetrievalOutcome` — keyword yang match BANYAK
      memory di database SAAT INI, mis. "arona" yang muncul di puluhan
      memory afeksi, otomatis dapat bobot jauh lebih KECIL daripada
      keyword yang match SEDIKIT memory, mis. "leadestate" yang cuma ada
      di 1 memory — analog IDF, murni hitungan). Kalau `keyword_frequency`
      TIDAK disediakan (None, dipakai test/pemanggil yang tidak lewat
      pencarian database sungguhan), fallback ke panjang kata mentah
      seperti sebelumnya (spec §11.2 "Specific beats generic" versi
      sederhana, TANPA kamus domain apa pun).
    - `8.0 * match_count` — jumlah keyword BERBEDA yang match (spec §5.2/
      §11.3). Kandidat yang cocok di 2 keyword vs 1 keyword HARUS menang,
      terlepas dari kata mana yang match.
    - `5.0 * coverage` — proporsi keyword yang match.

    CATATAN: recency SENGAJA TIDAK ikut dilebur ke angka ini — dipakai
    sebagai TIE-BREAK EKSPLISIT terpisah di `rank_memories()` (spec §5.5:
    "Recency MUST NOT automatically overpower topical relevance")."""
    matched = _matched_keywords(memory, keywords)
    match_count = len(matched)
    if keyword_frequency:
        match_weight_sum = sum(
            len(kw) / max(keyword_frequency.get(kw, 1), 1) for kw in matched
        )
    else:
        match_weight_sum = sum(len(kw) for kw in matched)
    coverage = (match_count / len(keywords)) if keywords else 0.0

    query_text = (raw_query_text or "").strip().lower()
    exact_phrase = 1.0 if (query_text and query_text in (memory.content or "").lower()) else 0.0

    return (
        50.0 * exact_phrase
        + 4.0 * match_weight_sum
        + 8.0 * match_count
        + 5.0 * coverage
    )


def rank_memories(
    memories: list["Memory"],
    keywords: list[str],
    raw_query_text: str = "",
    keyword_frequency: Optional[dict] = None,
) -> list["Memory"]:
    """Urutkan `memories` berdasarkan `score_memory()` DESCENDING, dengan
    tie-break BERTINGKAT sesuai urutan eksplisit spec §7 ("stronger keyword
    coverage -> exact phrase match -> newer memory -> existing memory
    order/stable ID"):

    1. `score_memory()` — sudah mencakup coverage & exact phrase & (kalau
       `keyword_frequency` disediakan) koreksi frekuensi.
    2. `updated_at` (di-parse dari string ISO lewat `_parse_timestamp()`) —
       memory yang lebih BARU menang kalau skor tahap 1 sama persis.
    3. `memory.id` ASCENDING — fallback PALING AKHIR, stabil & deterministik.

    Untuk input yang sama, urutan output SELALU identik — tidak ada
    randomness/non-determinism apa pun (spec §7 "Stable Ranking"). TIDAK
    menghapus/mengubah memory apa pun (spec §11.5) — murni mengembalikan
    list BARU, `memories` asli tidak disentuh."""
    def sort_key(m: "Memory"):
        return (
            -score_memory(m, keywords, raw_query_text, keyword_frequency),
            -_parse_timestamp(getattr(m, "updated_at", None)),
            m.id,
        )

    return sorted(memories, key=sort_key)


# v3.4 hotfix (round 4) — relevance floor untuk SELEKSI AKHIR (lihat
# docstring `rank_and_select()`), TERPISAH dari `_REFERENCE_NOTE_SCORE_RATIO`
# (0.6, di `ai/companion.py`) yang jadi lapisan KEDUA lebih ketat khusus
# untuk note klarifikasi. 0.5 dipilih SENGAJA lebih longgar dari 0.6 —
# kandidat yang lolos ke context (`[Konteks memori]`) boleh sedikit lebih
# lemah daripada kandidat yang layak disebut eksplisit sebagai "pilihan
# yang harus ditanyakan ke Teacher".
MIN_SELECTION_SCORE_RATIO = 0.5


def rank_and_select(
    memories: list["Memory"],
    keywords: list[str],
    limit: int,
    raw_query_text: str = "",
    keyword_frequency: Optional[dict] = None,
) -> tuple[list["Memory"], Optional[float]]:
    """Gabungan `rank_memories()` + relevance floor + pangkas ke `limit` —
    dipakai `Companion._search_memories_by_keywords()`. Return `(selected,
    top_score)` — `top_score` `None` kalau `memories` kosong.

    v3.4 hotfix (round 4, temuan Teacher — replikasi T70 di
    `test_v3_3_reference_recall.py`): SEBELUM ini, method cuma me-rank lalu
    memangkas ke `limit` APA ADANYA — kalau jumlah kandidat MENTAH lebih
    sedikit dari `limit` (kasus umum: database kecil/awal), SEMUA kandidat
    ikut lolos ke context TERLEPAS dari skornya seberapa rendah,
    ranking cuma mengubah URUTAN, bukan MENYARING. Ini kurang kalau salah
    satu keyword ternyata sangat umum di database (mis. "arona", nama
    companion sendiri, match di puluhan memory afeksi tak terkait) — 4-5
    memory yang CUMA kebetulan match keyword umum itu semuanya tetap
    lolos ke `[Konteks memori]` (dan berpotensi ke note klarifikasi)
    walau `keyword_frequency` sudah membuat SKOR mereka rendah — skor
    rendah itu TIDAK ADA GUNANYA kalau tidak pernah dipakai buat MEMBUANG.

    Perbaikan: kandidat yang skornya di bawah `MIN_SELECTION_SCORE_RATIO`
    (50%) dari skor kandidat #1 DIBUANG dari seleksi akhir — bukan cuma
    dari note klarifikasi (itu tetap jadi lapisan KEDUA yang lebih ketat,
    `_REFERENCE_NOTE_SCORE_RATIO`=60%, di `Companion._build_contents()`).
    Relevance floor ini CUMA berlaku kalau skor kandidat #1 > 0 (ADA
    match nyata) — kalau top_score == 0 (recency-style, tidak ada match
    keyword sama sekali di semua kandidat), TIDAK ADA dasar relatif untuk
    membuang siapa pun, jadi tidak difilter (spec §9: "must not remove
    all candidates merely because one weak scoring function fails").
    Kandidat #1 SENDIRI dijamin selalu lolos floor-nya sendiri (skor >=
    skor × rasio, untuk rasio <= 1), jadi hasil TIDAK PERNAH kosong
    selama `memories` tidak kosong."""
    if not memories:
        return [], None
    ranked = rank_memories(memories, keywords, raw_query_text, keyword_frequency)
    top_score = score_memory(ranked[0], keywords, raw_query_text, keyword_frequency)
    if top_score > 0:
        threshold = top_score * MIN_SELECTION_SCORE_RATIO
        strong_enough = [
            m for m in ranked
            if score_memory(m, keywords, raw_query_text, keyword_frequency) >= threshold
        ]
        ranked = strong_enough or ranked[:1]
    selected = ranked[:limit]
    return selected, top_score