from __future__ import annotations

import re

# v3.3 Phase 1+3 (Conversation Anchor Detection + Contextual Memory Query,
# spec V3.3_CONTEXTUAL_RECALL_REFERENCE_INTELLIGENCE.md) — pola IDENTIK
# `ai/conversation_signals.py` (v2.8): fungsi murni regex/keyword, TIDAK ADA
# LLM kedua, TIDAK ADA state/database baru. File terpisah dari
# conversation_signals.py murni supaya scope v3.3 (reference/recall) tidak
# tercampur dengan scope v2.8 (closure) — bukan alasan arsitektur baru,
# masih dipanggil dari `ai/companion.py` dengan cara yang persis sama.
#
# Hard Boundary spec v3.3 §2 EKSPLISIT melarang: RAG, vector DB,
# multi-agent, second LLM classifier, persistent topic database, dsb. Semua
# fungsi di file ini murni deterministic string processing, dipanggil ulang
# tiap kali dibutuhkan (tidak ada yang dipersist), konsisten dengan definisi
# "anchor" spec §4: "short-lived conversation signal", BUKAN persistent
# memory.

# ---------------------------------------------------------------------------
# Reference / follow-up phrase detection
# ---------------------------------------------------------------------------

# Target phrase persis dari spec §6 ("yang tadi", "yang barusan", "lanjut
# yang kemarin", "itu", "ini", "yang pertama", "project tadi", "masalah
# tadi", "yang sebelumnya") — SENGAJA konservatif (pola sama seperti
# `detect_closure()`: lebih baik false negative daripada false positive),
# karena sinyal ini HANYA dipakai sebagai penentu "apakah perlu mencoba
# anchor dari conversation sebelumnya" (lihat `Companion.
# _select_relevant_memories()`), BUKAN untuk mengontrol apakah Arona boleh
# menjawab sama sekali (itu tetap wewenang penuh LLM, dibantu
# `prompts/system_rules.txt` yang SUDAH secara eksplisit menginstruksikan
# "treat short/dependent messages as continuation" dan "ask a clarifying
# question kalau genuinely ambiguous" — instruksi itu TIDAK diubah oleh
# v3.3, ditemukan sudah ALREADY SATISFIED lewat Phase 0 audit).
_REFERENCE_PATTERNS = [
    r"\byang\s+tadi\b",
    r"\byang\s+barusan\b",
    r"\byang\s+ini\b",
    r"\byang\s+itu\b",
    r"\byang\s+kemarin\b",
    r"\byang\s+pertama\b",
    r"\byang\s+kedua\b",
    r"\byang\s+sebelumnya\b",
    r"\blanjut(?:in)?\s+(?:yang\s+)?(?:tadi|kemarin|barusan|itu)\b",
    r"\bproject\s+tadi\b",
    r"\bmasalah\s+tadi\b",
    r"\bbalik\s+ke\s+.+\s+tadi\b",
    r"\bterusin\b",
    r"\b(?:itu|ini)\s+tadi\b",
    r"\bkayak\s+yang\s+tadi\b",
    r"\byang\s+td\b",
    r"^\s*(?:itu|ini|lanjut)\s*[?.!]*\s*$",  # pesan super pendek berdiri sendiri
]

_COMPILED_REFERENCE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _REFERENCE_PATTERNS]


def detect_reference_signal(text: str) -> bool:
    """Return True kalau `text` (pesan Teacher) mengandung pola bahasa yang
    menunjuk balik ke sesuatu yang sudah dibicarakan sebelumnya ("yang
    tadi", "lanjut itu", dst) — murni pattern matching, TIDAK memanggil
    provider/LLM apa pun, aman dipanggil berkali-kali. Pola IDENTIK
    `detect_closure()` di `ai/conversation_signals.py`."""
    if not text or not text.strip():
        return False
    stripped = text.strip().rstrip(".!?, ")
    return any(pattern.search(stripped) for pattern in _COMPILED_REFERENCE_PATTERNS)


# ---------------------------------------------------------------------------
# Keyword extraction + generic-word filtering (Recall Priority, spec §8)
# ---------------------------------------------------------------------------

