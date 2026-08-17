# Audit Changelog — `ui/` + `developer/` + `database/` (19 file)

Batch terakhir sebelum `config/`. Termasuk cross-check temuan dari batch
`avatar/`+`speech/` sebelumnya terhadap path produksi (`window.py`).

---

## ✅ Selesai

### 🔴 Konfirmasi: bug `animation_state` (dari audit `avatar/`) aktif di
produksi — sudah di-fix
`window.py` inject `avatar_manager` NYATA (bukan `None`) ke
`DeveloperService`, dan `avatar_debug.py` mengaksesnya sebagai property.
Sebelum di-fix: setiap `get_avatar()`/`get_snapshot()`/`export_markdown()`
dari GUI sungguhan selalu gagal diam-diam (dibungkus try/except, jadi tidak
crash, tapi `active_animation_layers` selalu kosong + log spam "gagal
ambil avatar snapshot"). **Sudah dikonfirmasi user file `avatar_manager.py`
sudah punya `@property` yang benar — verified fixed.**

### 🟡 `DeveloperService.get_health()` — logic menyesatkan
Field `vision`/`routine`/`initiative`/`avatar`/`gemini` sebagian besar
placeholder (`vision` selalu `True`, `routine`/`initiative` cuma cek
`self._companion is not None` bukan state subsystem beneran, `avatar` cuma
cek object ada bukan `connection_state == READY`).

**Fix — `developer/developer.py`:** tambah import `AvatarState`, ganti
`get_health()` supaya `avatar` cek `avatar_snapshot.connection_state ==
AvatarState.READY.value` (bukan hardcode string), `routine`/`initiative`
pakai hasil `self.get_routine()`/`self.get_initiative()` (build snapshot
berhasil = sehat), plus docstring baru yang menjelaskan `gemini` itu PROXY
(disamakan `behavior_ok`) — bukan live probe, karena Developer Tools
dilarang kirim request Gemini sungguhan (Read-Only Policy). Ini masih
best-effort, BUKAN 100% akurat — vision/routine/initiative "sehat" di sini
berarti "snapshot berhasil dibangun tanpa exception", bukan "lagi ada
aktivitas". Limitasi wajar, bukan bug baru.

### 🔴 Bug baru ditemukan lewat cross-check: orphan `Routine` di `main_gui.py`
```python
routine = Routine(memory_manager=None)   # dibuat, TIDAK PERNAH dipakai
```
`Companion.__init__` tidak punya parameter `routine` untuk inject instance
dari luar — `Companion` sudah bikin `Routine`-nya sendiri secara internal
(`self._routine = Routine(memory_manager=self._memory_manager) if
enable_routine else None`). Jadi ada 2 instance `Routine` sesaat: 1 orphan
(`memory_manager=None`, tidak pernah persist, tidak dipakai sama sekali),
1 lagi yang beneran jalan di dalam `Companion`. Kemungkinan sisa kode
eksploratif dari sebelum keputusan desain "Companion bikin Routine sendiri"
final. Dampak: tidak crash, tidak ada efek fungsional buruk (karena tidak
dipakai), tapi buang resource kecil + sangat membingungkan pembaca kode.

**Fix — `main_gui.py`:** hapus blok `routine = Routine(...)`, hapus import
`from routine.routine import Routine` dan `from config.constants import
ROUTINE_TIMEZONE` (keduanya jadi tidak terpakai setelah orphan dihapus).
`companion = Companion(vision=vision, performance_tracker=performance_tracker)`
tidak berubah — perilaku aplikasi 100% identik, karena Routine yang
beneran dipakai memang selalu dari dalam `Companion`.

### 🟡 Docstring class kosong/ala kadarnya di `ui/`
`ChatWorker`, `VoiceWorker`, `SpeakWorker`, `AvatarWorker` — didokumentasi
ulang mengikuti pola "TIDAK PERNAH X" yang konsisten di
`behavior/`/`vision/`/`routine/`. Contoh (`AvatarWorker`):
```python
class AvatarWorker(QThread):
    """Menjalankan event loop asyncio AvatarManager + Idle Animation di
    background thread. GUI HANYA boleh panggil request_reaction(),
    animate_lipsync(), apply_mood(), dan stop_avatar() — tidak pernah
    menyentuh AvatarManager/VTubeStudioClient langsung."""
```
Ketiga class lain (`ChatWorker`/`VoiceWorker`/`SpeakWorker`) di-update
serupa. Tidak ada logic yang berubah.

---

## 🔲 Perlu keputusan — belum dieksekusi

### `database/database.py` — file kosong total (0 baris)
Kemungkinan sisa scaffolding v0.1 sebelum semua logic pindah ke
`memory_manager.py`. Dua opsi:
- **(a) Hapus** — direkomendasikan, karena "reserved for future DB
  abstraction" tidak sesuai Architecture Freeze Policy (semua persistence
  wajib lewat method publik MemoryManager yang sudah ada; abstraksi DB
  baru = keputusan desain besar yang butuh spec baru dari GPT, bukan
  disiapkan diam-diam lewat file kosong).
- **(b) Docstring placeholder** — kalau ternyata memang ada niat spesifik
  di baliknya yang belum tercatat di context doc manapun.

**Belum diputuskan** — user belum konfirmasi mau pilih yang mana.

### Constructor `main.py` vs `main_gui.py` — sudah diverifikasi, TERNYATA
KONSISTEN (bukan temuan aktif)
`main.py`: `Companion()` (semua default). `main_gui.py`:
`Companion(vision=vision, performance_tracker=performance_tracker)`.
Keduanya sama-sama tidak override `enable_routine`/`enable_initiative`,
jadi keduanya `True`/`True` — **tidak ada inkonsistensi UX di titik ini**.
Kekhawatiran awal audit ternyata tidak terbukti; dicatat di sini biar tidak
diaudit ulang sia-sia di masa depan.

---

## 🟢 Observasi bagus — tidak perlu diubah
- `chat.py` — fallback placeholder abu-abu untuk avatar icon yang hilang,
  detail UX kecil yang sudah tepat.
- `memory_manager.py` — file paling bersih di seluruh project yang pernah
  diaudit: type hints lengkap, docstring jelas, parameterized query (aman
  dari SQL injection). Contoh terbaik untuk Security Audit.
- `performance_debug.py` — satu-satunya tempat yang eksplisit pakai
  `threading.Lock`, konsisten dengan concern Thread Safety Audit dari
  batch `avatar/`+`speech/`.
- `window.py` — urutan inisialisasi Avatar-dulu-baru-VoiceManager (biar
  `animate_lipsync` bisa di-wire) tetap konsisten sesuai keputusan v0.5.1.
  Komentar riwayat edit (`<-- Tambahan Import`, dst) masih nempel — noise
  kecil, tidak mengganggu fungsi, bisa dibersihkan di cleanup pass
  terpisah (bukan diselipkan di tengah audit fungsional).
