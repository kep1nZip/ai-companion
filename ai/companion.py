from __future__ import annotations

from typing import Optional

from google.genai import types
from google.genai.errors import ClientError

from ai.personality import load_prompts
from ai.prompt_builder import build_system_prompt
from ai.gemini import GeminiClient, GeminiResponseError
from ai.conversation import Conversation
from ai.memory_extractor import MemoryExtractor
from ai.context_builder import ContextBuilder
from database.memory_manager import MemoryManager, Memory
from behavior.behavior_engine import BehaviorEngine
from behavior.behavior_state import BehaviorState, DEFAULT_BEHAVIOR_STATE
from vision.vision import Vision
from vision.vision_context import VisionContext
from config.settings import GEMINI_API_KEY
from config.constants import MODEL_NAME
from config.logger import logger

from routine.routine import Routine
from routine.routine_event import RoutineEvent

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
    Behavior Engine, dan (BARU v0.7) Vision — SEMUA opsional/read-only dari sisi
    Companion, Companion tetap cuma orchestrator."""

    def __init__(self, vision: Optional[Vision] = None, enable_routine: bool = True):
        prompts = load_prompts()
        system_prompt = build_system_prompt(prompts)

        self._gemini = GeminiClient(
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            system_prompt=system_prompt,
        )
        self._conversation = Conversation()
        self._memory_manager = MemoryManager()
        self._memory_extractor = MemoryExtractor(api_key=GEMINI_API_KEY, model_name=MODEL_NAME)

        self._behavior_engine = BehaviorEngine(memory_manager=self._memory_manager)
        self._context_builder = ContextBuilder()
        self._vision = vision
        self._routine = Routine(memory_manager=self._memory_manager) if enable_routine else None

        logger.info("Companion backend initialized. Model: {}", MODEL_NAME)

    def chat(self, user_input: str) -> str:
        self._conversation.add_user_message(user_input)
        logger.info("Teacher: {}", user_input)

        behavior_state = self._update_behavior(user_input)
        vision_context = self._vision.get_context() if self._vision else None  # reuse ONLY, tidak capture baru
        routine_event = self._routine.update(behavior_state, vision_context) if self._routine else None

        contents = self._build_contents(behavior_state, vision_context, routine_event)

        try:
            logger.info("Gemini Request")
            reply = self._gemini.send(contents)
            self._conversation.add_assistant_message(reply)
            logger.info("Gemini Reply")
            logger.info("Arona: {}", reply)

            if routine_event and self._routine:
                self._routine.mark_completed(routine_event)

        except GeminiResponseError as e:
            self._conversation.rollback_last_message()
            logger.warning("Balasan Gemini kosong, pesan Teacher di-rollback: {}", e)
            raise CompanionError(
                "Arona kehabisan kata-kata sesaat, Teacher... coba ulangi lagi ya."
            ) from e

        except ClientError as e:
            self._conversation.rollback_last_message()
            if "429" in str(e):
                logger.warning("Rate limit hit: {}", e)
                raise RateLimitError(str(e)) from e
            logger.error("Gemini ClientError: {}", e)
            raise CompanionError(str(e)) from e

        self._remember_if_useful(user_input)
        return reply

    # ---------- Conversation ----------

    def get_history(self) -> list:
        return self._conversation.get_history()

    def clear_history(self) -> None:
        self._conversation.clear()
        logger.info("Conversation history cleared.")

    # ---------- Memory ----------

    def list_memories(self, limit: int = 50) -> list[Memory]:
        return self._memory_manager.load_memories(limit=limit)

    def delete_memory(self, memory_id: int) -> None:
        self._memory_manager.delete_memory(memory_id)

    def clear_memories(self) -> None:
        self._memory_manager.clear_all()

    # ---------- Behavior ----------

    def current_behavior_state(self) -> BehaviorState:
        return self._behavior_engine.current

    # ---------- Vision (BARU v0.7) ----------

    def capture_vision(self) -> Optional[VisionContext]:
        """Trigger MANUAL eksplisit (mis. tombol GUI masa depan) — TIDAK PERNAH
        dipanggil otomatis dari chat() (Capture Policy: Manual Capture Only).
        Return None kalau Vision tidak diaktifkan (opsional, rekomendasi GPT #4)."""
        if self._vision is None:
            return None
        return self._vision.refresh()

    def current_vision_context(self) -> Optional[VisionContext]:
        if self._vision is None:
            return None
        return self._vision.get_context()

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
        self, behavior_state: BehaviorState, vision_context: Optional[VisionContext] = None
    ) -> list[types.Content]:
        history = self._conversation.get_history()
        contents: list[types.Content] = []

        try:
            ephemeral_text = self._context_builder.build(behavior_state, vision_context=vision_context)
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
            memories = self._memory_manager.load_memories(limit=10)
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
        logger.info("Behavior Injected")
        return contents

    def _remember_if_useful(self, user_input: str) -> None:
        try:
            facts = self._memory_extractor.extract(user_input)
            if not facts:
                logger.info("Tidak ada fakta layak diingat dari pesan ini.")
                return
            for fact in facts:
                self._memory_manager.save_memory(fact["category"], fact["content"])
        except Exception as e:
            logger.warning("Pipeline memori gagal, percakapan tetap lanjut: {}", e)

    # ---------- Routine (BARU v0.8, Developer Panel prep) ----------

    def get_pending_routine_events(self) -> list:
        return self._routine.get_pending_events() if self._routine else []

    def get_last_routine_event(self) -> Optional[object]:
        return self._routine.get_last_event() if self._routine else None

    def get_next_routine_schedule(self) -> dict:
        return self._routine.get_next_schedule() if self._routine else {}

    def clear_routine_queue(self) -> None:
        if self._routine:
            self._routine.clear_queue()

    def _build_contents(self, behavior_state, vision_context=None, routine_event=None) -> list[types.Content]:
        history = self._conversation.get_history()
        contents: list[types.Content] = []

        try:
            ephemeral_text = self._context_builder.build(behavior_state, vision_context=vision_context, routine_event=routine_event)
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=f"[Ephemeral runtime context — bukan pesan Teacher]\n{ephemeral_text}")],
            ))
            logger.info("Context Generated")
        except Exception as e:
            logger.warning("Gagal membangun ephemeral context, lanjut tanpa itu: {}", e)

        try:
            memories = self._memory_manager.load_memories(limit=10)
            memory_text = _format_memories(memories)
            if memory_text:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Konteks memori — bukan pesan langsung dari Teacher]\n{memory_text}")],
                ))
        except Exception as e:
            logger.warning("Gagal memuat memori, lanjut tanpa memori: {}", e)

        contents.extend(history)
        logger.info("Behavior Injected")
        return contents