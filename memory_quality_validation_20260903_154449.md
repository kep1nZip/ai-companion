# v2.2.2 — Local Memory Quality Validation — Hasil Otomatis

Dijalankan: 2026-09-03T08:44:49.787926+00:00

Laporan ini dibuat otomatis oleh `test_memory_quality_validation.py`. T09 (GUI responsiveness) dan T10 (Developer Dashboard) TIDAK ada di sini — perlu observasi manual, lihat bagian paling bawah.

## Provider Connectivity Check

Dicek LANGSUNG ke provider (di luar MemoryExtractor, jadi error TIDAK tertelan try/except internal) SEBELUM test matrix jalan — supaya hasil kosong bisa dibedakan antara "provider memang tidak bisa dihubungi" vs "model menilai dengan benar tidak ada fakta".

- **Local**: ✅ OK — Provider merespons: "[]"

## Test Matrix

| Test | Provider | Kategori | Input | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| T101 | Local | explicit_fact | Aku suka kopi americano. | Memory disimpan | 1 item -> 1 tersimpan | ✅ |
| T102 | Local | noise | Wah hari ini panas banget. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T103 | Local | noise | Hari ini aku cuma lagi santai. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T104 | Local | hedging | Mungkin aku suka kopi kali ya. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T105 | Local | hedging | Kayaknya aku suka americano. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T106 | Local | hedging | Sepertinya aku lebih suka kopi. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T107 | Local | hedging | Mungkin nanti aku mau coba kopi. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T108 | Local | hedging | Aku rasa aku suka game ini. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T109 | Local | hedging | Kayaknya aku suka kopi. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T110 | Local | hedging | Sepertinya aku suka americano. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T111 | Local | hedging | Mungkin aku bakal suka game ini. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T112 | Local | hedging | Aku rasa mungkin aku suka warna biru. | Tidak disimpan ([]) | 0 item -> 0 tersimpan | ✅ |
| T113 | Local | contradiction | Aku suka americano. | Catat hasil aktual | 1 item -> 1 tersimpan | 📝 |
| T114 | Local | contradiction | Sekarang aku sudah tidak suka americano. | Catat hasil aktual | 1 item -> 1 tersimpan | 📝 |

## Validation Log (format sesuai spec §10)

### Local (qwen3-vl-8b)

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Aku suka kopi americano.
Expected: Memory disimpan
Actual: [{'category': 'preference', 'content': 'suka kopi americano'}]
Memory Saved: Yes (1)
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T101, category=explicit_fact
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Wah hari ini panas banget.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T102, category=noise
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Hari ini aku cuma lagi santai.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T103, category=noise
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Mungkin aku suka kopi kali ya.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T104, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Kayaknya aku suka americano.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T105, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Sepertinya aku lebih suka kopi.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T106, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Mungkin nanti aku mau coba kopi.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T107, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Aku rasa aku suka game ini.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T108, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Kayaknya aku suka kopi.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T109, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Sepertinya aku suka americano.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T110, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Mungkin aku bakal suka game ini.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T111, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Aku rasa mungkin aku suka warna biru.
Expected: Tidak disimpan ([])
Actual: []
Memory Saved: No
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T112, category=hedging
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Aku suka americano.
Expected: Catat hasil aktual
Actual: [{'category': 'preference', 'content': 'suka americano'}]
Memory Saved: Yes (1)
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T113, category=contradiction
```

```text
Date: 2026-09-03
Provider: Local
Model: qwen3-vl-8b
Input: Sekarang aku sudah tidak suka americano.
Expected: Catat hasil aktual
Actual: [{'category': 'preference', 'content': 'tidak suka americano'}]
Memory Saved: Yes (1)
GUI Responsive: N/A (headless script, bukan lewat GUI)
Error: None
Notes: test_id=T114, category=contradiction
```

## Quality Evaluation (per provider)

### Local (qwen3-vl-8b)

- Extraction Quality (saran otomatis, BUKAN keputusan final): **Excellent**
- False Positive Rate (noise/hedging yang salah tersimpan): 0/11 = 0%
- False Negative Rate (explicit fact yang gagal tersimpan): 0/1 = 0%
- Error/crash selama test: 0/14 test case

## Known Issue — Contradiction (spec §9, TIDAK diselesaikan di v2.2.2)

### Local — kondisi akhir memori terkait 'americano' setelah kedua pesan contradiction dikirim:

- [preference] "tidak suka americano" (updated_at: 2026-09-03T08:44:49.782567+00:00)
- [preference] "suka americano" (updated_at: 2026-09-03T08:44:45.133499+00:00)

⚠️ **Dikonfirmasi: 2 entri kontradiktif hidup berdampingan** — known issue dari v2.2/v2.2.1 masih terjadi di provider ini. Sesuai spec §5E/§9, ini BUKAN kegagalan v2.2.2, cuma dicatat sebagai known issue yang masih terverifikasi ada.

## Langkah Manual yang BELUM Tercakup Laporan Ini

Script ini headless (tanpa GUI) — dua test berikut WAJIB dicek manual langsung di `main_gui.py`, tidak bisa diotomatisasi dengan jujur:

- **T09 (Local Background Extraction):** set `MEMORY_PROVIDER=local`, chat beberapa kali berturut-turut, amati apakah jendela freeze/lag saat extraction jalan di background, apakah input tetap bisa diketik, apakah aplikasi tetap bisa ditutup normal (tidak hang saat close).
- **T10 (Developer Dashboard):** buka Developer Dashboard, pastikan card "Memory Extraction (Async)" menunjukkan "Provider: Local" saat `MEMORY_PROVIDER=local`, dan "Provider: Gemini" saat di-set balik ke gemini (restart dibutuhkan tiap ganti, sesuai desain v2.2).
