from __future__ import annotations

import re
from typing import Optional

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
from ai.memory_worker import MemoryExtractionWorker, MemoryWorkerStatus
from ai.context_builder import ContextBuilder
from database.memory_manager import MemoryManager, Memory
from behavior.behavior_engine import BehaviorEngine
from behavior.behavior_state import BehaviorState, DEFAULT_BEHAVIOR_STATE
from vision.vision import Vision
from vision.vision_context import VisionContext
from config.settings import GEMINI_API_KEY, CONVERSATION_HISTORY_MAX_MESSAGES
from config.constants import MODEL_NAME, EPHEMERAL_CONTEXT_MEMORY_LIMIT
from config.logger import logger

from routine.routine import Routine
from routine.routine_event import RoutineEvent

from initiative.initiative import Initiative
from initiative.initiative_decision import DecisionResult

from developer.performance_debug import PerformanceTracker


class RateLimitError(Exception):
    """Terjadi saat Gemini API membalas rate limit (429)."""


class CompanionError(Exception):
    """Error umum lain dari Gemini API."""


def _format_memories(memories: list[Memory]) -> str:
    if not memories:
        return ""
    lines = [f"- ({m.category}) {m.content}" for m in memories]
    return "Berikut hal-hal yang Arona ingat tentang Teacher:\n" + "\n".join(lines)


