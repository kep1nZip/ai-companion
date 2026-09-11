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