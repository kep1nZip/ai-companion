from __future__ import annotations

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
from config.settings import GEMINI_API_KEY
from config.constants import MODEL_NAME
from config.logger import logger


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
    """Backend inti, UI-independent. Mengoordinasikan Conversation, Memory, dan
    (BARU v0.6.5) Behavior Engine — Companion cuma ORCHESTRATE, tidak pernah
    memiliki logic Behavior maupun merangkai string context sendiri."""

    def __init__(self):
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

        logger.info("Companion backend initialized. Model: {}", MODEL_NAME)

    def chat(self, user_input: str) -> str:
        self._conversation.add_user_message(user_input)
        logger.info("Teacher: {}", user_input)

        behavior_state = self._update_behavior(user_input)
        contents = self._build_contents(behavior_state)

        try:
            logger.info("Gemini Request")
            reply = self._gemini.send(contents)
            self._conversation.add_assistant_message(reply)
            logger.info("Gemini Reply")
            logger.info("Arona: {}", reply)

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

    # ---------- Behavior (BARU v0.6.5) ----------

    def current_behavior_state(self) -> BehaviorState:
        """Public read-only API. GUI/pihak luar HARUS lewat sini untuk baca
        BehaviorState — TIDAK PERNAH mengakses BehaviorEngine langsung."""
        return self._behavior_engine.current

    # ---------- Internal ----------

    def _update_behavior(self, user_input: str) -> BehaviorState:
        """Dipanggil SEBELUM Gemini membalas (Core Philosophy spec v0.6.5) — reply
        belum tersedia di titik ini. Dipassing string kosong karena tidak ada
        subsystem behavior (Emotion/Relationship/Internal State) yang membaca
        argumen `reply` saat ini (dikonfirmasi dari implementasi v0.6.2-v0.6.4)."""
        try:
            state = self._behavior_engine.update(user_input, "")
            logger.info("Behavior Updated")
            return state
        except Exception as e:
            logger.warning("Behavior Engine gagal, fallback ke default: {}", e)
            return DEFAULT_BEHAVIOR_STATE

    def _build_contents(self, behavior_state: BehaviorState) -> list[types.Content]:
        """Gabungkan ephemeral context (waktu+behavior, dari ContextBuilder) +
        memori (ephemeral) + history asli. TIDAK PERNAH disimpan permanen."""
        history = self._conversation.get_history()
        contents: list[types.Content] = []

        try:
            ephemeral_text = self._context_builder.build(behavior_state)
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Ephemeral runtime context — bukan pesan Teacher]\n{ephemeral_text}")],
                )
            )
            logger.info("Ephemeral Context Generated")
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