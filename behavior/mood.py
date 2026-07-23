from __future__ import annotations

from enum import Enum


class Mood(Enum):
    """Kecenderungan emosional JANGKA PANJANG Arona. Beda dari Emotion (jangka
    pendek, per-pesan) — Mood TIDAK langsung mengikuti Emotion, cuma bergeser
    kalau ada TREN emosi yang konsisten dari waktu ke waktu (lihat
    internal_state_rules.propose_mood)."""

    NEUTRAL = "neutral"
    CHEERFUL = "cheerful"
    CALM = "calm"
    SLEEPY = "sleepy"
    LONELY = "lonely"
    CURIOUS = "curious"
    FOCUSED = "focused"
    RELAXED = "relaxed"


DEFAULT_MOOD = Mood.NEUTRAL