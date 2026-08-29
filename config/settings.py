from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY tidak ditemukan. Pastikan file .env ada di root project "
        "dan berisi baris: GEMINI_API_KEY=api_key_kamu"
    )

# v2.0 — Provider Selection (§46 Step 6: Integrate configuration).
# "gemini" (default, tidak berubah dari sebelumnya) | "local" (LM Studio, dkk).
# GEMINI_API_KEY TETAP WAJIB ada apa pun pilihan AI_PROVIDER-nya — Vision
# (image_analyzer.py) dan Memory Extraction (memory_extractor.py) BELUM
# dimigrasikan (v2.0 §40: TTS/Vision sengaja di luar cakupan migrasi ini),
# jadi keduanya tetap butuh Gemini yang valid terlepas dari provider chat
# utama yang dipilih. Pilih AI_PROVIDER=local HANYA memindahkan generasi
# teks CHAT UTAMA ke local model — bukan seluruh aplikasi.
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()

LOCAL_PROVIDER_BASE_URL = os.getenv("LOCAL_PROVIDER_BASE_URL", "http://localhost:1234/v1")
LOCAL_PROVIDER_MODEL_NAME = os.getenv("LOCAL_PROVIDER_MODEL_NAME", "qwen3-vl-8b")