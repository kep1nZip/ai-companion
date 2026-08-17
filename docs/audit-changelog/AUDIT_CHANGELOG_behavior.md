# Audit Changelog — `behavior/` (18 file)

Scope: Emotion, Relationship, Internal State (Mood/Energy/Curiosity/
Initiative), BehaviorEngine/BehaviorState — semua file di folder `behavior/`.

Status arsitektur: ✅ bersih total — nol import Gemini/Qt/Avatar/Voice, semua
Independence Policy dipatuhi, immutability konsisten, nol pelanggaran
Architecture Freeze.

---

## ✅ Selesai

### 1. Naming collision `initiative.py` (v0.9.5)
`behavior/initiative.py` (define `InitiativeState`, dimensi internal state)
vs `initiative/initiative.py` (define `Initiative`, decision engine
autonomous) — nama file identik di 2 folder beda, gampang salah asumsi.
**Di-rename** jadi `behavior/initiative_state.py`, konsisten dengan pola
`emotion_state.py`/`relationship_state.py`. Import di `internal_state.py`
sudah diupdate ke `from behavior.initiative_state import InitiativeState,
DEFAULT_INITIATIVE`.

### 4. Duplicate Persistence Boilerplate (lintas domain, digabung dengan
temuan yang sama dari `routine/`+`initiative/`)
`RelationshipCoordinator.save()/load()` dan
`InternalStateCoordinator.save()/load()` — pola upsert
(`search_memory`→`update_memory`/`save_memory`, log "Persistence
Saved"/"Loaded") diduplikasi identik, cuma beda `_PERSISTENCE_MARKER` dan
serialize/deserialize payload.

**Solusi**: file baru `database/persistence_helper.py` (netral, tidak
melanggar Independence Policy — semua domain sudah boleh import
`database.memory_manager`) berisi 2 fungsi generik:
```python
def save_by_marker(memory_manager, marker: str, content: str) -> None: ...
def load_by_marker(memory_manager, marker: str) -> Optional[str]: ...
```
`relationship.py` dan `internal_state.py` sudah diupdate — `save()`/`load()`
diringkas jadi tinggal panggil 2 fungsi ini, serialize/deserialize spesifik
domain tetap utuh. (Bagian `routine_history.py`/`initiative_history.py` ada
di changelog `vision+routine+initiative`.)

**Catatan efek samping**: `InitiativeHistory.save()` yang aslinya TIDAK
pernah log "Persistence Saved" sekarang ikut log itu (konsisten dengan 3
lainnya) — bukan bug, cuma perubahan volume log.

---

## 🔲 Direkomendasikan — belum dieksekusi

### 2. Duplicate ring buffer: `EmotionHistory`/`RelationshipHistory`/
`InternalStateHistory`
Tiga implementasi identik (`record()`/`recent()`/`clear()`, `max_size=200`,
logic `pop(0)`), cuma beda type hint. Solusi yang sudah didesain lengkap
(kodenya siap tempel, tinggal eksekusi):

```python
# behavior/_ring_buffer.py (BARU)
from __future__ import annotations
from typing import Generic, TypeVar

T = TypeVar("T")

class RingBufferHistory(Generic[T]):
    """Ring buffer in-memory generik — dasar untuk EmotionHistory/
    RelationshipHistory/InternalStateHistory."""
    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._entries: list[T] = []

    def record(self, state: T) -> None:
        self._entries.append(state)
        if len(self._entries) > self._max_size:
            self._entries.pop(0)

    def recent(self, limit: int = 20) -> list[T]:
        return list(self._entries[-limit:])

    def clear(self) -> None:
        self._entries.clear()
```
Lalu `emotion_history.py`/`relationship_history.py`/
`internal_state_history.py` masing-masing jadi subclass 3 baris:
```python
class EmotionHistory(RingBufferHistory[EmotionState]):
    """<docstring asli dipertahankan>"""
    pass
```
`internal_state_history.py` tetap pakai `TYPE_CHECKING` guard untuk
`InternalState` (circular import). Docstring masing-masing file
dipertahankan apa adanya, tidak digeneralisir ke base class. Constructor
call di `emotion.py`/`relationship.py`/`internal_state.py` (mis.
`EmotionHistory()`) TIDAK perlu berubah.

### 3. Duplicate `_matches_any()` di `emotion_analyzer.py` dan
`relationship_analyzer.py`
Fungsi 2 baris identik, didefinisikan ulang di 2 file. Belum didesain
solusi konkretnya (belum ditentukan taruh di file shared mana) — masih
perlu dibahas sebelum eksekusi.

### 5. Type hint hilang: `InternalStateCoordinator.manual_override`
```python
def manual_override(self, component: str, value) -> InternalState:
```
`value` tanpa type hint karena polymorphic (str untuk mood, int untuk
energy/curiosity/initiative). Fix: `value: str | int`. Bandingkan dengan
`RelationshipCoordinator.manual_override(self, dimension: str, value: int)`
yang sudah lengkap.

### 6. Dead/write-only data: `RelationshipState.manual_override: bool`
Field di-set `True`/`False` tapi tidak pernah dibaca di manapun (bukan di
`ContextBuilder`, bukan di `BehaviorSnapshot`). Kemungkinan disiapkan untuk
GUI Developer Panel (badge "manually overridden") — fix-nya cukup komentar
penjelas di atas field, bukan hapus:
```python
manual_override: bool = False  # belum dibaca di manapun — disiapkan untuk
                                # GUI Developer Panel (badge "manually
                                # overridden"), lihat roadmap v1.0
```

---

## ✅ Yang sudah bagus (jangan "diperbaiki" tanpa perlu)
- Magic number di `emotion_rules.py`/`relationship_rules.py`/
  `internal_state_rules.py` (`_DECAY_TARGET`, `_DECAY_RATE_PER_SECOND`, dll)
  — domain-specific dan sengaja tidak dikonfigurasi user, sesuai CODE_STYLE
  §8, bukan pelanggaran.
- Docstring hampir semua class di folder ini adalah contoh terbaik di
  seluruh project — pola "TIDAK PERNAH X" konsisten dan jelas.
