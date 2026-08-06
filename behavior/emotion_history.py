from __future__ import annotations

from behavior._ring_buffer import RingBufferHistory
from behavior.emotion_state import EmotionState


class EmotionHistory(RingBufferHistory[EmotionState]):
    """Riwayat perubahan emosi SEMENTARA (in-memory, belum persisten). Sesuai spec:
    'SQLite integration comes later if needed' — v0.6.2 belum menyentuh
    database/memory_manager.py untuk history ini."""
    pass