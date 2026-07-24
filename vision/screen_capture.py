from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class ScreenCapture(ABC):
    """Antarmuka ABSTRAK screen capture — platform-independent sejak awal
    (rekomendasi GPT). Kode lain (Vision) cuma kenal interface ini, tidak pernah
    tahu implementasi konkretnya pakai library apa."""

    @abstractmethod
    def capture(self) -> Image.Image:
        ...


class MssScreenCapture(ScreenCapture):
    """Implementasi konkret via library `mss` — cross-platform (Windows/Linux/
    macOS) tanpa perlu kode berbeda per OS. Kalau nanti butuh implementasi lain
    (mis. Pillow ImageGrab khusus satu platform), tinggal buat class baru yang
    implement ScreenCapture, tidak ada kode lain yang perlu berubah."""

    def __init__(self, monitor_index: int = 1):
        self._monitor_index = monitor_index

    def capture(self) -> Image.Image:
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[self._monitor_index]
            raw = sct.grab(monitor)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")