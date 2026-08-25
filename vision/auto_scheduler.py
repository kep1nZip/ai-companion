from __future__ import annotations

import threading
from typing import Callable, Optional

from config.logger import logger


class VisionAutoScheduler:
    """Scheduler backend MURNI untuk Auto Vision (v1.5.2 §14-15).

    TIDAK PERNAH: import Qt, tahu GUI, tahu Gemini, tahu Avatar, tahu
    Behavior, tahu Companion.chat(). Tanggung jawabnya HANYA timing,
    cancellation, dan shutdown — scheduler cuma memanggil satu
    refresh_callback (yaitu Vision.refresh_if_needed()) secara berkala.

    Scheduler tidak pernah menginstansiasi Vision/ScreenCapture/ImageAnalyzer
    sendiri (spec §15) — ia hanya menerima callback dari luar.

    Satu worker thread saja per instance (spec §48). Pakai threading.Event
    untuk interruptible wait (bukan busy-wait/polling), jadi stop() bisa
    langsung membangunkan thread yang sedang menunggu interval berikutnya
    tanpa harus menunggu penuh interval_seconds."""

    def __init__(self, refresh_callback: Callable[[], object], interval_seconds: float = 30.0):
        self._refresh_callback = refresh_callback
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()  # cegah start()/stop() bersamaan dari thread berbeda

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self.is_running():
                return  # sudah jalan — jangan buat thread kedua (spec §48: "one worker/thread at most")
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="VisionAutoScheduler",
                daemon=True,  # jaga-jaga kalau stop() lupa dipanggil, thread tidak menahan proses exit
            )
            self._thread.start()
        logger.info("Auto Vision capture started")

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=10.0)  # clean stop — lihat spec §34/§48
        logger.info("Auto Vision disabled")

    def _run(self) -> None:
        # v1.5.2 §33: capture pertama SEGERA (bukan nunggu interval dulu)
        # supaya AUTO langsung berguna. refresh_if_needed() sendiri yang
        # memutuskan reuse context fresh vs capture baru (Freshness Policy
        # §11) — scheduler tidak tahu dan tidak peduli soal itu, murni timing.
        while not self._stop_event.is_set():
            try:
                self._refresh_callback()
            except Exception as e:
                # Retry Policy §38: satu siklus gagal TIDAK BOLEH mematikan
                # scheduler secara permanen — log lalu lanjut ke interval berikutnya.
                logger.warning("Auto Vision capture cycle gagal: {}", e)

            # Interruptible wait: kalau stop() dipanggil di tengah wait, thread
            # langsung bangun alih-alih tidur penuh interval_seconds (spec §48:
            # "avoid busy waiting").
            self._stop_event.wait(self._interval_seconds)