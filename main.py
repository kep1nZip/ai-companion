from ai.companion import Companion, RateLimitError, CompanionError
from ai.commands import is_command, run_command
from config.constants import APP_NAME, VERSION, MODEL_NAME
from config.logger import logger


def print_banner() -> None:
    print("=" * 40)
    print(f" {APP_NAME} v{VERSION}")
    print(f" Model: {MODEL_NAME}")
    print("=" * 40)
    print("Ketik /help untuk melihat daftar perintah.\n")


def main() -> None:
    logger.info("Application starting. {} v{}", APP_NAME, VERSION)

    print_banner()
    companion = Companion()
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