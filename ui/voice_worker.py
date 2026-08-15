from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from speech.voice_manager import VoiceManager, VoiceError, VoiceState


class VoiceWorker(QThread):
    """Menjalankan pipeline voice (STT → Companion → TTS → Playback) via
    VoiceManager di background thread. GUI TIDAK PERNAH memanggil
    Recorder/SpeechToText/TextToSpeech/AudioPlayer langsung — semua lewat
    VoiceManager, worker ini cuma menjembatani ke Qt Signal."""

    state_changed = Signal(str)
    reply_ready = Signal(str, str)  # (user_text, reply_text)
    error_occurred = Signal(str)

    def __init__(self, voice_manager: VoiceManager):
        super().__init__()
        self._voice_manager = voice_manager
        self._voice_manager.set_state_listener(self._emit_state)

    def _emit_state(self, state: VoiceState) -> None:
        self.state_changed.emit(state.value)

    def run(self) -> None:
        try:
            user_text, reply = self._voice_manager.stop_recording_and_respond()
            self.reply_ready.emit(user_text, reply)

        except VoiceError as e:
            self.error_occurred.emit(str(e))

        except Exception as e:
            self.error_occurred.emit(f"Terjadi kesalahan tak terduga, Teacher... {e}")