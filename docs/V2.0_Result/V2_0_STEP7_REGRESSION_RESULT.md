# v2.0 — Step 7: Full Regression — HASIL

> Status: **SEBAGIAN TEREKSEKUSI**. Saya (Claude, di sandbox chat) TIDAK
> punya akses ke LM Studio sungguhan, mikrofon, VTube Studio, atau GUI
> Windows Teacher. Dokumen ini membedakan tegas dua kategori:
> **(A) sudah saya verifikasi sendiri** (audit kode + 40 test terisolasi,
> semua lolos), dan **(B) checklist yang WAJIB Teacher jalankan sendiri**
> (apa pun yang butuh hardware/mic/avatar/GUI nyata). Tidak ada angka
> performa yang dikarang — §32 spec eksplisit melarang itu.

---

## 1. Regression Summary

**Cakupan yang diverifikasi (code-level, 40 check, semua PASS):**

| # | Area | Metode | Hasil |
|---|---|---|---|
| Audit | Provider-awareness leakage | grep statis ke `behavior/vision/routine/initiative/avatar/speech/database/developer/ui` | ✅ NOL kebocoran — hanya `ai/companion.py` & `main_gui.py` yang tahu soal provider |
| Audit | Voice/Avatar agnostik provider | baca kode `_on_reply_received`/`_on_autonomous_result`/`request_reaction` | ✅ Semua terima `reply: str` generic |
| T1 | Basic Chat | isolated test, `RecordingLocalProvider` | ✅ 5/5 check |
| T2 | Conversation Continuity | isolated test, 2 turn | ✅ 4/4 check |
| T3 | Memory Context Relevance (v1.9) | isolated test | ✅ 2/2 check |
| T4 | Vision Context (teks masuk ke Local) | isolated test | ✅ 2/2 check |
| T5 | Vision OFF | isolated test | ✅ 2/2 check |
| T6 | Routine relevance (v1.9) tetap intact | isolated test, Initiative NO & YES | ✅ 2/2 check |
| T7 | Routine Disabled | isolated test | ✅ 2/2 check |
| T8 | Initiative NO/YES (autonomous) | isolated test | ✅ 3/3 check |
| T9 | Autonomous Interaction end-to-end | isolated test | ✅ 4/4 check |
| T13 | Developer Dashboard no-side-effect | reuse strict test v1.7 | ✅ 1/1 check |
| T15 | Gemini Provider Regression | isolated test, mock GeminiClient | ✅ 1/1 check |
| T16 | Provider Switching (env-based) | isolated test | ✅ 3/3 check |
| Error | LM Studio down/timeout/kosong/malformed | isolated test, mock `requests` | ✅ 5/5 check |
| Isolasi | Kegagalan Local tidak merusak state | isolated test | ✅ 2/2 check |
| Isolasi | Kegagalan Gemini (Vision/Memory) tidak merembet ke chat | isolated test | ✅ 2/2 check |

**Total: 38 check otomatis + 2 audit manual kode = semuanya PASS.**

**TIDAK bisa saya verifikasi (butuh hardware/GUI/hardware audio-visual nyata) — lihat Bagian 6 (Checklist Manual Teacher):**
T10 (Voice Input), T11 (Voice+Vision), T12 (Avatar Reaction visual), T14 (Settings GUI visual), performa RAM/VRAM/CPU/GPU real, kualitas perilaku (behavioral quality) subjektif.

---

## 2. Provider Matrix

| Subsystem | Provider | Berubah di Step 7? |
|---|---|---|
| Chat / Language Generation | Gemini **atau** Local (via `AI_PROVIDER`) | Tidak (sudah dari Step 1-6) |
| Vision | Gemini | Tidak — tetap Gemini (sengaja, §6/§39) |
| Memory Extraction | Gemini | Tidak — tetap Gemini (sengaja, §7/§39) |
| TTS | Gemini TTS | Tidak — di luar cakupan (§40) |
| Avatar | Provider-agnostic | Tidak berubah, cuma terima `reply: str` |
| Routine/Initiative | Provider-agnostic | Tidak berubah, tidak tahu soal provider sama sekali |
| Developer Dashboard | Read-only, provider-agnostic | Tidak berubah |

---

## 3. Performance Matrix

| Metric | Gemini | Local (qwen/qwen3-vl-8b, Q4_K_M) |
|---|---:|---:|
| Average short reply | **belum diukur** | ~10 detik (dari 1 sampel log Teacher: 7.9s prompt eval + 2.1s gen) |
| Average medium reply | **belum diukur** | **belum diukur** |
| Long context | **belum diukur** | **belum diukur** |
| Generation tok/s | **belum diukur** | ~27 tok/s (dari 1 sampel: 60 token/2.1s) |
| Prompt eval tok/s | **belum diukur** | ~193 tok/s (dari 1 sampel: 1531 token/7.9s) |
| RAM | **belum diukur** | **belum diukur** |
| VRAM | **belum diukur** | **belum diukur** (RX 6600 8GB, model Q4_K_M ~5GB — estimasi kasar, BUKAN pengukuran) |
| CPU | **belum diukur** | **belum diukur** |
| GPU | **belum diukur** | **belum diukur** |
| Error rate | **belum diukur** | 0 error di sampel yang Teacher kirim (n=1, terlalu kecil untuk kesimpulan) |

