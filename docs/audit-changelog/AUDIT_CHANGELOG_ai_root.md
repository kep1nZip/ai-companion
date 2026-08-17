# Audit Changelog — `ai/` (8 file)

Scope: `commands.py`, `companion.py`, `context_builder.py`, `conversation.py`,
`gemini.py`, `memory_extractor.py`, `personality.py`, `prompt_builder.py`

Status arsitektur: ✅ bersih total — semua Independence Policy dipatuhi, nol
circular dependency, `_build_contents()` sudah satu definisi (fix sebelumnya
terverifikasi masih berlaku).

---

## ✅ Selesai (docstring final, siap ditempel)

**`conversation.py` — docstring `Conversation`:**
```python
class Conversation:
    """Riwayat percakapan SEMENTARA (in-memory only) untuk sesi yang sedang
    berjalan — BUKAN penyimpanan permanen. Sengaja dipisah total dari
    MemoryManager/SQLite (persistent, jangka panjang); keduanya TIDAK BOLEH
    digabung (Human-in-the-Loop Memory Policy, v0.3). Menyimpan objek
    `types.Content` mentah, siap dikirim langsung ke Gemini API tanpa
    transformasi tambahan."""
```

**`context_builder.py` — docstring `ContextBuilder` (update, sudah sinkron
sampai v0.9 Initiative):**
```python
class ContextBuilder:
    """SATU-SATUNYA modul yang merangkai teks Ephemeral Context. Menggabungkan
    Behavior + Vision (v0.7) + Routine (v0.8) + Initiative (v0.9) Context —
    Vision, Routine, dan Initiative semuanya OPSIONAL; pipeline tetap jalan
    normal walau salah satu (atau semua) mati.

    Routine & Initiative section HARUS ditulis sebagai peluang/saran netral,
    bukan instruksi yang mendikte kalimat Arona (Routine Decision Policy,
    Autonomous Permission Policy) — Gemini yang memutuskan bagaimana
    meresponsnya. Initiative section malah tidak pernah muncul sama sekali
    kecuali `decision_result.should_start == True`."""
```

---

## 🔲 Direkomendasikan — belum dieksekusi

1. **Missing `from __future__ import annotations`** di `conversation.py`,
   `personality.py`, `prompt_builder.py` — tambah 1 baris di masing-masing.
2. **Docstring hilang**: `GeminiClient` (gemini.py), `CommandResult`
   (commands.py) — belum didraft isinya, hanya ditemukan lewat audit.
3. **Type hint terlalu generik/hilang** di `companion.py`:
   - `get_last_routine_event() -> Optional[object]` → `Optional[RoutineEvent]`
   - `get_last_initiative_result()` → tambah `-> Optional[DecisionResult]`
   - `get_history() -> list` → `list[types.Content]`
   - `get_pending_routine_events() -> list` → `list[RoutineEvent]`
4. **Magic number** `limit=10` di `companion.py._build_contents()` (jumlah
   memori yang di-inject) → pindah ke `config/constants.py`, mis.
   `MEMORY_INJECT_LIMIT = 10`.
5. **Log message stale**: `logger.info("Behavior Injected")` di akhir
   `_build_contents()` — nama dari v0.6.5, sekarang method yang sama juga
   inject Vision/Routine/Initiative. Rename mis. `"Context Assembled"`.
6. **Import grouping** tidak konsisten di `companion.py` &
   `context_builder.py` — `routine.*`/`initiative.*` dipisah baris kosong
   sendiri, harusnya 1 blok project-local.
7. **Urutan private method** `ContextBuilder` tidak match urutan pemanggilan
   di `build()` — `_format_initiative`/`_format_routine` didefinisikan
   duluan padahal dipanggil paling akhir.

## 💬 Perlu keputusan desain dulu

8. **`personality.py` tanpa error handling** — kalau `prompts/*.txt` hilang/
   rename, `path.read_text()` raise `FileNotFoundError` mentah saat startup.
   Opsi: (a) raise exception custom + log/exit friendly (fail-fast,
   direkomendasikan untuk system prompt inti), atau (b) skip file yang
   hilang dan lanjut tanpa section itu (risiko: system prompt diam-diam
   tidak lengkap). Belum diputuskan mau pilih yang mana.
