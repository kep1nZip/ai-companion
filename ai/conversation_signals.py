from __future__ import annotations

import re

# v2.8 Phase 5 (Conversation Closure) — pola IDENTIK vision/vision_signals.py
# (fungsi murni, keyword/regex, TIDAK ADA LLM kedua, TIDAK ADA state/database
# baru). Dipanggil Companion terhadap teks pesan Teacher yang PALING TERAKHIR
# (lewat `Conversation.get_last_user_message()`) — hasilnya SATU boolean,
# diteruskan ke Initiative sebagai sinyal, PERSIS pola v2.7 Phase 5+6
# (Vision -> signal -> Initiative -> decision, BUKAN Conversation langsung
# mengontrol Initiative — spec v2.8 §10 eksplisit).
#
# SENGAJA konservatif (lebih baik false negative daripada false positive) —
# closure signal cuma dipakai sebagai SOFT PENALTY (§29 spec: "Closure signal
# DAPAT digunakan untuk MEMBANTU keputusan"), bukan hard suppression, jadi
# efek dari salah deteksi jauh lebih ringan dibanding suppression (mis.
# matches_presentation() di vision_signals.py) — tapi tetap dijaga presisi
# supaya sinyalnya bermakna.
_CLOSURE_PATTERNS = [
    r"\boke(?:h)?\s+(makasih|terima\s*kasih|deh|sip)\b",
    r"\bmakasih\s+(ya|banyak|banget)?\s*(arona)?\s*$",
    r"\bterima\s*kasih\s+(ya|banyak)?\s*(arona)?\s*$",
    r"\budah(?:an)?\s+(ngerti|paham|dulu|deh)\b",
    r"\bsudah\s+(mengerti|paham)\b",
    r"\bsip(?:lah)?\s*(deh|dah)?\s*$",
    r"\bbesok\s+(aja\s+)?lanjut\b",
    r"\bnanti\s+(aja\s+)?lanjut\b",
    r"\bsegitu\s+(aja\s+)?dulu\b",
    r"\bcukup\s+(segitu|itu)\s+dulu\b",
    r"\boke\s*(deh|lah)?\s*$",
    r"^\s*(sip|oke|ok|makasih)\s*[.!]*\s*$",  # balasan super pendek yang berdiri sendiri
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _CLOSURE_PATTERNS]


def detect_closure(text: str) -> bool:
    """Return True kalau `text` (pesan Teacher TERAKHIR) mengandung sinyal
    penutupan percakapan (mis. "oke makasih", "udah ngerti", "sip",
    "besok aja lanjut"). Murni pattern matching — TIDAK memanggil provider/
    LLM apa pun, TIDAK menyimpan state, aman dipanggil berkali-kali."""
    if not text or not text.strip():
        return False
    # Tanda baca akhir kalimat (. ! ? ,) dilepas dulu sebelum matching —
    # pattern yang di-anchor "$" (mis. "sip deh$") sebelumnya gagal kalau
    # Teacher menutup dengan tanda baca ("Sip deh.") — bukan perubahan
    # makna, cuma normalisasi supaya titik/tanda seru di akhir kalimat
    # tidak menggagalkan match yang seharusnya jelas.
    stripped = text.strip().rstrip(".!?, ")
    return any(pattern.search(stripped) for pattern in _COMPILED_PATTERNS)


# v3.0 Phase 10 (Developer Observability, Item F) — pola IDENTIK
# detect_closure() di atas (regex/keyword murni, TIDAK ADA LLM kedua).
#
# PENTING: detect_style_preference() di bawah MURNI OBSERVASIONAL — dipakai
# HANYA untuk field Dashboard "Response Style Signal" (Teacher eksplisit
# menolak "response-style engine baru" yang MENGONTROL perilaku; adaptasi
# gaya respons yang sebenarnya diserahkan ke model membaca riwayat mentah +
# panduan prompt v3.0 Item B, BUKAN mekanisme deteksi ini). TIDAK PERNAH
# dipakai untuk mengubah `contents` yang dikirim ke provider, TIDAK PERNAH
# memengaruhi Initiative/relation model/apa pun — kalau dihapus total, tidak
# ada behavior chat yang berubah, cuma satu baris Dashboard yang hilang.
_CONCISE_PATTERNS = [
    r"\bsingkat\s+aja\b",
    r"\bringkas\s+aja\b",
    r"\bto\s+the\s+point\b",
    r"\bgak\s+usah\s+panjang\b",
    r"\btidak\s+usah\s+panjang\b",
    r"\bintinya\s+aja\b",
    r"\bsingkat\s+saja\b",
]
_DETAILED_PATTERNS = [
    r"\bjelasin\s+(detail|lengkap|rinci)\b",
    r"\bjelaskan\s+(detail|lengkap|rinci|secara\s+detail)\b",
    r"\blebih\s+(detail|rinci|lengkap)\b",
    r"\bdetail(?:kan)?\s+(dong|ya|donk)\b",
    r"\bstep\s*by\s*step\b",
    r"\bjelas(?:in|kan)?\s+lebih\s+dalam\b",
]
_COMPILED_CONCISE = [re.compile(p, re.IGNORECASE) for p in _CONCISE_PATTERNS]
_COMPILED_DETAILED = [re.compile(p, re.IGNORECASE) for p in _DETAILED_PATTERNS]


def detect_style_preference(text: str) -> str | None:
    """Return "concise" | "detailed" | None (tidak terdeteksi salah satunya).
    Murni pattern matching, sama seperti detect_closure()."""
    if not text or not text.strip():
        return None
    stripped = text.strip().rstrip(".!?, ")
    if any(p.search(stripped) for p in _COMPILED_DETAILED):
        return "detailed"
    if any(p.search(stripped) for p in _COMPILED_CONCISE):
        return "concise"
    return None