"""
Kalkulator Initiative Score — berdiri sendiri, TIDAK menyentuh Companion/GUI/
database apa pun. Memakai KODE ASLI initiative/initiative_rules.py langsung
(bukan re-implementasi terpisah) — jadi angka yang keluar di sini DIJAMIN
sama persis dengan yang bakal muncul di app beneran untuk input yang sama.

Cara pakai:
    python test_initiative_calculator.py

Isi angka sesuai apa yang kamu lihat (Developer Dashboard / Routine page /
log app.log), kalkulator ini akan tunjukkin skor totalnya PLUS rincian
aturan mana yang nyala/mati dan kenapa — supaya nggak nebak-nebak lagi."""

from __future__ import annotations

import sys

from initiative.initiative_rules import DecisionContext, DEFAULT_RULES, DEFAULT_THRESHOLD, check_suppression
from behavior.behavior_state import BehaviorState
from behavior.relationship_state import RelationshipState, DimensionValue
from behavior.internal_state import InternalState
from behavior.mood import Mood
from behavior.energy import EnergyState
from behavior.curiosity import CuriosityState
from behavior.initiative_state import InitiativeState
from behavior.emotion_state import DEFAULT_EMOTION_STATE
from routine.routine_event import RoutineEvent, RoutineEventType, EventPriority
from datetime import datetime, timedelta, timezone


def ask_int(prompt: str, default: int) -> int:
    raw = input(f"{prompt} [{default}]: ").strip()
    return int(raw) if raw else default


def ask_float(prompt: str, default: float) -> float:
    raw = input(f"{prompt} [{default}]: ").strip()
    return float(raw) if raw else default


def ask_yes_no(prompt: str, default: bool) -> bool:
    raw = input(f"{prompt} (y/n) [{'y' if default else 'n'}]: ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def ask_mood() -> Mood:
    options = [m.value for m in Mood]
    print(f"Pilihan mood: {', '.join(options)}")
    raw = input(f"Mood Arona saat ini [neutral]: ").strip().lower()
    try:
        return Mood(raw) if raw else Mood.NEUTRAL
    except ValueError:
        print(f"'{raw}' tidak dikenal, pakai 'neutral'.")
        return Mood.NEUTRAL


def main() -> int:
    print("=" * 60)
    print("KALKULATOR INITIATIVE SCORE (pakai rule asli)")
    print("=" * 60)
    print("Isi sesuai kondisi yang kamu lihat di app. Kosongkan buat pakai default.\n")

    idle_minutes = ask_float("Sudah berapa menit idle (nggak ada interaksi)?", 15.0)
    trust = ask_int("Trust (0-100)", 0)
    comfort = ask_int("Comfort (0-100)", 0)
    affection = ask_int("Affection (0-100)", 0)
    mood = ask_mood()
    energy = ask_int("Energy (0-100)", 50)
    curiosity = ask_int("Curiosity level (0-100)", 4)
    initiative_level = ask_int("Internal Initiative level (0-100)", 2)
    routine_pending = ask_yes_no("Ada Routine event pending (status 'Current Routine' terisi)?", True)
    is_voice_active = ask_yes_no("Mic sedang aktif dipakai?", False)
    is_actively_typing = ask_yes_no("Sedang ngetik di kolom chat (belum kirim)?", False)

    relationship = RelationshipState(
        trust=DimensionValue(base=trust, current=trust),
        comfort=DimensionValue(base=comfort, current=comfort),
        affection=DimensionValue(base=affection, current=affection),
        respect=DimensionValue(base=0, current=0),
        familiarity=DimensionValue(base=0, current=0),
    )
    internal = InternalState(
        mood=mood,
        energy=EnergyState(value=energy),
        curiosity=CuriosityState(level=curiosity, topic=None),
        initiative=InitiativeState(level=initiative_level),
    )
    behavior_state = BehaviorState(
        emotion=DEFAULT_EMOTION_STATE,
        relationship=relationship,
        internal=internal,
    )

    routine_event = None
    if routine_pending:
        now = datetime.now(timezone.utc)
        routine_event = RoutineEvent(
            event_type=RoutineEventType.IDLE_CHAT,
            priority=EventPriority.LOW,
            payload="(contoh routine buat kalkulator)",
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )

    ctx = DecisionContext(
        idle_seconds=idle_minutes * 60,
        behavior_state=behavior_state,
        vision_context=None,
        routine_event=routine_event,
        hour=datetime.now().hour,
    )

    suppressed, suppression_reason = check_suppression(None, is_voice_active, is_actively_typing)

    print("\n" + "=" * 60)
    print("HASIL:")
    print("=" * 60)

    if suppressed:
        print(f"❌ SUPPRESSED — skor otomatis jadi 0, apa pun kondisi lain.")
        print(f"   Alasan: {suppression_reason}")
        print("\n   Ini override paksa — bukan soal kurang poin, tapi sistem")
        print("   sengaja bungkam total selagi kondisi ini aktif.")
        return 0

    total = 0.0
    print("Rincian per aturan:\n")
    for rule in DEFAULT_RULES:
        reason = rule.evaluate(ctx)
        if reason is not None:
            total += rule.weight
            sign = "+" if rule.weight >= 0 else ""
            print(f"  ✅ {rule.name:20s} {sign}{rule.weight:>6.1f}   ({reason})")
        else:
            print(f"  ⬜ {rule.name:20s} {'':>7}   (tidak aktif)")

    print(f"\n  {'TOTAL':20s} {total:>7.1f}   vs threshold {DEFAULT_THRESHOLD:.0f}")

    if total >= DEFAULT_THRESHOLD:
        print(f"\n✅ LOLOS ({total:.0f} >= {DEFAULT_THRESHOLD:.0f}) — Arona akan mengambil inisiatif.")
    else:
        kurang = DEFAULT_THRESHOLD - total
        print(f"\n❌ BELUM LOLOS — kurang {kurang:.0f} poin.")
        print("   Aturan yang TIDAK aktif di atas (⬜) itu yang bisa nambahin skor")
        print("   kalau kondisinya berubah (nunggu lebih dekat relationshipnya,")
        print("   mood lagi bagus, curiosity/initiative internal naik, dsb).")

    return 0


if __name__ == "__main__":
    sys.exit(main())