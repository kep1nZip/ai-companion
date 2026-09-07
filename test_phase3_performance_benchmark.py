"""
v2.4 Phase 3 — Performance Baseline.

JALANKAN DI MESIN TEACHER SENDIRI (butuh LM Studio menyala + GEMINI_API_KEY
valid di .env) — TIDAK bisa dijalankan di sandbox Claude (tidak ada GPU,
tidak ada akses ke Gemini API asli, tidak ada model lokal ter-load).

Script ini TIDAK mengubah provider aktif Teacher (AI_PROVIDER/dst di .env
tetap apa adanya) — untuk setiap subsystem, dia membuat SATU instance Local
dan SATU instance Gemini secara terpisah (lepas dari .env), lalu mengukur
keduanya, supaya hasilnya adalah PERBANDINGAN, bukan cuma "provider yang
lagi aktif sekarang".

Cara pakai:
    python test_phase3_performance_benchmark.py

Prasyarat:
    - LM Studio sudah menyala dengan model ter-load (default localhost:1234)
    - GEMINI_API_KEY valid di .env
    - (Untuk Vision) siapkan 1 screenshot nyata di layar Teacher saat run

Output: markdown ringkasan latency + error rate, ditulis ke
    phase3_benchmark_result.md
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ai.providers.base import ProviderError
from ai.providers.local_provider import LocalProvider
from ai.providers.gemini_provider import GeminiProvider
from ai.memory_extractor import EXTRACTION_SYSTEM_PROMPT
from config.settings import GEMINI_API_KEY, LOCAL_PROVIDER_BASE_URL, LOCAL_PROVIDER_MODEL_NAME
from config.constants import MODEL_NAME, VISION_MODEL_NAME
from google.genai import types

N_RUNS = 5  # v2.4 §9: ukur beberapa kali, bukan sekali tebak-tebakan

TEST_PROMPT = "Ceritakan dalam 2 kalimat bagaimana harimu, Arona."
MEMORY_TEST_TEXT = (
    "User: Aku baru beli kucing baru namanya Mochi, warnanya oren.\n"
    "Assistant: Wah selamat! Mochi nama yang lucu."
)


@dataclass
class BenchResult:
    label: str
    latencies: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def summary(self) -> str:
        if not self.latencies:
            return f"**{self.label}**: 0/{N_RUNS} sukses — semua gagal ({len(self.errors)} error, lihat detail di bawah)"
        mean = statistics.mean(self.latencies)
        p50 = statistics.median(self.latencies)
        worst = max(self.latencies)
        best = min(self.latencies)
        err_rate = len(self.errors) / N_RUNS * 100
        return (
            f"**{self.label}**: {len(self.latencies)}/{N_RUNS} sukses | "
            f"mean={mean:.2f}s p50={p50:.2f}s min={best:.2f}s max={worst:.2f}s | "
            f"error rate={err_rate:.0f}%"
        )


def run_bench(label: str, fn: Callable[[], None]) -> BenchResult:
    result = BenchResult(label=label)
    for i in range(N_RUNS):
        start = time.perf_counter()
        try:
            fn()
            result.latencies.append(time.perf_counter() - start)
        except Exception as e:
            result.errors.append(f"run {i+1}: {type(e).__name__}: {e}")
    return result


def content(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def bench_language() -> list[BenchResult]:
    local = LocalProvider(
        system_prompt="Kamu adalah asisten AI ramah.",
        model_name=LOCAL_PROVIDER_MODEL_NAME,
        base_url=LOCAL_PROVIDER_BASE_URL,
    )
    gemini = GeminiProvider(api_key=GEMINI_API_KEY, model_name=MODEL_NAME, system_prompt="Kamu adalah asisten AI ramah.")

    results = []
    results.append(run_bench("Language — Local", lambda: local.generate([content(TEST_PROMPT)])))
    results.append(run_bench("Language — Gemini", lambda: gemini.generate([content(TEST_PROMPT)])))
    return results


def bench_memory() -> list[BenchResult]:
    local = LocalProvider(
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        model_name=LOCAL_PROVIDER_MODEL_NAME,
        base_url=LOCAL_PROVIDER_BASE_URL,
        temperature=0.0, frequency_penalty=0.0, presence_penalty=0.0,
    )
    gemini = GeminiProvider(
        api_key=GEMINI_API_KEY, model_name=MODEL_NAME, system_prompt=EXTRACTION_SYSTEM_PROMPT, temperature=0.0,
    )
    results = []
    results.append(run_bench("Memory Extraction — Local", lambda: local.generate([content(MEMORY_TEST_TEXT)])))
    results.append(run_bench("Memory Extraction — Gemini", lambda: gemini.generate([content(MEMORY_TEST_TEXT)])))
    return results


def bench_vision() -> list[BenchResult]:
    from vision.local_image_analyzer import LocalImageAnalyzer
    from vision.image_analyzer import GeminiImageAnalyzer
    from vision.screen_capture import MssScreenCapture

    capture = MssScreenCapture()
    print("  (Vision) Mengambil screenshot nyata untuk dites...")
    image = capture.capture()

    local = LocalImageAnalyzer(base_url=LOCAL_PROVIDER_BASE_URL, model_name=LOCAL_PROVIDER_MODEL_NAME)
    gemini = GeminiImageAnalyzer(api_key=GEMINI_API_KEY, model_name=VISION_MODEL_NAME)

    results = []
    results.append(run_bench("Vision — Local", lambda: local.analyze(image)))
    results.append(run_bench("Vision — Gemini", lambda: gemini.analyze(image)))
    return results


def main():
    print(f"v2.4 Phase 3 — Performance Baseline ({N_RUNS} run per subsystem/provider)\n")
    all_results: list[BenchResult] = []

    print("[1/3] Language Generation...")
    all_results += bench_language()

    print("[2/3] Memory Extraction...")
    all_results += bench_memory()

    print("[3/3] Vision...")
    try:
        all_results += bench_vision()
    except Exception as e:
        print(f"  Vision benchmark dilewati (butuh screen capture aktif): {e}")

    lines = [f"# v2.4 Phase 3 — Performance Baseline Result", "", f"N_RUNS = {N_RUNS}", ""]
    for r in all_results:
        lines.append(f"- {r.summary()}")
        for err in r.errors:
            lines.append(f"    - ERROR: {err}")

    report = "\n".join(lines)
    print("\n" + report)
    with open("phase3_benchmark_result.md", "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print("\nHasil ditulis ke phase3_benchmark_result.md")


if __name__ == "__main__":
    main()
