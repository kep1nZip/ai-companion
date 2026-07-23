from __future__ import annotations

from enum import Enum
from typing import Callable, Optional

from ai.companion import Companion, RateLimitError, CompanionError
from speech.recorder import Recorder
from speech.whisper import SpeechToText
from speech.tts import TextToSpeech
from speech.player import AudioPlayer
from config.logger import logger


class VoiceState(Enum):
    IDLE = "Ready"
    RECORDING = "Listening..."
    TRANSCRIBING = "Transcribing..."
    THINKING = "Thinking..."
    SPEAKING = "Speaking..."


class VoiceError(Exception):
    """Error umum di pipeline voice. Tidak pernah membuat aplikasi crash."""


class VoiceManager:
    """Koordinator lengkap pipeline suara. GUI HANYA boleh bicara ke class ini,
    tidak boleh memanggil Recorder/STT/TTS/Player secara langsung."""

    def __init__(
        self,
        companion: Companion,
        api_key: str,
        stt_model_size: str,
        tts_model_name: str,
        voice_name: str = "Kore",
        on_state_change: Optional[Callable[[VoiceState], None]] = None,
        on_audio_ready: Optional[Callable[[bytes, int], None]] = None,   # BARU
    ):
        self._companion = companion
        self._recorder = Recorder()
        self._stt = SpeechToText(model_size=stt_model_size)
        self._tts = TextToSpeech(api_key=api_key, model_name=tts_model_name, voice_name=voice_name)
        self._player = AudioPlayer()
        self._state = VoiceState.IDLE
        self._on_state_change = on_state_change
        self._on_audio_ready = on_audio_ready   # BARU — VoiceManager TIDAK TAHU ini lip sync atau apa

    @property
    def state(self) -> VoiceState:
        return self._state

    def set_state_listener(self, callback: Callable[[VoiceState], None]) -> None:
        self._on_state_change = callback

    def _set_state(self, state: VoiceState) -> None:
        self._state = state
        logger.info("Voice state -> {}", state.name)
        if self._on_state_change:
            self._on_state_change(state)

    def start_recording(self) -> None:
        self._recorder.start()
        self._set_state(VoiceState.RECORDING)

    def cancel_recording(self) -> None:
        self._recorder.stop()
        self._set_state(VoiceState.IDLE)
        logger.info("Recording cancelled by Teacher.")

    def stop_recording_and_respond(self) -> tuple[str, str]:
        """Blocking. Jalankan di background thread dari sisi GUI.
        Return (teks_ucapan_teacher, balasan_arona)."""
        audio, samplerate = self._recorder.stop()

        self._set_state(VoiceState.TRANSCRIBING)
        try:
            user_text = self._stt.transcribe(audio, samplerate)
        except Exception as e:
            self._set_state(VoiceState.IDLE)
            logger.exception("STT failed: {}", e)
            raise VoiceError("Arona tidak bisa mendengar dengan jelas, Teacher...") from e

        if not user_text:
            self._set_state(VoiceState.IDLE)
            logger.warning("STT returned empty text.")
            raise VoiceError("Arona tidak menangkap suara apa pun, coba lagi ya, Teacher.")

        logger.info("STT success: {}", user_text)

        self._set_state(VoiceState.THINKING)
        try:
            reply = self._companion.chat(user_text)
        except RateLimitError as e:
            self._set_state(VoiceState.IDLE)
            raise VoiceError(
                "(Dark Blue Dripping Halo) Arona sedang lelah karena terlalu banyak berpikir..."
            ) from e
        except CompanionError as e:
            self._set_state(VoiceState.IDLE)
            raise VoiceError(f"(Eh?) Ada masalah sistem, Teacher... {e}") from e

        self._speak(reply)
        return user_text, reply

    def speak(self, text: str) -> None:
        """Ucapkan teks apa pun lewat TTS+Player. Dipakai juga untuk balasan dari chat TEKS,
        bukan cuma dari alur voice. Tidak memanggil Companion/STT sama sekali."""
        self._speak(text)

    def _speak(self, text: str) -> None:
        self._set_state(VoiceState.SPEAKING)
        try:
            pcm = self._tts.synthesize(text)
            if pcm is None:
                logger.info("Melewati playback — tidak ada teks yang terucapkan.")
            else:
                if self._on_audio_ready:
                    try:
                        self._on_audio_ready(pcm, TextToSpeech.SAMPLE_RATE)
                    except Exception as e:
                        logger.warning("Audio-ready hook gagal, playback tetap lanjut: {}", e)

                self._player.play(pcm, samplerate=TextToSpeech.SAMPLE_RATE)
        except Exception as e:
            logger.exception("TTS/Playback failed: {}", e)
        finally:
            self._set_state(VoiceState.IDLE)