"""
Script standalone buat tes koneksi ke local LLM server (LM Studio, dkk)
SEBELUM dipasang ke aplikasi utama. Jalankan setelah LM Studio sudah:
  1. Model sudah di-load (rekomendasi awal: Qwen3.5-9B, quant Q4_K_M)
  2. Local Server sudah di-"Start" (tab Developer, default port 1234)

Cara pakai:
    python test_local_provider.py
    python test_local_provider.py --model "nama-model-persis-di-LM-Studio"

Ini TIDAK menyentuh main_gui.py/Companion sama sekali — murni tes provider
secara terisolasi (v2.0 Migration Strategy Step 5: "Run same test suite
against both" providers, sebelum diintegrasikan/dijadikan default)."""

from __future__ import annotations

import argparse
import sys

from ai.providers.local_provider import LocalProvider
from ai.providers.base import ProviderError, ProviderResponseError, ProviderRateLimitError

# format Content/Part yang SAMA dengan yang dipakai Companion sungguhan
from google.genai import types


def main() -> int:
    parser = argparse.ArgumentParser(description="Tes koneksi ke local LLM server (LM Studio)")
    parser.add_argument("--model", default="local-model", help="Nama model persis seperti yang tampil di LM Studio")
    parser.add_argument("--base-url", default="http://localhost:1234/v1", help="URL local server")
    args = parser.parse_args()

    print(f"Menghubungi {args.base_url} dengan model '{args.model}'...\n")

    provider = LocalProvider(
        system_prompt=(
            "Kamu adalah Arona, AI companion yang ceria dan hangat. "
            "Balas singkat saja untuk tes koneksi ini."
        ),
        model_name=args.model,
        base_url=args.base_url,
    )

    contents = [
        types.Content(role="user", parts=[types.Part(text="Halo Arona, kamu bisa dengar aku?")]),
    ]

    try:
        reply = provider.generate(contents)
    except ProviderRateLimitError as e:
        print(f"❌ Rate limit dari local server: {e}")
        return 1
    except ProviderResponseError as e:
        print(f"❌ Server merespons tapi hasilnya tidak valid/kosong: {e}")
        return 1
    except ProviderError as e:
        print(f"❌ Gagal terhubung: {e}")
        print("\nCek lagi:")
        print("  - LM Studio sudah dibuka?")
        print("  - Model sudah di-load (bukan cuma di-download)?")
        print("  - Tombol 'Start Server' di tab Developer sudah ditekan?")
        return 1

    print("✅ Berhasil! Balasan dari local model:\n")
    print(f"    {reply}\n")
    print("Local provider siap dipakai. Kalau kualitas/kecepatannya terasa oke,")
    print("kabari Claude buat lanjut ke langkah berikutnya (integrasi ke Settings GUI).")
    return 0


if __name__ == "__main__":
    sys.exit(main())