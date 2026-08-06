from __future__ import annotations

import re


def matches_any(patterns: list[str], text: str) -> bool:
    """Return True jika text cocok dengan salah satu regex."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)