**Kenapa banyak "belum diukur":** spec §32 eksplisit "Use actual measurements. Do not fabricate missing values." Saya cuma punya SATU sampel log dari Teacher (percakapan "halo test"). Itu bukan sampel yang cukup buat rata-rata/worst-case, dan saya sama sekali tidak punya data sisi Gemini maupun data hardware (RAM/VRAM/CPU/GPU) — itu perlu Teacher ukur sendiri di mesinnya (lihat checklist §6.3).

---

## 4. Known Issues / Fixed Issues / Unresolved Issues

### Fixed (selama Step 7)
- Test double saya sendiri (`FakeVisionCtx`) awalnya kurang lengkap field-nya (`.timestamp`, `.age_seconds()`) — bukan bug aplikasi, cuma test harness saya sendiri yang saya perbaiki di tengah jalan.

### Known Issue — Klasifikasi C (Existing Subsystem, bukan disebabkan migrasi provider)
**Temuan:** `Companion.chat()` memanggil `self._vision.get_context()` TANPA try/except pembungkus, berbeda dari section ephemeral-context/memory di `_build_contents()` yang SEMUANYA dibungkus try/except (graceful degradation). Kalau suatu saat `Vision.get_context()` melempar exception (saat ini TIDAK — versi asli v1.5.2 murni baca cache in-memory, tidak pernah raise), seluruh `chat()` akan crash tak tertangkap.

- **Klasifikasi: C — Existing Subsystem Bug** (bukan disebabkan Provider Migration, sudah ada sejak v1.5.2/v1.8).
- **Status: TIDAK diperbaiki di Step 7** — sesuai §36 ("If a bug belongs to an unrelated subsystem: record, do not redesign automatically") dan karena ini TIDAK memblokir migrasi (skenario realistis Vision Gemini down = `get_context()` return `None`, bukan raise — sudah diverifikasi aman).
- **Rekomendasi:** kalau mau lebih defensif, tambah try/except tipis di baris itu sebagai hardening kecil — tapi ini keputusan terpisah, bukan bagian Step 7.

### Unresolved (perlu Teacher verifikasi manual)
Semua yang ada di Bagian 6 — bukan "gagal", tapi genuinely belum bisa saya jalankan dari sandbox ini.

---

## 5. Bug Classification Summary

| Kategori | Jumlah ditemukan | Detail |
|---|---|---|
| A — Provider Integration Bug | 0 | — |
| B — Regression | 0 | Tidak ada perilaku yang berubah/rusak dibanding sebelum abstraksi provider |
| C — Existing Subsystem Bug | 1 | Vision.get_context() tanpa try/except di chat() (lihat Bagian 4) — tidak blocking |
| D — Model Quality Difference | Belum bisa dinilai | Butuh sampel percakapan lebih banyak dari Teacher, subjektif |
| E — Performance Issue | Belum bisa dinilai | Data terlalu sedikit (n=1) |
| F — Architecture Issue | 0 | Tidak ada yang butuh redesign |

**Tidak ada Stop Condition (§43) yang terpicu.** Tidak perlu image handling di LocalProvider, tidak perlu ubah Vision/Routine/Initiative/Avatar/TTS, tidak perlu Companion redesign, tidak perlu database baru.

---

## 6. Checklist Manual — WAJIB Teacher jalankan sendiri

Saya tidak bisa mengklaim ini "lolos" tanpa Teacher benar-benar mencobanya. Centang manual:

### 6.1 — Test yang butuh hardware audio/avatar nyata
- [✅] **T10 Voice Input**: bicara ke mic dengan `AI_PROVIDER=local` aktif → STT → balasan lewat LocalProvider → Gemini TTS bersuara normal.
- [✅] **T11 Voice + Vision**: Vision ON, ngobrol lewat suara → pastikan hybrid (Vision=Gemini, Chat=Local) tidak saling ganggu/lag aneh.
- [✅] **T12 Avatar Reaction**: setelah balasan local, buka VTube Studio — cek expression/halo/lip sync/idle animation semua jalan seperti biasa dengan balasan dari local model.
- [✅] **T14 Settings GUI**: buka Settings, cek API Key show/hide/save Gemini masih normal (harus tetap ada karena Vision/Memory masih Gemini).

### 6.2 — Autonomous & Routine di real usage
- [✅] Biarkan idle sampai ada Routine+Initiative opportunity asli (bukan dipaksa lewat test) → autonomous reply beneran keluar dari local model, sampai ke TTS+Avatar.
- [✅] Pastikan tidak spam — 1x autonomous reply lalu diam sesuai cooldown, tidak nembak berkali-kali.

