from __future__ import annotations
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_FILES = {
    "identity": "identity.txt",
    "personality": "personality.txt",
    "relationship": "relationship.txt",
    "behavior": "behavior.txt",
    "speaking_style": "speaking_style.txt",
    "halo": "halo.txt",
    "system_rules": "system_rules.txt",
}


class PromptLoadError(Exception):
    """Terjadi saat file prompt wajib gagal dimuat."""

def load_prompts() -> dict[str, str]:
    prompts: dict[str, str] = {}

    for key, filename in _FILES.items():
        path = PROMPTS_DIR / filename

        try:
            prompts[key] = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as e:
            raise PromptLoadError(
                f"File prompt wajib tidak ditemukan: '{filename}'. "
                f"Pastikan file tersebut ada di folder '{PROMPTS_DIR}'."
            ) from e
        except OSError as e:
            raise PromptLoadError(
                f"Gagal membaca file prompt '{filename}': {e}"
            ) from e

    return prompts