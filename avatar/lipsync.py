from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from avatar.audio_analyzer import AudioAnalyzer
from avatar.mouth_mapper import MouthMapper
from config.logger import logger


class LipSyncCoordinator:
    """Koordinator lip sync. Menerima audio, minta amplitude ke AudioAnalyzer, petakan
    lewat MouthMapper, lalu update AvatarManager lewat callback. TIDAK PERNAH memanggil
    VTubeStudioClient secara langsung — itu domain AvatarManager."""

    def __init__(
        self,
        audio_analyzer: AudioAnalyzer,
        mouth_mapper: MouthMapper,
        on_mouth_update: Callable[[float], Awaitable[None]],
    ):
        self._analyzer = audio_analyzer
        self._mapper = mouth_mapper
        self._on_mouth_update = on_mouth_update

    async def animate(self, pcm_data: bytes, samplerate: int) -> None:
        logger.info("Lip Sync Started")

        try:
            amplitudes, window_seconds = self._analyzer.analyze(pcm_data, samplerate)
        except Exception as e:
            logger.warning("Lip Sync analysis failed, avatar mouth stays idle: {}", e)
            return

        try:
            for amplitude in amplitudes:
                mouth_value = self._mapper.map(amplitude)
                await self._on_mouth_update(mouth_value)
                await asyncio.sleep(window_seconds)
        except Exception as e:
            logger.warning("Lip Sync loop failed: {}", e)
        finally:
            try:
                await self._on_mouth_update(0.0)  # tutup mulut di akhir
            except Exception:
                pass
            logger.info("Lip Sync Finished")