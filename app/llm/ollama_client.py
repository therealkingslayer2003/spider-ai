import logging

from langchain_ollama import ChatOllama

from app.core.config import get_settings
from app.llm.base import BaseChatModelClient

logger = logging.getLogger(__name__)


class OllamaChatClient(BaseChatModelClient):
    def __init__(self) -> None:
        self._settings = get_settings()

        self._model_name = self._settings.ollama_chat_model
        self._llm = ChatOllama(
            model=self._settings.ollama_chat_model,
            base_url=self._settings.ollama_base_url,
            temperature=self._settings.ollama_temperature,
        )

    async def generate(self, message: str) -> str:
        if self._settings.app_log_flow_steps:
            logger.info(
                "llm.generate.start model=%s prompt_chars=%s",
                self._model_name,
                len(message),
            )

        if self._settings.app_log_llm_prompts:
            logger.debug(
                "llm.generate.prompt model=%s prompt=%s",
                self._model_name,
                self._preview(message),
            )

        try:
            response = await self._llm.ainvoke(message)
            output = str(response.content)
        except Exception:
            logger.exception("llm.generate.failed model=%s", self._model_name)
            raise

        if self._settings.app_log_flow_steps:
            logger.info(
                "llm.generate.success model=%s output_chars=%s",
                self._model_name,
                len(output),
            )

        if self._settings.app_log_llm_outputs:
            logger.debug(
                "llm.generate.output model=%s output=%s",
                self._model_name,
                self._preview(output),
            )

        return output

    @property
    def model_name(self) -> str:
        return self._model_name

    def _preview(self, value: str) -> str:
        max_chars = self._settings.app_log_preview_chars

        if len(value) <= max_chars:
            return value

        return value[: max_chars - 3].rstrip() + "..."
