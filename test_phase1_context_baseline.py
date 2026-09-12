"""
v2.9 Phase 1 — Baseline Measurement.

Bagian SIZE (message count, character count, estimated tokens) bisa
dijalankan di mana saja TANPA provider asli — murni konstruksi Conversation
sintetis + `Companion.get_context_debug_snapshot()` yang sudah ada (v2.9
Phase 0/7). Bagian LATENCY (context_assembly_latency_ms, llm_latency_ms,
kualitas reference resolution) BUTUH LM Studio/Gemini API asli — kalau tidak
ada, script tetap jalan dan cuma melewati bagian itu dengan catatan jelas.

Cara pakai:
    python test_phase1_context_baseline.py

Output: baseline size SELALU tercetak. Kalau GEMINI_API_KEY/LM Studio
tersedia, latency & 1 tes reference-resolution nyata (Scenario C) ikut
dijalankan dan dicetak.
"""
from __future__ import annotations

from ai.companion import Companion
from developer.performance_debug import PerformanceTracker


def _print_scenario(name: str, companion: Companion) -> None:
    snap = companion.get_context_debug_snapshot()
    print(f"--- {name} ---")
    print(f"  History messages : {snap['history_message_count']}")
    print(f"  History chars    : {snap['history_characters']}")
    print(f"  Ephemeral chars  : {snap['ephemeral_context_characters']}")
    print(f"  Est. total chars : {snap['estimated_total_characters']}")
    print(f"  Est. tokens (kasar, chars/4): {snap['estimated_context_tokens']}")
    print()


def scenario_a_short(companion: Companion) -> None:
    """5-10 pesan — expected: tidak ada filtering, tidak ada information loss."""
    msgs = [
        ("Halo Arona!", "Hai Teacher! Ada yang bisa dibantu?"),
        ("Aku lagi coding nih.", "Semangat ya! Lagi ngerjain apa?"),
        ("Bikin API sederhana.", "Wah seru, pakai framework apa?"),
        ("FastAPI.", "Nice, FastAPI emang enak buat prototyping cepat."),
    ]
    for user, reply in msgs:
        companion._conversation.add_user_message(user)
        companion._conversation.add_assistant_message(reply)
    _print_scenario("Scenario A — Short (5-10 pesan)", companion)


def scenario_b_medium(companion: Companion) -> None:
    """20-40 pesan — ukur history size, prompt size."""
    for i in range(15):
        companion._conversation.add_user_message(f"Pertanyaan teknis nomor {i} soal database indexing.")
        companion._conversation.add_assistant_message(f"Jawaban singkat nomor {i}: pakai B-tree index untuk kasus ini.")
    _print_scenario("Scenario B — Medium (+30 pesan lagi, total lebih panjang)", companion)


def scenario_c_multi_topic(companion: Companion) -> str:
    """Multi-topic: A1 A2 A3 B1 B2 C1 D1 D2 A-followup — return followup text
    untuk dites reference resolution kalau provider asli tersedia."""
    topics = [
        ("Kenapa API-ku error 500?", "Coba cek log server dulu."),
        ("Udah, ternyata null pointer.", "Coba tambah null check di handler-nya."),
        ("Oke, fixed! Makasih.", "Sama-sama Teacher!"),
        ("Eh ganti topik, kucingku sakit nih.", "Waduh, semoga cepat sembuh ya."),
        ("Udah dibawa ke dokter kok.", "Bagus, semoga hasilnya baik."),
        ("Btw aku juga lagi belajar Rust.", "Rust emang menantang tapi worth it!"),
        ("Rencana weekend mau healing ke pantai.", "Asik, semoga cuacanya bagus!"),
        ("Ntar aku ajak temen juga.", "Seru tuh, hati-hati di jalan ya."),
    ]
    for user, reply in topics:
        companion._conversation.add_user_message(user)
        companion._conversation.add_assistant_message(reply)
    _print_scenario("Scenario C — Multi-topic (sebelum follow-up)", companion)
    return "Eh balik lagi ke soal API tadi, null pointer-nya kenapa bisa muncul ya?"


def main():
    print("v2.9 Phase 1 — Baseline Measurement (bagian SIZE, deterministik)\n")

    companion = Companion(performance_tracker=PerformanceTracker())

    scenario_a_short(companion)

    companion_b = Companion(performance_tracker=PerformanceTracker())
    # scenario B dibangun DI ATAS percakapan yang sudah ada (persis kondisi nyata:
    # history terus bertambah dalam satu sesi, bukan direset tiap skenario)
    scenario_a_short(companion_b)
    scenario_b_medium(companion_b)

    companion_c = Companion(performance_tracker=PerformanceTracker())
    followup_text = scenario_c_multi_topic(companion_c)

    print("--- Scenario D/E (Autonomous & Voice/Text) ---")
    print("  Dikonfirmasi via audit kode (v2.9 Phase 0), bukan run-time test:")
    print("  - _build_autonomous_contents() memakai Conversation & cap yang SAMA")
    print("    dengan _build_contents() (dikonfirmasi baca kode, sekarang timernya juga sama).")
    print("  - Voice & Text sama-sama panggil Companion.chat() yang sama (satu Conversation).")
    print()

    # --- Bagian yang BUTUH provider asli ---
    try:
        print("--- Mencoba tes reference resolution nyata (Scenario C follow-up) ---")
        reply = companion_c.chat(followup_text)
        print(f"  Follow-up: {followup_text!r}")
        print(f"  Balasan Arona: {reply!r}")
        snap = companion_c.get_context_debug_snapshot()
        print(f"  context_assembly_latency_ms: {snap['context_assembly_latency_ms']:.2f}")
        print(f"  llm_latency_ms: {snap['llm_latency_ms']:.2f}")
        print()
        print("  -> Baca manual: apakah balasan Arona nyambung ke 'null pointer' dari")
        print("     3 topik yang lalu (bukan salah nyambung ke kucing/Rust/pantai)?")
    except Exception as e:
        print(f"  Dilewati — butuh LM Studio/Gemini API asli untuk tes ini: {type(e).__name__}: {e}")

    print()
    print("Baseline size selesai. Latency & reference-resolution TERGANTUNG provider asli Teacher.")


if __name__ == "__main__":
    main()