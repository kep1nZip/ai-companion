# V3.10_EXECUTION_REPORT — Evidence Consistency & Conflict Resolution

**Status akhir:** ✅ **PASS — IMPLEMENTED** (CONDITIONAL pada verifikasi manual `main_gui.py` oleh Teacher).

Rilis ini terdiri dari tiga bagian:

| Bagian | Isi | Asal |
|---|---|---|
| **A** | Inti v3.10: 2 bug evidence consistency | Spec PM (GPT) |
| **B** | Hotfix timeout Local (`max_tokens`, `LOCAL_PROVIDER_TIMEOUT`) | Temuan Teacher dari log LM Studio |
| **C** | Tombol suara Arona on/off di GUI | Permintaan Teacher |

B dan C di luar scope spec v3.10.

---

## 1. Bagian A — Evidence Consistency (inti v3.10)

### 1.1 Phase 0 (audit tanpa perubahan kode)
File yang diinspeksi: `ai/companion.py` (`_build_contents`, `_select_relevant_memories`, `_search_memories_by_keywords`, `_recent_conversation_anchor_keywords`, `_persist_fact`, `_schedule_memory_extraction`, `_build_autonomous_contents`), `ai/context_builder.py`, `ai/response_calibration.py`, `ai/conversation_feedback.py`, `ai/temporal_signals.py`, `ai/reference_signals.py`, `ai/conversation_signals.py`, `ai/conversation.py`, `ai/memory_extractor.py`, `database/memory_manager.py`, `prompts/*`, `config/settings.py`, test v3.3–v3.9.

**Evidence Source Map:** semua evidence dihitung SEKALI di `Companion._build_contents()` dan dipakai bersama oleh Local & Gemini. Temporal + Calibration → section ephemeral (awal); Memory → blok "[Konteks memori]" (sebelum riwayat); Riwayat → `contents.extend(history)`; Reference note v3.3 & Feedback v3.7 → paling akhir. Pesan Teacher saat ini selalu berada setelah memory.

### 1.2 Matriks konflik (hasil audit)

| Konflik | Hasil audit | Status |
|---|---|---|
| Preferensi singkat vs "jelaskan detail" | Pesan asli utuh; calibration memuat frasa eksplisit; `system_rules.txt` sudah menyatakan permintaan eksplisit menang | ALREADY SATISFIED (T02, T03) |
| Koreksi langsung "bukan itu maksudku" | Correction v3.7 terkirim di akhir contents; nol memory ditulis | ALREADY SATISFIED (T06) |
| Kembali ke topik lama, target punya memory | Tier current_message menemukan memory A | ALREADY SATISFIED (T09) |
| **Kembali ke topik lama, target hanya ada di riwayat** | Recency mengalahkan target eksplisit | **BUG R01 → FIXED** |
| Memory lama vs fakta saat ini | Memory berlabel "bukan pesan langsung Teacher", ditaruh sebelum pesan saat ini; app tidak memfilter/menimpa | ALREADY SATISFIED sisi aplikasi (T07); perilaku LLM → manual |
| Tanggal eksplisit vs cue inferensi | Teks user tidak pernah diganti; normalisasi hanya tambahan berlabel "dihitung dari kalender" | ALREADY SATISFIED (T11) |
| Frasa samar ("nanti", "minggu depan") | Tidak dinormalisasi, raw cue (v3.5) | ALREADY SATISFIED (T12) |
| **Self-correction satu pesan** | Dilabeli "saling bertentangan"; maksud akhir tidak dilaporkan | **BUG R02 → FIXED** |
| Instruksi benar-benar bertentangan ("satu kata tapi semua langkah") | Aplikasi tidak mendeteksi; klarifikasi adalah keputusan LLM | **Bukan kendali aplikasi** (T14 SKIP) |
| Instruksi sekali pakai vs preferensi durable | Modul evidence tidak punya akses tulis memory | ALREADY SATISFIED sisi aplikasi (T04, T15) |
| Repair "masih bingung, jelasin lebih gampang" | Feedback v3.7 di posisi akhir | ALREADY SATISFIED (T05) |

### 1.3 Reproduksi bug (sebelum fix)

