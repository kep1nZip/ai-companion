from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from vision.vision_context import VisionContext


@dataclass(frozen=True)
class VisionSnapshot:
    active: bool
    summary: Optional[str]
    application: Optional[str]
    captured_at: Optional[str]
    age_seconds: Optional[float]
    ttl: Optional[float]
    is_fresh: Optional[bool]
    mode: Optional[str]  # v1.7 §13: "off" | "manual" | "auto" | "unknown" — dari Companion.get_vision_mode()
    provider: Optional[str] = None  # v2.3 §18: "local" | "gemini" | "unknown" — dari Companion.get_vision_provider_name()


def build_vision_snapshot(context: Optional[VisionContext], mode: Optional[str] = None,
                           provider: Optional[str] = None) -> VisionSnapshot:
    if context is None:
        return VisionSnapshot(
            active=False, summary=None, application=None,
            captured_at=None, age_seconds=None, ttl=None, is_fresh=None,
            mode=mode, provider=provider,
        )
    return VisionSnapshot(
        active=True,
        summary=context.summary,
        application=context.application,
        captured_at=context.timestamp.strftime("%H:%M:%S"),
        age_seconds=context.age_seconds(),
        ttl=context.ttl,
        is_fresh=context.is_fresh(),
        mode=mode,
        provider=provider,
    )