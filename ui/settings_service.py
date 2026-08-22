from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, set_key

from config import constants
from config.settings import GEMINI_API_KEY
from config.logger import logger


class SettingsSaveError(Exception):
    """Terjadi saat penyimpanan setting gagal (mis. .env tidak ditemukan/tidak
    bisa ditulis). Pesan exception ini AMAN ditampilkan ke user — tidak pernah
    mengandung nilai secret."""


@dataclass(frozen=True)
class SettingsSnapshot:
    """Snapshot read-only konfigurasi aktual. SENGAJA TIDAK menyimpan nilai
    mentah GEMINI_API_KEY (cuma boolean `api_key_configured`) — supaya
    snapshot ini aman di-pass/di-log/di-export kapan pun tanpa risiko bocor,
    walau di masa depan ada yang lupa dan menaruhnya ke Developer Snapshot.
    Semua field lain murni Read Only: tidak ada setter/persistence mechanism
    nyata untuk field-field ini di source aktual (lih. V1_4_CLAUDE_CONTEXT.md
    untuk klasifikasi lengkap tiap field beserta alasannya)."""

    version: str
    theme: str
    model_name: str
    api_key_configured: bool
    tts_model_name: str
    tts_voice_name: str
    stt_model_size: str
    vtube_studio_url: str
    vtube_model_config_path: str
    vtube_token_present: bool


class SettingsService:
    """Boundary non-Qt antara Settings GUI dan configuration source
    (config/constants.py, config/settings.py, .env). TIDAK membuat sistem
    konfigurasi baru — SATU-SATUNYA field yang ditulis lewat class ini adalah
    GEMINI_API_KEY, lewat python-dotenv yang SUDAH jadi dependency project
    (config/settings.py sendiri sudah pakai `load_dotenv()`). Tidak menyentuh
    database, tidak menyentuh JSON baru, tidak menyentuh subsystem lain."""

    def get_snapshot(self) -> SettingsSnapshot:
        return SettingsSnapshot(
            version=constants.VERSION,
            theme="Dark",
            model_name=constants.MODEL_NAME,
            api_key_configured=bool(GEMINI_API_KEY),
            tts_model_name=constants.TTS_MODEL_NAME,
            tts_voice_name=constants.TTS_VOICE_NAME,
            stt_model_size=constants.STT_MODEL_SIZE,
            vtube_studio_url=constants.VTUBE_STUDIO_URL,
            vtube_model_config_path=constants.VTUBE_MODEL_CONFIG_PATH,
            vtube_token_present=Path(constants.VTUBE_TOKEN_PATH).exists(),
        )

    def reveal_api_key(self) -> str:
        """Dipanggil HANYA saat Teacher eksplisit klik 'Show' di GUI. Tidak
        pernah dipanggil otomatis, tidak pernah masuk snapshot, tidak pernah
        di-log."""
        return GEMINI_API_KEY or ""

    def validate_api_key(self, value: str) -> str | None:
        """Return pesan error kalau tidak valid, None kalau valid. Aturan
        non-empty ini BUKAN dikarang di sini — config/settings.py sendiri
        sudah raise RuntimeError kalau GEMINI_API_KEY kosong saat startup,
        jadi validasi ini konsisten dengan kontrak yang sudah ada."""
        if not value.strip():
            return "API Key cannot be empty."
        return None

    def save_api_key(self, value: str) -> None:
        """Tulis ke .env yang SAMA yang dibaca config/settings.py — dicari
        pakai find_dotenv() (bukan path ditebak/hardcode). TIDAK mengubah
        config.settings.GEMINI_API_KEY di memori: GeminiClient/VoiceManager/
        dst sudah construct sekali pakai nilai lama, mengubah modul attribute
        setelah itu tidak akan berefek nyata dan cuma menyesatkan (restart
        tetap wajib)."""
        error = self.validate_api_key(value)
        if error:
            raise SettingsSaveError(error)

        dotenv_path = find_dotenv(usecwd=True)
        if not dotenv_path:
            logger.warning("SettingsService: file .env tidak ditemukan, gagal menyimpan API key.")
            raise SettingsSaveError(
                "Unable to save settings. Your previous configuration is still active."
            )

        try:
            set_key(dotenv_path, "GEMINI_API_KEY", value.strip())
        except Exception as e:
            logger.warning("SettingsService: gagal menulis .env: {}", e)
            raise SettingsSaveError(
                "Unable to save settings. Your previous configuration is still active."
            ) from e

        logger.info("SettingsService: API key diperbarui di .env (restart dibutuhkan untuk berlaku).")