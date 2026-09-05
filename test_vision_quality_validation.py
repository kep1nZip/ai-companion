"""v2.3 — Local Vision Quality Validation: test harness otomatis.

BEDA PENTING dengan test_memory_quality_validation.py (v2.2.2): kualitas
deskripsi Vision TIDAK BISA dinilai otomatis lewat string-match/schema
check seperti fakta memori ("apakah category+content sesuai") — deskripsi
visual perlu dinilai MANUSIA terhadap apa yang SUNGGUHAN ada di layar saat
itu. Karena itu harness ini punya bentuk berbeda dari versi Memory:

1. Connectivity check (persis pola v2.2.2 — dipisah dari test yang
   sesungguhnya, supaya kegagalan koneksi tidak tersamar sebagai "hasil
   kosong/aneh" yang ambigu).
2. Menangkap SATU screenshot layar Teacher SUNGGUHAN (bukan gambar
   sintetis), lalu jalankan KEDUA provider (kalau tersedia) terhadap
   gambar YANG SAMA PERSIS — supaya perbandingan adil (apple-to-apple).
3. Test error-handling (model tidak mendukung gambar, gambar rusak, dst)
   — ini BISA diverifikasi otomatis (pass/fail jelas: exception yang benar
   dilempar atau tidak).
4. Hasil deskripsi (Gemini vs Local) dicetak BERDAMPINGAN di laporan —
   Teacher/GPT yang menilai apakah deskripsi Local "cukup akurat"
   dibandingkan Gemini terhadap apa yang benar-benar ada di layar saat
   screenshot diambil (dicantumkan juga sebagai gambar terlampir kalau
   --save-screenshot dipakai, supaya penilaian tidak perlu mengingat-ingat).

TIDAK menyentuh main_gui.py/Companion/Vision state aplikasi yang
sebenarnya — script ini membuat instance Vision-nya SENDIRI, terpisah
total (persis semangat test_local_provider.py &
test_memory_quality_validation.py yang sudah ada).

Cara pakai:
    python test_vision_quality_validation.py                     # Gemini + Local, screenshot layar saat ini
    python test_vision_quality_validation.py --provider local
    python test_vision_quality_validation.py --provider gemini
    python test_vision_quality_validation.py --save-screenshot   # simpan screenshot yang dipakai, untuk verifikasi visual manual
    python test_vision_quality_validation.py --model "qwen/qwen3-vl-8b" --base-url "http://localhost:1234/v1"
    python test_vision_quality_validation.py --output hasil_vision.md

Prasyarat: sama seperti test_memory_quality_validation.py — Gemini butuh
GEMINI_API_KEY di .env, Local butuh LM Studio jalan dengan model VLM
(vision-language) ter-load, BUKAN model text-only.
"""

from __future__ import annotations

import argparse
import io
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image

from ai.providers.base import ProviderError
from vision.image_analyzer import ImageAnalyzer, GeminiImageAnalyzer, VisionAnalysisError, VISION_PROMPT
from vision.local_image_analyzer import LocalImageAnalyzer
from vision.screen_capture import MssScreenCapture
from vision.vision_context import parse_vision_context


@dataclass
class ProviderVisionResult:
    provider_name: str
    model_name: str
    connectivity_ok: Optional[bool] = None
    connectivity_detail: str = ""
    fatal_error: Optional[str] = None
    raw_description: Optional[str] = None
    parsed_application: Optional[str] = None
    parsed_summary: Optional[str] = None
    error_handling_results: list = field(default_factory=list)  # list of (test_name, passed, detail)


