# v2.2.2 — Local Memory Quality Validation — Hasil Otomatis

Dijalankan: 2026-09-20T17:15:43.631899+00:00

Laporan ini dibuat otomatis oleh `test_memory_quality_validation.py`. T09 (GUI responsiveness) dan T10 (Developer Dashboard) TIDAK ada di sini — perlu observasi manual, lihat bagian paling bawah.

## Provider Connectivity Check

Dicek LANGSUNG ke provider (di luar MemoryExtractor, jadi error TIDAK tertelan try/except internal) SEBELUM test matrix jalan — supaya hasil kosong bisa dibedakan antara "provider memang tidak bisa dihubungi" vs "model menilai dengan benar tidak ada fakta".

- **Gemini**: ✅ OK — Provider merespons: "[]"
- **Local**: ❌ GAGAL — ProviderError: Tidak bisa terhubung ke local model server. Pastikan LM Studio (atau server lokal lain) sedang berjalan dan server-nya sudah di-start.

## Test Matrix

| Test | Provider | Kategori | Input | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| T001 | Gemini | explicit_fact | Aku suka kopi americano. | Memory disimpan | 1 item -> 1 tersimpan | ✅ |
| T002 | Gemini | noise | Wah hari ini panas banget. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T003 | Gemini | noise | Hari ini aku cuma lagi santai. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T004 | Gemini | hedging | Mungkin aku suka kopi kali ya. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T005 | Gemini | hedging | Kayaknya aku suka americano. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T006 | Gemini | hedging | Sepertinya aku lebih suka kopi. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T007 | Gemini | hedging | Mungkin nanti aku mau coba kopi. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T008 | Gemini | hedging | Aku rasa aku suka game ini. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T009 | Gemini | hedging | Kayaknya aku suka kopi. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T010 | Gemini | hedging | Sepertinya aku suka americano. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T011 | Gemini | hedging | Mungkin aku bakal suka game ini. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T012 | Gemini | hedging | Aku rasa mungkin aku suka warna biru. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T013 | Gemini | project_specific | Aku sedang mengerjakan LeadEstate. | Memory disimpan (cukup spesifik) | 0 item -> 0 tersimpan | ❌ |
| T014 | Gemini | project_specific | Aku lagi debugging backend LeadEstate. | Memory disimpan (cukup spesifik) | 0 item -> 0 tersimpan | ❌ |
| T015 | Gemini | activity_vague | Aku lagi debugging. | Tidak disimpan (terlalu samar) | 0 item -> 0 tersimpan | ✅ |
| T016 | Gemini | activity_vague | wkwk capek | Tidak disimpan (terlalu samar) | 0 item -> 0 tersimpan | ✅ |
| T017 | Gemini | temporary_intent | Aku lagi pengen belajar Rust malam ini. | Memory disimpan (minat saat ini) | 0 item -> 0 tersimpan | ❌ |
| T018 | Gemini | contradiction | Aku suka americano. | Persis 1 active memory (v2.5) | 0 item -> 0 tersimpan | 📝 |
| T019 | Gemini | contradiction | Sekarang aku sudah tidak suka americano. | Persis 1 active memory (v2.5) | 0 item -> 0 tersimpan | 📝 |
| - | Local | - | - | - | GAGAL SETUP: Connectivity check gagal, test matrix DIBATALKAN untuk provider ini: ProviderError: Tidak bisa terhubung ke local model server. Pastikan LM Studio (atau server lokal lain) sedang berjalan dan server-nya sudah di-start. | ⚠️ |

## Validation Log (format sesuai spec §10)