**R01 — explicit reference dikalahkan recency.** Memory: kopi americano, Valorant, Minecraft. Riwayat: (1) "aku lagi debugging parser JSON di tool kecilku", (2) soal kopi, (3) "semalam main Valorant… Minecraft juga". Pesan: **"balik ke parser JSON yang tadi dong"**. Kode asli hanya membaca 3 turn terbaru dan memotong di 8 keyword, sehingga turn (1) tidak pernah terbaca. Memory Minecraft/Valorant disuntik, lalu note: *"ADA LEBIH DARI SATU kemungkinan … WAJIB tanya klarifikasi"* padahal Teacher sudah menyebut parser JSON.

**R02 — self-correction dilabeli konflik.** Pesan **"jelaskan detail—eh, cukup ringkas saja"** → note *"instruksi gaya jawaban … tampak saling bertentangan … gunakan pertimbangan wajar"*. Seharusnya maksud akhir (ringkas) dilaporkan.

### 1.4 Perbaikan

| File | Perubahan |
|---|---|
| `ai/companion.py` | `_recent_conversation_anchor_keywords(target_keywords=None)`: bila kata kunci pesan saat ini muncul di turn user sebelumnya MANAPUN (full history), turn itu jadi anchor; tidak ada yang cocok → perilaku v3.3 identik. Satu baris pemanggil di `_select_relevant_memories`. |
| `ai/reference_signals.py` | `GENERIC_REFERENCE_STOPWORDS` + `balik`, `kembali`, `dong`, `donk` (pembawa referensi, bukan pembeda topik). |
| `ai/response_calibration.py` | `detect_depth_cues` direfaktor ke `_scan_depth_cues` (logic sama, kini mengembalikan span; API publik tak berubah). Field baru `self_correction_final`. Hanya aktif bila ada marker eksplisit (`eh`, `ralat`, `koreksi`, `maksudku`, `ga jadi`, `maaf salah`) di ANTARA cue detail & ringkas. Bukan aturan "klausa terakhir selalu menang". |
| `ai/context_builder.py` | Baris observasional maksud akhir; note "bertentangan" tidak muncul bila self-correction jelas. |

Tidak diubah: skema/semantik memory, extractor, `prompts/*`, `_build_autonomous_contents` (identik dengan versi asli), Initiative/Routine/Vision, tidak ada LLM/skor/DB baru. `CONVERSATION_HISTORY_MAX_MESSAGES` tetap `None` (T25).

---

## 2. Bagian B — Hotfix timeout Local

### 2.1 Kronologi dan bukti dari log LM Studio (2026-10-16)

| Log | Kecepatan generasi | Temuan |
|---|---|---|
| 09:38 (model baru dimuat) | ~25 t/s | Model jatuh ke **loop pengulangan** (2.629 token), tanpa `max_tokens` → 120 dtk habis → timeout |
| 10:41 dan 10:57 | ~2,9 t/s | Jawaban koheren, hanya terlalu lambat. Di jendela 10:57–10:59 hanya `slot id 2` aktif → **tidak ada request paralel** |
| 11:02 (chat langsung di LM Studio, tanpa Arona) | **3,12 t/s** | Lambat juga → bukan masalah Arona |
| 11:05 (setelah eject + load ulang model) | **3,65 t/s**, prompt 131 t/s (pagi: 239 t/s) | Tetap lambat; konfigurasi model identik dengan pagi (`n_gpu_layers=34`, `n_threads=6`) |

Konteks v3.10 untuk pesan "Untuk topik ini, jelaskan detail dan beri contoh" terbukti identik dengan v3.9 (567 karakter, hash sama): v3.10 bukan penyebab.

### 2.2 Kesimpulan
- Kelambatan ada di **LM Studio/hardware**, bukan di Arona. Hipotesis "request berebut server" (chat+memory+vision sama-sama `local`) **gugur** untuk jendela yang diamati.
- Dugaan terkuat (BELUM terbukti, perlu dicek Teacher): sebagian bobot/KV cache terdorong dari VRAM ke memori sistem (peringatan `failed to fit params to free device memory`), atau GPU di-throttle (mode daya/suhu/baterai). Whisper di aplikasi berjalan di CPU sehingga bukan penyebab.

### 2.3 Perubahan kode (hanya membatasi dampak, tidak memperbaiki kelambatan)

