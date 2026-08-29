"""
Diagnosa mikrofon — berdiri sendiri, TIDAK menyentuh Companion/GUI/model apa
pun. Tujuannya cuma satu: buktikan apakah mikrofon BENERAN menangkap suara
kamu dengan jelas, sebelum menuduh Whisper/kode yang salah.

Cara pakai:
    python test_microphone.py

Ini akan:
  1. List semua input device yang Windows/PortAudio kenali, tandai mana yang
     jadi DEFAULT (yang dipakai app tanpa kamu pilih apa-apa).
  2. Rekam 5 detik — SILAKAN NGOMONG pas hitungan mundur selesai.
  3. Simpan hasilnya sebagai microphone_test.wav — BUKA & DENGERIN file itu.
  4. Kasih laporan angka: volume rata-rata & puncak, biar kamu nggak cuma
     nebak "kedengeran" tapi ada angkanya juga.

Kalau pas didengerin file .wav itu SEPI/HENING padahal kamu jelas-jelas
ngomong pas rekam — itu BUKTI device default salah / mic ke-block, BUKAN
bug di kode Companion/Whisper. Kalau suaranya kedengeran jelas tapi
transcribe di app tetap kosong/aneh, baru itu kemungkinan soal lain (model
Whisper-nya, bukan mic-nya) — kabari saya dengan hasil ini."""

from __future__ import annotations

import sys
import time
import wave

import numpy as np
import sounddevice as sd


def list_devices() -> None:
    print("=" * 60)
    print("DAFTAR INPUT DEVICE (mikrofon) yang dikenali sistem:")
    print("=" * 60)
    devices = sd.query_devices()
    default_input_idx = sd.default.device[0]
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            marker = "  <-- DEFAULT (ini yang dipakai app kamu)" if idx == default_input_idx else ""
            print(f"[{idx}] {dev['name']}  (input channels: {dev['max_input_channels']}){marker}")
    print()


def record_test(duration: float = 5.0, samplerate: int = 16000) -> np.ndarray:
    print(f"Bersiap rekam {duration:.0f} detik lewat device DEFAULT di atas...")
    for i in range(3, 0, -1):
        print(f"  mulai dalam {i}...")
        time.sleep(1)
    print(">>> NGOMONG SEKARANG <<<")

    audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="float32")
    sd.wait()
    print(">>> Selesai merekam. <<<\n")
    return audio.flatten()


def save_wav(audio: np.ndarray, path: str, samplerate: int = 16000) -> None:
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio_int16.tobytes())


def report(audio: np.ndarray) -> None:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0

    print("=" * 60)
    print("HASIL:")
    print("=" * 60)
    print(f"  Volume puncak (peak) : {peak:.4f}   (skala 0.0 - 1.0)")
    print(f"  Volume rata-rata (RMS): {rms:.4f}")
    print()

    if peak < 0.01:
        print("❌ HAMPIR TOTAL HENING. Mic ini TIDAK menangkap suara sama sekali.")
        print("   -> Cek: device default di atas itu mic yang BENAR? Coba ganti")
        print("      default recording device di Windows Sound Settings, atau")
        print("      cek Settings > Privacy & Security > Microphone > pastikan")
        print("      'Let desktop apps access your microphone' AKTIF.")
    elif peak < 0.05:
        print("⚠️  Suara KETANGKEP tapi SANGAT PELAN. Ini kemungkinan besar")
        print("   penyebab hasil Whisper kosong/ngaco (termasuk halusinasi")
        print("   bahasa aneh yang sempat muncul di log kamu).")
        print("   -> Naikkan gain/volume mic di Windows Sound Settings, atau")
        print("      dekatkan posisi mic, atau cek mic fisiknya sendiri.")
    else:
        print("✅ Volume kedengeran cukup sehat secara angka.")
        print("   -> SILAKAN BUKA microphone_test.wav dan dengerin langsung.")
        print("      Kalau suara kamu jelas di situ tapi Whisper di app tetap")
        print("      ngaco, kemungkinan bukan soal mic lagi — kabari saya hasil")
        print("      ini + file .wav-nya (atau deskripsi apa yang kedengeran).")
    print()


def main() -> int:
    try:
        list_devices()
        audio = record_test()
        save_wav(audio, "microphone_test.wav")
        report(audio)
        print("File tersimpan: microphone_test.wav (di folder yang sama dengan script ini)")
        print("BUKA & DENGERIN file itu sebelum menyimpulkan apa pun.")
        return 0
    except Exception as e:
        print(f"❌ Gagal merekam sama sekali: {e}")
        print("   Ini sendiri sudah jadi info penting — kabari saya pesan error ini persis.")
        return 1


if __name__ == "__main__":
    sys.exit(main())