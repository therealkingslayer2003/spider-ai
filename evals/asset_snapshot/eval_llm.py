import logging
import time

from langchain_ollama import ChatOllama

from app.core.config import get_settings
from app.llm.base import BaseChatModelClient

logger = logging.getLogger(__name__)


class EvalOllamaClient(BaseChatModelClient):
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        temperature: float = 0.0,
    ) -> None:
        self._settings = get_settings()
        self._model_name = model
        self._llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature,
        )

    async def generate(self, message: str) -> str:
        started = time.perf_counter()
        if self._settings.app_log_flow_steps:
            logger.info(
                "eval.judge.llm.start model=%s prompt_chars=%s",
                self._model_name,
                len(message),
            )
        if self._settings.app_log_llm_prompts:
            logger.debug(
                "eval.judge.llm.prompt model=%s prompt=%s",
                self._model_name,
                self._preview(message),
            )
        try:
            response = await self._llm.ainvoke(message)
            output = str(response.content)
        except Exception:
            logger.exception(
                "eval.judge.llm.failed model=%s duration_seconds=%.3f",
                self._model_name,
                time.perf_counter() - started,
            )
            raise
        if self._settings.app_log_flow_steps:
            logger.info(
                "eval.judge.llm.success model=%s output_chars=%s duration_seconds=%.3f",
                self._model_name,
                len(output),
                time.perf_counter() - started,
            )
        if self._settings.app_log_llm_outputs:
            logger.debug(
                "eval.judge.llm.output model=%s output=%s",
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
