# Audit Changelog — `config/` (5 file)

Fokus audit: Security (API key handling, log sanitization, secrets/packaging).
Batch terakhir dari seluruh audit CODE_STYLE.md + V1.0_AUDIT_CHECKLIST.md.

---

## ✅ Selesai

### 🔴 KRITIS — API key bocor ke log file lewat `loguru diagnose`
`config/logger.py` tidak pernah set `diagnose` (default loguru: `True`),
yang mencetak nilai variabel lokal LENGKAP di tiap frame traceback saat
exception. Karena `HttpRequest`/`Client` milik `google-genai` menyimpan
header `x-goog-api-key`, setiap exception yang lewat objek itu ikut
mencatat potongan API key mentah ke `logs/app.log`. **Bukan teori — sudah
terbukti kejadian nyata**, ketemu langsung di traceback yang di-paste user
sendiri waktu debug bug TTS di sesi sebelumnya.

**Fix:**
```python
logger.add(
    _log_path,
    level=LOG_LEVEL,
    rotation=LOG_ROTATION,
    retention=LOG_RETENTION,
    encoding="utf-8",
    diagnose=False,   # cegah local variable (termasuk API key) tercetak di traceback log
)
```
Traceback tetap lengkap (module, line number, exception message) — cuma
nilai variabel lokal yang di-suppress.

**Tindakan di luar kode (disarankan ke user, status belum dikonfirmasi)**:
cek `logs/app.log` dan file rotation lama untuk kebocoran yang sudah
terlanjur tercatat; kalau ada dan log itu pernah di-share/paste ke mana
pun (termasuk ke chat AI manapun untuk debugging), anggap key itu sudah
tidak aman — rotate/hapus log lama, pertimbangkan generate API key baru
di Google AI Studio.

### 🟡 `GEMINI_API_KEY` tidak divalidasi saat startup
```python
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")   # bisa None diam-diam
```
Kalau `.env` hilang/typo nama variabel, error baru muncul jauh lebih dalam
(di `genai.Client(api_key=None)` atau saat request pertama) dengan pesan
generik dari SDK.

**Fix — `config/settings.py`:**
```python
from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY tidak ditemukan. Pastikan file .env ada di root project "
        "dan berisi baris: GEMINI_API_KEY=api_key_kamu"
    )
```
Fail-fast di titik paling awal (saat `config/settings.py` di-import).
Dikonfirmasi user: `.env` sudah ada di root berisi `GEMINI_API_KEY`, jadi
fix ini murni pengaman untuk skenario masa depan (misal `.env` kehapus
tidak sengaja atau setup ulang di komputer lain).

### 🟢 `from __future__ import annotations` hilang di `constants.py`/`logger.py`
Konsisten dengan temuan serupa di batch `ai/` — file "pinggiran"/config
cenderung lupa baris ini. Ditambahkan 1 baris di masing-masing file, nol
risiko (kedua file tidak punya type hint yang butuh lazy evaluation).

---

## 🔲 Perlu keputusan / belum dieksekusi

### `vtube_token.json` berisi token asli, bukan placeholder
Risiko rendah (token lokal antar-aplikasi di komputer yang sama, bukan
credential cloud), tapi tetap masuk kategori secrets untuk Packaging
Policy. Sebelum project dipublikasi (git/portable build), file ini wajib
masuk `.gitignore` bersama `database/memory.db` (isi percakapan pribadi)
dan `.env`. **Belum diverifikasi** — user belum upload `.gitignore` untuk
dicek apakah 3 file itu sudah ke-cover.

### `.env.example` belum ada
Item Packaging Policy untuk v1.0 (template tanpa API key asli). Karena
project masih di fase development aktif (belum rilis), ini ditunda — bisa
dibuat kapan saja (isinya simpel, cuma `GEMINI_API_KEY=your_gemini_api_key_here`
karena `settings.py` cuma baca 1 variabel).

### `DEVELOPER_MODE` constant belum ada
Sesuai roadmap v1.0 ("toggle Developer Mode... backend sudah lengkap sejak
v0.9.5"). **Sengaja tidak ditambahkan sekarang** — beda dari cleanup biasa,
nambah constant flag tanpa consumer yang jelas berisiko jadi dead code lagi
(sama kasusnya dengan `EventPriority.CRITICAL` di audit `routine/`). Definisi
persis apa yang di-toggle (menu GUI baru? unlock semua `DeveloperService`
method? keduanya?) adalah keputusan desain yang lebih pas didiskusikan ke
GPT dulu di spec resmi, bukan diasumsikan dari 1 baris constant.

### `VISION_MODEL_NAME` sama persis dengan `MODEL_NAME`
**Sengaja TIDAK digabung.** Duplikasi nilai ini adalah opsi masa depan yang
sengaja dibuka (biar bisa pakai model vision berbeda dari model chat utama
kalau nanti perlu, mis. model vision-only yang lebih murah/cepat) — bukan
technical debt. Kalau user yakin tidak akan pernah butuh model berbeda,
bisa digabung; kalau tidak, cukup ditambah komentar penjelas niatnya:
```python
VISION_MODEL_NAME = "gemini-2.5-flash"  # sengaja terpisah dari MODEL_NAME — biar bisa beda model kalau nanti perlu
```
Belum dieksekusi salah satunya — masih pilihan user.
