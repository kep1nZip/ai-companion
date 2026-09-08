from __future__ import annotations

import json
from typing import Optional

from google.genai import types

from ai.providers.base import LanguageModelProvider, ProviderError
from database.memory_manager import Memory
from config.logger import logger

# v2.5 Phase 1 (§6B "Explicit Relation" — "Jangan menyebarkan magic string
# bebas ke banyak file"): SATU tempat definisi relation yang valid, di-import
# oleh Companion (persistence dispatch) alih-alih tiap file menulis ulang
# string "NEW"/"SUPERSEDES"/dst sendiri-sendiri.
RELATION_NEW = "NEW"
RELATION_DUPLICATE = "DUPLICATE"
RELATION_UPDATE = "UPDATE"
RELATION_SUPERSEDES = "SUPERSEDES"
VALID_RELATIONS = {RELATION_NEW, RELATION_DUPLICATE, RELATION_UPDATE, RELATION_SUPERSEDES}

# v2.2.1 (temuan Teacher lewat test ambiguity §38): prompt v2.1/v2.2 TIDAK
# PERNAH punya instruksi soal kalimat RAGU-RAGU sejak v1.x — "mungkin aku
# suka kopi kali ya" konsisten tersimpan sebagai fakta pasti, di KEDUA
# provider (Gemini maupun Local, dikonfirmasi Teacher lewat testing
# langsung) — jadi ini bug prompt lama, bukan soal kualitas model tertentu.
# Ditambah SATU paragraf baru (§13/§37 "conservative extraction", "if
# uncertain: do not create a memory") — SISANYA (kategori, format JSON,
# aturan basa-basi) TIDAK diubah sama sekali dari v2.1, cuma DITAMBAH.
#
# v2.5 Phase 3 (§10 Extraction Contract): paragraf hedging/noise/kategori DI
# ATAS TIDAK DIUBAH SATU KATA PUN (guardrail #7 PM: "Preserve v2.2.1 hedging
# behavior") — HANYA menambah instruksi relation-awareness DI BAWAHNYA,
# ditambah format output baru yang mencakup "relation"/"target_memory_id".
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

Sebelum pesan Teacher, kamu KADANG akan diberi daftar "memori terkait yang sudah
ada" (masing-masing dengan id angka). Kalau daftar itu ADA, tentukan hubungan
("relation") setiap fakta baru yang kamu ekstrak terhadap memori terkait tersebut:

- "NEW": fakta ini benar-benar baru, tidak berkaitan dengan memori terkait manapun
  di daftar. target_memory_id = null.
- "DUPLICATE": fakta ini secara substansi SAMA PERSIS dengan salah satu memori
  terkait (walau beda kata-kata) — TIDAK menambah informasi baru. target_memory_id
  = id memori yang sama itu.
