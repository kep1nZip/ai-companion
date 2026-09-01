# v2.0 — Step 9: Default Provider Decision — STATUS FINAL: ✅ SELESAI

## Keputusan Resmi

```
Default language provider:     Local
Alternative language provider: Gemini (via Settings, atau AI_PROVIDER=gemini di .env)

Local model:        qwen/qwen3-vl-8b (Q4_K_M)
Vision:              Gemini
Memory Extraction:   Gemini
TTS:                 Gemini
```

Local dijadikan default berdasarkan hasil Step 7 Full Regression yang sudah
selesai & diterima Teacher lewat testing nyata — bukan semata-mata karena
gratis.

## Yang Dibangun

| File | Perubahan |
|---|---|
| `config/settings.py` | Default `AI_PROVIDER` `"gemini"` → `"local"`. `AI_PROVIDER=gemini` eksplisit di `.env` tetap dihormati (backward compatible). |
| `main_gui.py` | Komentar diperbarui, logic pemilihan provider tidak berubah (sudah benar sejak Step 6). |
| `ui/settings_service.py` | `SettingsSnapshot` tambah `ai_provider`/`local_provider_model_name`; tambah `validate_provider()`, `validate_local_model_name()`, `save_provider_settings()`. |
| `ui/settings.py` | Dropdown "Language Provider" (Local/Gemini), field "Local Model" (editable, muncul cuma saat Local dipilih), "Status" (config-sane check, bukan live health-check). |
| `ui/theme.py` | Style `QComboBox` dark theme (widget baru). |

Dirty-state Apply/Cancel sengaja dipisah per section (`_api_key_dirty` vs
`_provider_dirty`) — supaya ganti Provider doang tidak ikut memicu percobaan
simpan API Key kosong.

## Bug yang Ditemukan & Diperbaiki Selama Proses Ini

**Gejala:** ganti Provider ke Gemini di Settings, klik Apply, log bilang
"berhasil disimpan", tapi setelah restart tetap Local.

**Akar masalah:** `ui/settings_service.py` mencari file `.env` pakai
`find_dotenv(usecwd=True)` — itu resolve berdasar **current working
directory** saat app di-launch. Sementara `config/settings.py` sendiri pakai
`load_dotenv()` polos, yang secara default resolve berdasar **lokasi file
pemanggilnya** (call stack), bukan CWD. Kalau app dijalankan lewat
shortcut/launcher yang working directory-nya beda dari folder project (umum
di Windows), dua strategi pencarian ini bisa menemukan file `.env` yang
**berbeda** — penulisan "berhasil" tapi ke file yang tidak pernah dibaca
ulang saat restart.

**Perbaikan:** `find_dotenv(usecwd=True)` → `find_dotenv()` (tanpa
`usecwd`), supaya strategi pencarian **sama persis** dengan yang dipakai
`config/settings.py`. Ditambah log `"menulis {key} ke {path}"` supaya kalau
ada masalah serupa di masa depan, langsung kelihatan file mana yang
sebenarnya ditarget — tidak perlu tebak-tebakan lagi.

Ini murni bug di kode saya sendiri (bukan kesalahan konfigurasi Teacher) —
dicatat apa adanya, bukan didiamkan.

## No Silent Fallback — Tetap Terjaga

Audit sebelumnya (`self._gemini` di-assign tepat sekali, nol try/except yang
menyembunyikan kegagalan provider) tetap valid — bug `.env` di atas murni
soal *menyimpan pilihan*, bukan soal *runtime diam-diam pindah provider*.
Setelah fix, Apply → restart → provider yang benar-benar aktif dijamin
sama dengan yang dipilih di Settings.

## v2.0 Completion Criteria

```
Provider abstraction             ✅
Gemini Provider                  ✅
Local Provider                   ✅
Local Model validated            ✅
Configuration                    ✅
Full Regression                  ✅
Default Provider decision        ✅  (Local, resmi)
Provider selection UX            ✅  (Settings GUI, dikonfirmasi jalan setelah bugfix)
Gemini preserved                 ✅
No critical regression           ✅
```

## 🎉 v2.0 — Model Migration: SELESAI & DIKONFIRMASI AMAN

Arona sekarang defaultnya jalan di local model (`qwen/qwen3-vl-8b`), bisa
ditukar ke Gemini kapan saja lewat Settings tanpa perlu edit `.env` manual,
dan perpindahannya benar-benar tersimpan & berlaku setelah restart.
