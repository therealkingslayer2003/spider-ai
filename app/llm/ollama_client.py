from langchain_ollama import ChatOllama

from app.core.config import get_settings
from app.llm.base import BaseChatModelClient


class OllamaChatClient(BaseChatModelClient):
    def __init__(self) -> None:
        settings = get_settings()

        self._model_name = settings.ollama_chat_model
        self._llm = ChatOllama(
            model=settings.ollama_chat_model,
            base_url=settings.ollama_base_url,
            temperature=settings.ollama_temperature,
        )

    async def generate(self, message: str) -> str:
        response = await self._llm.ainvoke(message)
        return str(response.content)

    @property
    def model_name(self) -> str:
        return self._model_name
