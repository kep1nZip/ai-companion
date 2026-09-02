from __future__ import annotations

import json

from google.genai import types

from ai.providers.base import LanguageModelProvider, ProviderError
from config.logger import logger

# v2.2.1 (temuan Teacher lewat test ambiguity §38): prompt v2.1/v2.2 TIDAK
# PERNAH punya instruksi soal kalimat RAGU-RAGU sejak v1.x — "mungkin aku
# suka kopi kali ya" konsisten tersimpan sebagai fakta pasti, di KEDUA
# provider (Gemini maupun Local, dikonfirmasi Teacher lewat testing
# langsung) — jadi ini bug prompt lama, bukan soal kualitas model tertentu.
# Ditambah SATU paragraf baru (§13/§37 "conservative extraction", "if
# uncertain: do not create a memory") — SISANYA (kategori, format JSON,
# aturan basa-basi) TIDAK diubah sama sekali dari v2.1, cuma DITAMBAH.
EXTRACTION_SYSTEM_PROMPT = """
Kamu adalah sistem ekstraksi memori jangka panjang untuk AI companion bernama Arona.

Tugasmu: baca satu pesan dari Teacher (user), lalu tentukan apakah pesan itu berisi
fakta jangka panjang yang layak diingat tentang Teacher (preferensi, identitas, relasi,
project, jadwal, atau fakta umum penting).

JANGAN simpan basa-basi, sapaan, ucapan terima kasih, atau obrolan sesaat
(contoh: "halo", "selamat pagi", "haha", "makasih", "jam berapa sekarang").

JANGAN simpan pernyataan yang RAGU-RAGU atau tidak yakin sebagai fakta pasti.
Kalau Teacher memakai kata/nada seperti "mungkin", "kayaknya", "sepertinya",
"kali ya", "kayanya", "kalo gak salah", "entah kenapa tapi", "gatau deh", atau
nada bercanda/belum yakin — JANGAN perlakukan itu sebagai fakta yang layak
diingat, walau topiknya kedengaran seperti preferensi/identitas. Kalau ragu
apakah suatu pernyataan cukup yakin untuk disimpan, JANGAN simpan — lebih
baik tidak menyimpan apa pun daripada menyimpan fakta yang salah.

Kategori yang valid HANYA: preference, relationship, identity, project, schedule, general.

Balas HANYA dengan JSON array, tanpa teks lain, tanpa markdown code fence.
Format setiap item: {"category": "...", "content": "..."}
Jika tidak ada yang layak diingat, balas dengan array kosong: []
"""


class MemoryExtractor:
    """Decision layer: menentukan apakah sebuah pesan layak jadi memori jangka
    panjang. Pakai model call terpisah & ringan, bukan RAG/vector DB, bukan
    if-statement bertumpuk.

    v2.2 — Provider-Agnostic Memory Extraction (§8/§9/§10): SEBELUMNYA class
    ini membangun `google.genai.Client` sendiri di __init__ (hardcode ke
    Gemini). Sekarang MemoryExtractor TIDAK TAHU provider mana yang dipakai
    sama sekali — cuma menerima `LanguageModelProvider` (abstraksi yang SAMA
    persis dipakai Companion untuk chat utama, v2.0 §33-35) lewat dependency
    injection, lalu memanggil `provider.generate(contents) -> str` apa
    adanya. Tidak ada `if provider == "local"` di file ini (§8) — kelas ini
    TIDAK PEDULI Gemini/Local/LM Studio, keputusan provider mana yang dipakai
    ada di LUAR class ini (Companion.__init__ / main_gui.py), persis pola
    yang sudah dipakai chat utama sejak v2.0.

    Kontrak `extract()` (input: satu str pesan Teacher; output:
    `list[dict]` dengan key "category"/"content") TIDAK BERUBAH SEDIKIT PUN
    dari v2.1 — pemanggil (`ai/memory_worker.py` lewat `Companion.
    _schedule_memory_extraction`) tidak perlu tahu apa pun soal perubahan
    ini."""

    def __init__(self, provider: LanguageModelProvider):
        self._provider = provider

    def extract(self, user_input: str) -> list[dict]:
        try:
            # v2.2: bentuk `contents` SAMA PERSIS dengan sebelumnya (satu
            # Content role="user" berisi user_input apa adanya) — cuma
            # sekarang dikirim lewat `provider.generate()` (kontrak
            # LanguageModelProvider, v2.0 §33) alih-alih
            # `self._client.models.generate_content()` langsung.
            contents = [types.Content(role="user", parts=[types.Part(text=user_input)])]
            raw = self._provider.generate(contents)
            raw = (raw or "").strip()
            facts = json.loads(raw)

            if not isinstance(facts, list):
                return []

            cleaned = []
            for fact in facts:
                if isinstance(fact, dict) and "category" in fact and "content" in fact:
                    cleaned.append({"category": str(fact["category"]), "content": str(fact["content"])})
            return cleaned

        except ProviderError as e:
            # v2.2 §24/§37: kegagalan PROVIDER (network/timeout/rate-limit/
            # balasan kosong — baik dari Gemini maupun Local/LM Studio, lewat
            # exception provider-agnostic yang sama, v2.0 §35) TIDAK PERNAH
            # menghasilkan memori palsu — diperlakukan identik dengan "tidak
            # ada yang layak diingat", bukan dianggap error fatal.
            logger.warning("Ekstraksi memori gagal (provider error), diabaikan dengan aman: {}", e)
            return []
        except Exception as e:
            # v2.2 §14/§37 "No Fabricated Memory": SEMUA kegagalan lain (JSON
            # tidak valid, format tak terduga dari Local model yang kurang
            # patuh instruksi, dst) JUGA jatuh ke sini — "if uncertain: do not
            # create a memory". Tidak ada percobaan "perbaiki" JSON yang rusak
            # (mis. regex-strip code fence) — kalau modelnya tidak taat format
            # yang diminta prompt, hasilnya diabaikan dengan aman, bukan
            # dipaksakan masuk database.
            logger.warning("Ekstraksi memori gagal, diabaikan dengan aman: {}", e)
            return []