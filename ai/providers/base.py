from __future__ import annotations

from abc import ABC, abstractmethod

from google.genai import types


class ProviderError(Exception):
    """Kegagalan umum provider (network, auth, dsb) — PROVIDER-AGNOSTIC.
    Companion HANYA boleh menangkap exception dari sini, TIDAK PERNAH tipe
    spesifik satu provider (mis. google.genai.errors.ClientError) — supaya
    Companion tetap tidak peduli provider mana yang sedang aktif (v2.0 §35)."""


class ProviderResponseError(ProviderError):
    """Provider mengembalikan balasan kosong/tidak valid (mis. diblokir safety
    filter, tidak ada text part sama sekali)."""


class ProviderRateLimitError(ProviderError):
    """Provider melaporkan rate limit / kuota habis."""


class LanguageModelProvider(ABC):
    """Kontrak provider-agnostic untuk generasi teks (v2.0 §33-35). Companion
    HANYA boleh bergantung pada kelas abstrak ini, TIDAK PERNAH pada
    implementasi/tipe spesifik satu provider.

    Kontrak `generate()` DIRUMUSKAN dari kontrak `GeminiClient.send()` yang
    SUDAH ADA sejak v0.1 (ai/gemini.py) — BUKAN API yang ditebak (spec v2.0
    §33: "the exact interface must be designed by inspecting the actual
    Gemini usage"). `list[types.Content]` (tipe dari google-genai SDK)
    dipertahankan sebagai representasi bersama karena Conversation/
    ContextBuilder/Companion SEMUA sudah membangun struktur {role, parts:
    [text]} ini — mengubahnya jadi format lain berarti me-redesign
    Conversation/ContextBuilder juga, yang DILARANG spec (Stop Condition #2:
    "ContextBuilder must become provider-aware"; Regression: "No duplicate
    Conversation"). Provider lokal cukup MENERJEMAHKAN struktur ini jadi
    format prompt-nya sendiri DI DALAM implementasinya sendiri — Companion/
    ContextBuilder/Conversation tidak perlu tahu atau berubah sama sekali.

    Provider TIDAK PERNAH menyentuh Memory/Vision/Behavior/Routine/
    Initiative/Avatar/Voice/GUI (v2.0 §34) — tanggung jawabnya HANYA model
    request, generation, error provider-spesifik, dan config provider-spesifik."""

    @abstractmethod
    def generate(self, contents: list[types.Content]) -> str:
        """Kirim `contents` (riwayat percakapan + ephemeral context, sudah
        dirangkai Companion lewat ContextBuilder/Conversation — provider
        TIDAK PERNAH merangkai konteks sendiri) dan kembalikan balasan teks.

        Melempar:
        - ProviderResponseError: balasan kosong/tidak valid.
        - ProviderRateLimitError: rate limit/kuota habis.
        - ProviderError: kegagalan umum lainnya (network, auth, dst)."""
        raise NotImplementedError