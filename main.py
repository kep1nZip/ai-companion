from ai.companion import Companion, RateLimitError, CompanionError
from ai.commands import is_command, run_command
from ai.providers.factory import build_language_provider, build_memory_provider
from config.constants import APP_NAME, VERSION
from config.logger import logger


def print_banner(ai_model_name: str) -> None:
    print("=" * 40)
    print(f" {APP_NAME} v{VERSION}")
    print(f" Model: {ai_model_name}")
    print("=" * 40)
    print("Ketik /help untuk melihat daftar perintah.\n")


def main() -> None:
    logger.info("Application starting. {} v{}", APP_NAME, VERSION)

    # v2.4 Phase 1 — Configuration Cleanup: SEBELUMNYA `Companion()` dipanggil
    # polos tanpa provider apa pun di sini, jadi CLI diam-diam SELALU pakai
    # Gemini terlepas dari AI_PROVIDER/MEMORY_PROVIDER di .env (Provider Map
    # v2.4 Phase 0 §7 — temuan audit). Sekarang reuse factory yang SAMA
    # dengan main_gui.py (ai/providers/factory.py, TIDAK ditulis ulang) —
    # env yang sama sekarang menghasilkan provider yang sama, apa pun
    # entrypoint yang Teacher jalankan (GUI atau CLI).
    #
    # Vision SENGAJA TIDAK diikutkan di CLI ini — CLI tidak pernah punya
    # screen capture loop sama sekali sejak awal, menambahkannya sekarang
    # akan jadi subsystem baru di luar scope v2.4 (audit provider, bukan
    # penambahan fitur).
    provider, ai_model_name = build_language_provider()
    memory_provider, memory_model_name = build_memory_provider()

    print_banner(ai_model_name)
    companion = Companion(
        provider=provider,
        memory_provider=memory_provider,
        ai_model_name=ai_model_name,
        memory_model_name=memory_model_name,
    )
    print("Prompt berhasil dimuat.")
    print(f"{APP_NAME} siap, Teacher.\n")

    while True:
        user_input = input("Teacher: ").strip()

        if not user_input:
            continue

        if is_command(user_input):
            result = run_command(user_input, companion)
            print(f"Arona: {result.message}\n")

            if result.should_exit:
                logger.info("Application exiting via /exit command.")
                # v2.1: pastikan worker Memory Extraction background
                # (ai/memory_worker.py) tidak bertahan setelah CLI keluar —
                # sama seperti ui/window.py closeEvent, tapi untuk jalur CLI.
                companion.shutdown()
                break

            continue

        try:
            reply = companion.chat(user_input)
            print(f"Arona: {reply}\n")

        except RateLimitError:
            print(
                "Arona: (Dark Blue Dripping Halo) Maaf Teacher, Arona sedang lelah "
                "karena terlalu banyak berpikir... Tolong tunggu sebentar lagi ya...\n"
            )

        except CompanionError as e:
            print(f"Arona: (Eh?) Ada masalah sistem, Teacher... Error: {e}\n")


if __name__ == "__main__":
    main()