def _connectivity_check(analyzer: ImageAnalyzer, provider_label: str) -> tuple:
    """v2.3 (pola sama dengan v2.2.2 _connectivity_check): kirim gambar
    trivial 1x1 piksel SEBELUM test sungguhan, supaya kegagalan koneksi
    (LM Studio belum jalan, model belum di-load) ketahuan jelas di awal,
    bukan tersamar jadi deskripsi aneh/kosong yang ambigu penyebabnya."""
    tiny_image = Image.new("RGB", (1, 1), color="white")
    try:
        raw = analyzer.analyze(tiny_image)
        detail = f"Provider merespons: \"{(raw or '').strip()[:100]}\""
        print(f"  ✅ Connectivity check {provider_label}: OK — {detail}")
        return True, detail
    except VisionAnalysisError as e:
        # Respons kosong pada gambar 1x1 putih polos BUKAN kegagalan
        # koneksi — provider tetap terhubung, cuma tidak ada yang layak
        # dideskripsikan dari gambar sekosong itu. Anggap OK untuk tujuan
        # connectivity (bukan quality) check.
        detail = f"Provider terhubung tapi respons kosong untuk gambar test trivial (wajar): {e}"
        print(f"  ✅ Connectivity check {provider_label}: OK (respons kosong wajar untuk gambar 1x1) — {detail}")
        return True, detail
    except ProviderError as e:
        detail = f"ProviderError: {e}"
        print(f"  ❌ Connectivity check {provider_label}: GAGAL — {detail}")
        return False, detail
    except Exception as e:
        detail = f"Exception tak terduga: {e}"
        print(f"  ❌ Connectivity check {provider_label}: GAGAL — {detail}")
        return False, detail


