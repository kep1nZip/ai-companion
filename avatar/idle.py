from __future__ import annotations

from typing import Optional

from avatar.blink import BlinkAnimator
from avatar.breathing import BreathingAnimator
from avatar.idle_scheduler import IdleScheduler, OnParameterUpdate
from config.logger import logger

_MOOD_BLINK_TIMING: dict[str, tuple[float, float, float]] = {
    # mood: (min_interval, max_interval, blink_duration)
    "sleepy": (2.0, 4.0, 0.35),    # lebih sering + kedipan lebih lama (spec: Sleepy -> Long Blink)
    "cheerful": (4.0, 7.0, 0.12),
    "lonely": (5.0, 10.0, 0.18),
}
_DEFAULT_BLINK_TIMING = (4.0, 9.0, 0.15)

_MOOD_BREATHING_CYCLE: dict[str, float] = {
    "cheerful": 2.5,   # napas lebih cepat (spec: Cheerful -> Faster Breathing)
    "sleepy": 5.5,
    "calm": 4.0,
    "relaxed": 4.5,
}
_DEFAULT_BREATHING_CYCLE = 4.0


class IdleCoordinator:
    def __init__(
        self,
        on_update: OnParameterUpdate,
        blink: Optional[BlinkAnimator] = None,
        breathing: Optional[BreathingAnimator] = None,
    ):
        self._blink = blink or BlinkAnimator()
        self._breathing = breathing or BreathingAnimator()
        self._scheduler = IdleScheduler(self._blink, self._breathing, on_update)

    async def start(self) -> None:
        logger.info("Idle Started")
        await self._scheduler.start()

    async def stop(self) -> None:
        await self._scheduler.stop()
        logger.info("Idle Stopped")

    def apply_mood(self, mood_name: Optional[str]) -> None:
        """Satu-satunya titik yang boleh menerima Mood dari luar (sesuai spec
        v0.6.5). Mengubah TIMING blink & breathing, bukan menghasilkan emosi baru —
        Idle Animation cuma bereaksi, tidak pernah menentukan behavior."""
        if mood_name is None:
            return

        min_i, max_i, duration = _MOOD_BLINK_TIMING.get(mood_name, _DEFAULT_BLINK_TIMING)
        self._blink.set_timing(min_i, max_i)
        self._blink.set_duration(duration)

        cycle = _MOOD_BREATHING_CYCLE.get(mood_name, _DEFAULT_BREATHING_CYCLE)
        self._breathing.set_cycle_seconds(cycle)

        logger.info("Idle timing diperbarui untuk mood '{}'", mood_name)