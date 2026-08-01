# CODE_STYLE.md — AI Companion (Arona)

> Dokumen ini adalah kontrak gaya kode untuk project ini. Berlaku untuk siapa pun yang mengedit kode — manusia maupun AI (Claude, GPT, dll). Disusun dari pola yang sudah konsisten dipakai sejak v0.1.

---

## 1. Penamaan File & Folder

- Folder = 1 subsystem, huruf kecil, tanpa underscore kalau bisa 1 kata (`avatar/`, `behavior/`, `vision/`, `routine/`, `initiative/`, `developer/`).
- File = `snake_case.py`, deskriptif terhadap isi utamanya: `nama_domain.py` untuk public API/coordinator (`emotion.py`, `relationship.py`, `routine.py`), `nama_domain_state.py` untuk dataclass state (`emotion_state.py`, `relationship_state.py`), `nama_domain_rules.py` untuk logic transisi/aturan (`emotion_rules.py`), `nama_domain_history.py` untuk riwayat in-memory.
- Satu file = satu tanggung jawab utama. Kalau sebuah file mulai memuat >2 class/concept berbeda yang tidak saling berhubungan erat, itu sinyal harus dipecah.

## 2. Penamaan Class

- `PascalCase`, nama = peran, bukan implementasi (`Companion`, bukan `MainOrchestrator`; `RelationshipCoordinator`, bukan `RelationshipManagerImpl`).
- Public API coordinator = `<Domain>` atau `<Domain>Coordinator` (`Vision`, `Routine`, `RelationshipCoordinator`, `EmotionCoordinator`).
- Dataclass state = `<Domain>State` (`EmotionState`, `RelationshipState`, `InternalState`) atau `<Domain>Snapshot` khusus untuk Developer Tools (`BehaviorSnapshot`).
- Exception = `<Domain>Error` (`CompanionError`, `GeminiResponseError`, `RateLimitError`).
- Enum = kata benda tunggal (`Emotion`, `Mood`, `AvatarState`, `VoiceState`, `TimeWindow`), member = `UPPER_SNAKE_CASE`.

## 3. Penamaan Method & Fungsi

- `snake_case`, kata kerja di depan untuk aksi (`process_message`, `apply_transition`, `build_snapshot`), kata benda untuk getter (`current`, `get_history`).
- Getter murni tanpa efek samping: `get_xxx()` atau property `@property def xxx`.
- Method yang mengubah state: kata kerja aktif (`update`, `apply`, `record`, `save`, `load`, `reset`).
- Private/internal method: prefix `_` (`_build_contents`, `_update_behavior`, `_format_time`).
- **JANGAN PERNAH** mendefinisikan method dengan nama sama dua kali dalam satu class (lihat riwayat bug v0.9.5 — `_build_contents()` sempat terduplikasi 3x karena edit bertahap menambah method baru alih-alih mengedit yang lama). Kalau perlu tambah parameter ke method yang sudah ada, **selalu edit definisi yang ada**, jangan tambah definisi baru.

## 4. Type Hints

- **Wajib di semua public method/function** — parameter dan return type.
- Pakai `from __future__ import annotations` di baris pertama tiap file (memudahkan forward reference tanpa quote string).
- `Optional[X]` untuk nilai yang boleh `None`, jangan pakai `X | None` inline kalau file lain di project konsisten pakai `Optional` (ikuti mayoritas yang sudah ada).
- Dataclass field selalu punya type hint eksplisit, termasuk default value lewat `field(default_factory=...)` untuk mutable/objek kompleks.

## 5. Docstring

- Tiap class punya docstring 1-3 kalimat: **apa tanggung jawabnya** + **apa yang TIDAK boleh dia lakukan** (pola "TIDAK PERNAH X, TIDAK PERNAH Y" dipakai konsisten di seluruh project untuk menegaskan Independence Policy tiap subsystem).
- Method kompleks (>10 baris atau ada keputusan desain non-obvious) dapat docstring singkat menjelaskan **kenapa**, bukan cuma **apa** (kode sudah menjelaskan "apa").
- Hindari docstring generik ("This function does X") — ikuti pola project: jelaskan posisi dalam arsitektur.

## 6. Format Logging

- Selalu pakai `from config.logger import logger` (loguru), **jangan** `print()` untuk apa pun selain script test manual sekali pakai.
- Format pesan: `logger.info("Nama Event: {}", detail)` — nama event dalam Title Case English (`"Behavior Updated"`, `"Context Generated"`, `"Persistence Saved"`) diikuti detail dalam Bahasa Indonesia kalau perlu.
- Level:
  - `logger.info` — event normal yang berguna untuk tracing alur (state berubah, request dikirim, dst).
  - `logger.warning` — kegagalan yang di-*handle* gracefully (fallback ke default, retry, dst).
  - `logger.error`/`logger.exception` — kegagalan yang tidak sepenuhnya bisa dipulihkan, butuh perhatian; pakai `.exception` kalau ingin traceback lengkap tercatat.
