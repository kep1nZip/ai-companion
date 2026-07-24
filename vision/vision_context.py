from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_APP_PATTERN = re.compile(r"application\s*:\s*(.+)", re.IGNORECASE)
_SUMMARY_PATTERN = re.compile(r"summary\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class VisionContext:
    """Snapshot IMMUTABLE hasil analisis visual — dibuat sebagai OBJECT dulu
    (rekomendasi GPT), bukan langsung string. Pola sama persis dengan
    BehaviorState/EmotionState/RelationshipState: dataclass immutable + timestamp.
    ContextBuilder yang nanti mengubahnya jadi teks untuk Gemini."""

    summary: str
    application: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl: float = 30.0
    source: str = "screen"   # "screen" | "webcam" | "upload" — siap multimodal (rekomendasi GPT #3)

    def age_seconds(self) -> float:
        now = datetime.now(timezone.utc)
        return max(0.0, (now - self.timestamp).total_seconds())

    def is_fresh(self) -> bool:
        return self.age_seconds() <= self.ttl


def parse_vision_context(raw_text: str, source: str = "screen", ttl: float = 30.0) -> VisionContext:
    """Ubah teks natural dari Gemini Vision jadi VisionContext terstruktur.
    TIDAK PERNAH mengekspos JSON (Image Analysis Policy) — parsing berbasis
    regex sederhana atas teks natural, bukan structured output/JSON schema."""
    app_match = _APP_PATTERN.search(raw_text)
    summary_match = _SUMMARY_PATTERN.search(raw_text)

    application = app_match.group(1).strip() if app_match else None
    summary = summary_match.group(1).strip() if summary_match else raw_text.strip()

    return VisionContext(summary=summary, application=application, source=source, ttl=ttl)