from __future__ import annotations

import asyncio

from PySide6.QtCore import QThread, Signal

from avatar.avatar_manager import AvatarManager, AvatarState
from avatar.lipsync import LipSyncCoordinator
from avatar.audio_analyzer import AudioAnalyzer
from avatar.mouth_mapper import MouthMapper
from avatar.idle import IdleCoordinator
from config.constants import (
    LIPSYNC_WINDOW_MS, LIPSYNC_SILENCE_THRESHOLD, LIPSYNC_GAIN,
    IDLE_BLINK_MIN_INTERVAL, IDLE_BLINK_MAX_INTERVAL, IDLE_BLINK_DURATION,
    IDLE_DOUBLE_BLINK_CHANCE, IDLE_BREATHING_CYCLE_SECONDS, IDLE_BREATHING_AMPLITUDE,
)
from avatar.blink import BlinkAnimator
from avatar.breathing import BreathingAnimator


class AvatarWorker(QThread):
    """Menjalankan event loop asyncio AvatarManager + Idle Animation di background thread.
    GUI hanya boleh panggil request_reaction(), animate_lipsync(), dan stop_avatar()."""

    state_changed = Signal(str)

    def __init__(self, avatar_manager: AvatarManager):
        super().__init__()
        self._avatar_manager = avatar_manager
        self._avatar_manager.set_state_listener(self._emit_state)
        self._loop: asyncio.AbstractEventLoop | None = None

        self._lipsync = LipSyncCoordinator(
            audio_analyzer=AudioAnalyzer(window_ms=LIPSYNC_WINDOW_MS),
            mouth_mapper=MouthMapper(silence_threshold=LIPSYNC_SILENCE_THRESHOLD, gain=LIPSYNC_GAIN),
            on_mouth_update=self._update_mouth,
        )

        self._idle = IdleCoordinator(
            on_update=self._update_idle_parameter,
            blink=BlinkAnimator(
                min_interval=IDLE_BLINK_MIN_INTERVAL,
                max_interval=IDLE_BLINK_MAX_INTERVAL,
                blink_duration=IDLE_BLINK_DURATION,
                double_blink_chance=IDLE_DOUBLE_BLINK_CHANCE,
            ),
            breathing=BreathingAnimator(
                cycle_seconds=IDLE_BREATHING_CYCLE_SECONDS,
                amplitude=IDLE_BREATHING_AMPLITUDE,
            ),
        )

    def _emit_state(self, state: AvatarState) -> None:
        self.state_changed.emit(state.value)

    async def _update_mouth(self, value: float) -> None:
        await self._avatar_manager.update_parameter_layer("lipsync", "MouthOpen", value)

    async def _update_idle_parameter(self, layer_name: str, logical_parameter: str, value: float) -> None:
        await self._avatar_manager.update_parameter_layer(layer_name, logical_parameter, value)

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_all())
        finally:
            self._loop.close()

    async def _run_all(self) -> None:
        await self._idle.start()
        try:
            await self._avatar_manager.run_forever()
        finally:
            await self._idle.stop()

    def request_reaction(self, reply_text: str) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._avatar_manager.react_to_reply(reply_text), self._loop
        )

    def animate_lipsync(self, pcm_data: bytes, samplerate: int) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._lipsync.animate(pcm_data, samplerate), self._loop
        )

    def stop_avatar(self) -> None:
        self._avatar_manager.stop()
        self.wait(3000)

    async def _apply_mood_async(self, mood_name: str) -> None:
        self._idle.apply_mood(mood_name)

    def apply_mood(self, mood_name: str) -> None:
        """Dipanggil dari GUI thread. Diteruskan lewat event loop asyncio yang
        sama dengan idle scheduler, konsisten dengan pola request_reaction()/
        animate_lipsync() yang sudah ada."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._apply_mood_async(mood_name), self._loop)