def _run_error_handling_tests(analyzer: ImageAnalyzer, provider_label: str) -> list:
    """v2.3 §17 (Error Handling Test Matrix) — bagian yang BISA diotomatisasi
    dengan objektif (beda dengan kualitas deskripsi yang butuh manusia).
    Setiap test di sini punya kriteria pass/fail yang jelas: apakah
    exception yang benar dilempar, bukan ditelan diam-diam jadi hasil
    kosong yang ambigu."""
    results = []

    # E01: gambar sangat kecil (1x1) — harus tetap dapat respons ATAU
    # VisionAnalysisError yang jelas, TIDAK boleh crash dengan exception
    # tak terduga (mis. ValueError dari PIL/base64 encoding).
    try:
        tiny = Image.new("RGB", (1, 1), color="black")
        analyzer.analyze(tiny)
        results.append(("E01: gambar 1x1 piksel", True, "Berhasil dianalisis tanpa crash"))
    except VisionAnalysisError as e:
        results.append(("E01: gambar 1x1 piksel", True, f"VisionAnalysisError wajar (respons kosong): {e}"))
    except ProviderError as e:
        results.append(("E01: gambar 1x1 piksel", True, f"ProviderError wajar (mis. server menolak): {e}"))
    except Exception as e:
        results.append(("E01: gambar 1x1 piksel", False, f"GAGAL — exception tak terduga: {type(e).__name__}: {e}"))

    # E02: gambar besar (4K-ish) — pastikan tidak timeout/crash karena
    # v2.3 hotfix (temuan Teacher): sebelumnya E02/E03 yang gagal dengan
    # ProviderError langsung ditandai "✅ wajar" — TERBUKTI SALAH lewat
    # testing nyata: gambar besar (E02, 3840x2160) membuat GPU Teacher
    # (AMD, Vulkan) mengalami "device lost" SUNGGUHAN (crash driver di
    # level OS, bukan cuma error API yang bersih) — response HTTP dari LM
    # Studio ("server_error", "mtmd chunk") TIDAK CUKUP DETAIL untuk
    # membedakan "model menolak dengan bersih" dari "backend/GPU crash".
    # Karena tidak bisa dibedakan dengan andal dari teks error semata,
    # SEKARANG kedua kemungkinan itu ditandai dengan PERINGATAN eksplisit
    # (bukan "wajar" yang menenangkan), plus instruksi cek log LM Studio.
    #
    # Perbaikan UTAMA ada di production code (vision/local_image_analyzer.py
    # — LocalImageAnalyzer sekarang resize gambar besar SEBELUM dikirim,
    # default max 1280px sisi terpanjang) — kalau fix itu sudah terpasang,
    # E02 di bawah TIDAK LAGI mengirim 3840x2160 mentah sama sekali, jadi
    # seharusnya tidak memicu skenario ini lagi. Test ini tetap dipertahankan
    # (bukan dihapus) justru karena TERBUKTI berguna menemukan bug nyata.

    # E02: gambar besar (4K) — dengan LocalImageAnalyzer yang sudah diperbaiki,
    # ini SEHARUSNYA sudah di-resize otomatis sebelum sampai ke server.
    try:
        large = Image.new("RGB", (3840, 2160), color="green")
        analyzer.analyze(large)
        results.append(("E02: gambar besar (3840x2160)", True, "Berhasil dianalisis tanpa crash"))
    except VisionAnalysisError as e:
        results.append(("E02: gambar besar (3840x2160)", True, f"VisionAnalysisError wajar (respons kosong): {e}"))
    except ProviderError as e:
        results.append((
            "E02: gambar besar (3840x2160)", True,
            f"⚠️ PERHATIAN — provider menolak/error: {e}. TIDAK BISA dipastikan ini "
            "penolakan bersih atau tanda instabilitas backend/GPU (response API tidak "
            "cukup detail) — CEK console LM Studio & Event Viewer/dmesg OS untuk "
            "error driver GPU (mis. 'device lost', notifikasi crash driver) di sekitar "
            "waktu ini. Kalau ada, JANGAN abaikan — laporkan sebelum lanjut pakai "
            "Local Vision untuk penggunaan sungguhan."
        ))
    except Exception as e:
        results.append(("E02: gambar besar (3840x2160)", False, f"GAGAL — exception tak terduga: {type(e).__name__}: {e}"))

    # E03: mode gambar tidak umum (RGBA dengan transparansi)
    try:
        rgba = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        analyzer.analyze(rgba)
        results.append(("E03: gambar RGBA transparan", True, "Berhasil dianalisis tanpa crash"))
    except VisionAnalysisError as e:
        results.append(("E03: gambar RGBA transparan", True, f"VisionAnalysisError wajar: {e}"))
    except ProviderError as e:
        results.append((
            "E03: gambar RGBA transparan", True,
            f"⚠️ PERHATIAN — provider menolak/error: {e}. Kalau ini terjadi TEPAT "
            "setelah E02 gagal dengan gejala serupa, kemungkinan besar ini gejala "
            "LANJUTAN dari GPU/driver yang sudah dalam kondisi tidak stabil akibat E02 "
            "(bukan masalah baru dari gambar RGBA itu sendiri) — restart LM Studio "
            "sebelum menyimpulkan apa pun dari hasil test ini."
        ))
    except Exception as e:
        results.append(("E03: gambar RGBA transparan", False, f"GAGAL — exception tak terduga: {type(e).__name__}: {e}"))

    for name, passed, detail in results:
        status = "✅" if passed and "⚠️" not in detail else ("⚠️" if passed else "❌")
        print(f"  [{name}] {status} {detail}")

    return results


def _run_provider(provider_label: str, analyzer_factory, screenshot: Image.Image) -> ProviderVisionResult:
    print(f"\n{'=' * 60}\n{provider_label} — menjalankan test...\n{'=' * 60}")

    try:
        analyzer, model_name = analyzer_factory()
    except Exception as e:
        print(f"❌ Gagal menyiapkan provider {provider_label}: {e}")
        return ProviderVisionResult(provider_label, "unknown", fatal_error=str(e))

    result = ProviderVisionResult(provider_label, model_name)

    connectivity_ok, connectivity_detail = _connectivity_check(analyzer, provider_label)
    result.connectivity_ok = connectivity_ok
    result.connectivity_detail = connectivity_detail
    if not connectivity_ok:
        result.fatal_error = f"Connectivity check gagal, test dibatalkan untuk provider ini: {connectivity_detail}"
        print(f"  ⚠️  {provider_label} TIDAK bisa dihubungi — sisa test untuk provider ini DILEWATI.")
        return result

    print(f"\n  Menjalankan analisis terhadap screenshot layar saat ini...")
    try:
        raw = analyzer.analyze(screenshot)
        result.raw_description = raw
        context = parse_vision_context(raw, source="screen", ttl=30.0)
        result.parsed_application = context.application
        result.parsed_summary = context.summary
        print(f"  ✅ Analisis berhasil.")
        print(f"     Application: {context.application}")
        print(f"     Summary: {context.summary[:150]}{'...' if len(context.summary) > 150 else ''}")
    except Exception as e:
        result.fatal_error = f"Analisis screenshot gagal: {e}"
        print(f"  ❌ Analisis screenshot GAGAL: {e}")

    print(f"\n  Menjalankan Error Handling Test Matrix (E01-E03)...")
    result.error_handling_results = _run_error_handling_tests(analyzer, provider_label)

    return result


