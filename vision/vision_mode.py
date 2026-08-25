from __future__ import annotations

from enum import Enum


class VisionMode(Enum):
    """Tiga mode Vision (v1.5.2). Enum dipakai, BUKAN string bebas (spec §5),
    supaya transisi mode tervalidasi di level tipe, bukan runtime typo.

    OFF    -> tidak ada capture, tidak ada scheduler, get_context() selalu None.
    MANUAL -> tidak ada scheduler, capture hanya lewat Capture Now (refresh()).
    AUTO   -> scheduler aktif (refresh_if_needed() berkala), Capture Now tetap ada.
    """

    OFF = "off"
    MANUAL = "manual"
    AUTO = "auto"