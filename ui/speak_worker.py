from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from speech.voice_manager import VoiceManager, VoiceState


class SpeakWorker(QThread):
    """Jalankan TTS + playback untuk teks apa pun (misal balasan dari chat teks) di background."""

    state_changed = Signal(str)
    finished_speaking = Signal()

    def __init__(self, voice_manager: VoiceManager, text: str):
        super().__init__()
        self._voice_manager = voice_manager
        self._text = text
        self._voice_manager.set_state_listener(self._emit_state)

    def _emit_state(self, state: VoiceState) -> None:
        self.state_changed.emit(state.value)

    def run(self) -> None:
        self._voice_manager.speak(self._text)
        self.finished_speaking.emit()