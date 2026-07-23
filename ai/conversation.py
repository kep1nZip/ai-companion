from google.genai import types


class Conversation:

    def __init__(self):
        self._history: list[types.Content] = []

    def add_user_message(self, text: str) -> None:
        self._history.append(
            types.Content(role="user", parts=[types.Part(text=text)])
        )

    def add_assistant_message(self, text: str) -> None:
        self._history.append(
            types.Content(role="model", parts=[types.Part(text=text)])
        )

    def rollback_last_message(self) -> None:
        if self._history:
            self._history.pop()

    def clear(self) -> None:
        self._history.clear()

    def get_history(self) -> list[types.Content]:
        return list(self._history)