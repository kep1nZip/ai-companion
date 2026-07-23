from __future__ import annotations

import re
from enum import Enum


class Expression(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    EMBARRASSED = "embarrassed"
    EXCITED = "excited"
    THINKING = "thinking"
    SLEEPY = "sleepy"
    WORRIED = "worried"


_HALO_PATTERN = re.compile(r"\(([^)]*halo[^)]*)\)", re.IGNORECASE)

_HALO_TO_EXPRESSION: dict[str, Expression] = {
    "blue halo": Expression.NEUTRAL,
    "pink heart halo": Expression.HAPPY,
    "green glowing halo": Expression.EXCITED,
    "light blue flake halo": Expression.EMBARRASSED,
    "dark blue dripping halo": Expression.SAD,
    "red irregular halo": Expression.ANGRY,
}


class HaloMapper:
    """Memetakan deskripsi halo di teks balasan Arona -> Logical Expression.
    Tidak tahu VTube Studio, tidak tahu parameter model apa pun."""

    def map(self, reply_text: str) -> Expression:
        match = _HALO_PATTERN.search(reply_text)
        if not match:
            return Expression.NEUTRAL

        halo_text = match.group(1).strip().lower()
        return _HALO_TO_EXPRESSION.get(halo_text, Expression.NEUTRAL)