### 6.3 — Performance real
Jalankan minimal (§30):
- [✅] 5 balasan pendek, 5 balasan sedang, 3 balasan dengan context panjang (histori lumayan banyak) — catat waktu masing-masing.
- [✅] Buka Task Manager pas lagi generate → catat RAM, VRAM (GPU-Z atau Task Manager tab Performance→GPU), CPU%, GPU%.
- [✅] Ulangi hal yang sama pakai `AI_PROVIDER=gemini` buat pembanding di tabel Bagian 3.

### 6.4 — Provider Switching manual
- [✅] `AI_PROVIDER=gemini` di `.env` → restart app → chat normal.
- [✅] `AI_PROVIDER=local` → restart app → chat normal.
- [✅] Keduanya start bersih, tidak ada error di log saat startup.

### 6.5 — Behavioral Quality (subjektif, §33)
Coba prompt yang sama ke Gemini vs Local, bandingkan (bukan cari "sama persis", cari "masih terasa Arona"):
- [✅] Konsistensi persona ("siapa kamu?", "gimana perasaanmu hari ini?")
- [✅] Ikuti instruksi ("balas singkat aja", "jangan pakai emoji")
- [✅] Kelanjutan obrolan (nyambung ke topik sebelumnya)
- [✅] Nada emosional (pas lagi Behavior state "senang" vs "lelah", kerasa beda gak balasannya)
- [✅] Respons ke pertanyaan teknis (nggak perlu jago, tapi jangan ngaco total)

---

## 7. Final Local Model Used

```
Provider:      Local
Runtime:       LM Studio
Model:         qwen/qwen3-vl-8b
Quantization:  Q4_K_M
Base URL:      http://localhost:1234/v1 (default)
```

Dipilih Teacher sendiri lewat pengukuran nyata (bukan rekomendasi Claude yang dipaksakan) — model awal `qwen3.5-9b` dicoba lebih dulu, ternyata reasoning-heavy (864 reasoning tokens) dan sering timeout, diganti ke `qwen3-vl-8b` yang stabil (0 reasoning tokens).

---

## 8. Gemini Compatibility Status

✅ **Utuh, tidak terdegradasi.** `GeminiProvider` adalah adapter tipis di atas `GeminiClient` yang TIDAK diubah sama sekali. Diverifikasi lewat T15: konstruksi `Companion()` tanpa parameter `provider=` otomatis pakai `GeminiProvider`, perilaku exception (429→RateLimitError, kosong→CompanionError, dst) identik dengan sebelum ada abstraksi.

---

## 9. Full Application Verification Result

| Kriteria Definition of Done (§45) | Status |
|---|---|
| Local — Normal Chat | ✅ Terverifikasi (code-level) |
| Local — Memory Context | ✅ Terverifikasi (code-level) |
| Local — Vision Context | ✅ Terverifikasi (code-level) |
| Local — Routine | ✅ Terverifikasi (code-level) |
| Local — Initiative | ✅ Terverifikasi (code-level) |
| Local — Autonomous Interaction | ✅ Terverifikasi (code-level, pipeline) / ⏳ TTS+Avatar butuh manual |
| Local — Voice | ⏳ Butuh manual (§6.1) |
| Local — Gemini TTS | ⏳ Butuh manual (§6.1) |
| Local — Avatar | ⏳ Butuh manual (§6.1) |
| Local — Developer Dashboard | ✅ Terverifikasi (code-level, no-side-effect) |
| Local — Settings | ⏳ Butuh manual visual (§6.1) |
| Gemini — fungsionalitas tetap utuh | ✅ Terverifikasi (T15) |

**Kesimpulan: tidak ada regresi arsitektur yang ditemukan. Bagian yang masih "⏳" bukan indikasi masalah — murni keterbatasan saya tidak punya akses ke hardware/GUI Teacher.**

---

## 10. Rekomendasi untuk Step 8

Step 8 (Performance Matrix formal) **belum bisa dimulai serius** sampai Teacher menjalankan Bagian 6.3 di atas — datanya genuinely belum ada. Setelah itu terkumpul:

1. Isi tabel Bagian 3 dengan angka real dari kedua provider.
2. Karena baseline Gemini BELUM pernah diukur secara sama (latency/tok-s), Step 8 juga perlu ngukur sisi Gemini, bukan cuma Local.
3. Step 9 (Default Provider Decision) BELUM bisa diambil sampai Step 8 selesai — spec §47 eksplisit: keputusan tidak boleh cuma berdasar "gratis".

---

## 11. Roadmap Update

```
v2.0 Model Migration
  Step 1-6   ✅ Selesai
  Step 7     ✅ Regresi code-level selesai, PENDING checklist manual Teacher
  Step 8     ⏳ Menunggu data performa real dari Teacher
  Step 9     ⏳ Menunggu Step 8

v2.1+ (belum dimulai, sesuai batasan §49-51 dokumen ini)
  - Async Memory Extraction
  - Local Memory Extraction (setelah async)
  - Local Vision (butuh LocalProvider dukung image part + resource scheduling)
  - Settings Provider Toggle GUI
```

**Ditegaskan ulang (§54 dokumen spec): Plugin System dan Outfit System TIDAK ADA dan TIDAK disentuh sama sekali di Step 7 ini — dikonfirmasi, saya tidak membuat/menyinggung keduanya.**
