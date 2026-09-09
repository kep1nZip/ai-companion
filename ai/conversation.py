from __future__ import annotations
from google.genai import types


class Conversation:
    """Riwayat percakapan SEMENTARA (in-memory only) untuk sesi yang sedang
    berjalan — BUKAN penyimpanan permanen. Sengaja dipisah total dari
    MemoryManager/SQLite (persistent, jangka panjang); keduanya TIDAK BOLEH
    digabung (Human-in-the-Loop Memory Policy, v0.3). Menyimpan objek
    `types.Content` mentah, siap dikirim langsung ke Gemini API tanpa
    transformasi tambahan."""

    def __init__(self):
        self._history: list[types.Content] = []

    def add_user_message(self, text: str) -> None:
        self._history.append(
            types.Content(role="user", parts=[types.Part(text=text)])
        )

    def add_assistant_message(self, text: str) -> None:
        self._history.append(
            types.Content(role="model", parts=[types.Part(text=text)])
        )

    def rollback_last_message(self) -> None:
        if self._history:
            self._history.pop()

    def clear(self) -> None:
        self._history.clear()

    def get_history(self, max_messages: int | None = None) -> list[types.Content]:
        """v2.6 Phase 6 (Context Budget) — `max_messages` OPSIONAL, default
        `None` = TIDAK ADA BATAS, PERSIS perilaku sebelum v2.6 (zero behavior
        change kecuali Teacher eksplisit mengaktifkannya).

        SENGAJA tidak ada angka default yang "disarankan" di sini — spec
        v2.6 §12/§21 eksplisit: "Awali dengan baseline aktual... Gunakan
        baseline nyata Teacher", BUKAN angka yang saya tebak sendiri.
        Baseline itu sekarang bisa diamati lewat Developer Dashboard (Phase
        10 — section "Context" menampilkan jumlah message history saat
        ini). Setelah Teacher lihat angka aktualnya, baru masuk akal
        menentukan batas lewat `CONVERSATION_HISTORY_MAX_MESSAGES` di
        `.env` (lihat config/settings.py).

        `max_messages` membatasi jumlah RAW Content (bukan "turn" — satu
        turn biasanya 2 Content [user+assistant], tapi bisa ganjil kalau
        ada `rollback_last_message()` yang belum sempat dibalas) — dipotong
        dari yang PALING LAMA, mempertahankan N pesan PALING BARU (paling
        relevan ke percakapan saat ini)."""
        if max_messages is None or max_messages <= 0 or len(self._history) <= max_messages:
            return list(self._history)
        return list(self._history[-max_messages:])

    def message_count(self) -> int:
        """v2.6 Phase 10 (Observability) — dipakai Developer Dashboard untuk
        menampilkan baseline nyata ukuran history, TANPA memotong apa pun."""
        return len(self._history)