| File | Perubahan |
|---|---|
| `config/settings.py` | `LOCAL_PROVIDER_MAX_TOKENS` (default 1024, `0` = tanpa batas); `LOCAL_PROVIDER_TIMEOUT` (default 120 dtk, nilai tak valid → 120) |
| `ai/providers/local_provider.py` | Parameter `max_tokens` opsional, dikirim ke payload bila > 0 |
| `ai/providers/factory.py` | Chat utama memakai `max_tokens`; chat dan memory memakai `LOCAL_PROVIDER_TIMEOUT` |

Catatan: log 11:05 membuktikan `max_tokens: 1024` sudah terkirim, tetapi request tetap putus tepat 120 dtk → **`LOCAL_PROVIDER_TIMEOUT` belum diterapkan Teacher** (perlu salin file terbaru dan menambah baris di `.env`). Pada ~3,65 t/s, 1.024 token butuh ~5 menit, jadi `max_tokens` saja tidak menolong.

### 2.4 Yang perlu dilakukan Teacher
1. Tambah ke `.env`: `LOCAL_PROVIDER_TIMEOUT=400`, restart aplikasi (jalan keluar sementara).
2. Periksa GPU: Task Manager → GPU utilization dan Dedicated/Shared GPU memory saat generate; siapa yang memakai VRAM (VTube Studio, browser, game, OBS).
3. Turunkan **GPU Offload** di LM Studio dari 34 ke ~24 lalu load ulang. Naik ke ≥ 8 t/s → dugaan VRAM penuh terkonfirmasi.
4. Pastikan colok listrik dan mode daya bukan "Power saver". Coba restart PC.
5. Sementara itu bisa memakai `AI_PROVIDER=gemini`.

---

## 3. Bagian C — Tombol suara Arona (🔊/🔇)

| File | Perubahan |
|---|---|
| `config/settings.py` | `SPEECH_ENABLED` dari `.env` `ARONA_SPEECH_ENABLED` (default nyala) |
| `speech/player.py` | `AudioPlayer.stop()` — menghentikan playback berjalan |
| `speech/voice_manager.py` | `speech_enabled`, `set_speech_enabled()`; `_speak()` melewati TTS+playback bila mati (hemat kuota API), state kembali IDLE; mute saat sintesis → hasil tidak diputar |
| `ui/settings_service.py` | `save_speech_enabled()` — menyimpan pilihan ke `.env` |
| `ui/window.py` | Tombol 🔊/🔇 di baris input chat, handler toggle, `_speak_text` dilewati saat mati |

Gerbang berada di `VoiceManager._speak()` sehingga semua jalur suara tercakup: balasan chat teks, mode mic, dan pesan otonom. Yang dimatikan hanya OUTPUT suara; teks, STT/mic, reaksi avatar, dan Companion tidak berubah.

**Batas verifikasi:** `VoiceManager` diuji dengan stub. `ui/window.py` lolos compile tetapi **belum dijalankan** (sandbox tanpa PySide6/PortAudio/mic).

---

## 4. Tes

| Suite | Sebelum | Sesudah | Skip |
|---|---|---|---|
| v3.3 | 24/0 gagal | 24/0 | 0 |
| v3.4 | 14/0 | 14/0 | 0 |
| v3.5 | 24/0 | 24/0 | 0 |
| v3.6 | 24/0 | 24/0 | 3 (regresi file terpisah, sudah ada sebelumnya) |
| v3.7 | 27/0 | 27/0 | 4 (idem) |
| v3.8 | 24/0 | 24/0 | 4 (idem) |
| v3.9 | 16/0 | 16/0 | 5 (idem) |
| **v3.10 (baru)** | – | **31 total, 0 gagal, 30 PASS** | **1 (T14)** |
| `test_local_max_tokens.py` (baru) | – | 6/0 gagal | 0 |
| `test_speech_toggle.py` (baru) | – | 8/0 gagal | 0 |

- T14 SKIP: klarifikasi atas instruksi yang benar-benar bertentangan adalah keputusan LLM; aplikasi tidak punya jalur deterministik untuk itu.
- Test v3.10 yang dijalankan terhadap kode ASLI langsung crash di R01 (parameter belum ada). Bukti "sebelum" untuk R01/R02 adalah output probe di §1.3, bukan assert merah di suite.
- Compile (`py_compile`) dan import semua file yang diubah: OK.

---

## 5. Daftar file (tanpa .zip, salin dengan struktur folder yang sama)

