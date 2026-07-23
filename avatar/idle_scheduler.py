from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from avatar.blink import BlinkAnimator
from avatar.breathing import BreathingAnimator
from config.logger import logger

# (layer_name, logical_parameter, value) -> None
OnParameterUpdate = Callable[[str, str, float], Awaitable[None]]

_BREATHING_TICK_SECONDS = 0.2
_BREATHING_LOG_EVERY_N_TICKS = 25  # ~5 detik, hindari log spam sesuai requirement performance


class IdleScheduler:
    """Menjadwalkan event idle (blink, breathing) lewat asyncio task ringan.
    TIDAK ADA logic animasi di sini — cuma orkestrasi timing, delegasi nilai ke
    BlinkAnimator/BreathingAnimator. Tidak ada busy loop (semua pakai asyncio.sleep)."""

    def __init__(self, blink: BlinkAnimator, breathing: BreathingAnimator, on_update: OnParameterUpdate):
        self._blink = blink
        self._breathing = breathing
        self._on_update = on_update
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("Scheduler Started")
        self._tasks = [
            asyncio.create_task(self._blink_loop()),
            asyncio.create_task(self._breathing_loop()),
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks = []
        logger.info("Scheduler Stopped")

    async def _blink_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._blink.next_interval())
                if not self._running:
                    break
                await self._run_blink_curve()
                if self._blink.should_double_blink():
                    await asyncio.sleep(0.15)
                    await self._run_blink_curve()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Blink loop gagal, idle animation tetap lanjut tanpa blink: {}", e)

    async def _run_blink_curve(self) -> None:
        logger.info("Blink Triggered")
        for delay, value in self._blink.blink_curve():
            if delay > 0:
                await asyncio.sleep(delay)
            await self._safe_update("blink", "EyeOpen", value)

    async def _breathing_loop(self) -> None:
        logger.info("Breathing Started")
        tick = 0
        try:
            while self._running:
                value = self._breathing.current_value()
                await self._safe_update("breathing", "BreathParam", value)

                tick += 1
                if tick % _BREATHING_LOG_EVERY_N_TICKS == 0:
                    logger.info("Breathing Updated")

                await asyncio.sleep(_BREATHING_TICK_SECONDS)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Breathing loop gagal, idle animation tetap lanjut tanpa breathing: {}", e)

    async def _safe_update(self, layer_name: str, logical_parameter: str, value: float) -> None:
        try:
            await self._on_update(layer_name, logical_parameter, value)
        except Exception as e:
            logger.warning("Idle update gagal untuk layer '{}': {}", layer_name, e)