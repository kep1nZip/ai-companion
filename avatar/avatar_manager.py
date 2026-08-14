from __future__ import annotations

import asyncio
from enum import Enum
from typing import Callable, Optional

from avatar.vtube import VTubeStudioClient
from avatar.expression import HaloMapper
from avatar.parameter_mapper import ParameterMapper
from config.logger import logger

from avatar.animation_state import AnimationState


class AvatarState(Enum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    AUTHENTICATED = "Authenticated"
    READY = "Ready"
    BUSY = "Busy"


class AvatarManager:
    """Koordinator avatar. Menerima balasan Arona, memetakannya lewat HaloMapper +
    ParameterMapper, lalu memicu VTube Studio lewat adapter. Tidak ada websocket di sini."""

    def __init__(
        self,
        vtube_client: VTubeStudioClient,
        halo_mapper: HaloMapper,
        parameter_mapper: ParameterMapper,
        reconnect_interval: float = 5.0,
        on_state_change: Optional[Callable[["AvatarState"], None]] = None,
    ):
        self._client = vtube_client
        self._halo_mapper = halo_mapper
        self._parameter_mapper = parameter_mapper
        self._reconnect_interval = reconnect_interval
        self._on_state_change = on_state_change
        self._state = AvatarState.DISCONNECTED
        self._should_run = False
        self._parameter_layers: dict[str, float] = {}
        
    @property
    def state(self) -> AvatarState:
        return self._state

    @property
    def animation_state(self) -> AnimationState:
        """Snapshot read-only layer animasi yang sedang aktif — dibangun dari
        self._parameter_layers yang sudah ada sejak v0.5.1, tidak ada state baru."""
        return AnimationState(active_layers=frozenset(self._parameter_layers.keys()))

    def set_state_listener(self, callback: Callable[["AvatarState"], None]) -> None:
        self._on_state_change = callback

    def _set_state(self, state: AvatarState) -> None:
        self._state = state
        logger.info("Avatar state -> {}", state.name)
        if self._on_state_change:
            self._on_state_change(state)

    async def run_forever(self) -> None:
        """Loop koneksi + auto-reconnect. Jalankan sebagai satu task asyncio
        di background thread terpisah dari GUI."""
        self._should_run = True

        while self._should_run:
            try:
                self._set_state(AvatarState.CONNECTING)
                await self._client.connect()
                await self._client.authenticate()
                self._set_state(AvatarState.READY)

                while self._should_run:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.warning("VTube Studio tidak terjangkau / terputus: {}", e)
                self._set_state(AvatarState.DISCONNECTED)
                await self._client.close()

                if not self._should_run:
                    break

                await asyncio.sleep(self._reconnect_interval)

    def stop(self) -> None:
        self._should_run = False

    async def react_to_reply(self, reply_text: str) -> None:
        """Dipanggil SETELAH Companion menghasilkan balasan. Avatar tidak pernah
        memengaruhi logika AI — cuma bereaksi terhadap hasilnya."""
        if self._state != AvatarState.READY:
            logger.info("Avatar belum siap ({}), reaksi dilewati.", self._state.name)
            return

        expression = self._halo_mapper.map(reply_text)
        hotkey = self._parameter_mapper.get_hotkey(expression)

        if not hotkey:
            logger.info("Tidak ada hotkey untuk expression '{}', dilewati.", expression.value)
            return

        self._set_state(AvatarState.BUSY)
        try:
            await self._client.trigger_hotkey(hotkey)
        except Exception as e:
            logger.warning("Gagal memicu ekspresi avatar: {}", e)
        finally:
            self._set_state(AvatarState.READY)

    async def update_parameter_layer(self, layer_name: str, logical_parameter: str, value: float) -> None:
        """Dipanggil oleh layer animasi manapun (Lip Sync sekarang; nanti Eye Blink/Breathing
        di v0.5.2). AvatarManager yang bertanggung jawab menggabungkan seluruh layer aktif
        sebelum kirim ke VTube Studio, supaya satu layer tidak menimpa layer lain begitu saja.
        Catatan ekstensi masa depan: implementasi saat ini set langsung 1 nilai per parameter_id.
        Kalau nanti ada 2 layer berbeda menargetkan parameter_id yang SAMA, logic di sini perlu
        digabung (misal weighted sum) alih-alih overwrite — belum relevan selama tiap layer
        (mouth, eye, breathing) punya parameter_id masing-masing yang berbeda."""
        if self._state not in (AvatarState.READY, AvatarState.BUSY):
            return

        parameter_id = self._parameter_mapper.get_parameter_id(logical_parameter)
        if not parameter_id:
            logger.info("Tidak ada parameter VTS untuk '{}', dilewati.", logical_parameter)
            return

        self._parameter_layers[layer_name] = value
        try:
            await self._client.set_parameter(parameter_id, value)
        except Exception as e:
            logger.warning("Gagal update parameter avatar [{}]: {}", logical_parameter, e)