def _persist_fact(memory_manager: MemoryManager, fact: dict) -> Optional[Memory]:
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
    v2.1 §22/§31)."""
    relation = fact.get("relation", RELATION_NEW)
    category = fact["category"]
    content = fact["content"]
    target_id = fact.get("target_memory_id")

    try:
        if relation == RELATION_SUPERSEDES and target_id is not None:
            return memory_manager.supersede_memory(target_id, category, content)
        elif relation == RELATION_UPDATE and target_id is not None:
            memory_manager.update_memory(target_id, content=content, category=category)
            return None
        elif relation == RELATION_DUPLICATE and target_id is not None:
            memory_manager.touch_memory(target_id)
            return None
        else:
            # RELATION_NEW, atau relation lain tapi target_id kosong
            # (seharusnya sudah di-fallback ke NEW oleh MemoryExtractor.
            # extract(), ini jaring pengaman kedua — bukan jalur yang
            # diharapkan tereksekusi dalam kondisi normal).
            return memory_manager.save_memory(category, content)
    except Exception as e:
        logger.warning("Gagal mempersist fakta memori (relation={}): {}", relation, e)
        return None


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
        fresh, tidak pernah stale)."""
        vision_context = self._vision.get_context() if self._vision else None
        try:
            active_memory_count = len(self._memory_manager.load_memories(limit=10_000))
        except Exception:
            active_memory_count = None
        return {
            "history_message_count": self._conversation.message_count(),
            "history_cap": CONVERSATION_HISTORY_MAX_MESSAGES,
            "vision_fresh": vision_context is not None,
            "active_memory_count": active_memory_count,
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
        if vision_context is None:
            return 0
        query_text = f"{vision_context.application or ''} {vision_context.summary or ''}".strip()
        if not query_text:
            return 0
        try:
            return len(self._select_relevant_memories(query_text))
        except Exception as e:
            logger.warning("Gagal hitung relevant_memory_count untuk Initiative: {}", e)
            return 0

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
        set di .env) — lihat config/settings.py & Conversation.get_history()."""
        history = self._conversation.get_history(max_messages=CONVERSATION_HISTORY_MAX_MESSAGES)
        contents: list[types.Content] = []

        try:
            ephemeral_text = self._context_builder.build(
                behavior_state,
                vision_context=vision_context,
                routine_event=routine_event,
                decision_result=decision_result,
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
            memories = self._timed("memory_query", lambda: self._select_relevant_memories(user_input))
            memory_text = _format_memories(memories)
            if memory_text:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=f"[Konteks memori — bukan pesan langsung dari Teacher]\n{memory_text}")],
                    )
                )
        except Exception as e:
            logger.warning("Gagal memuat memori, lanjut tanpa memori: {}", e)

        contents.extend(history)
        logger.info("Ephemeral Context Injected")
        return contents

    def _select_relevant_memories(self, user_input: str) -> list[Memory]:
        """v1.9 Companion Intelligence — Memory Relevance (§8). Sebelumnya
        SELALU load N memori TERBARU tanpa peduli topik pesan Teacher saat
        ini — jadi memori project lama bisa nyempil di obrolan santai, atau
        sebaliknya. Sekarang pakai `search_memory()` yang SUDAH ADA sejak
        v1.1 (SQL LIKE, dipakai juga oleh Memory GUI search) — TIDAK ada
        search engine/Vector DB/RAG baru (spec eksplisit melarang).

        `search_memory()` mencocokkan SATU string utuh sebagai substring,
        bukan multi-kata — jadi di sini dipanggil PER KATA signifikan dari
        pesan Teacher (kata >= 4 huruf, heuristik sederhana buat menyaring
        kata sambung pendek seperti 'aku'/'kamu'/'ini'), hasilnya
        digabung+dedupe. Kalau nol match sama sekali, fallback ke N-terbaru
        (perilaku lama) — supaya tidak tiba-tiba context memori kosong total
        untuk pesan yang memang tidak mengandung kata kunci apa pun."""
        keywords = [w for w in re.findall(r"\w+", user_input.lower()) if len(w) >= 4]

        seen_ids: set[int] = set()
        relevant: list[Memory] = []
        for word in keywords[:5]:  # batasi jumlah query per pesan
            try:
                matches = self._memory_manager.search_memory(word, limit=EPHEMERAL_CONTEXT_MEMORY_LIMIT)
            except Exception as e:
                logger.warning("Memory relevance search gagal untuk kata '{}': {}", word, e)
                continue
            for m in matches:
                # v2.6 Phase 1 (Context Hygiene, §26 spec v2.6 — resmi masuk
                # scope sekarang, SEBELUMNYA sengaja ditunda sebagai known
                # issue terpisah di v2.5 Phase 0 Audit §5). Filter PERSIS
                # sama dengan yang sudah ada di
                # `_select_related_memories_for_extraction()` (v2.5) — marker
                # internal (RoutineHistory/InitiativeHistory/InternalState/
                # Relationship) TIDAK BOLEH bocor sebagai "memori tentang
                # Teacher" ke chat context. Solusi di context boundary ini
                # (retrieval), BUKAN menghapus/mengubah memory internal itu
                # sendiri (§26: "solusi harus dilakukan di context boundary,
                # bukan dengan menghapus memory internal").
                if m.id not in seen_ids and not m.content.startswith("__ARONA_"):
                    seen_ids.add(m.id)
                    relevant.append(m)
            if len(relevant) >= EPHEMERAL_CONTEXT_MEMORY_LIMIT:
                break

        if relevant:
            logger.info("Memory Relevance: {} match ditemukan", len(relevant))
            return relevant[:EPHEMERAL_CONTEXT_MEMORY_LIMIT]

        logger.info("Memory Relevance: tidak ada match, fallback ke recency")
        # v2.6 Phase 1: fallback recency JUGA rawan kontaminasi marker — malah
        # LEBIH rawan dari keyword search, karena marker internal
        # (RoutineHistory/InitiativeHistory/dst) di-refresh `updated_at`-nya
        # tiap kali subsystem itu update state (kemungkinan lebih sering
        # daripada Teacher bikin memory baru), jadi wajar mendominasi urutan
        # "N paling baru" kalau tidak difilter. `include_superseded=False`
        # (default, TIDAK diubah) tetap berlaku seperti biasa.
        recent = self._memory_manager.load_memories(limit=EPHEMERAL_CONTEXT_MEMORY_LIMIT * 2)
        filtered = [m for m in recent if not m.content.startswith("__ARONA_")]
        return filtered[:EPHEMERAL_CONTEXT_MEMORY_LIMIT]

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
        memberikan seluruh database ke model")."""
        keywords = [w for w in re.findall(r"\w+", user_input.lower()) if len(w) >= 4]

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

        v2.6 Phase 6: cap sama persis seperti _build_contents()."""
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
            return []

        try:
            memories = self._timed("memory_query", lambda: self._memory_manager.load_memories(limit=EPHEMERAL_CONTEXT_MEMORY_LIMIT))
            memory_text = _format_memories(memories)
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

        def _extract_and_save() -> None:
            related_memories = select_related(user_input)
            facts = memory_extractor.extract(user_input, related_memories=related_memories)
            if not facts:
                logger.info("Tidak ada fakta layak diingat dari pesan ini.")
                return
            for fact in facts:
                _persist_fact(memory_manager, fact)

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