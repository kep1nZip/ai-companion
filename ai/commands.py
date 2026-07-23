from __future__ import annotations

from typing import Callable

from config.constants import APP_NAME, VERSION, MODEL_NAME
from config.logger import logger


class CommandResult:
    def __init__(self, message: str, should_exit: bool = False):
        self.message = message
        self.should_exit = should_exit


def _cmd_help(companion) -> CommandResult:
    text = (
        "Perintah yang tersedia:\n"
        "/help     - menampilkan daftar perintah\n"
        "/history  - menampilkan riwayat percakapan\n"
        "/clear    - menghapus riwayat percakapan\n"
        "/version  - menampilkan versi aplikasi\n"
        "/exit     - keluar dari aplikasi"
    )
    return CommandResult(text)


def _cmd_history(companion) -> CommandResult:
    history = companion.get_history()

    if not history:
        return CommandResult("Belum ada riwayat percakapan.")

    lines = []
    for content in history:
        speaker = "Teacher" if content.role == "user" else "Arona"
        text = content.parts[0].text if content.parts else ""
        lines.append(f"{speaker}: {text}")

    return CommandResult("\n".join(lines))


def _cmd_clear(companion) -> CommandResult:
    companion.clear_history()
    return CommandResult("Riwayat percakapan sudah dihapus.")


def _cmd_version(companion) -> CommandResult:
    return CommandResult(f"{APP_NAME} v{VERSION} — model: {MODEL_NAME}")


def _cmd_exit(companion) -> CommandResult:
    return CommandResult("Sampai jumpa lagi, Teacher...", should_exit=True)


_COMMANDS: dict[str, Callable] = {
    "/help": _cmd_help,
    "/history": _cmd_history,
    "/clear": _cmd_clear,
    "/version": _cmd_version,
    "/exit": _cmd_exit,
}


def is_command(text: str) -> bool:
    return text.strip().startswith("/")


def run_command(text: str, companion) -> CommandResult:
    name = text.strip().split()[0].lower()
    handler = _COMMANDS.get(name)

    if handler is None:
        logger.warning("Unknown command: {}", name)
        return CommandResult(f"Perintah tidak dikenal: {name}. Ketik /help untuk bantuan.")

    return handler(companion)