from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from google.genai import types

from ai.personality import load_prompts
from ai.prompt_builder import build_system_prompt
from ai.providers.base import LanguageModelProvider, ProviderError, ProviderRateLimitError, ProviderResponseError
from ai.providers.gemini_provider import GeminiProvider
from ai.conversation import Conversation
from ai.memory_extractor import (
    MemoryExtractor,
    EXTRACTION_SYSTEM_PROMPT,
    RELATION_NEW,
    RELATION_DUPLICATE,
    RELATION_UPDATE,
    RELATION_SUPERSEDES,
)
from ai.conversation_signals import detect_closure, detect_style_preference
# v3.3 Phase 1+3 (Conversation Anchor Detection + Contextual Memory Query) —
# `extract_keywords`/`filter_search_keywords` SATU-SATUNYA tempat definisi
# "kata signifikan untuk pencarian memori" (sebelumnya diduplikasi inline di
# 2 tempat file ini, lihat docstring `ai/reference_signals.py`).
# `detect_reference_signal` murni sinyal observasional (pola IDENTIK
# `detect_closure` di atas), dipakai HANYA untuk Developer Dashboard +
# menentukan kapan anchor conversation dicoba di `_select_relevant_memories`.
from ai.reference_signals import detect_reference_signal, extract_keywords, filter_search_keywords
# v3.4 Phase 1+2 (Memory Relevance Ranking) — modul BARU, pure/deterministic
# (lihat docstring `ai/memory_ranking.py`), dipakai `_search_memories_by_
# keywords()` untuk meranking kandidat SEBELUM dipangkas ke budget akhir.
from ai.memory_ranking import rank_and_select, score_memory, RetrievalOutcome
# v3.5 Phase 1/2/4/8 (Temporal Awareness & Task Continuity) — modul BARU,
# pure/deterministic (lihat docstring `ai/temporal_signals.py`), TIDAK
# menggantikan `ai/reference_signals.py` (v3.3) sama sekali — dua sistem
# independen, dipakai bersamaan (spec §8 Phase 3).
from ai.temporal_signals import detect_temporal_signals, format_memory_age, TemporalSignals
from ai.memory_worker import MemoryExtractionWorker, MemoryWorkerStatus
from ai.context_builder import ContextBuilder, categorize_continuity
from database.memory_manager import MemoryManager, Memory
from behavior.behavior_engine import BehaviorEngine
from behavior.behavior_state import BehaviorState, DEFAULT_BEHAVIOR_STATE
from vision.vision import Vision
from vision.vision_context import VisionContext
from config.settings import GEMINI_API_KEY, CONVERSATION_HISTORY_MAX_MESSAGES
from config.constants import MODEL_NAME, EPHEMERAL_CONTEXT_MEMORY_LIMIT, MEMORY_CANDIDATE_POOL_LIMIT, ROUTINE_TIMEZONE
from config.logger import logger

from routine.routine import Routine
from routine.routine_event import RoutineEvent

from initiative.initiative import Initiative
from initiative.initiative_decision import DecisionResult

from developer.performance_debug import PerformanceTracker


from developer.performance_debug import PerformanceTracker

# v3.3 hotfix ROUND 3 — dipakai `_build_contents()` untuk menyaring kandidat
# yang layak masuk note klarifikasi ambigu (lihat komentar lengkap di sana).
# Kandidat #2 dst harus punya skor `ai/memory_ranking.py::score_memory()`
# minimal RATIO ini dikali skor kandidat #1 supaya dianggap "kemungkinan
# yang sama masuk akal" — di bawah itu dianggap noise (mis. cuma cocok satu
# keyword generik/nama Arona sendiri), bukan kandidat bersaing sungguhan.
# Angka 0.6 dipilih dari perbandingan konkret 2 skenario nyata (lihat
# `test_v3_3_reference_recall.py` T70): kandidat ambigu yang GENUINE (mis.
# "LeadEstate" vs "project Arona", sama-sama match >=1 keyword spesifik)
# rasio skornya ~0.7-0.8; kandidat NOISE (cuma match nama Arona sendiri vs
# kandidat yang match 3 keyword sekaligus) rasionya ~0.2-0.3 — ambang 0.6
# memisahkan keduanya dengan jelas tanpa perlu tuning rumit.
_REFERENCE_NOTE_SCORE_RATIO = 0.6
_REFERENCE_NOTE_MAX_CANDIDATES = 3


class RateLimitError(Exception):
    """Terjadi saat Gemini API membalas rate limit (429)."""


class CompanionError(Exception):
    """Error umum lain dari Gemini API."""


def _format_memories(memories: list[Memory], now: Optional[datetime] = None) -> str:
    if not memories:
        return ""
    # v3.5 Phase 8 (Memory Freshness Awareness) — `now` OPSIONAL (default
    # None = perilaku IDENTIK sebelum v3.5, backward-compat penuh untuk
    # pemanggil lama). Kalau diisi, tiap baris memory dapat sufiks usia
    # ringkas ("~2 jam lalu") lewat `format_memory_age()` (`ai/temporal_
    # signals.py`) — MURNI tampilan, TIDAK mengubah `status`/urutan/isi
    # memory apa pun (spec §13: "Old ≠ false"). `age` `None` (updated_at
    # kosong/tidak valid) -> tidak ada sufiks sama sekali, bukan error.
    lines = []
    for m in memories:
        age = format_memory_age(m.updated_at, now) if now is not None else None
        suffix = f" (diperbarui {age})" if age else ""
        lines.append(f"- ({m.category}) {m.content}{suffix}")
    return "Berikut hal-hal yang Arona ingat tentang Teacher:\n" + "\n".join(lines)


def _persist_fact(memory_manager: MemoryManager, fact: dict, history: Optional[list] = None) -> Optional[Memory]:
    """v2.5 Phase 4 (Persistence Semantics, §11 spec): SATU-SATUNYA tempat
    yang menerjemahkan relation hasil keputusan MemoryExtractor jadi
    panggilan MemoryManager yang benar. Module-level (BUKAN method
    Companion) supaya bisa dipanggil dari closure `_extract_and_save` tanpa
    closure itu perlu meng-capture `self` (v2.1 §11/§12 — lihat
    `_schedule_memory_extraction`), DAN supaya bisa direuse langsung oleh
    `test_memory_quality_validation.py` (v2.5 Phase 6/9 — "Maximum reuse",
    bukan menulis ulang logic dispatch yang sama di file test).

    Return value (`Optional[Memory]`) SENGAJA ditambahkan supaya pemanggil
    (test harness) bisa melacak id memory hasil akhir — closure produksi di
    `_schedule_memory_extraction` TETAP mengabaikan return value ini persis
    seperti sebelumnya (tidak ada perubahan perilaku produksi). Return
    `None` untuk relation DUPLICATE (touch_memory tidak membuat/mengubah
    row yang perlu dilacak lewat objek Memory baru) atau kalau persist
    gagal.

    Dibungkus try/except PER FAKTA (bukan per-batch) — satu fakta gagal
    dipersist (mis. target_memory_id sudah tidak ada di DB sama sekali,
    walau sudah difilter di extract()) TIDAK BOLEH menggagalkan fakta
    lain dalam pesan yang sama (§25 guardrail #9 "Avoid destructive
    deletion", error isolation konsisten dengan pola MemoryExtractionWorker
    v2.1 §22/§31).

    v3.2 Phase 6 (Memory Explainability) — `history` OPSIONAL, default
    `None` = perilaku IDENTIK sebelum v3.2 (backward-compat penuh, termasuk
    untuk `test_memory_quality_validation.py` yang memanggil fungsi ini
    tanpa argumen ketiga). Kalau diisi (list, mutable — dikirim closure
    produksi sebagai REFERENSI ke `Companion._memory_decision_history`,
    BUKAN `self` yang di-capture, tetap patuh aturan v2.1 §11/§12), setiap
    panggilan menambah SATU record berisi relation/category/content/outcome
    — data yang SUDAH ADA & deterministik sejak v2.5 (`MemoryExtractor.
    extract()` sudah menghitung `relation`), cuma SEBELUMNYA hilang begitu
    saja setelah `_persist_fact()` selesai. Tidak ada LLM/reasoning baru
    dipanggil di sini — murni mencatat keputusan yang sudah terjadi."""
    relation = fact.get("relation", RELATION_NEW)
    category = fact["category"]
    content = fact["content"]
    target_id = fact.get("target_memory_id")
    record = {
        "timestamp": datetime.now(timezone.utc),
        "category": category,
        "content": content,
        "relation": relation,
        "target_memory_id": target_id,
        "outcome": None,
        "error": None,
    }

    try:
        if relation == RELATION_SUPERSEDES and target_id is not None:
            result = memory_manager.supersede_memory(target_id, category, content)
            record["outcome"] = "superseded"
            return result
        elif relation == RELATION_UPDATE and target_id is not None:
            memory_manager.update_memory(target_id, content=content, category=category)
            record["outcome"] = "updated"
            return None
        elif relation == RELATION_DUPLICATE and target_id is not None:
            memory_manager.touch_memory(target_id)
            record["outcome"] = "duplicate_ignored"
            return None
        else:
            # RELATION_NEW, atau relation lain tapi target_id kosong
            # (seharusnya sudah di-fallback ke NEW oleh MemoryExtractor.
            # extract(), ini jaring pengaman kedua — bukan jalur yang
            # diharapkan tereksekusi dalam kondisi normal).
            result = memory_manager.save_memory(category, content)
            record["outcome"] = "saved"
            return result
    except Exception as e:
        record["outcome"] = "failed"
        record["error"] = str(e)
        logger.warning("Gagal mempersist fakta memori (relation={}): {}", relation, e)
        return None
    finally:
        if history is not None:
            history.append(record)


