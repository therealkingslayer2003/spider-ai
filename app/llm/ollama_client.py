import logging
from typing import cast, overload

from langchain_ollama import ChatOllama
from pydantic import BaseModel

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
            num_ctx=self._settings.ollama_num_ctx,
        )

    @overload
    async def generate(self, message: str, *, response_schema: None = None) -> str: ...

    @overload
    async def generate[T: BaseModel](
        self, message: str, *, response_schema: type[T]
    ) -> T: ...

    async def generate(
        self,
        message: str,
        *,
        response_schema: type[BaseModel] | None = None,
    ) -> str | BaseModel:
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
            output: str | BaseModel
            if response_schema is not None:
                structured_model = self._llm.with_structured_output(response_schema)
                output = cast(BaseModel, await structured_model.ainvoke(message))
            else:
                response = await self._llm.ainvoke(message)
                output = str(response.content)
        except Exception:
            logger.exception("llm.generate.failed model=%s", self._model_name)
            raise

        if self._settings.app_log_flow_steps:
            logger.info(
                "llm.generate.success model=%s output_type=%s",
                self._model_name,
                type(output).__name__,
            )

        if self._settings.app_log_llm_outputs:
            preview_text = (
                output.model_dump_json() if isinstance(output, BaseModel) else output
            )
            logger.debug(
                "llm.generate.output model=%s output=%s",
                self._model_name,
                self._preview(preview_text),
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
