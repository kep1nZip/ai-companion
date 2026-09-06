from __future__ import annotations

from typing import Optional, Tuple

from ai.personality import load_prompts
from ai.prompt_builder import build_system_prompt
from ai.providers.base import LanguageModelProvider
from ai.providers.local_provider import LocalProvider
from ai.memory_extractor import EXTRACTION_SYSTEM_PROMPT
from config.settings import (
    AI_PROVIDER,
    MEMORY_PROVIDER,
    LOCAL_PROVIDER_BASE_URL,
    LOCAL_PROVIDER_MODEL_NAME,
)
from config.constants import MODEL_NAME
from config.logger import logger

# v2.4 Phase 1 — Configuration Cleanup (Provider Map §7/§11.2).
#
# SEBELUM v2.4, logic pemilihan provider (baca AI_PROVIDER/MEMORY_PROVIDER,
# construct LocalProvider dengan config yang benar, log baris yang benar)
# HANYA ada di main_gui.py — main.py (CLI) memanggil `Companion()` polos
# tanpa provider apa pun, jadi CLI diam-diam SELALU pakai Gemini apa pun
# nilai .env-nya. Ini melanggar prinsip v2.4 §5.1 ("provider selection
# harus explicit, independent, observable, STABLE" — env yang sama TIDAK
# BOLEH menghasilkan provider berbeda tergantung entrypoint mana yang
# dipakai Teacher) dan §5.2 ("Single Configuration Source" — jangan
# menduplikasi logic pemilihan provider di lebih dari satu tempat).
#
# Modul ini TIDAK menambah provider baru, TIDAK mengubah kontrak
# LanguageModelProvider, dan TIDAK mengubah default apa pun — murni
# MEMINDAHKAN logic if/else yang SUDAH ADA di main_gui.py ke satu tempat
# bersama, supaya main.py bisa reuse persis logic yang sama alih-alih
# menulis ulang (atau lupa menulis sama sekali).
#
# Vision SENGAJA TIDAK diikutkan di factory ini — CLI (main.py) tidak
# pernah punya Vision sama sekali (tidak ada screen capture loop di CLI),
# menambahkannya sekarang akan jadi feature addition baru yang di luar
# scope "provider consistency" (v2.4 §4 Out of Scope: "Subsystem AI baru").
# Kalau Vision di CLI memang diinginkan, itu keputusan/milestone terpisah,
# bukan bagian dari audit provider ini.


def build_language_provider() -> Tuple[Optional[LanguageModelProvider], str]:
    """Construct provider Language Generation sesuai AI_PROVIDER, PERSIS
    logic yang sebelumnya inline di main_gui.py (tidak ditulis ulang,
    cuma dipindah). Return (provider, model_name):
    - provider=None berarti "pakai default Companion sendiri" (GeminiProvider)
      — pola yang SUDAH ADA sejak v2.0, dipertahankan apa adanya.
    - model_name SELALU diisi (bukan None) supaya composition root bisa
      meneruskannya ke Companion untuk observability (Developer Dashboard,
      v2.4 Phase 2) tanpa Companion perlu menebak dari tipe provider."""
    if AI_PROVIDER == "local":
        prompts = load_prompts()
        system_prompt = build_system_prompt(prompts)
        provider: LanguageModelProvider = LocalProvider(
            system_prompt=system_prompt,
            model_name=LOCAL_PROVIDER_MODEL_NAME,
            base_url=LOCAL_PROVIDER_BASE_URL,
        )
        logger.info("AI Provider: LOCAL ({} @ {})", LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL)
        return provider, LOCAL_PROVIDER_MODEL_NAME

    logger.info("AI Provider: GEMINI ({})", MODEL_NAME)
    return None, MODEL_NAME


def build_memory_provider() -> Tuple[Optional[LanguageModelProvider], str]:
    """Construct provider Memory Extraction sesuai MEMORY_PROVIDER — KEPUTUSAN
    TERPISAH dari AI_PROVIDER (v2.2 §27), PERSIS logic yang sebelumnya inline
    di main_gui.py. Return (provider, model_name) — pola identik dengan
    build_language_provider() di atas."""
    if MEMORY_PROVIDER == "local":
        provider: LanguageModelProvider = LocalProvider(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            model_name=LOCAL_PROVIDER_MODEL_NAME,
            base_url=LOCAL_PROVIDER_BASE_URL,
            temperature=0.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )
        logger.info(
            "Memory Extraction Provider: LOCAL ({} @ {})", LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL
        )
        return provider, LOCAL_PROVIDER_MODEL_NAME

    logger.info("Memory Extraction Provider: GEMINI ({})", MODEL_NAME)
    return None, MODEL_NAME