class Companion:
    """Backend inti, UI-independent. Mengoordinasikan Conversation, Memory,
    Behavior Engine, Vision, Routine, Initiative — SEMUA opsional/read-only dari
    sisi Companion, Companion tetap cuma orchestrator."""

    def __init__(
        self,
        vision: Optional[Vision] = None,
        enable_routine: bool = True,
        enable_initiative: bool = True,
        performance_tracker: Optional[PerformanceTracker] = None,
        provider: Optional[LanguageModelProvider] = None,
        memory_provider: Optional[LanguageModelProvider] = None,
        ai_model_name: Optional[str] = None,
        memory_model_name: Optional[str] = None,
    ):
        prompts = load_prompts()
        system_prompt = build_system_prompt(prompts)

        # v2.0 §35: Companion sekarang bergantung pada LanguageModelProvider
        # (abstrak), TIDAK PERNAH pada GeminiClient secara langsung. Default
        # tetap GeminiProvider (Gemini TIDAK dihapus, cuma jadi salah satu
        # implementasi) — parameter `provider` opsional supaya provider lain
        # (local/free, masih di luar cakupan v2.0 langkah ini) bisa disuntik
        # nanti TANPA mengubah Companion lagi. Konstruktor lama yang tidak
        # mengisi `provider` tetap jalan persis seperti sebelumnya.
        self._gemini: LanguageModelProvider = provider or GeminiProvider(
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            system_prompt=system_prompt,
        )
        # v2.4 Phase 2 (Runtime Observability): pola IDENTIK
        # `_memory_provider_name` di bawah — nama provider Language
        # Generation SEBELUMNYA tidak bisa diobservasi sama sekali dari luar
        # Companion (Provider Map v2.4 Phase 0 §8: satu-satunya dari 3
        # subsystem provider yang tidak punya getter). `ai_model_name`
        # OPSIONAL — kalau composition root tidak mengisinya (mis. kode lama
        # yang belum diupdate, atau test yang construct Companion() polos),
        # fallback ke MODEL_NAME (nama Gemini default), TIDAK PERNAH None,
        # supaya Dashboard tidak perlu menangani kasus kosong secara khusus.
        self._ai_provider_name = "local" if provider is not None else "gemini"
        self._ai_model_name = ai_model_name or MODEL_NAME
        self._conversation = Conversation()
        self._memory_manager = MemoryManager()
        # v3.2 Phase 6+7 (Memory Explainability + Developer Observability) —
        # in-memory murni (TIDAK ADA database baru, TIDAK ADA MemoryManager2),
        # rolling window sederhana (pola sama dengan `PerformanceTracker`,
        # developer/performance_debug.py) supaya tidak tumbuh tanpa batas.
        # Data yang dicatat SUDAH deterministik & sudah ada sejak v2.5/v2.7
        # (relation model, hasil retrieval) — cuma sebelumnya hilang begitu
        # saja setelah dipakai sekali. Hilang total kalau app di-restart —
        # ini DISENGAJA (observability sesi berjalan, bukan histori
        # permanen — kalau permanen dibutuhkan itu jadi milestone lain).
        self._memory_decision_history: list[dict] = []
        self._recall_decision_history: list[dict] = []
        # v3.3 hotfix round 3 (temuan Teacher: note klarifikasi ambigu di
        # `_build_contents()` sempat mendaftar memory yang TIDAK relevan
        # sebagai "kandidat", karena hotfix round 2 mengambil `memories[:5]`
        # apa adanya tanpa cek seberapa jauh skornya dari kandidat teratas).
        # Cache skor deterministik (`ai/memory_ranking.py::score_memory()`)
        # dari pemanggilan `_select_relevant_memories()` PALING TERAKHIR —
        # diisi ulang SETIAP kali method itu dipanggil, dibaca `_build_
        # contents()` tepat setelahnya (pemanggilan sinkron, sama thread,
        # tidak ada risiko balapan). BUKAN riwayat/database — cuma "hasil
        # perhitungan satu giliran terakhir", persis seperti kenapa
        # `_recall_decision_history` juga in-memory & sekali pakai per
        # observability, cuma ini TIDAK di-log sebagai histori (terlalu
        # sering berubah untuk berguna sebagai riwayat).
        self._last_recall_scores: dict[int, float] = {}
        # v3.5 Phase 11/15 — cache read-only murni untuk Developer
        # Dashboard, pola IDENTIK `_last_recall_scores` di atas. `None`
        # sebelum chat() pertama kali dipanggil (belum ada sinyal apa pun
        # untuk di-cache).
        self._last_temporal_signals: Optional[TemporalSignals] = None
        self._MEMORY_HISTORY_LIMIT = 30
        # v2.2 §21 (Developer Diagnostics): simpan NAMA provider yang benar2
        # dipakai (bukan re-deteksi dari type() nanti) — murni string
        # read-only untuk Developer Dashboard, tidak memengaruhi extract()
        # sama sekali.
        self._memory_provider_name = "local" if memory_provider is not None else "gemini"
        # v2.4 Phase 2: pola identik _ai_model_name di atas.
        self._memory_model_name = memory_model_name or MODEL_NAME
        # v2.2 §8/§10: pola IDENTIK dengan `self._gemini` di atas — parameter
        # `memory_provider` opsional supaya provider Memory Extraction bisa
        # disuntik (Local, lewat main_gui.py) TANPA Companion perlu tahu apa
        # pun soal Gemini/Local/LM Studio. Default kalau tidak disuntik:
        # GeminiProvider BARU (instance TERPISAH dari self._gemini di atas,
        # SENGAJA — chat utama & Memory Extraction butuh system_prompt DAN
        # temperature yang beda total, lihat catatan panjang di
        # ai/providers/gemini_provider.py & ai/memory_extractor.py) yang
        # dikonfigurasi khusus untuk ekstraksi: system_prompt =
        # EXTRACTION_SYSTEM_PROMPT (BUKAN persona Arona), temperature=0.0
        # (deterministic — v2.2 §13 "factuality + conservative extraction",
        # SAMA PERSIS dengan config yang dipakai `google.genai.Client`
        # langsung di v2.1, cuma sekarang lewat GeminiProvider).
        self._memory_extractor = MemoryExtractor(
            provider=memory_provider or GeminiProvider(
                api_key=GEMINI_API_KEY,
                model_name=MODEL_NAME,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                temperature=0.0,
            )
        )
        # v2.1 — Async Memory Extraction: MemoryExtractor & MemoryManager
        # TIDAK berubah sama sekali (v2.1 Rule 2/3) — cuma DIPANGGIL secara
        # berbeda sekarang, lewat worker background ini alih-alih inline di
        # chat() (lihat _schedule_memory_extraction). max_workers=1: task
        # dijamin jalan satu per satu, jadi kita tidak perlu membuktikan
        # MemoryExtractor/MemoryManager aman dipanggil dari banyak thread
        # SEKALIGUS — cukup aman dipanggil dari SATU thread lain yang bukan
        # main/GUI thread, yang sudah terpenuhi (MemoryManager membuka
        # koneksi SQLite baru tiap panggilan, tidak pernah menyimpan
        # connection sebagai state bersama — lihat database/memory_manager.py).
        # v2.2 §18: satu worker thread ini TETAP dipakai apa adanya untuk
        # provider Local juga — TIDAK ditambah worker count sekadar karena
        # Local inference lebih lambat dari Gemini (§18 eksplisit melarang
        # ini); task tetap serial, satu per satu.
        self._memory_worker = MemoryExtractionWorker()

        self._behavior_engine = BehaviorEngine(memory_manager=self._memory_manager)
        self._context_builder = ContextBuilder()
        self._vision = vision
        self._routine = Routine(memory_manager=self._memory_manager) if enable_routine else None
        self._initiative = Initiative(memory_manager=self._memory_manager) if enable_initiative else None

        self._performance = performance_tracker

        logger.info("Companion backend initialized. Model: {}", MODEL_NAME)

    def _timed(self, name: str, fn):
        if self._performance is None:
            return fn()
        with self._performance.timer(name):
            return fn()

    def chat(self, user_input: str) -> str:
        self._conversation.add_user_message(user_input)
        logger.info("Teacher: {}", user_input)

        behavior_state = self._timed("behavior_update", lambda: self._update_behavior(user_input))
        vision_context = self._vision.get_context() if self._vision else None
        routine_event = (
            self._timed("routine_update", lambda: self._routine.update(behavior_state, vision_context))
            if self._routine else None
        )
        decision_result = (
            self._timed(
                "initiative_update",
                lambda: self._initiative.update(
                    behavior_state, vision_context, routine_event,
                    relevant_memory_count=self._count_relevant_memories_for_vision(vision_context),
                    conversation_closed=self._detect_conversation_closure(),
                ),
            )
            if self._initiative else None
        )

        contents = self._build_contents(user_input, behavior_state, vision_context, routine_event, decision_result)

        try:
            # v2.4 Phase 1 (Provider Consistency): log sekarang menyebut nama
            # provider yang BENAR-BENAR aktif (self._ai_provider_name),
            # BUKAN literal "Gemini" — SEBELUMNYA baris ini tetap tertulis
            # "Gemini Request" walau AI_PROVIDER=local, membingungkan saat
            # membaca log (Provider Map v2.4 Phase 0 §1). Tidak ada
            # perubahan behavior, murni teks log.
            logger.info("{} Request", self._ai_provider_name.capitalize())
            reply = self._timed("gemini", lambda: self._gemini.generate(contents))
            self._conversation.add_assistant_message(reply)
            logger.info("{} Reply", self._ai_provider_name.capitalize())
            logger.info("Arona: {}", reply)

            # BUGFIX: sebelumnya routine_event ditandai "completed" (masuk
            # Recent History, mulai cooldown) HANYA karena Gemini berhasil
            # membalas APA PUN — padahal Routine cuma dikirim sebagai
            # "saran" (Routine Suggestion) yang Gemini bebas abaikan.
            # Akibatnya: Stretch/Lunch Reminder bisa tercatat "selesai" di
            # Recent History walau Arona sama sekali tidak menyinggungnya
            # (mis. Teacher lagi ngobrol topik lain). Sekarang HANYA ditandai
            # selesai kalau Initiative juga bilang ini momen yang pas untuk
            # proaktif (decision_result.should_start) — kalau tidak, event
            # tetap pending sampai expired atau sampai momen yang benar-benar
            # kondusif tiba.
            if routine_event and self._routine and decision_result and decision_result.should_start:
                self._routine.mark_completed(routine_event)
            if decision_result and decision_result.should_start and self._initiative:
                self._initiative.mark_started()

        # v2.0: Companion sekarang cuma menangkap exception PROVIDER-AGNOSTIC
        # (ai/providers/base.py) — logic deteksi "429"/dsb sudah pindah ke
        # dalam GeminiProvider (v2.0 §34: itu tanggung jawab provider, bukan
        # Companion). Kalau nanti provider lain (local) aktif, blok except
        # ini TIDAK PERLU diubah sama sekali.
        except ProviderResponseError as e:
            self._conversation.rollback_last_message()
            logger.warning("Balasan provider kosong, pesan Teacher di-rollback: {}", e)
            raise CompanionError(
                "Arona kehabisan kata-kata sesaat, Teacher... coba ulangi lagi ya."
            ) from e

        except ProviderRateLimitError as e:
            self._conversation.rollback_last_message()
            logger.warning("Rate limit hit: {}", e)
            raise RateLimitError(str(e)) from e

        except ProviderError as e:
            self._conversation.rollback_last_message()
            logger.error("Provider error: {}", e)
            raise CompanionError(str(e)) from e

        # v2.1 §10 Ordering Rule: dipanggil SETELAH reply divalidasi & masuk
        # Conversation (add_assistant_message di atas sudah terjadi, dan kita
        # sudah lewat blok except tanpa exception) — TAPI cuma untuk
        # MENJADWALKAN, bukan menunggu hasilnya. Baris ini sendiri tidak
        # memblokir apa pun (submit() di MemoryExtractionWorker return
        # seketika) — chat() return SEKARANG tidak lagi menunggu Gemini
        # extraction call kedua seperti sebelum v2.1.
        self._schedule_memory_extraction(user_input)
        return reply

    def check_autonomous_opportunity(
        self, is_voice_active: bool = False, is_actively_typing: bool = False
    ) -> Optional[str]:
        """v1.8 — Autonomous Interaction Pipeline. Dipanggil TANPA user_input,
        dari trigger periodik GUI (lihat ui/window.py). BUKAN orchestrator
        kedua — reuse persis subsystem yang sama dengan chat() (Behavior read,
        Routine.update(), Vision.get_context(), Initiative.update(),
        ContextBuilder, Gemini, Conversation). Bedanya cuma dua: (1) tidak ada
        pesan Teacher yang ditambahkan ke history karena memang Teacher tidak
        mengetik apa pun, (2) Gemini HANYA dipanggil kalau
        decision_result.should_start == True (Autonomous Permission Policy —
        'Initiative decides whether Arona may speak. Gemini decides what
        Arona says.'). Return None berarti Arona tetap diam — ini hasil yang
        VALID dan diharapkan di sebagian besar pemanggilan."""
        if self._initiative is None:
            return None

        behavior_state = self.current_behavior_state()
        vision_context = self._vision.get_context() if self._vision else None
        routine_event = (
            self._timed("routine_update", lambda: self._routine.update(behavior_state, vision_context))
            if self._routine else None
        )

        decision_result = self._timed(
            "initiative_update",
            lambda: self._initiative.update(
                behavior_state, vision_context, routine_event,
                is_voice_active=is_voice_active, is_actively_typing=is_actively_typing,
                relevant_memory_count=self._count_relevant_memories_for_vision(vision_context),
                conversation_closed=self._detect_conversation_closure(),
            ),
        )

        if not decision_result.should_start:
            return None

        contents = self._build_autonomous_contents(behavior_state, vision_context, routine_event, decision_result)
        if not contents:
            logger.warning("Autonomous context kosong, batal bicara.")
            return None

        try:
            logger.info("{} Request (Autonomous)", self._ai_provider_name.capitalize())
            reply = self._timed("gemini", lambda: self._gemini.generate(contents))
            self._conversation.add_assistant_message(reply)
            logger.info("{} Reply (Autonomous)", self._ai_provider_name.capitalize())
            logger.info("Arona (Autonomous): {}", reply)

            if routine_event and self._routine:
                self._routine.mark_completed(routine_event)
            self._initiative.mark_started()

            # v2.1 §18 catatan: giliran otonom SENGAJA tidak menjadwalkan
            # memory extraction di sini. MemoryExtractor.extract() adalah
            # kontrak yang membaca SATU PESAN TEACHER (lihat system prompt
            # di ai/memory_extractor.py: "baca satu pesan dari Teacher") —
            # pada giliran otonom TIDAK ADA pesan Teacher sama sekali (itu
            # sebabnya method ini dipanggil tanpa parameter user_input).
            # Mengekstrak dari balasan Arona sendiri akan mengubah makna
            # ekstraksi (v2.1 Rule 42/Stop Condition #9: semantik ekstraksi
            # tidak boleh berubah substansial di milestone ini) — jadi
            # perilaku di sini SAMA seperti sebelum v2.1 (giliran otonom
            # memang tidak pernah memicu memory extraction, dikonfirmasi
            # lewat inspeksi kode v1.8-v2.0 sebelum perubahan ini dibuat).
            return reply

        except ProviderError as e:
            # v1.8 §30: kegagalan otonom TIDAK BOLEH crash & TIDAK BOLEH
            # menampilkan pesan error ke Teacher (Teacher tidak meminta apa
            # pun) — log, tetap diam, tunggu kesempatan berikutnya. v2.0:
            # ProviderError adalah base class ProviderResponseError/
            # ProviderRateLimitError, jadi satu except ini menangkap semuanya
            # persis seperti (GeminiResponseError, ClientError) sebelumnya.
            logger.warning("Autonomous Gemini call gagal, tetap diam: {}", e)
            return None

    # ---------- Conversation ----------

    def get_history(self) -> list[types.Content]:
        return self._conversation.get_history()

    def clear_history(self) -> None:
        self._conversation.clear()
        logger.info("Conversation history cleared.")

    def get_context_debug_snapshot(self) -> dict:
        """v2.6 Phase 10 (Observability) — READ-ONLY, murni untuk Developer
        Dashboard. TIDAK memicu apa pun (tidak capture Vision baru, tidak
        query provider apa pun) — cuma membaca state yang SUDAH ada.

        `history_cap` None berarti unbounded (default v2.6 — lihat
        CONVERSATION_HISTORY_MAX_MESSAGES di config/settings.py, Phase 6).
        `vision_fresh` True kalau `current_vision_context()` mengembalikan
        sesuatu (Vision.get_context() SUDAH memfilter stale sejak v1.5.2,
        lihat v2.6 Phase 0 Audit §3 — jadi non-None DI SINI selalu berarti
        fresh, tidak pernah stale).

        v2.9 Phase 0/1/7 (Context Scaling Audit/Observability) — field baru:
        - `history_characters`: jumlah karakter history yang BENAR-BENAR
          akan terkirim (sudah kena cap kalau aktif) — dihitung langsung
          dari `Conversation._history`, bukan estimasi.
        - `ephemeral_context_characters`: panjang teks Ephemeral Context
          SAAT INI (dihitung dengan memanggil `ContextBuilder.build()` yang
          sudah ada — fungsi murni/deterministik, TIDAK ada efek samping,
          TIDAK memicu Vision capture baru apa pun, aman dipanggil kapan
          saja). Memory Context TIDAK diikutkan di sini — ukurannya
          tergantung query pesan Teacher yang belum tentu ada saat snapshot
          diminta (Dashboard bisa dibuka kapan saja, bukan cuma pas ada
          chat aktif) — dicatat eksplisit sebagai keterbatasan, BUKAN
          disamarkan sebagai angka lengkap (§7 spec v2.9: "hanya data yang
          benar-benar tersedia").
        - `estimated_context_tokens`: estimasi KASAR (karakter / 4 — rule of
          thumb umum, BUKAN tokenizer sungguhan — spec v2.9 §6 eksplisit
          melarang menambah dependency tokenizer baru cuma untuk ini).
          Diberi label "estimated" di semua tempat ditampilkan, tidak pernah
          diklaim sebagai angka pasti.
        - `context_assembly_latency_ms` / `llm_latency_ms`: reuse
          `PerformanceTracker` yang SUDAH ADA sejak v2.2 (`self._performance`,
          key "context_assembly" baru ditambahkan v2.9 di `_build_contents()`/
          `_build_autonomous_contents()`, key "gemini" SUDAH ADA sejak awal
          untuk durasi panggilan provider apa pun yang aktif — TIDAK pernah
          benar-benar Gemini-only, cuma nama key historis)."""
        vision_context = self._vision.get_context() if self._vision else None
        try:
            active_memory_count = len(self._memory_manager.load_memories(limit=10_000))
        except Exception:
            active_memory_count = None

        # v2.8 Phase 20 — SEMUA angka di bawah dihitung dari data yang SUDAH
        # ADA (Conversation._history + cap v2.6 + detektor closure v2.8),
        # TIDAK ADA nilai yang dikarang (spec v2.8 §20 eksplisit: "Tidak
        # boleh ada nilai yang dibuat-buat"). "Current Topic"/"Follow-up
        # Detected"/"Topic Shift" SENGAJA TIDAK ditambahkan di sini — audit
        # Phase 0 v2.8 §9 membuktikan itu butuh classifier sungguhan untuk
        # diisi jujur, yang berarti STOP CONDITION #1 spec ("Topic detection
        # requires another LLM") — bukan keputusan yang saya ambil sepihak.
        history_available = self._conversation.message_count()
        capped_history = self._conversation.get_history(max_messages=CONVERSATION_HISTORY_MAX_MESSAGES)
        recent_turns_used = len(capped_history)
        history_characters = sum(
            len(part.text or "") for content in capped_history for part in (content.parts or [])
        )

        try:
            ephemeral_context_characters = len(
                self._context_builder.build(self.current_behavior_state(), vision_context=vision_context)
            )
        except Exception as e:
            logger.warning("Gagal hitung ukuran ephemeral context untuk debug snapshot: {}", e)
            ephemeral_context_characters = None

        estimated_total_characters = history_characters + (ephemeral_context_characters or 0)

        perf_snapshot = self._performance.snapshot() if self._performance is not None else {}
        context_assembly_metric = perf_snapshot.get("context_assembly")
        llm_metric = perf_snapshot.get("gemini")

        return {
            "history_message_count": history_available,
            "history_cap": CONVERSATION_HISTORY_MAX_MESSAGES,
            "vision_fresh": vision_context is not None,
            "active_memory_count": active_memory_count,
            "recent_turns_used": recent_turns_used,
            "history_filtered": history_available - recent_turns_used,
            "conversation_closed": self._detect_conversation_closure(),
            "history_characters": history_characters,
            "ephemeral_context_characters": ephemeral_context_characters,
            "estimated_total_characters": estimated_total_characters,
            "estimated_context_tokens": round(estimated_total_characters / 4),
            "context_assembly_latency_ms": context_assembly_metric.avg_ms if context_assembly_metric else None,
            "llm_latency_ms": llm_metric.avg_ms if llm_metric else None,
        }

    def get_personalization_debug_snapshot(self) -> dict:
        """v3.0 Phase 10 (Developer Observability, Item F) — READ-ONLY, murni
        untuk Developer Dashboard, TIDAK memicu apa pun (nol capture Vision
        baru, nol query provider). Semua field di sini adalah SINYAL YANG
        TERSEDIA untuk personalisasi — BUKAN klaim bahwa LLM benar-benar
        memakainya di respons terakhir (itu tidak bisa diketahui pasti,
        v3.0 Phase 0 Audit §7: menampilkannya sebagai "applied" akan jadi
        fabricated telemetry — Teacher eksplisit menolak field itu).

        `relationship_*`: reuse `BehaviorState.relationship` yang SUDAH ADA
        sejak awal (sama seperti yang dikirim ke prompt tiap giliran lewat
        `ContextBuilder._format_relationship()`).
        `emotion_current`/`energy_current`: reuse `BehaviorState.emotion`/
        `internal` yang SUDAH ADA.
        `relevant_preference_count`: reuse `_count_relevant_memories_for_vision()`
        (v2.7/v3.0) — SAMA PERSIS dengan sinyal yang dipakai Initiative.
        `response_style_signal`: reuse `detect_style_preference()` (v3.0,
        `ai/conversation_signals.py`) terhadap pesan Teacher TERAKHIR — MURNI
        observasional, TIDAK mengontrol apa pun (lihat docstring fungsi itu).
        `personalization_signal_available`: True kalau ADA SALAH SATU sinyal
        di atas yang non-default (relationship lumayan dekat, ada memory
        relevan, atau style signal terdeteksi) — INI BUKAN "applied", cuma
        "tersedia untuk dipertimbangkan model", sesuai keputusan Teacher.

        v3.1 Phase 7: `continuity_state` — reuse `categorize_continuity()`
        (`ai/context_builder.py`, v3.1 Phase 1+2) terhadap `idle_seconds`
        yang SAMA PERSIS dipakai untuk menyusun teks "Conversation Status"
        yang dikirim ke model — SATU fungsi kategorisasi, dua pemakai
        (prompt & Dashboard), TIDAK PERNAH bisa tidak sinkron."""
        behavior_state = self.current_behavior_state()
        vision_context = self._vision.get_context() if self._vision else None
        r = behavior_state.relationship
        relationship_average = round((r.trust.current + r.comfort.current + r.affection.current) / 3, 1)
        relevant_preference_count = self._count_relevant_memories_for_vision(vision_context)
        last_message = self._conversation.get_last_user_message() or ""
        style_signal = detect_style_preference(last_message)
        continuity_state = categorize_continuity(behavior_state.internal.elapsed_seconds())

        return {
            "relationship_trust": r.trust.current,
            "relationship_comfort": r.comfort.current,
            "relationship_affection": r.affection.current,
            "relationship_respect": r.respect.current,
            "relationship_familiarity": r.familiarity.current,
            "relationship_average": relationship_average,
            "emotion_current": behavior_state.emotion.current.value,
            "energy_current": behavior_state.internal.energy.value,
            "relevant_preference_count": relevant_preference_count,
            "response_style_signal": style_signal,
            "continuity_state": continuity_state,
            "personalization_signal_available": (
                relevant_preference_count > 0 or style_signal is not None or relationship_average >= 60
            ),
        }

    def get_memory_decision_debug_snapshot(self) -> dict:
        """v3.2 Phase 6+7 (Memory Explainability + Developer Observability) —
        READ-ONLY, murni membaca `_memory_decision_history`/
        `_recall_decision_history` yang SUDAH ADA (v3.2, in-memory, rolling
        window). TIDAK memicu ekstraksi/recall baru apa pun.

        Field mengikuti istilah jujur yang diminta spec v3.2 §10 (Signal/
        Count/State/Decision) — TIDAK ADA klaim "LLM used memory
        successfully", cuma angka deterministik dari keputusan yang SUDAH
        terjadi (relation model v2.5, retrieval v1.9-v2.6).

        - `candidate_count`: jumlah fakta yang diproses `_persist_fact()`
          dalam window terakhir (SEMUANYA sudah lolos filter hedging/noise
          di dalam `extract()` — "candidate" di sini berarti "fakta yang
          benar-benar sampai ke tahap persist", bukan "seluruh kemungkinan
          sebelum LLM memutuskan").
        - `saved_count` / `updated_count` / `superseded_count` /
          `duplicate_ignored_count` / `failed_count`: breakdown per outcome
          — SEMUA dihitung dari `outcome` yang SAMA PERSIS dipakai
          `_persist_fact()` untuk memutuskan pemanggilan MemoryManager mana
          yang dieksekusi (bukan angka terpisah yang bisa tidak sinkron).
        - `recent_decisions`: daftar ringkas (maks 10 terbaru) untuk
          ditampilkan Dashboard, format sesuai contoh spec §9 (Decision +
          Reason ringkas).
        - `recall_query_count` / `recall_result_total`: dari
          `_recall_decision_history` — jumlah event recall & total memory
          yang dikembalikan dalam window terakhir.

        v3.3 Phase 10 (Developer Observability, spec §16) — 3 field
        tambahan, SEMUA dihitung dari `_recall_decision_history` yang
        sudah diperluas `_record_recall()` (v3.3 Phase 1/3/7), TIDAK ADA
        state baru:
        - `reference_signal_count`: berapa recall dalam window ini pesan
          Teacher-nya terdeteksi mengandung pola referensi ("yang tadi",
          dst) — MURNI hitungan sinyal deterministik (`detect_reference_
          signal()`), BUKAN klaim "LLM berhasil resolve referensi" (spec
          §16 eksplisit melarang klaim non-deterministik semacam itu).
        - `conversation_anchor_used_count` / `vision_assisted_count`:
          berapa kali `query_source` yang BENAR-BENAR dipakai adalah
          "conversation_anchor"/"vision_context" — jujur menunjukkan
          seberapa sering pesan Teacher sendiri tidak cukup, dan sumber
          fallback mana yang menyelamatkan pencarian.
        - `recent_recalls`: ringkasan (maks 10 terbaru) untuk Dashboard,
          field mengikuti pola `recent_decisions` di atas."""
        decisions = self._memory_decision_history
        outcome_counts = {"saved": 0, "updated": 0, "superseded": 0, "duplicate_ignored": 0, "failed": 0}
        for d in decisions:
            outcome = d.get("outcome")
            if outcome in outcome_counts:
                outcome_counts[outcome] += 1

        recent_decisions = [
            {
                "category": d["category"],
                "content_preview": d["content"][:60],
                "relation": d["relation"],
                "outcome": d["outcome"],
            }
            for d in decisions[-10:]
        ]

        recalls = self._recall_decision_history
        recall_result_total = sum(r["result_count"] for r in recalls)
        reference_signal_count = sum(1 for r in recalls if r.get("reference_signal"))
        conversation_anchor_used_count = sum(1 for r in recalls if r.get("query_source") == "conversation_anchor")
        vision_assisted_count = sum(1 for r in recalls if r.get("query_source") == "vision_context")

        recent_recalls = [
            {
                "query_preview": r["query_preview"],
                "signal": r["signal"],
                "reference_signal": r.get("reference_signal", False),
                "query_source": r.get("query_source", "current_message"),
                "result_count": r["result_count"],
                "candidate_count": r.get("candidate_count", 0),
                "duplicates_removed": r.get("duplicates_removed", 0),
                "top_score": r.get("top_score"),
                "top_match_preview": r.get("top_match_preview"),
            }
            for r in recalls[-10:]
        ]

        # v3.4 Phase 8/9 (Developer Observability, spec §12) — ringkasan
        # recall PALING BARU dalam bentuk field datar, format PERSIS contoh
        # dashboard di spec ("Candidates/Ranked/Selected/Duplicates
        # Removed/Top Match/Top Score/Query Source") supaya Dashboard tidak
        # perlu menggali `recent_recalls[-1]` sendiri. "Ranked" == jumlah
        # kandidat yang benar-benar melalui `rank_memories()` — SAMA dengan
        # `candidate_count` (semua kandidat yang lolos dedup memang selalu
        # diranking, tidak ada yang dilewati diam-diam). `None` kalau belum
        # pernah ada recall sama sekali dalam window (mis. app baru start).
        last_ranking = None
        if recalls:
            last = recalls[-1]
            last_ranking = {
                "candidates": last.get("candidate_count", 0),
                "ranked": last.get("candidate_count", 0),
                "selected": last["result_count"],
                "duplicates_removed": last.get("duplicates_removed", 0),
                "query_source": last.get("query_source", "current_message"),
                "top_match_preview": last.get("top_match_preview"),
                "top_score": last.get("top_score"),
            }

        return {
            "candidate_count": len(decisions),
            "saved_count": outcome_counts["saved"],
            "updated_count": outcome_counts["updated"],
            "superseded_count": outcome_counts["superseded"],
            "duplicate_ignored_count": outcome_counts["duplicate_ignored"],
            "failed_count": outcome_counts["failed"],
            "recent_decisions": recent_decisions,
            "recall_query_count": len(recalls),
            "recall_result_total": recall_result_total,
            "reference_signal_count": reference_signal_count,
            "conversation_anchor_used_count": conversation_anchor_used_count,
            "vision_assisted_count": vision_assisted_count,
            "recent_recalls": recent_recalls,
            "last_ranking": last_ranking,
        }

    def get_temporal_debug_snapshot(self) -> dict:
        """v3.5 Phase 15 (Developer Observability) — READ-ONLY, murni
        membaca `_last_temporal_signals` (dicache `_build_contents()` di
        atas) + `_recall_decision_history` yang SUDAH ADA (v3.2/v3.3/v3.4)
        untuk field "Anchor" (reuse `top_match_preview`/`query_source` dari
        recall TERAKHIR — TIDAK ADA pencarian/kalkulasi baru apa pun di
        sini). TIDAK memicu apa pun, TIDAK menyimpulkan task_status/
        deadline/priority (Hard Boundary spec §4.2/§4.3) — field yang
        dikembalikan SEMUA cuma echo dari evidence yang sudah dihitung
        `ai/temporal_signals.py` untuk pesan TERAKHIR.

        Return dict dengan SEMUA field kosong/`None` kalau belum pernah
        ada chat sama sekali (`_last_temporal_signals is None`) — Dashboard
        menampilkan "Belum ada data" untuk kondisi ini, bukan error."""
        signals = self._last_temporal_signals
        recalls = self._recall_decision_history
        last_recall = recalls[-1] if recalls else None

        if signals is None:
            return {
                "relative_terms": (),
                "normalized_dates": (),
                "continuation_cues": (),
                "completion_cues": (),
                "unresolved_cues": (),
                "anchor_preview": None,
                "anchor_source": None,
            }

        return {
            "relative_terms": signals.relative_terms,
            "normalized_dates": signals.normalized_dates,
            "continuation_cues": signals.continuation_cues,
            "completion_cues": signals.completion_cues,
            "unresolved_cues": signals.unresolved_cues,
            # v3.5 Phase 5 (Conversation Anchor Reuse): "Anchor" di sini
            # SEPENUHNYA reuse field yang SUDAH ADA dari v3.3/v3.4 recall
            # TERAKHIR — BUKAN anchor/topic-tracking baru. `None` kalau
            # belum pernah ada recall sama sekali.
            "anchor_preview": last_recall.get("top_match_preview") if last_recall else None,
            "anchor_source": last_recall.get("query_source") if last_recall else None,
        }

    # ---------- Memory ----------

    def list_memories(self, limit: int = 50) -> list[Memory]:
        # v2.6 Phase 0/2 audit — fix regresi tak disengaja dari v2.5: method
        # ini dipakai Memory GUI (Teacher-facing, lihat ui/memory_service.py)
        # untuk melihat/kelola SEMUA memory-nya sendiri, BUKAN untuk chat
        # context. Default v2.5 (`include_superseded=False`) BENAR untuk
        # chat context (`_select_relevant_memories` di bawah, TIDAK diubah)
        # tapi SALAH kalau ikut diwarisi ke sini — Teacher jadi tidak bisa
        # lihat riwayat memory yang sudah di-supersede lewat relation model
        # v2.5, padahal masih ada di database (cuma status berubah, tidak
        # pernah dihapus). GUI SEHARUSNYA menampilkan histori lengkap;
        # active-only itu kebutuhan khusus jalur chat context, bukan
        # kebutuhan Teacher saat mengelola memorinya sendiri.
        return self._memory_manager.load_memories(limit=limit, include_superseded=True)

    def search_memories(self, query: str, limit: int = 50) -> list[Memory]:
        """Passthrough read-only ke MemoryManager.search_memory — dipakai Memory
        GUI (v1.1). TIDAK memanggil Gemini/embedding, murni SQL LIKE yang sudah
        ada di MemoryManager (Search Policy v1.1: tidak ada mesin pencarian baru).

        v2.6: `include_superseded=True` — alasan PERSIS SAMA dengan
        `list_memories()` di atas."""
        return self._memory_manager.search_memory(query, limit=limit, include_superseded=True)

    def delete_memory(self, memory_id: int) -> None:
        self._memory_manager.delete_memory(memory_id)

    def clear_memories(self) -> None:
        self._memory_manager.clear_all()

    # ---------- Behavior ----------

    def current_behavior_state(self) -> BehaviorState:
        return self._behavior_engine.current

    # ---------- Vision ----------

    def capture_vision(self) -> Optional[VisionContext]:
        """Trigger MANUAL eksplisit (mis. tombol GUI masa depan) — TIDAK PERNAH
        dipanggil otomatis dari chat() (Capture Policy: Manual Capture Only).
        Return None kalau Vision tidak diaktifkan."""
        if self._vision is None:
            return None
        return self._vision.refresh()

    def current_vision_context(self) -> Optional[VisionContext]:
        if self._vision is None:
            return None
        return self._vision.get_context()

    def get_vision_mode(self) -> str:
        """v1.7 (Developer Diagnostics §13): passthrough READ-ONLY tipis ke
        Vision.get_mode() yang sudah ada sejak v1.5.2 — sebelumnya cuma
        dipakai VisionPage lewat instance Vision yang diteruskan langsung
        (lihat main_gui.py), belum pernah di-expose lewat Companion. TIDAK
        memanggil refresh()/capture apa pun, murni baca state mode saat ini."""
        if self._vision is None:
            return "unknown"
        return self._vision.get_mode().value

    def get_vision_provider_name(self) -> str:
        """v2.3 §18: passthrough READ-ONLY tipis ke Vision.get_provider_name()
        — pola identik get_vision_mode() di atas."""
        if self._vision is None:
            return "unknown"
        return self._vision.get_provider_name()

    # ---------- Routine (Developer Panel prep v0.9.5, Routine GUI v1.6) ----------

    def get_pending_routine_events(self) -> list[RoutineEvent]:
        return self._routine.get_pending_events() if self._routine else []

    def get_last_routine_event(self) -> Optional[RoutineEvent]:
        return self._routine.get_last_event() if self._routine else None

    def get_next_routine_schedule(self) -> dict:
        return self._routine.get_next_schedule() if self._routine else {}

    def clear_routine_queue(self) -> None:
        if self._routine:
            self._routine.clear_queue()

    def is_routine_enabled(self) -> bool:
        """v1.6: False juga kalau Routine subsystem tidak diaktifkan sama
        sekali saat konstruksi Companion (enable_routine=False) — bukan cuma
        soal flag runtime di dalam Routine."""
        return self._routine.is_enabled() if self._routine else False

    def enable_routine(self) -> None:
        if self._routine:
            self._routine.enable()

    def disable_routine(self) -> None:
        if self._routine:
            self._routine.disable()

    def get_routine_history(self, limit: int = 10) -> list[RoutineEvent]:
        return self._routine.get_recent_history(limit=limit) if self._routine else []

    def get_routine_suppression(self) -> Optional[tuple]:
        return self._routine.get_last_suppression() if self._routine else None

    # ---------- Initiative Developer Metrics passthrough ----------

    def get_initiative_score(self) -> float:
        return self._initiative.get_current_score() if self._initiative else 0.0

    def get_last_initiative_result(self) -> Optional[DecisionResult]:
        return self._initiative.get_last_result() if self._initiative else None

    def get_initiative_suppressions(self) -> list[str]:
        return self._initiative.get_active_suppressions() if self._initiative else []

    def get_initiative_budget(self) -> dict:
        return self._initiative.get_remaining_budget() if self._initiative else {}

    def get_initiative_cooldowns(self) -> dict:
        return self._initiative.get_cooldowns() if self._initiative else {}

    # ---------- Internal ----------

    def _detect_conversation_closure(self) -> bool:
        """v2.8 Phase 5 (Conversation Closure) — reuse `Conversation.
        get_last_user_message()` (v2.8, murni baca `_history`, TIDAK ADA
        state baru) + `ai/conversation_signals.py::detect_closure()`
        (pattern matching murni, TIDAK ADA LLM kedua). Dipanggil dari KEDUA
        titik (`chat()` maupun `check_autonomous_opportunity()`) — hasilnya
        SELALU sama untuk kedua jalur karena keduanya membaca pesan user
        TERAKHIR yang sama dari `Conversation` yang sama (Companion satu-
        satunya orchestrator, Conversation satu-satunya source of truth)."""
        try:
            last_message = self._conversation.get_last_user_message()
            return detect_closure(last_message or "")
        except Exception as e:
            logger.warning("Gagal deteksi conversation closure: {}", e)
            return False

    def _vision_query_text(self, vision_context: Optional[VisionContext]) -> str:
        """v3.0 Phase 7 (Autonomous Personalization) — diekstrak dari
        `_count_relevant_memories_for_vision()` (v2.7) supaya query yang
        SAMA PERSIS bisa dipakai di DUA tempat: (1) Initiative scoring
        (lewat `_count_relevant_memories_for_vision` di bawah) dan (2) isi
        konten respons otonom (lewat `_relevant_memories_for_vision` di
        bawah). SEBELUM v3.0, keduanya BERBEDA — Initiative memutuskan
        "boleh bicara" berdasarkan Vision+Memory, tapi respons otonom yang
        BENAR-BENAR keluar memakai memory recency biasa yang TIDAK ADA
        hubungannya dengan Vision (v3.0 Phase 0 Audit §5, temuan
        ketidaksinkronan nyata). Fungsi ini SATU-SATUNYA tempat query itu
        dibangun, supaya keduanya TIDAK PERNAH lagi berbeda."""
        if vision_context is None:
            return ""
        return f"{vision_context.application or ''} {vision_context.summary or ''}".strip()

    def _count_relevant_memories_for_vision(self, vision_context: Optional[VisionContext]) -> int:
        """v2.7 Phase 5+6 — Vision (application/summary) dipakai sebagai
        QUERY ke retrieval Memory yang SUDAH ADA (`_select_relevant_
        memories()`, TIDAK dibuat ulang, TIDAK memanggil provider/LLM apa
        pun — murni SQL keyword search yang sama persis dipakai chat
        context). Cuma mengembalikan JUMLAH (int), BUKAN daftar Memory
        (keputusan eksplisit Teacher — Initiative tidak boleh menerima isi
        memory penuh).

        Kalau Vision tidak aktif/kosong (None — baik karena OFF maupun
        stale, keduanya sudah di-gate `Vision.get_context()` sejak v1.5.2/
        v2.6), return 0 — tidak ada query yang masuk akal, rule ini
        simply tidak berkontribusi (bukan dipaksakan)."""
        query_text = self._vision_query_text(vision_context)
        if not query_text:
            return 0
        try:
            return len(self._select_relevant_memories(query_text))
        except Exception as e:
            logger.warning("Gagal hitung relevant_memory_count untuk Initiative: {}", e)
            return 0

    def _relevant_memories_for_autonomous(self, vision_context: Optional[VisionContext]) -> list[Memory]:
        """v3.0 Phase 7 — dipakai `_build_autonomous_contents()` untuk isi
        KONTEN respons otonom, reuse QUERY yang SAMA PERSIS (`_vision_query_
        text()`) dengan yang dipakai Initiative untuk SCORING di atas.

        Kalau Vision tidak aktif/kosong, `_select_relevant_memories("")`
        TETAP dipanggil (BUKAN dilewati) — `_select_relevant_memories`
        SUDAH punya fallback ke recency (marker-filtered, v2.6) untuk kasus
        keyword kosong, jadi perilakunya PERSIS sama dengan
        `load_memories()` recency lama, cuma sekarang lewat jalur yang
        sudah difilter marker — bonus fix kecil dari penyatuan ini (v3.0
        Phase 0 Audit §5: jalur lama `load_memories()` langsung di sini
        TIDAK PERNAH difilter marker, beda dari jalur chat context)."""
        query_text = self._vision_query_text(vision_context)
        try:
            return self._select_relevant_memories(query_text)
        except Exception as e:
            logger.warning("Gagal ambil memory relevan utk autonomous content: {}", e)
            return []

    def _update_behavior(self, user_input: str) -> BehaviorState:
        try:
            state = self._behavior_engine.update(user_input, "")
            logger.info("Behavior Updated")
            return state
        except Exception as e:
            logger.warning("Behavior Engine gagal, fallback ke default: {}", e)
            return DEFAULT_BEHAVIOR_STATE

    def _build_contents(
        self,
        user_input: str,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
        routine_event: Optional[RoutineEvent] = None,
        decision_result: Optional[DecisionResult] = None,
    ) -> list[types.Content]:
        """SATU-SATUNYA definisi _build_contents (sebelumnya ada 3 definisi
        duplikat menumpuk di file — cuma yang terakhir yang benar-benar terpakai
        oleh Python, sisanya kode mati. Sudah dikonsolidasi di sini).

        v1.9: `user_input` sekarang diteruskan supaya bisa dipakai
        `_select_relevant_memories()` — sebelumnya method ini blind-load N
        memori terbaru tanpa peduli topik pesan Teacher.

        v2.6 Phase 6: `CONVERSATION_HISTORY_MAX_MESSAGES` (default None =
        unbounded, TIDAK BERUBAH dari sebelumnya kecuali Teacher eksplisit
        set di .env) — lihat config/settings.py & Conversation.get_history().

        v2.9 Phase 0/7 (Context Scaling Audit/Observability): seluruh isi
        method ini (mulai `get_history()` sampai `return`) sekarang dibungkus
        timer `context_assembly` — SEBELUMNYA cuma sub-bagian `memory_query`
        yang punya timer sendiri, "biaya assembly total" (ephemeral+memory+
        history digabung jadi list `contents`) belum pernah terukur sebagai
        satu angka. Nested dengan `memory_query` (memory_query tetap muncul
        terpisah di Dashboard) — ini pola profiling yang wajar, bukan bug."""
        _assembly_start = time.perf_counter()
        history = self._conversation.get_history(max_messages=CONVERSATION_HISTORY_MAX_MESSAGES)
        contents: list[types.Content] = []

        # v3.5 Phase 1/2/4/11 (Temporal Awareness & Task Continuity) —
        # dihitung SEKALI di sini dari `user_input` (pesan Teacher yang
        # SEDANG diproses turn ini) — BUKAN dari riwayat, BUKAN dari
        # balasan Arona (spec §19: "Autonomous turns must not invent
        # Teacher temporal facts", dan secara umum sinyal ini soal apa
        # yang BARU SAJA Teacher katakan). `now` dari timezone project
        # yang SUDAH ADA (`config.constants.ROUTINE_TIMEZONE`, dipakai
        # Routine sejak awal) — TIDAK membuat sumber waktu baru.
        # `self._last_temporal_signals` dicache murni untuk Developer
        # Dashboard (`get_temporal_debug_snapshot()`, read-only, pola
        # IDENTIK `_last_recall_scores`).
        temporal_signals = detect_temporal_signals(user_input, now=datetime.now(ZoneInfo(ROUTINE_TIMEZONE)))
        self._last_temporal_signals = temporal_signals

        try:
            ephemeral_text = self._context_builder.build(
                behavior_state,
                vision_context=vision_context,
                routine_event=routine_event,
                decision_result=decision_result,
                temporal_signals=temporal_signals,
            )
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Ephemeral runtime context — bukan pesan Teacher]\n{ephemeral_text}")],
                )
            )
            logger.info("Context Generated")
        except Exception as e:
            logger.warning("Gagal membangun ephemeral context, lanjut tanpa itu: {}", e)

        try:
            # v3.3 Phase 7 (Vision-assisted Reference): `vision_context`
            # SUDAH tersedia sebagai parameter method ini (dipanggil chat()
            # lewat `self._vision.get_context()` SEBELUM `_build_contents`
            # dipanggil sama sekali, TIDAK ADA capture Vision baru di sini)
            # — sebelum v3.3 parameter ini TIDAK diteruskan ke
            # `_select_relevant_memories`, jadi jalur chat() biasa tidak
            # pernah memakai Vision sebagai bantuan recall (beda dari jalur
            # autonomous yang SUDAH memakainya sejak v3.0, lihat
            # `_relevant_memories_for_autonomous`). Diteruskan di sini
            # murni supaya kedua jalur konsisten — Vision TETAP hanya
            # dipakai sebagai fallback PALING AKHIR (lihat implementasi
            # `_select_relevant_memories`), bukan authority.
            memories = self._timed(
                "memory_query", lambda: self._select_relevant_memories(user_input, vision_context)
            )
            memory_text = _format_memories(memories, now=datetime.now(timezone.utc))
            if memory_text:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=f"[Konteks memori — bukan pesan langsung dari Teacher]\n{memory_text}")],
                    )
                )
        except Exception as e:
            logger.warning("Gagal memuat memori, lanjut tanpa memori: {}", e)
            # v3.3 hotfix: `memories` HARUS tetap terdefinisi walau blok di
            # atas gagal (exception SEBELUM baris assignment sempat
            # jalan) — supaya blok reference-note di bawah (yang membaca
            # `memories`) tidak ikut meledak jadi NameError. `[]` di sini
            # artinya "tidak ada kandidat untuk disebutkan", note di bawah
            # otomatis jatuh ke varian generik (bukan varian dengan daftar
            # kandidat).
            memories = []

        contents.extend(history)

        # v3.3 Phase 2/4 hotfix ROUND 2 (Teacher konfirmasi: setelah hotfix
        # round 1 — reinforcement note abstrak di posisi akhir `contents` —
        # Gemini SUDAH sesuai ekspektasi, TAPI Local TETAP menebak). Root
        # cause lebih dalam: note round 1 masih berupa META-INSTRUKSI
        # ("kalau ada >1 kemungkinan, tanya") yang MENGHARUSKAN model
        # sendiri menyimpulkan APA SAJA kandidatnya dari riwayat percakapan
        # — satu langkah inferensi tambahan yang model kecil/quantized
        # (LM Studio, dsb — lihat `ai/providers/local_provider.py`) terbukti
        # tidak cukup andal melakukannya, apalagi dengan `temperature=0.85`
        # yang SENGAJA tinggi di provider itu (mitigasi masalah lain, lihat
        # dokumentasi di `LocalProvider.__init__` — TIDAK diubah di sini,
        # bukan wewenang v3.3 mengubah trade-off yang sudah didokumentasikan
        # Teacher sendiri).
        #
        # Perbaikan: kalau kandidat memory yang BENAR-BENAR ditemukan
        # `_select_relevant_memories()` (`memories`, variabel yang SUDAH
        # ADA di atas, TIDAK dihitung ulang) lebih dari satu DAN pesan ini
        # terdeteksi referensial — kandidatnya DISEBUTKAN LANGSUNG,
        # verbatim, di dalam note (bukan cuma "ada beberapa kemungkinan").
        # Ini menghilangkan satu langkah inferensi yang tadinya dibebankan
        # ke model: model tidak perlu lagi MENCARI SENDIRI apa saja
        # kandidatnya, tinggal MEMILIH ANTARA yang sudah eksplisit
        # disebutkan. TETAP TIDAK ADA LLM kedua/classifier ambiguity
        # (Hard Boundary §2) — daftar kandidat ini murni hasil `search_
        # memory()` yang SUDAH dihitung buat mengisi `[Konteks memori]` di
        # atas, cuma direuse+ditegaskan ulang di posisi paling akhir.
        #
        # Kalau kandidat CUMA SATU (atau nol) — TIDAK ada dasar untuk
        # bilang "ada beberapa pilihan" (itu akan jadi klaim yang tidak
        # didukung data, bisa membuat model malah bertanya klarifikasi
        # padahal harusnya tidak perlu, spec §23 juga melarang over-
        # clarification) — note tetap muncul TAPI versi ringan yang cuma
        # menegaskan "pakai riwayat/memori di atas untuk memahami
        # maksudnya", tanpa memaksakan cabang "tanya klarifikasi".
        #
        # v3.3 hotfix ROUND 3 (temuan Teacher: note round 2 pernah
        # mendaftar memory yang TIDAK relevan sebagai "kandidat" — kasus
        # nyata: kata "Arona" adalah nama Arona SENDIRI, muncul di hampir
        # semua memory afeksi/relationship, jadi query yang menyebut
        # "Arona" menarik banyak memory yang cuma KEBETULAN menyebut nama
        # itu, bukan benar-benar kandidat topik yang bersaing). Root cause:
        # round 2 mengambil `memories[:5]` APA ADANYA (asal masuk top-N
        # hasil ranking v3.4) tanpa cek seberapa jauh skornya dari kandidat
        # #1 — padahal `ai/memory_ranking.py::score_memory()` v3.4 SUDAH
        # menghitung skor per kandidat, cuma belum dipakai untuk MENYARING
        # di sini.
        #
        # Perbaikan: kandidat yang masuk daftar note SEKARANG cuma yang
        # skornya (`self._last_recall_scores`, diisi `_select_relevant_
        # memories()` TEPAT SEBELUM baris ini, TIDAK dihitung ulang) minimal
        # `_REFERENCE_NOTE_SCORE_RATIO` (60%) dari skor kandidat #1 — kalau
        # kandidat #2 dst jauh lebih lemah (mis. cuma cocok 1 keyword generik
        # dibanding kandidat #1 yang cocok 3 keyword spesifik), itu bukan
        # "kemungkinan yang sama masuk akal", jadi TIDAK didaftarkan sebagai
        # kandidat bersaing. Dibatasi maksimal `_REFERENCE_NOTE_MAX_CANDIDATES`
        # (3, turun dari 5) — daftar klarifikasi yang masuk akal untuk
        # ditanyakan ke Teacher memang jarang lebih dari segelintir opsi.
        # Kalau `self._last_recall_scores` kosong (mis. hasil recency
        # fallback, TIDAK ada skor valid untuk dihitung — lihat `_select_
        # relevant_memories()`), TIDAK ADA dasar untuk mengklaim ada
        # >1 kandidat sama sekali, jadi otomatis jatuh ke varian ringan.
        if detect_reference_signal(user_input):
            scores = self._last_recall_scores or {}
            strong_candidates = memories
            if scores:
                top_score = max(scores.get(m.id, 0.0) for m in memories) if memories else 0.0
                threshold = top_score * _REFERENCE_NOTE_SCORE_RATIO
                strong_candidates = [m for m in memories if scores.get(m.id, 0.0) >= threshold]
            elif memories:
                # Tidak ada skor valid (recency fallback) -> jangan anggap
                # kandidat recency yang tidak ada hubungannya sebagai
                # "pilihan yang bersaing".
                strong_candidates = memories[:1]
            strong_candidates = strong_candidates[:_REFERENCE_NOTE_MAX_CANDIDATES]

            if len(strong_candidates) > 1:
                candidate_lines = "\n".join(f"{i + 1}. {m.content}" for i, m in enumerate(strong_candidates))
                note_text = (
                    "[INSTRUKSI PENTING — bukan pesan Teacher, jangan disebut ke Teacher: "
                    "pesan Teacher barusan menunjuk balik ke sesuatu yang sudah dibicarakan "
                    f"sebelumnya, dan ADA LEBIH DARI SATU kemungkinan yang cocok:\n{candidate_lines}\n"
                    "Kalau Arona TIDAK YAKIN persis yang mana dari daftar itu yang dimaksud "
                    "Teacher, WAJIB tanya klarifikasi singkat dulu (sebutkan pilihannya) — "
                    "JANGAN langsung menjawab salah satu secara asal tanpa bertanya."
                )
            else:
                note_text = (
                    "[Catatan internal — bukan pesan Teacher, jangan disebut ke Teacher: "
                    "pesan Teacher barusan tampaknya menunjuk balik ke sesuatu yang sudah "
                    "dibicarakan sebelumnya (\"yang tadi\"/\"itu\"/\"lanjut\"/dst). Gunakan "
                    "riwayat percakapan & konteks memori di atas untuk memahami maksudnya, "
                    "lalu lanjutkan dengan percaya diri."
                )
            contents.append(types.Content(role="user", parts=[types.Part(text=note_text)]))

        logger.info("Ephemeral Context Injected")
        if self._performance is not None:
            self._performance.record("context_assembly", (time.perf_counter() - _assembly_start) * 1000)
        return contents

    def _select_relevant_memories(
        self, user_input: str, vision_context: Optional[VisionContext] = None
    ) -> list[Memory]:
        """v1.9 Companion Intelligence — Memory Relevance (§8). Sebelumnya
        SELALU load N memori TERBARU tanpa peduli topik pesan Teacher saat
        ini — jadi memori project lama bisa nyempil di obrolan santai, atau
        sebaliknya. Sekarang pakai `search_memory()` yang SUDAH ADA sejak
        v1.1 (SQL LIKE, dipakai juga oleh Memory GUI search) — TIDAK ada
        search engine/Vector DB/RAG baru (spec eksplisit melarang).

        `search_memory()` mencocokkan SATU string utuh sebagai substring,
        bukan multi-kata — jadi di sini dipanggil PER KATA signifikan dari
        pesan Teacher, hasilnya digabung+dedupe.

        v3.3 Phase 1+3+7 (Conversation Anchor Detection, Contextual Memory
        Query, Vision-assisted Reference — spec
        V3.3_CONTEXTUAL_RECALL_REFERENCE_INTELLIGENCE.md): SEBELUM v3.3,
        kata kunci HANYA diambil dari `user_input` (kata >= 4 huruf, TANPA
        stopword filter — Phase 0 Audit v3.3 menemukan ini bug nyata: kata
        referensi generik seperti "yang"/"tadi"/"lanjut" ikut lolos jadi
        substring pencarian, yang buat pesan seperti "lanjut yang tadi"
        bisa mencocokkan HAMPIR SEMUA memory secara acak — persis kondisi
        yang spec §23 larang: "memory irrelevant masuk sebagai reference
        utama"). Sekarang, sesuai Recall Priority spec §8 (Current message
        > Immediate previous turns > Active anchor > Recent memory), kata
        kunci dicoba berurutan dari SUMBER yang paling relevan ke paling
        umum, BERHENTI di sumber pertama yang menghasilkan kata kunci:

        1. `user_input` sendiri (SETELAH stopword filter) — TIDAK berubah
           urutan prioritasnya dari v1.9, cuma sekarang lebih bersih.
        2. Kalau tier 1 nihil (baik karena pesan memang tidak punya kata
           kunci berguna sama sekali, ATAU karena kata kuncinya ada tapi
           TIDAK match satu pun memory DAN pesan ini terdeteksi bersifat
           referensial — `detect_reference_signal()`, mis. "yang ini
           error" yang kata "error"-nya sendiri belum pernah tersimpan
           sebagai memory) — coba beberapa pesan Teacher TERAKHIR di
           `Conversation` yang SUDAH ADA (in-memory, TIDAK dipersist di
           sini, lihat `_recent_conversation_anchor_keywords()`). Ini
           PERSIS target Phase 1 (Conversation Anchor Detection) & Phase 3
           (Contextual Memory Query) — TIDAK membuat anchor/reference
           database baru (Hard Boundary §2), murni membaca ulang riwayat
           percakapan yang sudah ada tiap kali dibutuhkan.
        3. Kalau tier 2 JUGA nihil, dengan syarat gate YANG SAMA (kosong
           ATAU referensial) DAN Vision fresh tersedia — coba kata kunci
           dari Vision (`_vision_query_text()`, SUDAH ADA sejak v3.0,
           TIDAK ada capture Vision baru). Phase 7 contoh persis: "yang
           ini error" + Vision menunjukkan dialog error di layar. Vision
           cuma SUPPORTING signal paling akhir, BUKAN authority — dicoba
           PALING TERAKHIR, setelah conversation.

        Syarat "kosong ATAU referensial" ini SENGAJA membatasi eskalasi
        tier 2/3 supaya TIDAK terpicu untuk pesan biasa yang kebetulan
        tidak match memory apa pun (mis. topik benar-benar baru pertama
        kali dibicarakan) — kalau eskalasi terjadi tanpa syarat itu,
        memory dari topik SEBELUMNYA berisiko nyempil ke topik BARU yang
        tidak berkaitan sama sekali, persis kondisi yang spec v3.3 §23
        FAIL condition larang ("old topic mendominasi current topic").
        Eskalasi HANYA masuk akal kalau ada sinyal bahwa pesan ini memang
        MENUNJUK ke sesuatu yang sudah dibicarakan sebelumnya.

        Kalau SEMUA sumber di atas nihil, fallback ke N-terbaru (perilaku
        lama v1.9, TIDAK berubah) — supaya tidak tiba-tiba context memori
        kosong total."""
        reference_signal = detect_reference_signal(user_input)
        current_keywords = filter_search_keywords(extract_keywords(user_input))
        should_try_wider_context = (not current_keywords) or reference_signal

        # v3.4 Phase 1/2 (Memory Relevance Ranking): `raw_query_text` ikut
        # diteruskan ke tiap tier — dipakai `score_memory()` (`ai/memory_
        # ranking.py`) HANYA untuk bonus "exact phrase match" (spec §5.3).
        # Untuk tier current_message, itu `user_input` apa adanya (satu
        # kalimat utuh, exact-phrase match masuk akal). Untuk tier
        # conversation_anchor, TIDAK ADA satu "kalimat utuh" yang mewakili
        # anchor (bisa gabungan beberapa turn) — raw_query_text dibiarkan
        # kosong (exact-phrase bonus otomatis nol, tier ini tetap jalan
        # normal lewat match_count/coverage). Untuk tier vision_context,
        # dipakai teks Vision itu sendiri (`_vision_query_text()`, SUDAH
        # ADA, TIDAK dihitung ulang di sini — dipanggil lagi cuma untuk
        # ambil teksnya, bukan re-capture Vision).
        outcome = self._search_memories_by_keywords(current_keywords, raw_query_text=user_input)
        matched_source = "current_message" if outcome.memories else None
        winning_keywords, winning_raw_text = current_keywords, user_input

        if not outcome.memories and should_try_wider_context:
            anchor_keywords = self._recent_conversation_anchor_keywords()
            outcome = self._search_memories_by_keywords(anchor_keywords)
            if outcome.memories:
                matched_source = "conversation_anchor"
                winning_keywords, winning_raw_text = anchor_keywords, ""

        if not outcome.memories and should_try_wider_context and vision_context is not None:
            vision_text = self._vision_query_text(vision_context)
            vision_keywords = filter_search_keywords(extract_keywords(vision_text))
            outcome = self._search_memories_by_keywords(vision_keywords, raw_query_text=vision_text)
            if outcome.memories:
                matched_source = "vision_context"
                winning_keywords, winning_raw_text = vision_keywords, vision_text

        if outcome.memories:
            logger.info(
                "Memory Relevance: {} match ditemukan (source={}, candidates={}, duplicates={}, top_score={})",
                len(outcome.memories), matched_source, outcome.candidate_count,
                outcome.duplicates_removed, outcome.top_score,
            )
            # v3.3 hotfix round 3: cache skor PER MEMORY (bukan cuma
            # top_score tunggal) dari kandidat yang benar-benar dipakai
            # tier pemenang — dipakai `_build_contents()` untuk menyaring
            # note klarifikasi (lihat komentar di `__init__`).
            #
            # v3.4 hotfix (round 4): SEKARANG ikut meneruskan `outcome.
            # keyword_frequency` (v3.4, `ai/memory_ranking.py`) ke
            # `score_memory()` di sini — SEBELUMNYA skor round 3 dihitung
            # TANPA koreksi frekuensi, jadi kata yang TERLALU UMUM di
            # database (mis. "arona", nama companion sendiri, match di
            # puluhan memory afeksi) masih dapat bobot penuh berdasarkan
            # panjang kata semata, membuat memory yang cuma KEBETULAN
            # match keyword umum itu masih bisa lolos ambang
            # `_REFERENCE_NOTE_SCORE_RATIO` (60%) dan ikut disebut sebagai
            # "kandidat" di note klarifikasi — persis bug yang dilaporkan
            # Teacher. Dengan koreksi frekuensi, kata umum otomatis dapat
            # bobot kecil, skor memory yang cuma match lewat kata itu jadi
            # jauh di bawah top_score, sehingga TIDAK lolos ambang lagi.
            self._last_recall_scores = {
                m.id: score_memory(m, winning_keywords, winning_raw_text, outcome.keyword_frequency)
                for m in outcome.memories
            }
            self._record_recall(
                user_input, outcome.memories, signal=matched_source,
                reference_signal=reference_signal, query_source=matched_source,
                candidate_count=outcome.candidate_count,
                duplicates_removed=outcome.duplicates_removed,
                top_score=outcome.top_score,
            )
            return outcome.memories

        logger.info("Memory Relevance: tidak ada match, fallback ke recency")
        # v2.6 Phase 1: fallback recency JUGA rawan kontaminasi marker — malah
        # LEBIH rawan dari keyword search, karena marker internal
        # (RoutineHistory/InitiativeHistory/dst) di-refresh `updated_at`-nya
        # tiap kali subsystem itu update state (kemungkinan lebih sering
        # daripada Teacher bikin memory baru), jadi wajar mendominasi urutan
        # "N paling baru" kalau tidak difilter. `include_superseded=False`
        # (default, TIDAK diubah) tetap berlaku seperti biasa.
        #
        # v3.4 Phase 5.5/7 catatan: fallback ini SENGAJA TIDAK diranking —
        # tidak ada keyword untuk diskor terhadapnya (semua tier keyword
        # sudah gagal), recency MEMANG satu-satunya sinyal yang tersisa di
        # sini by design, bukan celah yang lupa ditangani.
        recent = self._memory_manager.load_memories(limit=EPHEMERAL_CONTEXT_MEMORY_LIMIT * 2)
        filtered = [m for m in recent if not m.content.startswith("__ARONA_")]
        result = filtered[:EPHEMERAL_CONTEXT_MEMORY_LIMIT]
        # v3.3 hotfix round 3: TIDAK ADA skor yang valid untuk hasil
        # recency fallback (tidak ada keyword yang dicocokkan terhadapnya)
        # — kosongkan cache, supaya `_build_contents()` TIDAK menganggap
        # memory recency yang kebetulan lolos sebagai "kandidat setara"
        # (lihat gating di `_build_contents()`).
        self._last_recall_scores = {}
        self._record_recall(
            user_input, result, signal="recency_fallback",
            reference_signal=reference_signal, query_source="recency_fallback",
            candidate_count=len(filtered), duplicates_removed=0, top_score=None,
        )
        return result

    def _search_memories_by_keywords(
        self, keywords: list[str], raw_query_text: str = ""
    ) -> RetrievalOutcome:
        """v1.9-v3.3 — loop pencarian & filter marker `__ARONA_` (TIDAK
        BERUBAH satu baris pun sejak v3.3, cuma dipindah jadi method
        terpisah supaya dipakai 3 tier). SEJAK v3.4, method ini TIDAK
        LAGI mengembalikan kandidat mentah apa adanya dalam urutan
        insertion (urutan hasil `search_memory()` per kata, yang TIDAK
        mencerminkan relevansi sama sekali) — sekarang:

        1. Kumpulkan kandidat MENTAH sampai `MEMORY_CANDIDATE_POOL_LIMIT`
           (v3.4 Phase 5, lebih besar dari budget final
           `EPHEMERAL_CONTEXT_MEMORY_LIMIT`) — supaya ranking di langkah 2
           punya cukup bahan untuk memilih yang PALING relevan, bukan cuma
           yang kebetulan ditemukan duluan. Sekalian dicatat berapa memory
           yang di-match TIAP kata kunci (`keyword_frequency`) — v3.4
           hotfix, dipakai `score_memory()`/`select_strong_candidates()`
           untuk mendeteksi kata yang TERLALU UMUM di database SAAT INI
           (mis. "arona" yang muncul di puluhan memory afeksi kalau nama
           companion itu sendiri kebetulan jadi keyword) TANPA query
           tambahan apa pun — angkanya sudah ada gratis dari pencarian yang
           sama.
        2. Rank deterministik lewat `rank_and_select()` (`ai/memory_
           ranking.py`, v3.4 — pure function, TIDAK ADA LLM/network) lalu
           pangkas ke `EPHEMERAL_CONTEXT_MEMORY_LIMIT` (budget final TIDAK
           BERUBAH dari v1.9-v3.3, cuma SEKARANG isinya kandidat TERKUAT,
           bukan yang pertama ditemukan).

        Dedup by-id (marker `__ARONA_` + `seen_ids`) TIDAK BERUBAH dari
        v1.9 — SEKARANG jumlah duplikat yang di-skip ikut dihitung
        (`duplicates_removed`) murni untuk observability (spec v3.4 §12),
        TIDAK memengaruhi logic apa pun.

        Return `RetrievalOutcome` (v3.4, `ai/memory_ranking.py`) — caller
        (`_select_relevant_memories`) yang menerjemahkan `candidate_count
        == 0` jadi "tier ini gagal, coba tier berikutnya"."""
        seen_ids: set[int] = set()
        candidates: list[Memory] = []
        duplicates_removed = 0
        keyword_frequency: dict[str, int] = {}
        for word in keywords[:5]:  # batasi jumlah query per pesan
            try:
                matches = self._memory_manager.search_memory(word, limit=MEMORY_CANDIDATE_POOL_LIMIT)
            except Exception as e:
                logger.warning("Memory relevance search gagal untuk kata '{}': {}", word, e)
                continue
            # v3.4 hotfix: dicatat SEBELUM filter marker/dedup — frekuensi
            # di sini murni menjawab "seberapa umum kata ini di database",
            # bukan "berapa yang akhirnya dipakai jadi context" (dua
            # pertanyaan berbeda; yang pertama yang relevan untuk menilai
            # SPESIFISITAS kata itu sendiri).
            keyword_frequency[word] = len(matches)
            for m in matches:
                # v2.6 Phase 1 (Context Hygiene, §26 spec v2.6) — marker
                # internal (RoutineHistory/InitiativeHistory/InternalState/
                # Relationship) TIDAK BOLEH bocor sebagai "memori tentang
                # Teacher" ke chat context.
                if m.content.startswith("__ARONA_"):
                    continue
                if m.id in seen_ids:
                    duplicates_removed += 1
                    continue
                seen_ids.add(m.id)
                candidates.append(m)
            if len(candidates) >= MEMORY_CANDIDATE_POOL_LIMIT:
                break

        if not candidates:
            return RetrievalOutcome(
                memories=[], candidate_count=0, duplicates_removed=duplicates_removed,
                top_score=None, keyword_frequency=keyword_frequency,
            )

        selected, top_score = rank_and_select(
            candidates, keywords, EPHEMERAL_CONTEXT_MEMORY_LIMIT, raw_query_text,
            keyword_frequency=keyword_frequency,
        )
        return RetrievalOutcome(
            memories=selected,
            candidate_count=len(candidates),
            duplicates_removed=duplicates_removed,
            top_score=top_score,
            keyword_frequency=keyword_frequency,
        )

    def _recent_conversation_anchor_keywords(self, max_user_turns: int = 3, max_keywords: int = 8) -> list[str]:
        """v3.3 Phase 1 (Conversation Anchor Detection) — TIDAK membuat
        anchor object/state baru yang dipersist di mana pun (Hard Boundary
        §2: "Conversation database baru" & "Persistent topic database"
        dilarang keras). Anchor di sini murni DIHITUNG ULANG tiap kali
        dipanggil, dari `Conversation.get_history()` yang SUDAH ADA
        (in-memory, process-lifetime) — sesuai definisi eksplisit spec
        §4: "Anchor adalah short-lived conversation signal", BUKAN
        persistent memory. Kalau dipanggil lagi sedetik kemudian dengan
        history yang sudah berubah, hasilnya otomatis ikut berubah — tidak
        ada snapshot yang bisa basi.

        Membaca `max_user_turns` pesan Teacher (role='user') SEBELUM pesan
        yang sedang diproses saat ini (pesan saat ini sendiri sudah dicoba
        duluan oleh pemanggil dan gagal menghasilkan keyword — itu sebabnya
        method ini dipanggil sama sekali). Kata signifikan diambil lewat
        `extract_keywords()` + `filter_search_keywords()` yang SAMA PERSIS
        dipakai untuk pesan saat ini (spec §7: "reuse `_select_relevant_
        memories(query)`, jangan membuat recall engine kedua" — utilitas
        ekstraksi kata kuncinya pun SATU-SATUNYA, dipakai bersama, lihat
        `ai/reference_signals.py`).

        Urutan turn PALING BARU didahulukan (Recall Priority spec §8:
        "Immediate previous turns" sebelum turn yang lebih lama) — dedupe
        mempertahankan urutan kemunculan pertama, yang berarti dari turn
        TERBARU duluan."""
        history = self._conversation.get_history()
        # Pesan user TERAKHIR di history saat method ini dipanggil sudah
        # PASTI pesan yang sedang diproses chat() saat ini (ditambahkan
        # `add_user_message()` sebelum `_build_contents()` dipanggil) —
        # index [0] setelah reversed() karenanya dilewati (slice [1:]),
        # supaya anchor benar-benar berasal dari turn SEBELUMNYA.
        user_messages = [
            content.parts[0].text
            for content in reversed(history)
            if content.role == "user" and content.parts and content.parts[0].text
        ]
        previous_user_messages = user_messages[1:1 + max_user_turns]

        seen: set[str] = set()
        anchor_keywords: list[str] = []
        for text in previous_user_messages:
            for word in filter_search_keywords(extract_keywords(text)):
                if word not in seen:
                    seen.add(word)
                    anchor_keywords.append(word)
            if len(anchor_keywords) >= max_keywords:
                break
        return anchor_keywords[:max_keywords]

    def _record_recall(
        self,
        query_text: str,
        result: list[Memory],
        signal: str,
        reference_signal: bool = False,
        query_source: str = "current_message",
        candidate_count: int = 0,
        duplicates_removed: int = 0,
        top_score: Optional[float] = None,
    ) -> None:
        """v3.2 Phase 6/7 (Memory Explainability + Developer Observability) —
        murni MENCATAT hasil retrieval yang SUDAH TERJADI (`_select_relevant_
        memories()` di atas), TIDAK menambah logic recall apa pun baru.
        Rolling window sama seperti `_memory_decision_history` — in-memory,
        hilang saat restart, bukan database baru. `query_text` dipotong
        pendek (bukan full text) — cukup untuk Teacher mengenali konteksnya
        di Dashboard, tidak perlu menyimpan seluruh kalimat panjang.

        v3.3 Phase 10: `reference_signal` (bool) dan `query_source` (string)
        — lihat versi sebelumnya untuk detail.

        v3.4 Phase 8 (Developer Observability, spec §12) — 3 field baru,
        SEMUA dihitung dari `RetrievalOutcome` yang SUDAH ADA
        (`_search_memories_by_keywords()`, `ai/memory_ranking.py`), TIDAK
        ADA perhitungan ulang:
        - `candidate_count`: jumlah kandidat mentah unik SEBELUM dipangkas
          ke budget final (0 untuk jalur recency_fallback, karena di situ
          `result` itu sendiri sudah = kandidatnya, tidak ada tahap ranking
          terpisah — TIDAK dikarang jadi angka lain).
        - `duplicates_removed`: berapa match diskip karena id sudah pernah
          ditemukan lewat keyword lain di tier yang sama.
        - `top_score`: skor deterministik kandidat #1 hasil ranking (`ai/
          memory_ranking.py::score_memory()`) — TIDAK PERNAH diklaim
          sebagai "confidence"/"certainty" (spec §12 Telemetry Rules
          eksplisit melarang), murni angka mekanis yang bisa dijelaskan
          persis dari mana asalnya (lihat docstring `score_memory()`)."""
        self._recall_decision_history.append({
            "timestamp": datetime.now(timezone.utc),
            "query_preview": query_text.strip()[:60],
            "signal": signal,
            "result_count": len(result),
            "reference_signal": reference_signal,
            "query_source": query_source,
            "candidate_count": candidate_count,
            "duplicates_removed": duplicates_removed,
            "top_score": round(top_score, 2) if top_score is not None else None,
            "top_match_preview": result[0].content[:60] if result else None,
        })
        if len(self._recall_decision_history) > self._MEMORY_HISTORY_LIMIT:
            del self._recall_decision_history[:-self._MEMORY_HISTORY_LIMIT]

    def _select_related_memories_for_extraction(self, user_input: str) -> list[Memory]:
        """v2.5 Phase 2 (Related Memory Retrieval, §9 spec) — sengaja
        DUPLIKAT STRUKTUR `_select_relevant_memories()` di atas (bukan
        di-reuse langsung), BUKAN "refactor besar tak terkait" (guardrail
        #14 PM) — cuma nambah SATU filter yang penting: exclude memory
        marker internal (RoutineHistory/InitiativeHistory/InternalState/
        Relationship, lihat Phase 0 Audit v2.5 §4/§5).

        `_select_relevant_memories()` di atas dipakai untuk CHAT CONTEXT dan
        SENGAJA TIDAK diubah sama sekali di sini (spec v2.5 §5 rekomendasi
        (b): filter kontaminasi cukup ditambahkan di jalur BARU ini, bukan
        mengubah jalur lama yang sudah stabil — kontaminasi ke chat context
        dicatat sebagai known issue terpisah, BUKAN diperbaiki diam-diam di
        milestone ini).

        TIDAK fallback ke recency kalau nol match (BEDA dari
        `_select_relevant_memories`) — kalau memang tidak ada memori
        terkait, extractor cukup tahu itu ('related_memories=[]' -> prompt
        relation-aware tidak disisipkan sama sekali, model otomatis
        menghasilkan relation="NEW" untuk semua fakta, persis §9 "Jangan
        memberikan seluruh database ke model").

        v3.3 Phase 0 Audit — perbaikan simetris: kata kunci sekarang lewat
        `filter_search_keywords()` yang sama dipakai `_select_relevant_
        memories()` (lihat `ai/reference_signals.py`), supaya kata generik
        ("yang"/"tadi"/dst) tidak ikut jadi kandidat pencarian memori
        terkait di sini juga — mencegah MemoryExtractor menerima daftar
        "memori terkait" yang bising, yang berisiko salah menyarankan
        relation UPDATE/SUPERSEDES terhadap memory yang sebetulnya tidak
        berkaitan sama sekali (cuma kebetulan sama-sama mengandung kata
        umum). TIDAK ada fallback anchor-conversation/vision di sini (BEDA
        dari `_select_relevant_memories`) — kontrak `extract()` membaca
        SATU pesan Teacher (lihat catatan v2.1 §18 di
        `check_autonomous_opportunity`), jadi memperluas sumber kata kunci
        ke luar pesan itu sendiri di luar scope perbaikan ini."""
        keywords = filter_search_keywords(extract_keywords(user_input))

        seen_ids: set[int] = set()
        related: list[Memory] = []
        for word in keywords[:5]:
            try:
                matches = self._memory_manager.search_memory(word, limit=EPHEMERAL_CONTEXT_MEMORY_LIMIT)
            except Exception as e:
                logger.warning("Related memory search (extraction) gagal untuk kata '{}': {}", word, e)
                continue
            for m in matches:
                # v2.5 Phase 0 Audit §4/§5: exclude marker row internal state
                # — TIDAK boleh jadi kandidat UPDATE/SUPERSEDES sama sekali,
                # itu bukan fakta Teacher. Pola prefix generik ("__ARONA_"),
                # BUKAN daftar 4 string hardcoded — supaya konsumen
                # persistence_helper.save_by_marker() BARU di masa depan
                # otomatis ikut terfilter tanpa perlu mengingat update
                # daftar ini.
                if m.id not in seen_ids and not m.content.startswith("__ARONA_"):
                    seen_ids.add(m.id)
                    related.append(m)
            if len(related) >= EPHEMERAL_CONTEXT_MEMORY_LIMIT:
                break

        if related:
            logger.info("Related Memory Retrieval (extraction): {} match ditemukan", len(related))
        return related[:EPHEMERAL_CONTEXT_MEMORY_LIMIT]

    def _build_autonomous_contents(
        self,
        behavior_state: BehaviorState,
        vision_context: Optional[VisionContext] = None,
        routine_event: Optional[RoutineEvent] = None,
        decision_result: Optional[DecisionResult] = None,
    ) -> list[types.Content]:
        """v1.8: sama seperti _build_contents(), TAPI ephemeral+memory context
        diletakkan SETELAH history (bukan sebelum). Untuk giliran otonom TIDAK
        ADA pesan Teacher baru yang masuk history, jadi content PALING AKHIR
        harus role='user' supaya Gemini punya 'giliran saat ini' yang jelas
        untuk direspons — kalau posisinya sama seperti _build_contents() biasa
        (ephemeral di awal), giliran terakhir bisa jadi role='model' (balasan
        Arona sebelumnya) yang membingungkan Gemini. ContextBuilder TETAP
        satu-satunya sumber teksnya (reuse self._context_builder.build() apa
        adanya, TIDAK diduplikasi) — ini murni keputusan URUTAN di level
        Companion, orchestrator tetap satu.

        v2.6 Phase 6: cap sama persis seperti _build_contents().

        v2.9 Phase 0/7: timer `context_assembly` sama persis pola
        `_build_contents()` — DUA early-return (`[]` kalau ephemeral gagal
        dibangun) TETAP direkam durasinya (percobaan yang gagal pun tetap
        "biaya" nyata yang layak diukur, bukan disembunyikan dari metrik)."""
        _assembly_start = time.perf_counter()
        history = self._conversation.get_history(max_messages=CONVERSATION_HISTORY_MAX_MESSAGES)
        contents: list[types.Content] = list(history)

        try:
            ephemeral_text = self._context_builder.build(
                behavior_state,
                vision_context=vision_context,
                routine_event=routine_event,
                decision_result=decision_result,
            )
        except Exception as e:
            logger.warning("Gagal membangun autonomous context, batal bicara: {}", e)
            if self._performance is not None:
                self._performance.record("context_assembly", (time.perf_counter() - _assembly_start) * 1000)
            return []

        try:
            # v3.0 Phase 7 (Autonomous Personalization) — SEBELUMNYA baris ini
            # `self._memory_manager.load_memories(limit=...)` LANGSUNG (recency
            # biasa, TIDAK ada hubungan dengan Vision, dan TIDAK melewati
            # filter marker __ARONA_... sama sekali — v3.0 Phase 0 Audit §5:
            # ketidaksinkronan nyata antara alasan Initiative "boleh bicara"
            # [lihat _count_relevant_memories_for_vision di atas, query SAMA]
            # dan isi konten yang benar-benar diucapkan. Sekarang KEDUANYA
            # pakai `_vision_query_text()` yang SAMA PERSIS — kalau Initiative
            # bicara "karena lihat Game X", isi respons SEKARANG benar-benar
            # membawa memory soal Game X juga, bukan memory acak yang baru
            # diubah. Bonus: otomatis ikut ter-filter marker (sebelumnya tidak).
            memories = self._timed("memory_query", lambda: self._relevant_memories_for_autonomous(vision_context))
            memory_text = _format_memories(memories, now=datetime.now(timezone.utc))
        except Exception as e:
            logger.warning("Gagal memuat memori (autonomous), lanjut tanpa memori: {}", e)
            memory_text = ""

        if memory_text:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Konteks memori — bukan pesan langsung dari Teacher]\n{memory_text}")],
                )
            )

        autonomous_note = (
            "[Autonomous check-in — bukan pesan Teacher. Teacher belum mengatakan "
            "apa-apa saat ini. Initiative & Routine memberi sinyal bahwa momen ini "
            "wajar untuk Arona memulai obrolan singkat secara natural, sesuai "
            "konteks di atas. Kalau tidak ada yang perlu dikatakan, respons singkat "
            "dan hangat tetap lebih baik daripada dipaksakan.]"
        )
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=f"{ephemeral_text}\n\n{autonomous_note}")],
            )
        )
        logger.info("Context Generated (Autonomous)")
        if self._performance is not None:
            self._performance.record("context_assembly", (time.perf_counter() - _assembly_start) * 1000)
        return contents

    def _schedule_memory_extraction(self, user_input: str) -> None:
        """v2.1 — Async Memory Extraction. Sebelumnya (`_remember_if_useful`,
        v1.x-v2.0) method ini MEMANGGIL LANGSUNG MemoryExtractor.extract()
        secara sinkron, di dalam chat() yang sama, sebelum reply
        dikembalikan ke Teacher — jadi Teacher menunggu DUA panggilan
        Gemini berurutan (bahasa utama + ekstraksi memori) walau cuma satu
        yang benar-benar dia tunggu jawabannya. Sekarang method ini HANYA
        menyusun closure lalu men-submit ke MemoryExtractionWorker
        (ai/memory_worker.py) — tidak menunggu apa pun, return seketika.

        v2.1 §11/§12: `user_input` di-terima sebagai str (sudah immutable,
        sudah jadi snapshot alami sejak jadi parameter chat()) — closure di
        bawah TIDAK menerima Companion/Conversation/objek aplikasi lain,
        cuma menyentuh MemoryExtractor & MemoryManager (keduanya sudah ada,
        tidak diubah kontraknya) lewat referensi yang di-capture di sini.
        Closure ini TIDAK PERNAH memanggil add_user_message()/
        add_assistant_message()/rollback_last_message() — Conversation
        SUDAH final untuk giliran ini sebelum baris ini dipanggil (lihat
        ordering di chat()), worker cuma baca/tulis Memory, tidak pernah
        menyentuh Conversation sama sekali.

        v2.5 Phase 2/4: retrieval memori terkait (`_select_related_memories_
        for_extraction`) SENGAJA dipanggil DI DALAM closure (bukan sebelum
        `submit()`, di main/chat thread) — supaya chat() tetap return
        seketika PERSIS seperti sebelum v2.5 (nol pekerjaan baru di jalur
        sinkron), query SQLite untuk retrieval ikut pindah ke background
        thread yang sama dengan extraction itu sendiri."""
        memory_extractor = self._memory_extractor
        memory_manager = self._memory_manager
        select_related = self._select_related_memories_for_extraction
        # v3.2 Phase 6/7: capture REFERENSI ke list yang sama (BUKAN `self`)
        # — patuh aturan v2.1 §11/§12 di atas. List ini mutable, append dari
        # closure (thread worker) langsung terlihat oleh Dashboard (thread
        # GUI) tanpa perlu API tambahan apa pun.
        decision_history = self._memory_decision_history
        history_limit = self._MEMORY_HISTORY_LIMIT

        def _extract_and_save() -> None:
            related_memories = select_related(user_input)
            facts = memory_extractor.extract(user_input, related_memories=related_memories)
            if not facts:
                logger.info("Tidak ada fakta layak diingat dari pesan ini.")
                return
            for fact in facts:
                _persist_fact(memory_manager, fact, history=decision_history)
            # v3.2 Phase 6: rolling window sederhana (pola PerformanceTracker)
            # — bukan database, murni supaya list ini tidak tumbuh tanpa
            # batas selama sesi panjang.
            if len(decision_history) > history_limit:
                del decision_history[:-history_limit]

        self._memory_worker.submit(_extract_and_save)

    # ---------- Memory Worker (Developer Diagnostics, v2.1 §21) ----------

    def get_memory_worker_status(self) -> MemoryWorkerStatus:
        """Passthrough READ-ONLY untuk Developer Dashboard — TIDAK ADA
        start()/stop()/pause() yang di-expose di sini (v2.1 §21: "Developer
        Dashboard does not control the worker"), cuma angka observasi."""
        return self._memory_worker.status()

    def get_memory_provider_name(self) -> str:
        """v2.2 §21: passthrough READ-ONLY — "local" | "gemini", provider
        yang BENAR-BENAR dipakai MemoryExtractor saat ini (ditentukan sekali
        saat __init__, tidak berubah selama proses hidup — restart wajib
        untuk ganti, sama seperti Language Provider)."""
        return self._memory_provider_name

    def get_ai_provider_name(self) -> str:
        """v2.4 Phase 2: pola IDENTIK get_memory_provider_name()/
        get_vision_provider_name() di atas — read-only murni, "local" |
        "gemini", provider yang BENAR-BENAR dipakai Language Generation."""
        return self._ai_provider_name

    def get_ai_model_name(self) -> str:
        """v2.4 Phase 2: read-only murni untuk Developer Dashboard."""
        return self._ai_model_name

    def get_memory_model_name(self) -> str:
        """v2.4 Phase 2: read-only murni untuk Developer Dashboard."""
        return self._memory_model_name

    def get_vision_model_name(self) -> Optional[str]:
        """v2.4 Phase 2: passthrough READ-ONLY ke Vision.get_model_name() —
        pola IDENTIK get_vision_provider_name() di bawah. None kalau Vision
        tidak aktif sama sekali (mis. entrypoint CLI)."""
        return self._vision.get_model_name() if self._vision else None

    # ---------- Shutdown (v2.1 §29/§30) ----------

    def shutdown(self) -> None:
        """Dipanggil dari luar (ui/window.py closeEvent, main.py sebelum
        keluar) — pola yang SAMA dengan Vision.shutdown() yang sudah ada
        (v1.5.2). Memory extraction yang sedang jalan diberi kesempatan
        selesai dengan batas waktu (lihat MemoryExtractionWorker.shutdown),
        TIDAK PERNAH menggantung tanpa batas dan TIDAK PERNAH menyisakan
        worker yang bertahan setelah aplikasi ditutup."""
        self._memory_worker.shutdown()