from __future__ import annotations

import re
from typing import Optional

from vision.vision_context import VisionContext

# Satu-satunya sumber keyword untuk deteksi "Teacher sedang meeting/presentasi"
# dan "Teacher sedang fokus kerja" dari VisionContext — dipakai bareng oleh
# routine/routine_rules.py dan initiative/initiative_rules.py supaya kedua
# subsystem tidak pernah berbeda pendapat soal kapan harus diam.
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
    """True kalau Vision mendeteksi Teacher sedang meeting/rapat/presentasi/call."""
    if vision_context is None:
        return False
    text = _text_of(vision_context)
    return any(re.search(p, text) for p in _PRESENTATION_KEYWORDS)


def matches_focused_work(vision_context: Optional[VisionContext]) -> bool:
    """True kalau Vision mendeteksi Teacher sedang coding/menulis email/mengetik intensif."""
    if vision_context is None:
        return False
    text = _text_of(vision_context)
    return any(re.search(p, text) for p in _FOCUSED_WORK_KEYWORDS)