**Diubah:** `ai/companion.py`, `ai/context_builder.py`, `ai/reference_signals.py`, `ai/response_calibration.py`, `ai/providers/local_provider.py`, `ai/providers/factory.py`, `config/settings.py`, `speech/player.py`, `speech/voice_manager.py`, `ui/settings_service.py`, `ui/window.py`

**Baru:** `test_v3_10_evidence_consistency.py`, `test_local_max_tokens.py`, `test_speech_toggle.py`, `V3.10_EXECUTION_REPORT.md`

---

## 6. Checklist manual `main_gui.py` — ⬜ NOT YET VERIFIED

**A. v3.10**
1. **Per-turn override:** di percakapan yang sudah punya topik, "jelaskan detail soal LeadEstate dan beri contoh" → jawaban detail; pertanyaan berikutnya tanpa instruksi → kembali ke default; Memory GUI tidak mendapat preferensi baru.
2. **Koreksi:** pancing salah paham → "Bukan itu maksudku; yang kumaksud …" → jawaban ke makna baru; Memory GUI tidak berubah tanpa alasan.
3. **Return topik (R01):** bahas topik A (tanpa memory), lalu B, C → "balik ke <kata kunci A> yang tadi" → Arona melanjutkan A, tidak menanyakan pilihan B/C.
4. **Self-correction (R02):** "jelaskan detail—eh, cukup ringkas saja" → jawaban ringkas; Dashboard calibration menampilkan maksud akhir.
5. **Tanggal:** "rapat tanggal 15 Oktober jam 3", lalu "nanti aku kabarin" → eksplisit tetap eksplisit.
6. **Konflik asli (T14):** "jawab satu kata tapi jelaskan semua langkahnya" → amati apakah Arona bertanya klarifikasi (perilaku LLM; bila tidak, catat sebagai keterbatasan).
7. **Memory vs fakta saat ini:** memory "pakai Flask", ketik "sekarang pakai FastAPI, bukan Flask lagi" → jawaban memakai FastAPI.
8. **Local vs Gemini:** input sama → section Dashboard identik.

**B. Hotfix Local**
9. Setelah `LOCAL_PROVIDER_TIMEOUT` diset dan hardware diperiksa: jawaban detail datang tanpa "Ada masalah sistem… timeout".

**C. Tombol suara**
10. Klik 🔊 → 🔇, status bar "Suara Arona: mati". Kirim chat → teks muncul, tidak ada suara, mic tetap bisa diklik.
11. Saat Arona sedang bicara, klik 🔇 → suara langsung berhenti.
12. Mode mic saat mati → Arona tetap membalas (teks), status kembali "Ready".
13. Tutup & buka aplikasi → tombol mengikuti pilihan terakhir (`.env` berisi `ARONA_SPEECH_ENABLED`).
14. Pesan inisiatif Arona saat mati → hanya teks.

---

## 7. Catatan dan keterbatasan

- **Perilaku LLM** untuk T07/T14 dan risiko extractor menyimpan instruksi sekali pakai ("kali ini singkat aja") tidak bisa dibuktikan offline; `EXTRACTION_SYSTEM_PROMPT` tidak punya aturan eksplisit untuk itu. Tidak diubah (bukan bug terbukti). Bila checklist 1–2 menunjukkan memory yang tidak diinginkan, itu dasar sah untuk perubahan prompt kecil.
- Pada target eksplisit tanpa memory apa pun, fallback recency v1.9 tetap menyuntik memory terbaru (perilaku lama); note kini versi ringan, bukan klarifikasi paksa.
- Marker self-correction sengaja sempit; koreksi tanpa marker tetap ditandai "bertentangan" seperti v3.6.
- **Pesan inisiatif Arona** (Autonomous Interaction v1.8) muncul tanpa diketik Teacher: cek tiap 60 dtk, jeda 45 menit, maks 3/jam dan 10/hari, lalu diucapkan lewat TTS. Ini perilaku yang disengaja, bukan bug. Belum ada tombol GUI untuk mematikannya (tidak diubah di rilis ini; tombol 🔇 hanya mematikan suaranya). Kandidat pekerjaan berikutnya bila Teacher menginginkannya.
- Kelambatan Local (§2) adalah masalah hardware/LM Studio. Opsi lanjutan bila tetap lambat: turunkan GPU offload, model lebih kecil, atau streaming agar timeout berbasis idle (belum dibangun, belum terbukti perlu).
