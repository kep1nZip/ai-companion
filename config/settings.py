from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY tidak ditemukan. Pastikan file .env ada di root project "
        "dan berisi baris: GEMINI_API_KEY=api_key_kamu"
    )