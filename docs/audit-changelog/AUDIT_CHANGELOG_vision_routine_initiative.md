# Audit Changelog — `vision/` + `routine/` + `initiative/` (16 file)

Status arsitektur: ✅ bersih — nol pelanggaran Independence Policy antar 3
domain ini, urutan dependency benar (`initiative` boleh tahu `routine`+
`vision`, `routine` boleh tahu `vision`, `vision` tidak tahu keduanya).

---

## ✅ Selesai

### Inkonsistensi Exception & Konstruksi Request Gemini (`vision/image_analyzer.py`)
- `vision/` tidak punya domain exception sendiri (beda pola dari
  `GeminiResponseError`/`CompanionError`) → ditambah `VisionAnalysisError`.
- `contents` mencampur `Part` dengan string mentah → dibungkus konsisten
  jadi `types.Content(role="user", parts=[...])` seperti `gemini.py`/
  `memory_extractor.py`.

File final:
```python
from __future__ import annotations

import io

from PIL import Image
from google import genai
from google.genai import types

from config.logger import logger

_VISION_PROMPT = (
    "Describe what is currently visible in this image, in natural language, "
    "in Indonesian. On the first line, write 'Application: ' followed by the "
    "name of the active application/window if identifiable (or 'Unknown' if not). "
    "Then on the following lines, write 'Summary: ' followed by a short natural "
    "description of what appears to be happening."
)


class VisionAnalysisError(Exception):
    """Terjadi saat Gemini Vision mengembalikan respons kosong/tidak valid —
    pola sama dengan GeminiResponseError (gemini.py) dan CompanionError
    (companion.py), sesuai CODE_STYLE §7."""


class ImageAnalyzer:
    """Cuma mengirim gambar ke Gemini Vision dan menerima deskripsi natural
    language. TIDAK membangun prompt akhir, TIDAK tahu behavior/memory/GUI."""

    def __init__(self, api_key: str, model_name: str):
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def analyze(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    types.Part(text=_VISION_PROMPT),
                ],
            )
        ]

        logger.info("Vision Request")
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
        )
        logger.info("Vision Response")

        text = response.text
        if not text:
            raise VisionAnalysisError("Gemini Vision mengembalikan respons kosong.")
        return text
```
Pemanggil (`vision.py`, `except Exception` generik) tidak perlu diubah.

### Observasi minor: lazy `import mss` (`vision/screen_capture.py`)
Bukan bug — ditambah komentar penjelas niatnya:
```python
def capture(self) -> Image.Image:
    import mss  # lazy import: dependency ini cuma wajib kalau implementasi ini yang dipakai

    with mss.mss() as sct:
        ...
```

### Duplicate Persistence Boilerplate — bagian `routine_history.py` &
`initiative_history.py`
Sama seperti temuan di `behavior/` (lihat `AUDIT_CHANGELOG_behavior.md` #4),
memakai `database/persistence_helper.py` (`save_by_marker`/`load_by_marker`).
`RoutineHistory.save()/load()` dan `InitiativeHistory.save()/load()` sudah
diringkas — parsing payload (dict event_type→isoformat untuk Routine, list
isoformat untuk Initiative) tetap inline di masing-masing file karena tidak
ada fungsi `_serialize`/`_deserialize` terpisah, beda dari pola
Relationship/InternalState.

**Catatan bug yang sempat kejadian & sudah diperbaiki**: saat rename
`behavior/initiative.py` → `behavior/initiative_state.py`, sempat ada baris
import salah tertulis balik jadi `from behavior.initiative import ...` di
`internal_state.py` — sudah dikonfirmasi diperbaiki jadi
`from behavior.initiative_state import ...`.

---

## 🔲 Direkomendasikan — belum dikonfirmasi eksekusi

### Suppression Keyword List Terduplikasi & Divergen (`routine_rules.py` vs
`initiative_rules.py`) 🔴 paling penting
Dua domain punya keyword list sendiri-sendiri untuk deteksi "Teacher lagi
meeting/coding" dari `VisionContext.summary`, dan sudah tidak sinkron
(`initiative_rules.py` ketinggalan `"presentation"`/`"email"`, tapi punya
`"debugging"` yang tidak ada di `routine_rules.py`).