### Gemini (gemini-3.6-flash)

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku suka kopi americano.
Expected: Memory disimpan
Actual: [{'category': 'preference', 'content': 'Teacher suka kopi americano', 'relation': 'NEW', 'target_memory_id': None}]
Memory Saved: Yes (1)
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T001, category=explicit_fact
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Wah hari ini panas banget.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T002, category=noise
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Hari ini aku cuma lagi santai.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T003, category=noise
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Mungkin aku suka kopi kali ya.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T004, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Kayaknya aku suka americano.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T005, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Sepertinya aku lebih suka kopi.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T006, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Mungkin nanti aku mau coba kopi.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T007, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku rasa aku suka game ini.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T008, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Kayaknya aku suka kopi.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T009, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Sepertinya aku suka americano.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T010, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Mungkin aku bakal suka game ini.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T011, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku rasa mungkin aku suka warna biru.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T012, category=hedging
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku sedang mengerjakan LeadEstate.
Expected: Memory disimpan (cukup spesifik)
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T013, category=project_specific
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku lagi debugging backend LeadEstate.
Expected: Memory disimpan (cukup spesifik)
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T014, category=project_specific
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku lagi debugging.
Expected: Tidak disimpan (terlalu samar)
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T015, category=activity_vague
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: wkwk capek
Expected: Tidak disimpan (terlalu samar)
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T016, category=activity_vague
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku lagi pengen belajar Rust malam ini.
Expected: Memory disimpan (minat saat ini)
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T017, category=temporary_intent
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Aku suka americano.
Expected: Persis 1 active memory (v2.5)
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T018, category=contradiction
```

```text
Date: 2026-09-20
Provider: Gemini
Model: gemini-3.6-flash
Input: Sekarang aku sudah tidak suka americano.
Expected: Persis 1 active memory (v2.5)
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T019, category=contradiction
```

## Quality Evaluation (per provider)

### Gemini (gemini-3.6-flash)

- Extraction Quality (saran otomatis, BUKAN keputusan final): **Excellent**
- False Positive Rate (noise/hedging yang salah tersimpan): 0/11 = 0%
- False Negative Rate (explicit fact yang gagal tersimpan): 0/1 = 0%
- Error/crash selama test: 0/19 test case

### Local

GAGAL SETUP: Connectivity check gagal, test matrix DIBATALKAN untuk provider ini: ProviderError: Tidak bisa terhubung ke local model server. Pastikan LM Studio (atau server lokal lain) sedang berjalan dan server-nya sudah di-start.

## Contradiction — Primary Test v2.5 (§13/§22: relation-aware, BUKAN lagi "boleh 2 memory")

### Gemini — active memory 'americano' setelah kedua pesan contradiction:

- ⚠️ (tidak ada entri active tersimpan — kedua pesan tidak menghasilkan memory sama sekali di provider ini)

⚠️ **INCOMPLETE — 0 active memory.** Ini BUKAN state terlarang §24 ("dua active memory kontradiktif"), tapi juga BUKAN hasil yang diharapkan §22 ("New memory menjadi current/active"). Kemungkinan model menganggap fakta yang menegaskan-ulang/membatalkan memori terkait sebagai "tidak ada info baru" lalu mengembalikan array kosong, alih-alih tetap menyertakan entri dengan relation DUPLICATE/SUPERSEDES. Perlu dites ulang setelah prompt diperjelas (lihat catatan prompt di EXTRACTION_SYSTEM_PROMPT).

## Langkah Manual yang BELUM Tercakup Laporan Ini

Script ini headless (tanpa GUI) — dua test berikut WAJIB dicek manual langsung di `main_gui.py`, tidak bisa diotomatisasi dengan jujur:

- **T09 (Local Background Extraction):** set `MEMORY_PROVIDER=local`, chat beberapa kali berturut-turut, amati apakah jendela freeze/lag saat extraction jalan di background, apakah input tetap bisa diketik, apakah aplikasi tetap bisa ditutup normal (tidak hang saat close).
- **T10 (Developer Dashboard):** buka Developer Dashboard, pastikan card "Memory Extraction (Async)" menunjukkan "Provider: Local" saat `MEMORY_PROVIDER=local`, dan "Provider: Gemini" saat di-set balik ke gemini (restart dibutuhkan tiap ganti, sesuai desain v2.2).
