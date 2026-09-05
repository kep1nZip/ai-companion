from __future__ import annotations

import re
from typing import Optional

from google.genai import types

from ai.personality import load_prompts
from ai.prompt_builder import build_system_prompt
from ai.providers.base import LanguageModelProvider, ProviderError, ProviderRateLimitError, ProviderResponseError
from ai.providers.gemini_provider import GeminiProvider
from ai.conversation import Conversation
from ai.memory_extractor import MemoryExtractor, EXTRACTION_SYSTEM_PROMPT
from ai.memory_worker import MemoryExtractionWorker, MemoryWorkerStatus
from ai.context_builder import ContextBuilder
from database.memory_manager import MemoryManager, Memory
from behavior.behavior_engine import BehaviorEngine
from behavior.behavior_state import BehaviorState, DEFAULT_BEHAVIOR_STATE
from vision.vision import Vision
from vision.vision_context import VisionContext
from config.settings import GEMINI_API_KEY
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
        self._conversation = Conversation()
        self._memory_manager = MemoryManager()
        # v2.2 §21 (Developer Diagnostics): simpan NAMA provider yang benar2
        # dipakai (bukan re-deteksi dari type() nanti) — murni string
        # read-only untuk Developer Dashboard, tidak memengaruhi extract()
        # sama sekali.
        self._memory_provider_name = "local" if memory_provider is not None else "gemini"
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
                lambda: self._initiative.update(behavior_state, vision_context, routine_event),
            )
            if self._initiative else None
        )

        contents = self._build_contents(user_input, behavior_state, vision_context, routine_event, decision_result)

        try:
            logger.info("Gemini Request")
            reply = self._timed("gemini", lambda: self._gemini.generate(contents))
            self._conversation.add_assistant_message(reply)
            logger.info("Gemini Reply")
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
            ),
        )

        if not decision_result.should_start:
            return None

        contents = self._build_autonomous_contents(behavior_state, vision_context, routine_event, decision_result)
        if not contents:
            logger.warning("Autonomous context kosong, batal bicara.")
            return None

        try:
            logger.info("Gemini Request (Autonomous)")
            reply = self._timed("gemini", lambda: self._gemini.generate(contents))
            self._conversation.add_assistant_message(reply)
            logger.info("Gemini Reply (Autonomous)")
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

    # ---------- Memory ----------

    def list_memories(self, limit: int = 50) -> list[Memory]:
        return self._memory_manager.load_memories(limit=limit)

    def search_memories(self, query: str, limit: int = 50) -> list[Memory]:
        """Passthrough read-only ke MemoryManager.search_memory — dipakai Memory
        GUI (v1.1). TIDAK memanggil Gemini/embedding, murni SQL LIKE yang sudah
        ada di MemoryManager (Search Policy v1.1: tidak ada mesin pencarian baru)."""
        return self._memory_manager.search_memory(query, limit=limit)

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
        memori terbaru tanpa peduli topik pesan Teacher."""
        history = self._conversation.get_history()
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
                if m.id not in seen_ids:
                    seen_ids.add(m.id)
                    relevant.append(m)
            if len(relevant) >= EPHEMERAL_CONTEXT_MEMORY_LIMIT:
                break

        if relevant:
            logger.info("Memory Relevance: {} match ditemukan", len(relevant))
            return relevant[:EPHEMERAL_CONTEXT_MEMORY_LIMIT]

        logger.info("Memory Relevance: tidak ada match, fallback ke recency")
        return self._memory_manager.load_memories(limit=EPHEMERAL_CONTEXT_MEMORY_LIMIT)

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
        Companion, orchestrator tetap satu."""
        history = self._conversation.get_history()
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
        menyentuh Conversation sama sekali."""
        memory_extractor = self._memory_extractor
        memory_manager = self._memory_manager

        def _extract_and_save() -> None:
            facts = memory_extractor.extract(user_input)
            if not facts:
                logger.info("Tidak ada fakta layak diingat dari pesan ini.")
                return
            for fact in facts:
                memory_manager.save_memory(fact["category"], fact["content"])

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

    # ---------- Shutdown (v2.1 §29/§30) ----------

    def shutdown(self) -> None:
        """Dipanggil dari luar (ui/window.py closeEvent, main.py sebelum
        keluar) — pola yang SAMA dengan Vision.shutdown() yang sudah ada
        (v1.5.2). Memory extraction yang sedang jalan diberi kesempatan
        selesai dengan batas waktu (lihat MemoryExtractionWorker.shutdown),
        TIDAK PERNAH menggantung tanpa batas dan TIDAK PERNAH menyisakan
        worker yang bertahan setelah aplikasi ditutup."""
        self._memory_worker.shutdown()