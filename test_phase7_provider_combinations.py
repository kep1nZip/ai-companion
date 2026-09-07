"""
v2.4 Phase 7 — Provider Combination Tests.

JALANKAN DI MESIN TEACHER SENDIRI (butuh LM Studio menyala + GEMINI_API_KEY
valid) — TIDAK bisa dijalankan penuh di sandbox Claude.

Menguji 4 kombinasi dari v2.4_PROVIDER_EXPANSION_OPTIMIZATION_DESIGN_SPEC.md
§13, MEMASTIKAN tidak ada efek samping silang antar pilihan provider —
bukan menguji kualitas balasan (itu tugas test_*_quality_validation.py yang
sudah ada), murni "apakah kombinasi ini construct & jalan tanpa exception
tak terduga dan tanpa silent fallback".

Kombinasi (Vision di sini diuji construct-level saja, TANPA screenshot asli,
supaya script ini ringan dijalankan berkali-kali):

  A: AI=Local   Memory=Gemini  Vision=Local   TTS=Gemini(fixed)
  B: AI=Gemini  Memory=Local   Vision=Local   TTS=Gemini(fixed)
  C: AI=Local   Memory=Local   Vision=Gemini  TTS=Gemini(fixed)
  D: AI=Gemini  Memory=Gemini  Vision=Gemini  TTS=Gemini(fixed)

Cara pakai:
    python test_phase7_provider_combinations.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from google.genai import types

from ai.companion import Companion
from ai.providers.local_provider import LocalProvider
from ai.providers.gemini_provider import GeminiProvider
from ai.memory_extractor import EXTRACTION_SYSTEM_PROMPT
from ai.personality import load_prompts
from ai.prompt_builder import build_system_prompt
from vision.vision import Vision
from vision.local_image_analyzer import LocalImageAnalyzer
from vision.image_analyzer import GeminiImageAnalyzer
from vision.screen_capture import MssScreenCapture
from config.settings import GEMINI_API_KEY, LOCAL_PROVIDER_BASE_URL, LOCAL_PROVIDER_MODEL_NAME
from config.constants import MODEL_NAME, VISION_MODEL_NAME, VISION_DEFAULT_TTL


@dataclass
class Combo:
    label: str
    ai: str      # "local" | "gemini"
    memory: str  # "local" | "gemini"
    vision: str  # "local" | "gemini"


COMBOS = [
    Combo("A", ai="local", memory="gemini", vision="local"),
    Combo("B", ai="gemini", memory="local", vision="local"),
    Combo("C", ai="local", memory="local", vision="gemini"),
    Combo("D", ai="gemini", memory="gemini", vision="gemini"),
]


def build_companion_for(combo: Combo) -> Companion:
    system_prompt = build_system_prompt(load_prompts())

    if combo.ai == "local":
        provider = LocalProvider(system_prompt=system_prompt, model_name=LOCAL_PROVIDER_MODEL_NAME, base_url=LOCAL_PROVIDER_BASE_URL)
        ai_model_name = LOCAL_PROVIDER_MODEL_NAME
    else:
        provider = None
        ai_model_name = MODEL_NAME

    if combo.memory == "local":
        memory_provider = LocalProvider(
            system_prompt=EXTRACTION_SYSTEM_PROMPT, model_name=LOCAL_PROVIDER_MODEL_NAME,
            base_url=LOCAL_PROVIDER_BASE_URL, temperature=0.0, frequency_penalty=0.0, presence_penalty=0.0,
        )
        memory_model_name = LOCAL_PROVIDER_MODEL_NAME
    else:
        memory_provider = None
        memory_model_name = MODEL_NAME

    if combo.vision == "local":
        analyzer = LocalImageAnalyzer(base_url=LOCAL_PROVIDER_BASE_URL, model_name=LOCAL_PROVIDER_MODEL_NAME)
        vision_provider_name, vision_model_name = "local", LOCAL_PROVIDER_MODEL_NAME
    else:
        analyzer = GeminiImageAnalyzer(api_key=GEMINI_API_KEY, model_name=VISION_MODEL_NAME)
        vision_provider_name, vision_model_name = "gemini", VISION_MODEL_NAME

    vision = Vision(
        screen_capture=MssScreenCapture(), image_analyzer=analyzer, default_ttl=VISION_DEFAULT_TTL,
        provider_name=vision_provider_name, model_name=vision_model_name,
    )

    return Companion(
        vision=vision, provider=provider, memory_provider=memory_provider,
        ai_model_name=ai_model_name, memory_model_name=memory_model_name,
    )


def main():
    print("v2.4 Phase 7 — Provider Combination Tests\n")
    report_lines = ["# v2.4 Phase 7 — Provider Combination Test Result", ""]

    for combo in COMBOS:
        print(f"--- Kombinasi {combo.label}: AI={combo.ai} Memory={combo.memory} Vision={combo.vision} ---")
        row = [f"## Kombinasi {combo.label}: AI={combo.ai}, Memory={combo.memory}, Vision={combo.vision}, TTS=gemini(fixed)"]
        try:
            companion = build_companion_for(combo)

            # 1) Konfirmasi observability melaporkan provider yang BENAR
            #    (bukan cuma "tidak crash" — ini poin utama v2.4 §5.1 "observable")
            assert companion.get_ai_provider_name() == combo.ai, "AI provider name salah!"
            assert companion.get_memory_provider_name() == combo.memory, "Memory provider name salah!"
            assert companion.get_vision_provider_name() == combo.vision, "Vision provider name salah!"
            row.append("- Observability (get_*_provider_name()) sesuai kombinasi: ✅ PASS")

            # 2) Coba 1 chat sungguhan (BUTUH LM Studio/Gemini API asli menyala)
            start = time.perf_counter()
            reply = companion.chat("Halo Arona, kamu lagi kombinasi provider apa?")
            elapsed = time.perf_counter() - start
            row.append(f"- Chat 1x sukses ({elapsed:.2f}s): ✅ PASS — balasan: {reply[:80]!r}")

        except AssertionError as e:
            row.append(f"- ❌ FAIL (observability salah): {e}")
        except Exception as e:
            row.append(f"- ❌ FAIL ({type(e).__name__}): {e}")

        report_lines += row + [""]
        for line in row:
            print(f"  {line}")
        print()

    report = "\n".join(report_lines)
    with open("phase7_combination_result.md", "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print("Hasil ditulis ke phase7_combination_result.md")


if __name__ == "__main__":
    main()
