from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, set_key

from config import constants
from config.settings import GEMINI_API_KEY, AI_PROVIDER, LOCAL_PROVIDER_MODEL_NAME
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
    untuk klasifikasi lengkap tiap field beserta alasannya), KECUALI
    ai_provider & local_provider_model_name (v2.0 Step 9 — sama seperti
    GEMINI_API_KEY, keduanya sudah punya mekanisme persistence nyata lewat
    .env sejak v2.0 Step 6, cuma belum pernah di-expose ke GUI)."""

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
    ai_provider: str  # v2.0 Step 9: "local" | "gemini"
    local_provider_model_name: str  # v2.0 Step 9


class SettingsService:
    """Boundary non-Qt antara Settings GUI dan configuration source
    (config/constants.py, config/settings.py, .env). TIDAK membuat sistem
    konfigurasi baru — field yang ditulis lewat class ini adalah
    GEMINI_API_KEY dan (v2.0 Step 9) AI_PROVIDER/LOCAL_PROVIDER_MODEL_NAME,
    semuanya lewat python-dotenv yang SUDAH jadi dependency project
    (config/settings.py sendiri sudah pakai `load_dotenv()`). Tidak menyentuh
    database, tidak menyentuh JSON baru, tidak menyentuh subsystem lain."""

    _VALID_PROVIDERS = ("local", "gemini")  # v2.0 Step 9 §8: cuma provider yang benar2 diimplementasikan

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
            ai_provider=AI_PROVIDER,
            local_provider_model_name=LOCAL_PROVIDER_MODEL_NAME,
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

        self._write_env_key("GEMINI_API_KEY", value.strip())
        logger.info("SettingsService: API key diperbarui di .env (restart dibutuhkan untuk berlaku).")

    # ---------- Provider (v2.0 Step 9) ----------

    def validate_provider(self, value: str) -> str | None:
        if value.strip().lower() not in self._VALID_PROVIDERS:
            return f"Provider must be one of: {', '.join(self._VALID_PROVIDERS)}."
        return None

    def validate_local_model_name(self, value: str) -> str | None:
        """Sekadar cek non-empty (§12: 'verify what the existing architecture
        can safely verify, such as endpoint/model configuration') — BUKAN
        live connectivity check ke LM Studio. Health-check subsystem baru
        eksplisit dilarang spec (§12)."""
        if not value.strip():
            return "Local model name cannot be empty."
        return None

    def save_provider_settings(self, provider: str, local_model_name: str) -> None:
        """Tulis AI_PROVIDER + LOCAL_PROVIDER_MODEL_NAME ke .env yang sama.
        Reuse nama config yang SUDAH ADA sejak v2.0 Step 6 (§19) — tidak ada
        nama alternatif baru. Restart tetap wajib (provider di-construct
        SEKALI saat startup di main_gui.py, lihat §10-11 — tidak ada
        hot-swap)."""
        provider_error = self.validate_provider(provider)
        if provider_error:
            raise SettingsSaveError(provider_error)

        normalized_provider = provider.strip().lower()
        if normalized_provider == "local":
            model_error = self.validate_local_model_name(local_model_name)
            if model_error:
                raise SettingsSaveError(model_error)
            self._write_env_key("LOCAL_PROVIDER_MODEL_NAME", local_model_name.strip())

        self._write_env_key("AI_PROVIDER", normalized_provider)
        logger.info(
            "SettingsService: AI provider diperbarui ke '{}' di .env (restart dibutuhkan untuk berlaku).",
            normalized_provider,
        )

    # ---------- Shared .env write helper ----------

    def _write_env_key(self, key: str, value: str) -> None:
        # BUGFIX (temuan Teacher): SEBELUMNYA pakai find_dotenv(usecwd=True)
        # di sini — itu resolve berdasar CURRENT WORKING DIRECTORY app
        # di-launch. config/settings.py sendiri pakai load_dotenv() POLOS,
        # yang secara default (usecwd=False) resolve berdasar LOKASI FILE
        # PEMANGGILNYA (call stack), bukan CWD. Kalau app dijalankan dari
        # shortcut/launcher yang working directory-nya beda dari folder
        # project (umum di Windows), DUA cara ini bisa nemuin file .env yang
        # BEDA — tulisan "berhasil" tapi ke file yang salah, jadi tidak
        # pernah kebaca ulang pas restart. Sekarang dipanggil TANPA
        # usecwd=True, supaya strategi pencarian SAMA PERSIS dengan yang
        # dipakai config/settings.py — walk-up dari lokasi file ini sendiri
        # (ui/settings_service.py), yang tetap konvergen ke .env yang sama
        # di root project terlepas dari CWD app.
        dotenv_path = find_dotenv()
        if not dotenv_path:
            logger.warning("SettingsService: file .env tidak ditemukan, gagal menyimpan {}.", key)
            raise SettingsSaveError(
                "Unable to save settings. Your previous configuration is still active."
            )

        logger.info("SettingsService: menulis {} ke {}", key, dotenv_path)

        try:
            set_key(dotenv_path, key, value)
        except Exception as e:
            logger.warning("SettingsService: gagal menulis .env ({}): {}", key, e)
            raise SettingsSaveError(
                "Unable to save settings. Your previous configuration is still active."
            ) from e