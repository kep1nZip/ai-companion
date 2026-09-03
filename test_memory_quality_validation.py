"""v2.2.2 — Local Memory Quality Validation: test harness otomatis.

Menjalankan Test Matrix T01-T08 dari
V2_2_2_LOCAL_MEMORY_QUALITY_VALIDATION_DESIGN_SPEC.md langsung terhadap
MemoryExtractor SUNGGUHAN (Gemini dan/atau Local), lalu menulis laporan
.md sesuai format "Validation Log Template" (spec §10) secara otomatis —
Teacher tinggal jalankan satu perintah, bukan mengetik ulang tes manual
satu-satu di GUI.

TIDAK menyentuh main_gui.py/Companion/memory.db Teacher yang sebenarnya
sama sekali (persis semangat test_local_provider.py yang sudah ada) —
semua penyimpanan memory di sini pakai SQLite file TEMPORARY yang dibuang
begitu proses selesai, supaya hasil test "Aku suka americano" dkk TIDAK
mencemari memori jangka panjang Arona yang asli.

T09 (GUI responsiveness) dan T10 (Developer Dashboard provider check)
SENGAJA TIDAK diotomatisasi di sini — keduanya butuh observasi visual
manusia langsung (freeze/lag terlihat, dashboard ke-render benar) yang
tidak bisa diukur jujur lewat script headless. Instruksi manual untuk
keduanya dicetak di akhir laporan.

Cara pakai:
    python test_memory_quality_validation.py                  # Gemini + Local
    python test_memory_quality_validation.py --provider gemini
    python test_memory_quality_validation.py --provider local
    python test_memory_quality_validation.py --model "qwen/qwen3-vl-8b" --base-url "http://localhost:1234/v1"
    python test_memory_quality_validation.py --output hasil_validasi.md

Prasyarat:
  - Gemini: GEMINI_API_KEY sudah ada di .env (dibaca lewat config/settings.py
    seperti biasa).
  - Local: LM Studio sudah jalan & model sudah di-load (sama seperti
    prasyarat test_local_provider.py).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai.memory_extractor import MemoryExtractor, EXTRACTION_SYSTEM_PROMPT
from ai.providers.base import LanguageModelProvider, ProviderError
from ai.providers.gemini_provider import GeminiProvider
from ai.providers.local_provider import LocalProvider
from database.memory_manager import MemoryManager

# ---------- Test cases — persis dari spec §7, digabung tanpa dipisah per
# provider (setiap provider diuji dengan SEMUA variasi hedging yang
# disebut spec, bukan cuma subset yang "kebagian" providernya di teks
# spec — supaya cakupan lebih menyeluruh, bukan malah dikurangi). ----------

EXPLICIT_FACT_CASES = [
    "Aku suka kopi americano.",
]

NOISE_CASES = [
    "Wah hari ini panas banget.",
    "Hari ini aku cuma lagi santai.",
]

HEDGING_CASES = [
    "Mungkin aku suka kopi kali ya.",
    "Kayaknya aku suka americano.",
    "Sepertinya aku lebih suka kopi.",
    "Mungkin nanti aku mau coba kopi.",
    "Aku rasa aku suka game ini.",
    "Kayaknya aku suka kopi.",
    "Sepertinya aku suka americano.",
    "Mungkin aku bakal suka game ini.",
    "Aku rasa mungkin aku suka warna biru.",
]

CONTRADICTION_SEQUENCE = [
    "Aku suka americano.",
    "Sekarang aku sudah tidak suka americano.",
]


@dataclass
class CaseResult:
    test_id: str
    category: str  # "explicit_fact" | "noise" | "hedging" | "contradiction"
    input_text: str
    expected: str
    actual_facts: list  # raw extract() output, atau None kalau error
    saved_count: int
    error: Optional[str] = None
    saved_memory_ids: list = field(default_factory=list)  # ID persis dari save_memory(), BUKAN dicari lagi lewat substring match

    @property
    def got_memory(self) -> bool:
        return self.saved_count > 0

    @property
    def passed(self) -> bool:
        if self.category == "contradiction":
            return True  # spec §5E: contradiction "boleh" jadi 2 memory, bukan fail
        if self.category == "explicit_fact":
            return self.got_memory and self.error is None
        # noise & hedging: lolos kalau TIDAK menghasilkan memory
        return (not self.got_memory) and self.error is None


@dataclass
class ProviderRun:
    provider_name: str  # "Gemini" | "Local"
    model_name: str
    results: list = field(default_factory=list)
    fatal_error: Optional[str] = None
    contradiction_final_state: list = field(default_factory=list)
    connectivity_ok: Optional[bool] = None  # None = belum dicek, True/False = hasil pre-check
    connectivity_detail: str = ""


def _connectivity_check(provider: LanguageModelProvider, provider_label: str) -> tuple:
    """v2.2.2 hotfix (respons atas temuan Teacher — 14/14 kasus Local
    kembali kosong tanpa satu pun error tercatat): `MemoryExtractor.
    extract()` menangkap SEMUA error provider secara internal dan cuma
    menulis log-nya ke FILE (logs/app.log), BUKAN ke console/laporan
    harness ini — jadi sebelumnya TIDAK ADA CARA membedakan "model
    memutuskan tidak ada fakta layak diingat" dari "provider gagal
    merespons sama sekali" hanya dari laporan yang dihasilkan.

    Fungsi ini memanggil `provider.generate()` LANGSUNG (di luar
    MemoryExtractor, TIDAK lewat try/except-nya yang menelan error) dengan
    SATU prompt trivial, SEBELUM test matrix jalan — supaya kalau provider
    memang tidak bisa dihubungi sama sekali (LM Studio belum jalan, model
    belum di-load, base_url salah, dst), itu ketahuan JELAS di awal,
    bukan tersamar sebagai "14/14 hasil kosong" yang ambigu."""
    from google.genai import types
    try:
        contents = [types.Content(role="user", parts=[types.Part(text="Balas dengan kata OK saja, tanpa tanda baca.")])]
        raw = provider.generate(contents)
        detail = f"Provider merespons: \"{(raw or '').strip()[:120]}\""
        print(f"  ✅ Connectivity check {provider_label}: OK — {detail}")
        return True, detail
    except ProviderError as e:
        detail = f"ProviderError: {e}"
        print(f"  ❌ Connectivity check {provider_label}: GAGAL — {detail}")
        return False, detail
    except Exception as e:
        detail = f"Exception tak terduga: {e}"
        print(f"  ❌ Connectivity check {provider_label}: GAGAL — {detail}")
        return False, detail


# ---------- Provider construction — pola IDENTIK dengan main_gui.py /
# Companion.__init__ (temperature=0.0, system_prompt=EXTRACTION_SYSTEM_PROMPT)
# supaya hasil test benar-benar merepresentasikan apa yang akan terjadi di
# aplikasi sungguhan, bukan konfigurasi test yang beda sendiri. ----------

def _build_gemini_extractor():
    from config.settings import GEMINI_API_KEY
    from config.constants import MODEL_NAME

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY kosong/tidak ditemukan di .env")

    provider = GeminiProvider(
        api_key=GEMINI_API_KEY,
        model_name=MODEL_NAME,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
    )
    return MemoryExtractor(provider=provider), MODEL_NAME, provider


def _build_local_extractor(model_name: str, base_url: str):
    provider = LocalProvider(
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        model_name=model_name,
        base_url=base_url,
        temperature=0.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    )
    return MemoryExtractor(provider=provider), model_name, provider


def _run_case(extractor: MemoryExtractor, memory_manager: MemoryManager,
              test_id: str, category: str, input_text: str, expected: str) -> CaseResult:
    try:
        facts = extractor.extract(input_text)
    except Exception as e:
        # v2.2.2 §5B "Provider error ditangani sesuai perilaku yang sudah
        # ada" — MemoryExtractor.extract() SUDAH menangkap ProviderError &
        # Exception internal sendiri (v2.2), jadi baris ini seharusnya
        # TIDAK PERNAH tereksekusi kecuali ada regresi. Tetap dijaga di
        # sini murni supaya SATU test case gagal tidak menghentikan
        # seluruh test run.
        return CaseResult(test_id, category, input_text, expected, None, 0, error=str(e))

    saved_count = 0
    saved_ids: list = []
    for fact in facts:
        try:
            saved = memory_manager.save_memory(fact.get("category", "general"), fact.get("content", ""))
            saved_count += 1
            saved_ids.append(saved.id)
        except Exception as e:
            return CaseResult(test_id, category, input_text, expected, facts, saved_count, error=f"save_memory gagal: {e}", saved_memory_ids=saved_ids)

    return CaseResult(test_id, category, input_text, expected, facts, saved_count, saved_memory_ids=saved_ids)


def _run_provider(provider_label: str, extractor_factory, test_id_prefix: str) -> ProviderRun:
    print(f"\n{'=' * 60}\n{provider_label} — menjalankan test...\n{'=' * 60}")

    try:
        extractor, model_name, provider = extractor_factory()
    except Exception as e:
        print(f"❌ Gagal menyiapkan provider {provider_label}: {e}")
        return ProviderRun(provider_label, "unknown", fatal_error=str(e))

    run = ProviderRun(provider_label, model_name)

    # v2.2.2 hotfix (temuan Teacher: 14/14 hasil Local kosong tanpa error
    # tercatat sama sekali — lihat _connectivity_check docstring). Kalau
    # provider TIDAK bisa dihubungi sama sekali, HENTIKAN di sini dengan
    # fatal_error yang jelas — JANGAN lanjut menjalankan 14 test case yang
    # hasilnya cuma akan kosong semua secara ambigu (tidak bisa dibedakan
    # dari "model menilai dengan benar tidak ada fakta").
    connectivity_ok, connectivity_detail = _connectivity_check(provider, provider_label)
    run.connectivity_ok = connectivity_ok
    run.connectivity_detail = connectivity_detail
    if not connectivity_ok:
        run.fatal_error = f"Connectivity check gagal, test matrix DIBATALKAN untuk provider ini: {connectivity_detail}"
        print(f"  ⚠️  {provider_label} TIDAK bisa dihubungi — test matrix untuk provider ini DILEWATI (bukan dipaksa jalan dengan hasil kosong yang ambigu).")
        return run

    # v2.2.2 hotfix: SQLite TEMPORARY, dibuang setelah proses selesai —
    # TIDAK PERNAH menyentuh database/memory.db (memori jangka panjang
    # Arona yang asli). MemoryManager dipakai APA ADANYA (bukan ditulis
    # ulang), cuma db_path-nya diarahkan ke file sementara — parameter ini
    # SUDAH ADA di constructor sejak awal, bukan penambahan baru.
    #
    # `ignore_cleanup_errors=True`: pertahanan lapis KEDUA. Akar masalah
    # asli (koneksi SQLite yang tidak pernah ditutup di
    # database/memory_manager.py -> PermissionError WinError 32 di Windows
    # saat direktori ini dibersihkan) SUDAH diperbaiki di sumbernya
    # (_connect() sekarang benar-benar menutup koneksi). Parameter ini
    # murni jaga-jaga tambahan supaya SEKALIPUN ada file lock transien lain
    # di masa depan (mis. antivirus Windows kebetulan sedang scan file
    # tepat saat itu), seluruh test run & laporan yang sudah susah payah
    # dikumpulkan TIDAK ikut hilang gara-gara crash di baris cleanup paling
    # akhir — direktori temp yang gagal dihapus akan dibersihkan OS sendiri
    # nanti (harmless, cuma beberapa KB).
    with tempfile.TemporaryDirectory(prefix="arona_memory_quality_test_", ignore_cleanup_errors=True) as tmpdir:
        temp_db_path = Path(tmpdir) / "test_memory.db"
        memory_manager = MemoryManager(db_path=temp_db_path)
        print(f"(Memory sementara khusus test — tidak menyentuh memory.db asli: {temp_db_path})\n")

        idx = 1
        for text in EXPLICIT_FACT_CASES:
            tid = f"{test_id_prefix}{idx:02d}"
            r = _run_case(extractor, memory_manager, tid, "explicit_fact", text, "Memory disimpan")
            run.results.append(r)
            _print_case(r)
            idx += 1

        for text in NOISE_CASES:
            tid = f"{test_id_prefix}{idx:02d}"
            r = _run_case(extractor, memory_manager, tid, "noise", text, "Tidak disimpan ([])")
            run.results.append(r)
            _print_case(r)
            idx += 1

        for text in HEDGING_CASES:
            tid = f"{test_id_prefix}{idx:02d}"
            r = _run_case(extractor, memory_manager, tid, "hedging", text, "Tidak disimpan ([])")
            run.results.append(r)
            _print_case(r)
            idx += 1

        # Contradiction — dijalankan TERAKHIR & BERURUTAN (bukan diacak),
        # supaya urutan "suka" lalu "tidak suka lagi" persis seperti
        # skenario Teacher yang sebenarnya. TIDAK ADA percobaan
        # supersede/replace di sini (spec §7 T04/T08: "Jangan melakukan
        # implementasi supersession hanya untuk membuat test ini terlihat
        # 'lulus'") — murni mencatat apa yang benar-benar terjadi.
        contradiction_results = []
        for i, text in enumerate(CONTRADICTION_SEQUENCE):
            tid = f"{test_id_prefix}{idx:02d}"
            r = _run_case(extractor, memory_manager, tid, "contradiction", text, "Catat hasil aktual")
            contradiction_results.append(r)
            run.results.append(r)
            _print_case(r)
            idx += 1

        final_memories = memory_manager.load_memories(limit=50)
        # v2.2.2 (fix hasil self-test harness): SEBELUMNYA dicari lewat
        # substring "americano" di content — ternyata salah tangkap kalau
        # ada test case LAIN (mis. explicit_fact "suka kopi americano")
        # yang kebetulan juga menyebut kata sama. Sekarang dilacak lewat
        # ID PERSIS yang dikembalikan save_memory() cuma untuk kedua
        # CONTRADICTION_SEQUENCE case di atas — presisi, tidak tergantung
        # isi teks test case lain sama sekali.
        contradiction_ids = {mid for r in contradiction_results for mid in r.saved_memory_ids}
        run.contradiction_final_state = [m for m in final_memories if m.id in contradiction_ids]

    return run


def _print_case(r: CaseResult) -> None:
    if r.error:
        status = "⚠️ ERROR"
    elif r.category == "contradiction":
        status = "📝 DICATAT"
    else:
        status = "✅ PASS" if r.passed else "❌ FAIL"
    saved = f"{r.saved_count} tersimpan" if r.saved_count else "tidak disimpan"
    print(f"  [{r.test_id}] {status} — \"{r.input_text}\" -> {saved}" + (f" ({r.error})" if r.error else ""))


# ---------- Laporan .md — format Validation Log Template (spec §10) +
# Test Matrix (spec §6) + Known Issue (spec §9), diisi otomatis dari hasil
# run di atas. ----------

def _quality_label(fp_rate: float, fn_rate: float) -> str:
    # v2.2.2 §11/§12: heuristik SARAN saja — keputusan PASS/CONDITIONAL
    # PASS/FAIL tetap keputusan Teacher/GPT (Decision Gate spec §12 penuh
    # pertimbangan kualitatif, bukan cuma angka), skor ini cuma bantu baca
    # cepat.
    if fp_rate == 0 and fn_rate == 0:
        return "Excellent"
    if fp_rate <= 0.15 and fn_rate == 0:
        return "Good"
    if fp_rate <= 0.3:
        return "Acceptable"
    if fp_rate <= 0.5:
        return "Weak"
    return "Fail"


def _build_report(runs: list) -> str:
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# v2.2.2 — Local Memory Quality Validation — Hasil Otomatis",
        "",
        f"Dijalankan: {now}",
        "",
        "Laporan ini dibuat otomatis oleh `test_memory_quality_validation.py`. "
        "T09 (GUI responsiveness) dan T10 (Developer Dashboard) TIDAK ada di "
        "sini — perlu observasi manual, lihat bagian paling bawah.",
        "",
        "## Provider Connectivity Check",
        "",
        "Dicek LANGSUNG ke provider (di luar MemoryExtractor, jadi error TIDAK "
        "tertelan try/except internal) SEBELUM test matrix jalan — supaya hasil "
        "kosong bisa dibedakan antara \"provider memang tidak bisa dihubungi\" "
        "vs \"model menilai dengan benar tidak ada fakta\".",
        "",
    ]

    for run in runs:
        status = "✅ OK" if run.connectivity_ok else ("❌ GAGAL" if run.connectivity_ok is False else "⚠️ Tidak dicek (gagal setup provider)")
        lines.append(f"- **{run.provider_name}**: {status} — {run.connectivity_detail or run.fatal_error or ''}")

    lines += [
        "",
        "## Test Matrix",
        "",
        "| Test | Provider | Kategori | Input | Expected | Actual | Status |",
        "|---|---|---|---|---|---|---|",
    ]

    for run in runs:
        if run.fatal_error:
            lines.append(f"| - | {run.provider_name} | - | - | - | GAGAL SETUP: {run.fatal_error} | ⚠️ |")
            continue
        for r in run.results:
            status = "⚠️" if r.error else ("📝" if r.category == "contradiction" else ("✅" if r.passed else "❌"))
            actual = r.error or (f"{len(r.actual_facts)} item -> {r.saved_count} tersimpan" if r.actual_facts is not None else "(tidak ada respons)")
            lines.append(f"| {r.test_id} | {run.provider_name} | {r.category} | {r.input_text} | {r.expected} | {actual} | {status} |")

    lines += ["", "## Validation Log (format sesuai spec §10)", ""]

    for run in runs:
        if run.fatal_error:
            continue
        lines.append(f"### {run.provider_name} ({run.model_name})")
        lines.append("")
        for r in run.results:
            lines += [
                "```text",
                f"Date: {now[:10]}",
                f"Provider: {run.provider_name}",
                f"Model: {run.model_name}",
                f"Input: {r.input_text}",
                f"Expected: {r.expected}",
                f"Actual: {r.actual_facts if r.actual_facts is not None else '(error)'}",
                f"Memory Saved: {'Yes (' + str(r.saved_count) + ')' if r.got_memory else 'No'}",
                "GUI Responsive: N/A (headless script, bukan lewat GUI)",
                f"Error: {r.error or 'None'}",
                f"Notes: test_id={r.test_id}, category={r.category}",
                "```",
                "",
            ]

    lines += ["## Quality Evaluation (per provider)", ""]

    for run in runs:
        if run.fatal_error:
            lines += [f"### {run.provider_name}", "", f"GAGAL SETUP: {run.fatal_error}", ""]
            continue

        fp_cases = [r for r in run.results if r.category in ("noise", "hedging")]
        fn_cases = [r for r in run.results if r.category == "explicit_fact"]
        fp_count = sum(1 for r in fp_cases if r.got_memory)
        fn_count = sum(1 for r in fn_cases if not r.got_memory)
        fp_rate = (fp_count / len(fp_cases)) if fp_cases else 0.0
        fn_rate = (fn_count / len(fn_cases)) if fn_cases else 0.0
        error_count = sum(1 for r in run.results if r.error)

        lines += [
            f"### {run.provider_name} ({run.model_name})",
            "",
            f"- Extraction Quality (saran otomatis, BUKAN keputusan final): **{_quality_label(fp_rate, fn_rate)}**",
            f"- False Positive Rate (noise/hedging yang salah tersimpan): {fp_count}/{len(fp_cases)} = {fp_rate:.0%}",
            f"- False Negative Rate (explicit fact yang gagal tersimpan): {fn_count}/{len(fn_cases)} = {fn_rate:.0%}",
            f"- Error/crash selama test: {error_count}/{len(run.results)} test case",
            "",
        ]

        if fp_count > 0:
            lines.append("**Detail false positive (harus ditinjau manual):**")
            lines.append("")
            for r in fp_cases:
                if r.got_memory:
                    lines.append(f"- [{r.test_id}] \"{r.input_text}\" -> tersimpan: {r.actual_facts}")
            lines.append("")

    lines += ["## Known Issue — Contradiction (spec §9, TIDAK diselesaikan di v2.2.2)", ""]

    for run in runs:
        if run.fatal_error:
            continue
        final_state = run.contradiction_final_state
        lines.append(f"### {run.provider_name} — kondisi akhir memori terkait 'americano' setelah kedua pesan contradiction dikirim:")
        lines.append("")
        if not final_state:
            lines.append("- (tidak ada entri tersimpan — kedua pesan contradiction tidak menghasilkan memory sama sekali di provider ini)")
        else:
            for m in final_state:
                lines.append(f"- [{m.category}] \"{m.content}\" (updated_at: {m.updated_at})")
            if len(final_state) > 1:
                lines.append("")
                lines.append(
                    f"⚠️ **Dikonfirmasi: {len(final_state)} entri kontradiktif hidup berdampingan** "
                    "— known issue dari v2.2/v2.2.1 masih terjadi di provider ini. Sesuai spec §5E/§9, "
                    "ini BUKAN kegagalan v2.2.2, cuma dicatat sebagai known issue yang masih terverifikasi ada."
                )
        lines.append("")

    lines += [
        "## Langkah Manual yang BELUM Tercakup Laporan Ini",
        "",
        "Script ini headless (tanpa GUI) — dua test berikut WAJIB dicek manual "
        "langsung di `main_gui.py`, tidak bisa diotomatisasi dengan jujur:",
        "",
        "- **T09 (Local Background Extraction):** set `MEMORY_PROVIDER=local`, chat "
        "beberapa kali berturut-turut, amati apakah jendela freeze/lag saat "
        "extraction jalan di background, apakah input tetap bisa diketik, "
        "apakah aplikasi tetap bisa ditutup normal (tidak hang saat close).",
        "- **T10 (Developer Dashboard):** buka Developer Dashboard, pastikan card "
        "\"Memory Extraction (Async)\" menunjukkan \"Provider: Local\" saat "
        "`MEMORY_PROVIDER=local`, dan \"Provider: Gemini\" saat di-set balik ke "
        "gemini (restart dibutuhkan tiap ganti, sesuai desain v2.2).",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="v2.2.2 — Local Memory Quality Validation test harness")
    parser.add_argument(
        "--provider", choices=["both", "gemini", "local"], default="both",
        help="Provider mana yang diuji (default: both)",
    )
    parser.add_argument("--model", default=None, help="Override nama model Local (default: LOCAL_PROVIDER_MODEL_NAME dari .env)")
    parser.add_argument("--base-url", default=None, help="Override base URL Local (default: LOCAL_PROVIDER_BASE_URL dari .env)")
    parser.add_argument("--output", default=None, help="Path file laporan .md (default: memory_quality_validation_<timestamp>.md)")
    args = parser.parse_args()

    runs = []

    if args.provider in ("both", "gemini"):
        runs.append(_run_provider("Gemini", _build_gemini_extractor, "T0"))

    if args.provider in ("both", "local"):
        from config.settings import LOCAL_PROVIDER_MODEL_NAME, LOCAL_PROVIDER_BASE_URL
        model_name = args.model or LOCAL_PROVIDER_MODEL_NAME
        base_url = args.base_url or LOCAL_PROVIDER_BASE_URL
        runs.append(_run_provider("Local", lambda: _build_local_extractor(model_name, base_url), "T1"))

    report = _build_report(runs)

    output_path = Path(args.output) if args.output else Path(
        f"memory_quality_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    )
    output_path.write_text(report, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"Selesai. Laporan lengkap ditulis ke: {output_path}")
    print(f"{'=' * 60}")

    any_fatal = any(r.fatal_error for r in runs)
    return 1 if any_fatal else 0


if __name__ == "__main__":
    sys.exit(main())