from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from avatar.expression import Expression
from config.logger import logger


class ParameterMapper:
    """Model Configuration layer: memetakan Logical Expression -> Hotkey, DAN
    logical parameter (mis. 'MouthOpen') -> nama parameter VTS untuk model SAAT INI.
    Ganti model = edit JSON ini saja, TIDAK menyentuh kode Python apa pun."""

    def __init__(self, config_path: Path):
        self._config_path = config_path
        self._expression_mapping: dict[str, str] = {}
        self._parameter_mapping: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._parameter_mapping = data.pop("parameters", {})
            self._expression_mapping = data
            logger.info("Model expression config dimuat: {}", self._config_path)
        except Exception as e:
            logger.warning("Gagal memuat model expression config, avatar akan diam: {}", e)
            self._expression_mapping = {}
            self._parameter_mapping = {}

    def get_hotkey(self, expression: Expression) -> Optional[str]:
        return self._expression_mapping.get(expression.value)

    def get_parameter_id(self, logical_name: str) -> Optional[str]:
        """Mis. get_parameter_id('MouthOpen') -> 'ParamMouthOpenY' (tergantung model)."""
        return self._parameter_mapping.get(logical_name)

    def reload(self) -> None:
        self._load()