from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY tidak ditemukan. Pastikan file .env ada di root project "
        "dan berisi baris: GEMINI_API_KEY=api_key_kamu"
    )

# v2.0 Step 9 — Default Provider Decision: "local" adalah DEFAULT resmi
# sekarang (sebelumnya "gemini") — diputuskan berdasarkan Step 7 Full
# Regression yang sudah selesai & diterima Teacher, bukan cuma karena gratis.
# "gemini" (fallback eksplisit lewat .env) | "local" (LM Studio, dkk, DEFAULT).
# Backward compatible: AI_PROVIDER=gemini di .env TETAP dihormati apa adanya
# (§17) — ini cuma mengubah apa yang terjadi kalau variabelnya TIDAK di-set
# sama sekali.
#
# GEMINI_API_KEY TETAP WAJIB ada apa pun pilihan AI_PROVIDER-nya — Vision
# (image_analyzer.py) dan Memory Extraction (memory_extractor.py) BELUM
# dimigrasikan (v2.0 §21-22: sengaja di luar cakupan Step 9 juga), jadi
# keduanya tetap butuh Gemini yang valid terlepas dari provider chat utama
# yang dipilih. Pilih AI_PROVIDER=local HANYA memindahkan generasi teks CHAT
# UTAMA ke local model — bukan seluruh aplikasi (§5).
AI_PROVIDER = os.getenv("AI_PROVIDER", "local").strip().lower()

LOCAL_PROVIDER_BASE_URL = os.getenv("LOCAL_PROVIDER_BASE_URL", "http://localhost:1234/v1")
LOCAL_PROVIDER_MODEL_NAME = os.getenv("LOCAL_PROVIDER_MODEL_NAME", "qwen3-vl-8b")

# v2.2 — Local Memory Extraction: provider Memory Extraction adalah KEPUTUSAN
# TERPISAH dari AI_PROVIDER (§27: "Language Provider = Local" TIDAK otomatis
# berarti "Memory Provider = Local"). Default TETAP "gemini" (BUKAN ikut
# default AI_PROVIDER="local") — beda dengan AI_PROVIDER yang defaultnya
# dipindah ke "local" di v2.0 Step 9 SETELAH Full Regression selesai &
# dikonfirmasi Teacher lewat testing nyata. Belum ada siklus konfirmasi yang
# sama untuk kualitas ekstraksi Local (v2.2 §26: "final default choice...
# must be based on extraction quality/reliability testing" — testing itu
# baru bisa terjadi di mesin Teacher sungguhan, dengan LM Studio live).
# Sampai itu terjadi & dikonfirmasi, default aman = provider yang sudah
# v2.1-verified (Gemini). "gemini" (default) | "local".
#
# TIDAK ADA LOCAL_MEMORY_MODEL_NAME/LOCAL_MEMORY_BASE_URL terpisah (§20/§30)
# — Local Memory Extraction SENGAJA reuse LOCAL_PROVIDER_MODEL_NAME/
# LOCAL_PROVIDER_BASE_URL yang sama dipakai chat utama. §20 eksplisit:
# "The first implementation should NOT create a second LM Studio process
# automatically" — jadi kalau Memory Provider=local, dia bicara ke SERVER &
# MODEL LM Studio YANG SAMA dengan chat (kalau Language Provider juga local),
# bukan instance kedua.
MEMORY_PROVIDER = os.getenv("MEMORY_PROVIDER", "gemini").strip().lower()

# v2.3 — Local Vision: KEPUTUSAN TERPISAH lagi dari AI_PROVIDER dan
# MEMORY_PROVIDER (§6: Language/Memory/Vision masing-masing provider policy
# sendiri-sendiri, tidak ada yang otomatis mengikuti yang lain). Default
# TETAP "gemini" dengan alasan PERSIS SAMA seperti MEMORY_PROVIDER di atas —
# belum ada siklus validasi kualitas Local Vision yang selesai & dikonfirmasi
# Teacher (v2.3 §6: "Perubahan Local menjadi default hanya boleh dilakukan
# setelah validasi kualitas Local Vision selesai. Jangan mengubah default
# hanya karena provider Local sudah tersedia."). "gemini" (default) | "local".
#
# TIDAK ADA LOCAL_VISION_MODEL_NAME/LOCAL_VISION_BASE_URL terpisah (§7) —
# Local Vision SENGAJA reuse LOCAL_PROVIDER_MODEL_NAME/LOCAL_PROVIDER_BASE_URL
# yang sama dipakai chat & Memory Extraction Local — audit kode (vision/
# local_image_analyzer.py) tidak menemukan kebutuhan teknis nyata untuk
# konfigurasi terpisah (§7: "kecuali audit kode membuktikan pemisahan
# tersebut benar-benar diperlukan" — tidak terbukti perlu).
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "gemini").strip().lower()