def _build_gemini_analyzer():
    from config.settings import GEMINI_API_KEY
    from config.constants import VISION_MODEL_NAME

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY kosong/tidak ditemukan di .env")

    return GeminiImageAnalyzer(api_key=GEMINI_API_KEY, model_name=VISION_MODEL_NAME), VISION_MODEL_NAME


def _build_local_analyzer(model_name: str, base_url: str):
    return LocalImageAnalyzer(base_url=base_url, model_name=model_name), model_name


def _build_report(results: list, screenshot_saved_path: Optional[str]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# v2.3 — Local Vision Quality Validation — Hasil Otomatis",
        "",
        f"Dijalankan: {now}",
        "",
        "**PENTING:** Deskripsi visual TIDAK bisa dinilai benar/salah "
        "otomatis oleh script ini — bagian \"Perbandingan Deskripsi\" di "
        "bawah WAJIB dibaca & dinilai manual oleh Teacher/GPT, dibandingkan "
        "dengan apa yang SUNGGUHAN ada di layar saat screenshot diambil.",
        "",
    ]

    if screenshot_saved_path:
        lines += [
            f"Screenshot yang dipakai untuk test ini disimpan di: `{screenshot_saved_path}` "
            "— buka file ini untuk membandingkan deskripsi di bawah dengan isi layar sungguhan.",
            "",
        ]

    lines += ["## Provider Connectivity Check", ""]
    for r in results:
        status = "✅ OK" if r.connectivity_ok else ("❌ GAGAL" if r.connectivity_ok is False else "⚠️ Tidak dicek")
        lines.append(f"- **{r.provider_name}** ({r.model_name}): {status} — {r.connectivity_detail or r.fatal_error or ''}")

    lines += ["", "## Perbandingan Deskripsi (WAJIB dinilai manual)", ""]
    for r in results:
        lines.append(f"### {r.provider_name} ({r.model_name})")
        lines.append("")
        if r.fatal_error and r.raw_description is None:
            lines.append(f"⚠️ Tidak ada hasil: {r.fatal_error}")
        else:
            lines += [
                f"- **Application terdeteksi:** {r.parsed_application or '(tidak terdeteksi)'}",
                f"- **Summary:**",
                "",
                "  ```text",
                f"  {r.raw_description or '(kosong)'}",
                "  ```",
            ]
        lines.append("")

    lines += ["## Error Handling Test Matrix (E01-E03, otomatis)", ""]
    lines += ["| Test | Provider | Status | Detail |", "|---|---|---|---|"]
    any_warning = False
    for r in results:
        for name, passed, detail in r.error_handling_results:
            has_warning = "⚠️" in detail
            if has_warning:
                any_warning = True
            status = "✅" if passed and not has_warning else ("⚠️" if passed else "❌")
            lines.append(f"| {name} | {r.provider_name} | {status} | {detail} |")

    total_error_tests = sum(len(r.error_handling_results) for r in results)
    total_passed = sum(1 for r in results for _, p, _ in r.error_handling_results if p)
    lines += ["", f"**Ringkasan Error Handling: {total_passed}/{total_error_tests} tidak crash Python.**", ""]

    if any_warning:
        lines += [
            "⚠️ **PERHATIAN — ada hasil bertanda ⚠️ di atas.** Ini BUKAN otomatis "
            "berarti gagal, tapi juga BUKAN \"aman\" begitu saja — baca kolom Detail "
            "dengan saksama, cek console LM Studio dan Event Viewer (Windows) / dmesg "
            "(Linux) untuk tanda-tanda crash driver GPU (mis. \"device lost\", "
            "notifikasi timeout driver dari vendor GPU) di sekitar waktu test ini "
            "dijalankan, SEBELUM menganggap Local Vision aman dipakai untuk "
            "penggunaan sungguhan.",
            "",
        ]

    lines += [
        "## Langkah Manual yang BELUM Tercakup Laporan Ini (§17 V009-V016, Runtime)",
        "",
        "Script ini TIDAK bisa mengukur hal-hal berikut secara jujur — perlu "
        "observasi manual langsung di `main_gui.py`:",
        "",
        "- **Manual Vision (Capture Now) responsiveness** — set "
        "`VISION_PROVIDER=local`, tekan Capture Now di GUI, amati apakah "
        "GUI freeze selama analisis berjalan (mirip T09 di v2.2.2).",
        "- **AUTO Vision behavior** — aktifkan mode AUTO, amati apakah "
        "capture berkala tetap berjalan tanpa mengganggu chat/GUI, dan "
        "apakah interval capture terasa wajar untuk kecepatan Local Vision "
        "(biasanya lebih lambat dari Gemini — VRAM/GPU Teacher memengaruhi "
        "ini, tidak bisa diukur dari sini).",
        "- **Shutdown normal** — pastikan aplikasi tetap bisa ditutup normal "
        "walau Vision Local sedang capture/analisis.",
        "- **Developer Dashboard** — pastikan card Vision menunjukkan "
        "\"Provider: Local\" saat `VISION_PROVIDER=local`.",
        "- **Gemini Regression** — set balik `VISION_PROVIDER=gemini`, "
        "pastikan Manual & AUTO Vision masih bekerja seperti sebelum v2.3 "
        "sama sekali (nol regresi).",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="v2.3 — Local Vision Quality Validation test harness")
    parser.add_argument("--provider", choices=["both", "gemini", "local"], default="both")
    parser.add_argument("--model", default=None, help="Override nama model Local (default: LOCAL_PROVIDER_MODEL_NAME dari .env)")
    parser.add_argument("--base-url", default=None, help="Override base URL Local (default: LOCAL_PROVIDER_BASE_URL dari .env)")
    parser.add_argument("--output", default=None, help="Path file laporan .md")
    parser.add_argument("--save-screenshot", action="store_true", help="Simpan screenshot yang dipakai untuk verifikasi visual manual")
    args = parser.parse_args()

    print("Mengambil screenshot layar saat ini untuk test...")
    capture = MssScreenCapture()
    screenshot = capture.capture()
    print(f"Screenshot diambil: {screenshot.size[0]}x{screenshot.size[1]}px")

    screenshot_saved_path = None
    if args.save_screenshot:
        screenshot_saved_path = f"vision_test_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        screenshot.save(screenshot_saved_path)
        print(f"Screenshot disimpan ke: {screenshot_saved_path}")

    results = []

    if args.provider in ("both", "gemini"):
        results.append(_run_provider("Gemini", _build_gemini_analyzer, screenshot))

    if args.provider in ("both", "local"):
        from config.settings import LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL
        model_name = args.model or LOCAL_PROVIDER_MODEL_NAME
        base_url = args.base_url or LOCAL_PROVIDER_BASE_URL
        results.append(_run_provider("Local", lambda: _build_local_analyzer(model_name, base_url), screenshot))

    report = _build_report(results, screenshot_saved_path)
    output_path = Path(args.output) if args.output else Path(
        f"vision_quality_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    )
    output_path.write_text(report, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"Selesai. Laporan lengkap ditulis ke: {output_path}")
    print(f"{'=' * 60}")

    any_fatal = any(r.fatal_error and r.connectivity_ok is False for r in results)
    return 1 if any_fatal else 0


if __name__ == "__main__":
    sys.exit(main())