**Solusi yang sudah didesain lengkap** (siap tempel): file baru
`vision/vision_signals.py`, pure function baca `VisionContext`, tidak tahu
Routine/Initiative sama sekali (searah, aman terhadap dependency order):
```python
from __future__ import annotations

import re
from typing import Optional

from vision.vision_context import VisionContext

_PRESENTATION_KEYWORDS = [
    r"\bmeeting\b", r"\brapat\b", r"\bpresentasi\b", r"\bpresentation\b",
    r"\bcall\b", r"\bzoom\b",
]
_FOCUSED_WORK_KEYWORDS = [
    r"\bcoding\b", r"\bdebugging\b", r"\bmenulis kode\b", r"\bmengetik\b", r"\bemail\b",
]

def _text_of(vision_context: VisionContext) -> str:
    return f"{vision_context.application or ''} {vision_context.summary}".lower()

def matches_presentation(vision_context: Optional[VisionContext]) -> bool:
    if vision_context is None:
        return False
    return any(re.search(p, _text_of(vision_context)) for p in _PRESENTATION_KEYWORDS)

def matches_focused_work(vision_context: Optional[VisionContext]) -> bool:
    if vision_context is None:
        return False
    return any(re.search(p, _text_of(vision_context)) for p in _FOCUSED_WORK_KEYWORDS)
```
`routine_rules.py.suppression_level()` dan `initiative_rules.py.
check_suppression()` diupdate untuk memanggil 2 fungsi ini, keyword list dan
`import re` lokal di kedua file dihapus. **Docstring `check_suppression()`
TETAP dipertahankan apa adanya** (isinya soal hard-override behavior dan
alasan `is_voice_active`/`is_actively_typing` berupa boolean — tidak
menyinggung keyword Vision sama sekali, jadi tidak jadi basi).

**Efek samping behavior nyata (union dari 2 list lama)**:
- Initiative ikut suppressed kalau Teacher lagi nulis **email** (sebelumnya
  tidak).
- Initiative ikut suppressed kalau Teacher **mengetik** secara umum, bukan
  cuma coding.
- Routine ikut suppress non-casual kalau Vision deteksi **debugging**.
- `"presentation"` (Inggris) sekarang juga bikin Initiative suppressed.

### Type Hint Hilang: `Initiative.evaluate()`
```python
def evaluate(self, *args, **kwargs) -> DecisionResult:
    """Alias eksplisit sesuai Public API spec — sama seperti update()."""
    return self.update(*args, **kwargs)
```
Ganti jadi eksplisit sama persis signature `update()`:
```python
def evaluate(
    self,
    behavior_state: BehaviorState,
    vision_context: Optional[VisionContext] = None,
    routine_event: Optional[RoutineEvent] = None,
    is_voice_active: bool = False,
    is_actively_typing: bool = False,
) -> DecisionResult:
    """Alias eksplisit sesuai Public API spec — sama seperti update()."""
    return self.update(
        behavior_state, vision_context, routine_event, is_voice_active, is_actively_typing,
    )
```
Tidak ada import baru dibutuhkan.

---

## 🟢 Observasi — bukan bug, cuma catatan (tidak perlu eksekusi kode)
- `EventPriority.CRITICAL` didefinisikan tapi tidak pernah dipakai di
  `_PRIORITY` dict manapun — cabang `SuppressionLevel.ALL_NON_CRITICAL` di
  `is_suppressed()` efeknya selalu total karena belum ada event CRITICAL.
  Infrastruktur sudah siap, cuma belum ada pemakainya. **Sengaja tidak
  diubah** — menambah event baru = perubahan scope, di luar Architecture
  Freeze Policy kalau tidak diminta eksplisit. Cukup dicatat di context doc
  biar tidak dikira dead code di audit berikutnya.
