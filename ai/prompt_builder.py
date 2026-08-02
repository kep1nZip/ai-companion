from __future__ import annotations

def build_system_prompt(prompts: dict[str, str]) -> str:
    sections = [
        ("IDENTITY", prompts["identity"]),
        ("PERSONALITY", prompts["personality"]),
        ("RELATIONSHIP", prompts["relationship"]),
        ("BEHAVIOR", prompts["behavior"]),
        ("SPEAKING STYLE", prompts["speaking_style"]),
        ("HALO", prompts["halo"]),
        ("SYSTEM RULES", prompts["system_rules"]),
    ]

    parts = [f"### {title}\n{content}" for title, content in sections]
    return "\n\n".join(parts)