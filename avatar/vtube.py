from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

import websockets

from config.logger import logger


class VTubeStudioError(Exception):
    """Error umum komunikasi dengan VTube Studio."""


class VTubeStudioClient:
    """Implementasi murni protokol VTube Studio API. Tidak tahu logical expression,
    tidak tahu Companion, tidak ada logic lain selain koneksi & request/response."""

    API_NAME = "VTubeStudioPublicAPI"
    API_VERSION = "1.0"

    def __init__(self, url: str, plugin_name: str, plugin_developer: str, token_path: Path):
        self._url = url
        self._plugin_name = plugin_name
        self._plugin_developer = plugin_developer
        self._token_path = token_path
        self._ws = None
        self._send_lock = asyncio.Lock()

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url, ping_interval=None)
        logger.info("Terhubung ke VTube Studio di {}", self._url)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
            logger.info("Koneksi VTube Studio ditutup.")

    async def authenticate(self) -> None:
        if self._ws is None:
            raise VTubeStudioError("Belum terhubung ke VTube Studio.")

        token = self._load_token()

        if not token:
            token = await self._request_new_token()
            self._save_token(token)

        authenticated = await self._try_authenticate(token)

        if not authenticated:
            logger.warning("Token lama ditolak, meminta token baru...")
            token = await self._request_new_token()
            self._save_token(token)

            if not await self._try_authenticate(token):
                raise VTubeStudioError("Autentikasi ke VTube Studio ditolak.")

        logger.info("Autentikasi VTube Studio berhasil.")

    async def _try_authenticate(self, token: str) -> bool:
        response = await self._send_request(
            "AuthenticationRequest",
            {
                "pluginName": self._plugin_name,
                "pluginDeveloper": self._plugin_developer,
                "authenticationToken": token,
            },
        )
        return bool(response.get("data", {}).get("authenticated", False))

    async def trigger_hotkey(self, hotkey_name: str) -> None:
        if self._ws is None:
            raise VTubeStudioError("Belum terhubung ke VTube Studio.")

        await self._send_request("HotkeyTriggerRequest", {"hotkeyID": hotkey_name})
        logger.info("Hotkey dipicu: {}", hotkey_name)

    async def set_parameter(self, parameter_id: str, value: float) -> None:
        if self._ws is None:
            raise VTubeStudioError("Belum terhubung ke VTube Studio.")

        await self._send_request(
            "InjectParameterDataRequest",
            {
                "faceFound": False,
                "mode": "set",
                "parameterValues": [{"id": parameter_id, "value": value}],
            },
        )

    async def _request_new_token(self) -> str:
        response = await self._send_request(
            "AuthenticationTokenRequest",
            {"pluginName": self._plugin_name, "pluginDeveloper": self._plugin_developer},
        )
        token = response.get("data", {}).get("authenticationToken")

        if not token:
            raise VTubeStudioError("Gagal mendapatkan authentication token dari VTube Studio.")

        return token

    async def _send_request(self, message_type: str, data: dict) -> dict:
        request = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": str(uuid.uuid4()),
            "messageType": message_type,
            "data": data,
        }
        async with self._send_lock:
            await self._ws.send(json.dumps(request))
            raw_response = await self._ws.recv()
            return json.loads(raw_response)

    def _load_token(self) -> Optional[str]:
        if not self._token_path.exists():
            return None
        try:
            with open(self._token_path, "r", encoding="utf-8") as f:
                return json.load(f).get("token")
        except Exception as e:
            logger.warning("Gagal membaca token tersimpan: {}", e)
            return None

    def _save_token(self, token: str) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._token_path, "w", encoding="utf-8") as f:
            json.dump({"token": token}, f)
        logger.info("Token autentikasi VTube Studio disimpan.")