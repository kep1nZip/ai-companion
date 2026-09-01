from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from config.logger import logger

_DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0  # konsisten dengan thread.join(timeout=10.0)
# di vision/auto_scheduler.py — bukan angka baru yang ditebak.

_SHUTDOWN_SENTINEL = object()


@dataclass(frozen=True)
class MemoryWorkerStatus:
    """Snapshot read-only (v2.1 §21) — dipakai Developer Dashboard untuk
    MENGAMATI worker, tidak pernah untuk MENGONTROLnya (tidak ada start/
    stop/pause di sini, cuma angka)."""

    pending: int
    total_completed: int
    total_failed: int
    last_success_at: Optional[str]
    last_failure_at: Optional[str]


class MemoryExtractionWorker:
    """Infrastruktur background MURNI (v2.1 Rule 4) — TIDAK tahu apa itu
    "memori", "ekstraksi", "Gemini", atau "Teacher". Satu-satunya tanggung
    jawabnya: menjalankan callable yang di-submit, satu per satu, di SATU
    background thread, tanpa pernah memblokir pemanggil submit().

    Ini BUKAN MemoryAgent/MemoryBrain/MemoryReasoner (v2.1 Rule 4) — nol
    logic ekstraksi ada di sini. Companion yang menyusun closure lengkap
    (sudah membungkus MemoryExtractor + MemoryManager dengan snapshot
    input yang immutable, lihat Companion._schedule_memory_extraction)
    lalu menyerahkannya ke sini murni sebagai "jalankan fungsi ini nanti,
    di background thread, satu per satu, berurutan".

    ## Kenapa threading.Thread(daemon=True) + queue.Queue, BUKAN
    ## concurrent.futures.ThreadPoolExecutor

    Percobaan pertama modul ini pakai ThreadPoolExecutor(max_workers=1).
    Setelah ditest (v2.1 §47 poin 16 "test application shutdown with
    pending work"), ketahuan stdlib ThreadPoolExecutor mendaftarkan
    `atexit` hook GLOBAL (`concurrent.futures.thread._python_exit`) yang
    men-join SEMUA worker thread dari SEMUA executor yang pernah dibuat di
    proses itu — hook ini tetap berjalan terlepas dari
    `executor.shutdown(wait=False)` yang sudah dipanggil eksplisit pada
    satu instance. Akibatnya: kalau ada satu task yang macet/lambat (mis.
    provider Gemini network hang) saat aplikasi ditutup, PROSES PYTHON
    ITU SENDIRI tetap menggantung sampai task itu selesai — melanggar
    v2.1 §30 ("A background task must never keep the process alive
    forever") walau `MemoryExtractionWorker.shutdown()` sendiri sudah
    return tepat waktu (dikonfirmasi lewat test manual: subprocess yang
    membungkus shutdown(timeout=1.0) dengan task tidur 8 detik tetap makan
    waktu total ~8 detik, bukan ~1 detik).

    threading.Thread(daemon=True) TIDAK punya masalah ini — daemon thread
    tidak pernah ditunggu interpreter saat proses keluar, itu sebabnya
    vision/auto_scheduler.py (Vision Auto Scheduler, backend
    UI-independent yang sudah ada sejak v1.5.2) sudah lebih dulu memilih
    pola ini secara eksplisit ("daemon=True — jaga-jaga kalau stop() lupa
    dipanggil, thread tidak menahan proses exit"). Modul ini mengikuti
    pola yang SAMA persis, bukan menciptakan mekanisme baru (v2.1 §15/§16:
    "Do not introduce a new concurrency abstraction if an existing one can
    safely be reused").

    Satu thread pekerja saja (bukan pool) — task selalu jalan berurutan,
    tidak pernah overlap, jadi kita tidak perlu membuktikan
    MemoryExtractor/MemoryManager aman dipanggil dari BEBERAPA thread
    SEKALIGUS (v2.1 §7) — cukup aman dipanggil dari SATU thread lain yang
    bukan main/GUI thread (MemoryManager membuka koneksi SQLite baru tiap
    panggilan, tidak pernah menyimpan connection sebagai state bersama —
    lihat database/memory_manager.py).

    Qt TIDAK dipakai di sini (v2.1 Stop Condition #10) — ai/ adalah
    backend UI-independent (lihat docstring Companion), murni stdlib
    threading + queue."""

    def __init__(self):
        self._queue: "queue.Queue[object]" = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._total_completed = 0
        self._total_failed = 0
        self._last_success_at: Optional[str] = None
        self._last_failure_at: Optional[str] = None
        self._is_shutdown = False
        self._thread = threading.Thread(
            target=self._run,
            name="MemoryExtractionWorker",
            daemon=True,  # v2.1 §30 — lihat catatan panjang di docstring kelas ini
        )
        self._thread.start()

    def submit(self, task: Callable[[], None]) -> None:
        """Jadwalkan `task` untuk jalan di background — TIDAK PERNAH
        menunggu hasilnya (v2.1 §3: "schedule ... RETURN immediately").
        `queue.Queue.put()` sendiri tidak pernah memblokir untuk queue
        tak terbatas seperti ini, jadi submit() sungguh-sungguh seketika.

        `task` idealnya sudah menangani exception spesifiknya sendiri
        (closure yang disusun Companion memang begitu) — try/except di
        `_run()` di bawah ini murni jaring pengaman KEDUA (v2.1 §22/§31
        Error Isolation), supaya satu task gagal TIDAK PERNAH mematikan
        worker untuk task berikutnya, dan TIDAK PERNAH bocor ke pemanggil
        chat() yang sudah lama return duluan."""
        with self._lock:
            if self._is_shutdown:
                logger.warning("Memory extraction worker sudah shutdown, task dibatalkan.")
                return
            self._pending += 1

        logger.info("Memory extraction queued")
        self._queue.put(task)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SHUTDOWN_SENTINEL:
                break

            try:
                logger.info("Memory extraction started")
                item()
                with self._lock:
                    self._total_completed += 1
                    self._last_success_at = datetime.now(timezone.utc).isoformat()
                logger.info("Memory extraction completed")
            except Exception as e:
                with self._lock:
                    self._total_failed += 1
                    self._last_failure_at = datetime.now(timezone.utc).isoformat()
                # v2.1 §32: tidak melempar traceback teknis ke user — ini
                # background thread, tidak ada user yang menunggu di sisi
                # lain. logger.warning (bukan .exception) supaya konsisten
                # dengan gaya logging proyek yang sudah ada di seluruh
                # ai/*.py, dan config/logger.py sudah diaset diagnose=False
                # (tidak membocorkan local variable/API key di traceback).
                logger.warning("Memory extraction failed: {}", e)
            finally:
                with self._lock:
                    self._pending = max(0, self._pending - 1)

    def status(self) -> MemoryWorkerStatus:
        with self._lock:
            return MemoryWorkerStatus(
                pending=self._pending,
                total_completed=self._total_completed,
                total_failed=self._total_failed,
                last_success_at=self._last_success_at,
                last_failure_at=self._last_failure_at,
            )

    def shutdown(self, wait: bool = True, timeout: float = _DEFAULT_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """v2.1 §29/§30: task yang SEDANG jalan dibiarkan selesai kalau
        memungkinkan (supaya tidak ada tulisan SQLite yang terputus di
        tengah) — TAPI shutdown TIDAK BOLEH menggantung tanpa batas.
        `thread.join(timeout=...)` di sini yang memberi batas itu, persis
        pola VisionAutoScheduler.stop() yang sudah ada. Kalau task yang
        sedang jalan belum selesai setelah `timeout` detik (mis. provider
        Gemini network hang), shutdown() tetap return apa adanya — thread
        daemon yang tersisa TIDAK PERNAH menahan proses Python keluar
        (lihat catatan panjang di docstring kelas ini)."""
        with self._lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True

        logger.info("Memory extraction worker shutting down")
        self._queue.put(_SHUTDOWN_SENTINEL)

        if wait:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "Memory extraction worker: task masih berjalan setelah {}s, "
                    "shutdown dilanjutkan tanpa menunggu lebih lama (thread daemon, "
                    "tidak akan menahan proses keluar).",
                    timeout,
                )
