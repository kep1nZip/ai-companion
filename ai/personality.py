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


def load_prompts() -> dict[str, str]:
    prompts = {}
    for key, filename in _FILES.items():
        path = PROMPTS_DIR / filename
        prompts[key] = path.read_text(encoding="utf-8").strip()
    return prompts