# v3.3 Phase 0 Audit finding: `Companion._select_relevant_memories()` (sejak
# v1.9) mengambil SEMUA kata >= 4 huruf dari pesan Teacher sebagai kandidat
# keyword `search_memory()` (SQL LIKE substring) TANPA stopword filter apa
# pun. Untuk pesan referensi ("lanjut yang tadi") kata seperti "yang"/
# "tadi"/"lanjut" ikut lolos filter panjang dan dipakai sebagai substring
# pencarian — SQL `LIKE '%yang%'` bisa cocok ke HAMPIR SEMUA memory (kata
# "yang" muncul di kalimat Indonesia mana pun), yang berarti memory TIDAK
# RELEVAN berpotensi mendominasi context (persis kondisi yang spec v3.3 §8
# "Recall Priority" & §23 FAIL condition eksplisit larang: "memory
# irrelevant masuk sebagai reference utama"). Ini BUG NYATA yang sudah ada
# sejak v1.9, ditemukan lewat audit v3.3 — bukan fitur baru yang ditambah,
# jadi diperbaiki di sini sebagai "smallest safe change" (spec Prinsip #5),
# BUKAN dengan mengganti mekanisme pencarian (tetap SQL LIKE, tetap
# `search_memory()` yang sama).
#
# Daftar ini HANYA berisi kata FUNGSI/REFERENSI generik Bahasa Indonesia
# (dan padanan singkat Inggris umum di percakapan campur) yang tidak pernah
# membawa informasi PEMBEDA untuk pencarian substring — bukan daftar kata
# yang "boleh diabaikan AI" secara umum. Kata seperti "lagi" dikecualikan
# HANYA dari peran sebagai keyword pencarian memory (tidak memengaruhi
# `EXTRACTION_SYSTEM_PROMPT` di `ai/memory_extractor.py`, yang tetap
# memakai kata itu sebagai sinyal linguistik terpisah untuk LLM, sistem
# yang sama sekali berbeda dan TIDAK disentuh file ini).
GENERIC_REFERENCE_STOPWORDS = frozenset({
    "yang", "tadi", "barusan", "kemarin", "sebelumnya", "pertama", "kedua",
    "terakhir", "sekarang", "lanjut", "lanjutin", "terusin", "lagi", "dulu",
    "masih", "sudah", "udah", "belum", "kalau", "kalo", "gimana", "kayak",
    "kayaknya", "begini", "begitu", "gini", "gitu", "dengan", "untuk",
    "tentang", "tersebut", "tolong", "boleh", "bisa", "kapan", "dimana",
    "kenapa", "banget", "tapi", "atau", "tetap", "tetapi", "juga", "sama",
    "cuma", "hanya", "emang", "memang", "soalnya", "makanya", "biar",
    "supaya", "kayanya", "sepertinya", "mungkin",
})


def extract_keywords(text: str, min_length: int = 4) -> list[str]:
    """SATU-SATUNYA tempat ekstraksi kata kunci mentah dari teks bebas —
    SEBELUM v3.3 logic ini diduplikasi persis di dua tempat berbeda
    (`Companion._select_relevant_memories()` dan `Companion.
    _select_related_memories_for_extraction()`). Diekstrak ke sini supaya
    KEDUA tempat itu (dan `_recent_conversation_anchor_keywords()` baru di
    v3.3) memakai definisi "kata signifikan" yang PERSIS SAMA — perbaikan
    di satu tempat (mis. stopword filter di bawah) otomatis berlaku di
    semua pemanggil, tidak ada risiko salah satu tempat lupa diupdate.

    TIDAK ada perubahan perilaku ekstraksi panjang kata (>= 4 huruf, sama
    persis heuristik v1.9) — perubahan v3.3 murni penambahan
    `filter_search_keywords()` terpisah di bawah, dipanggil eksplisit oleh
    caller, supaya jelas di titik mana filter itu berlaku."""
    return [w for w in re.findall(r"\w+", (text or "").lower()) if len(w) >= min_length]


def filter_search_keywords(words: list[str]) -> list[str]:
    """Buang kata fungsi/referensi generik (`GENERIC_REFERENCE_STOPWORDS`)
    dari daftar kandidat keyword SEBELUM dipakai `search_memory()` (SQL LIKE
    substring) — TIDAK mengubah `search_memory()`/`MemoryManager` sama
    sekali (Hard Boundary §2: "New MemoryManager" dilarang), murni
    mengurangi kandidat query yang dikirim ke situ. Mempertahankan urutan
    asli (tidak mengurutkan ulang) — pemanggil di `Companion` sudah
    membatasi jumlah kata yang benar-benar dipakai (`keywords[:5]`) SETELAH
    filter ini, jadi urutan tetap penting."""
    return [w for w in words if w not in GENERIC_REFERENCE_STOPWORDS]