- **Jangan log data sensitif** (API key, isi lengkap PCM audio, dst) — lihat Security Audit di `V1.0_AUDIT_CHECKLIST.md`.
- Satu event = satu baris log. Jangan gabung beberapa event jadi 1 baris panjang.

## 7. Struktur Exception

- Tiap modul yang butuh exception custom mendefinisikan di file yang sama dengan class utamanya (bukan file exception terpusat) — pola: `class XError(Exception): """Kalimat singkat kapan ini terjadi."""`.
- Urutan `except` di caller: paling spesifik dulu (`GeminiResponseError`), baru yang lebih umum (`ClientError`), baru `Exception` generik kalau memang perlu catch-all (selalu dengan `logger.warning`/`exception`, tidak pernah silent).
- Tidak ada bare `except:` — selalu `except SomeException as e:` atau minimal `except Exception as e:`.

## 8. Penempatan Constants

- **Semua** angka/string konfigurasi (threshold, cooldown, model name, URL, path) masuk `config/constants.py` — **tidak ada magic number** di logic file.
- Konstanta domain-spesifik yang cuma dipakai 1 subsystem boleh didefinisikan sebagai module-level constant di file itu sendiri (`_MAX_STEP = 5` di `relationship_rules.py`) KALAU nilainya bukan sesuatu yang masuk akal untuk dikonfigurasi user — kalau iya (threshold, interval, dst yang mungkin ingin di-tweak), taruh di `config/constants.py`.
- Nama constant: `UPPER_SNAKE_CASE`. Private module-level constant: prefix `_`.

## 9. Konvensi Import

- Urutan import per file: stdlib → third-party (`google.genai`, `PySide6`, dst) → project-local (`ai.`, `behavior.`, dst) — dipisah baris kosong antar grup.
- **Tidak ada wildcard import** (`from x import *`).
- Import cuma yang dipakai — hapus import yang sudah tidak dipanggil (bagian dari Code Quality Audit v1.0).
- Cross-subsystem import HARUS sesuai Independence Policy masing-masing (lihat `ARCHITECTURE.md` / master context) — kalau sebuah subsystem butuh import dari domain yang dilarang, itu tanda desain perlu ditinjau ulang, BUKAN alasan untuk melanggar aturan.

## 10. Dataclass & Immutability

- State object (BehaviorState, EmotionState, RelationshipState, VisionContext, RoutineEvent, DecisionResult, semua `*Snapshot`) **WAJIB** `@dataclass(frozen=True)`.
- Perubahan state selalu berupa instance BARU, tidak pernah mutasi in-place.
- Default value untuk field mutable (list, dict, nested dataclass) selalu lewat `field(default_factory=...)`, tidak pernah default langsung (`= []` salah, `= field(default_factory=list)` benar).

## 11. Formatting Umum

- 4 spasi indentasi, tidak pakai tab.
- Baris maksimal ~110 karakter (fleksibel untuk docstring/string panjang).
- 1 baris kosong antar method dalam class, 2 baris kosong antar top-level class/function.
- f-string untuk interpolasi string biasa, tapi logging **selalu** pakai format loguru (`"{}"` placeholder), bukan f-string, supaya lazy evaluation & structured logging tetap jalan.

## 12. Komentar

- Komentar menjelaskan **kenapa**, bukan **apa** (kode yang menjelaskan apa).
- Komentar yang merujuk kebijakan arsitektur (mis. "TIDAK PERNAH panggil Gemini di sini — Autonomous Independence Policy") lebih disukai daripada komentar deskriptif biasa — ini pola yang sudah konsisten dipakai untuk menjaga developer/AI berikutnya tidak melanggar aturan tanpa sadar.
- Hapus komentar `# TODO` yang sudah tidak relevan; komentar `# TODO(vX.Y)` yang menunjuk milestone spesifik boleh dipertahankan kalau memang belum dikerjakan.

## 13. Prinsip yang Tidak Boleh Dilanggar (Ringkasan)

Sesuai Architecture Freeze Policy v1.0 — daftar lengkap ada di master context, tapi versi singkatnya:

- `Companion` = satu-satunya orchestrator. Gemini = satu-satunya penghasil bahasa.
- Setiap subsystem (Behavior, Vision, Routine, Initiative, Developer Tools) independen — tidak saling import kecuali lewat pola yang sudah ditetapkan (Dependency Injection eksplisit, bukan import langsung antar domain yang dilarang).
- `ContextBuilder` = satu-satunya yang merangkai ephemeral context. `PromptBuilder` = satu-satunya yang merangkai system prompt permanen. Keduanya tidak boleh saling tahu.
- Qt/PySide6 cuma boleh di `ui/`.
- **Kalau sebuah fitur baru mengharuskan merombak `Companion` atau mengubah tanggung jawab subsystem yang sudah ada, desain fitur itu perlu ditinjau ulang dulu — bukan langsung diimplementasikan.** (Prinsip pasca-v1.0 dari rekomendasi GPT.)