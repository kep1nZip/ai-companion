from __future__ import annotations

from pathlib import Path
from loguru import logger

from config.constants import LOG_DIR, LOG_FILE, LOG_LEVEL, LOG_ROTATION, LOG_RETENTION

_log_path = Path(LOG_DIR) / LOG_FILE
_log_path.parent.mkdir(exist_ok=True)

logger.remove()
logger.add(
    _log_path,
    level=LOG_LEVEL,
    rotation=LOG_ROTATION,
    retention=LOG_RETENTION,
    encoding="utf-8",
    diagnose=False,   # cegah local variable (termasuk API key) tercetak di traceback log
)

__all__ = ["logger"]