- "UPDATE": fakta ini menambah/mengubah DETAIL dari memori terkait TANPA
  membalikkan fakta utamanya (mis. "suka americano" -> "suka americano tanpa
  gula" — masih suka, cuma detail baru). target_memory_id = id memori yang
  di-update.
- "SUPERSEDES": fakta ini MEMBATALKAN/membalikkan fakta utama dari memori
  terkait (mis. "suka americano" -> "tidak suka americano lagi"). target_memory_id
  = id memori lama yang dibatalkan.

Kalau TIDAK ada daftar memori terkait sama sekali, atau tidak ada satu pun yang
benar-benar berkaitan, relation SELALU "NEW" dan target_memory_id null — JANGAN
menebak-nebak id yang tidak ada di daftar.

PENTING: kalau pesan Teacher menegaskan ulang ("DUPLICATE") ATAU membatalkan/
membalikkan ("SUPERSEDES") fakta yang sudah ada di daftar memori terkait, kamu
TETAP WAJIB menyertakan satu entri untuk fakta itu di output — JANGAN
mengembalikan array kosong hanya karena informasinya "tidak baru". Array kosong
HANYA untuk basa-basi/noise/hedging yang memang tidak layak diingat sama sekali
(lihat aturan di atas). Menegaskan ulang atau membatalkan preferensi TETAP
merupakan sinyal yang harus dicatat lewat relation yang sesuai, BUKAN diabaikan.

Contoh konkret (WAJIB diikuti formatnya, bukan cuma dipahami konsepnya):

Input:
Memori terkait yang sudah ada:
- [id=7] (preference) Teacher suka amerciano
Pesan baru dari Teacher:
Sekarang aku sudah tidak suka americano lagi.

Output yang BENAR (JANGAN balas array kosong untuk kasus seperti ini):
[{"category": "preference", "content": "Teacher tidak suka americano lagi", "relation": "SUPERSEDES", "target_memory_id": 7}]

Output yang SALAH untuk kasus di atas: [] — ini SALAH karena pesan Teacher
JELAS membalikkan fakta yang sudah ada, bukan basa-basi/noise/hedging.

Balas HANYA dengan JSON array, tanpa teks lain, tanpa markdown code fence.
Format setiap item: {"category": "...", "content": "...", "relation": "NEW"|"DUPLICATE"|"UPDATE"|"SUPERSEDES", "target_memory_id": <angka id atau null>}
Jika tidak ada yang layak diingat, balas dengan array kosong: []
"""


def _format_related_memories(related_memories: list[Memory]) -> str:
    """v2.5 Phase 2/3: format persis pola `_format_memories()` di
    ai/companion.py (bullet list "- (category) content"), DITAMBAH id di
    depan supaya model bisa mengisi target_memory_id dengan tepat. Fungsi
    murni presentasi, TIDAK menyentuh MemoryManager/database sama sekali."""
    lines = [f"- [id={m.id}] ({m.category}) {m.content}" for m in related_memories]
    return "Memori terkait yang sudah ada:\n" + "\n".join(lines)


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

    Kontrak `extract()` (input: satu str pesan Teacher + opsional daftar
    memori terkait; output: `list[dict]` dengan key "category"/"content"/
    "relation"/"target_memory_id") DIPERLUAS di v2.5 (§10 Extraction
    Contract) — TAPI backward compatible: pemanggil yang tidak mengisi
    `related_memories` sama sekali mendapat perilaku PERSIS v2.1/v2.2
    (relation selalu "NEW", target_memory_id selalu None)."""

    def __init__(self, provider: LanguageModelProvider):
        self._provider = provider

    def extract(self, user_input: str, related_memories: Optional[list[Memory]] = None) -> list[dict]:
        try:
            # v2.5 Phase 2/3: kalau ada related_memories, disisipkan SEBELUM
            # pesan Teacher dalam SATU Content yang sama (bukan Content
            # terpisah) — model membaca ini sebagai satu blok konteks utuh,
            # bukan riwayat percakapan (kontrak `contents` tetap satu Content
            # role="user", TIDAK BERUBAH dari v2.1/v2.2, cuma isinya
            # sekarang bisa lebih panjang). Kalau related_memories kosong/
            # None (mis. pemanggil lama yang belum diupdate), behavior PERSIS
            # sama seperti sebelum v2.5 — cuma user_input polos.
            message_text = user_input
            if related_memories:
                message_text = f"{_format_related_memories(related_memories)}\n\nPesan baru dari Teacher:\n{user_input}"

            contents = [types.Content(role="user", parts=[types.Part(text=message_text)])]
            raw = self._provider.generate(contents)
            raw = (raw or "").strip()
            facts = json.loads(raw)

            if not isinstance(facts, list):
                return []

            cleaned = []
            for fact in facts:
                if isinstance(fact, dict) and "category" in fact and "content" in fact:
                    # v2.5 Phase 3: relation/target_memory_id OPSIONAL dari
                    # sisi model — kalau model tidak menyertakan field ini
                    # sama sekali (mis. Local model kurang patuh instruksi
                    # baru), fallback aman ke NEW/None, PERSIS behavior lama
                    # sebelum v2.5 (§37 "No Fabricated Memory" — tidak
                    # menebak-nebak relation yang tidak eksplisit dinyatakan
                    # model). Relation yang tidak dikenali (typo/halusinasi
                    # model) JUGA fallback ke NEW, bukan crash.
                    relation = str(fact.get("relation", RELATION_NEW)).strip().upper()
                    if relation not in VALID_RELATIONS:
                        relation = RELATION_NEW

                    target_memory_id = fact.get("target_memory_id")
                    if relation == RELATION_NEW:
                        target_memory_id = None
                    else:
                        try:
                            target_memory_id = int(target_memory_id) if target_memory_id is not None else None
                        except (TypeError, ValueError):
                            target_memory_id = None
                        if target_memory_id is None:
                            # Relation selain NEW tapi tidak ada target valid
                            # -> tidak bisa dieksekusi relasinya, fallback ke
                            # NEW (aman: worst case jadi entri baru biasa,
                            # BUKAN silent data loss/update ke row yang salah).
                            relation = RELATION_NEW

                    cleaned.append({
                        "category": str(fact["category"]),
                        "content": str(fact["content"]),
                        "relation": relation,
                        "target_memory_id": target_memory_id,
                    })
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