# Audit Changelog — `avatar/` + `speech/` (17 file)

Fokus audit: Thread Safety (sesuai catatan di V1.0_AUDIT_CHECKLIST). Status
arsitektur umum: bersih (avatar/speech tetap tidak saling kenal Behavior/
Gemini/GUI di luar kontrak yang sudah ada).

---

## ✅ Selesai

### 🔴 BUG NYATA — `AvatarManager.animation_state` kehilangan `@property`
`avatar/avatar_manager.py`:
```python
def animation_state(self) -> AnimationState:   # ❌ tidak ada @property
```
Dampak nyata: `developer/avatar_debug.py` (dari audit v0.9.5) manggilnya
sebagai property (`avatar_manager.animation_state.active_layers`), jadi
tanpa decorator ini bakal `AttributeError: 'method' object has no attribute
'active_layers'` setiap kali dipanggil dengan `avatar_manager` aktif (GUI
sungguhan) — lolos test manual kemarin karena
`test_developer_snapshot.py` pakai `avatar_manager=None`.

**Fix (1 baris):**
```python
@property
def animation_state(self) -> AnimationState:
    """Snapshot read-only layer animasi yang sedang aktif — dibangun dari
    self._parameter_layers yang sudah ada sejak v0.5.1, tidak ada state baru."""
    return AnimationState(active_layers=frozenset(self._parameter_layers.keys()))
```
Perlu di-grep dulu (`grep -rn "animation_state"`) untuk pastiin tidak ada
pemanggil lain yang treat ini sebagai method biasa (pakai kurung `()`) —
berdasarkan file yang diaudit, cuma `avatar_debug.py` yang manggil, dan
sudah treat sebagai property.

### 🔴 Concurrency — `VTubeStudioClient._send_request()` tidak thread/task-safe
`requestID` di-generate tapi tidak pernah dicocokkan dengan response;
`send()`→`recv()` bisa saling interleave antar 3 sumber pemanggil konkuren
(`IdleScheduler` breathing/blink loop, `LipSyncCoordinator`,
`AvatarManager.react_to_reply()`) yang jalan di event loop asyncio yang
sama — bisa bikin coroutine A menerima response milik coroutine B. Efek
halus (parameter avatar kadang keliru sesaat), bukan crash — makanya belum
pernah kelihatan sebagai bug jelas.

**Fix — `avatar/vtube.py`:** tambah `import asyncio` + `self._send_lock =
asyncio.Lock()` di `__init__`, bungkus body `_send_request()` dengan
`async with self._send_lock:`. Semua request (termasuk `connect()`/
`authenticate()`) otomatis ikut terserialisasi karena semuanya lewat
`_send_request()` yang sama — aman, tidak deadlock, karena tidak ada
panggilan nested/konkuren ke lock yang sama.

**Catatan verifikasi**: race condition ini probabilistic, tidak bisa
dipastikan 100% hilang dari 1x testing manual singkat — cukup jalankan app
dengan idle animation aktif + chat (biar lip sync ikut jalan) beberapa
menit, pastikan tidak ada parameter avatar yang kelihatan "salah sebentar"
dan tidak ada regresi/lag baru.

### 🟡 Thread Safety — `Recorder._frames` tanpa lock
`_frames` ditulis dari audio callback thread milik `sounddevice`, dibaca/
direset dari GUI/worker thread saat `stop()`. Race window sempit (biasanya
`stream.stop()` blocking sampai callback thread beres), tapi worth
dibereskan permanen untuk Thread Safety Audit resmi.

**Fix — `speech/recorder.py`:** tambah `import threading` +
`self._lock = threading.Lock()` di `__init__`. `_on_audio_chunk()` bungkus
`self._frames.append(...)` dengan `with self._lock:`. `start()` reset
`self._frames = []` juga di dalam lock. `stop()` ambil referensi
`frames = self._frames` + reset `self._frames = []` DI DALAM lock (critical
section sesingkat mungkin — cuma swap referensi), baru `np.concatenate()`
di LUAR lock karena `frames` lokal sudah "milik" `stop()` sepenuhnya.

Primitive `threading.Lock` (bukan `asyncio.Lock`) dipakai karena ini murni
antar-thread OS (`sounddevice` callback thread), beda kasus dari
`VTubeStudioClient` yang semuanya coroutine di 1 event loop.

### 🟢 Docstring hilang: `IdleCoordinator`
`avatar/idle.py` — satu-satunya class di folder ini tanpa docstring.
```python
class IdleCoordinator:
    """Koordinator idle animation (blink + breathing). Satu-satunya titik yang
    boleh menerima Mood dari luar (apply_mood, v0.6.5) dan satu-satunya yang
    tahu IdleScheduler — modul lain (AvatarManager) cuma tahu class ini lewat
    start()/stop()/apply_mood()."""
```

---

## 🟢 Observasi — sengaja TIDAK dieksekusi
`expression.py` filename tidak ikuti pola `_state.py` yang dipakai
`behavior/` untuk enum serupa (`Expression` enum ada di `expression.py`,
bukan `expression_state.py`). **Sengaja dibiarkan** — beda dari kasus
`behavior/initiative.py` (yang punya alasan kuat: naming collision antar 2
folder beda konsep), di sini rename cuma demi kosmetik dan risikonya
(breaking semua import `from avatar.expression import ...` di tempat lain)
tidak sepadan manfaatnya. Ini pola v0.5 yang sudah lama establish — jangan
diubah tanpa alasan struktural yang kuat.
