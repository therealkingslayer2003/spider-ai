from abc import ABC, abstractmethod
from typing import overload

from pydantic import BaseModel


class BaseChatModelClient(ABC):
    @overload
    async def generate(self, message: str, *, response_schema: None = None) -> str: ...

    @overload
    async def generate[T: BaseModel](
        self, message: str, *, response_schema: type[T]
    ) -> T: ...

    @abstractmethod
    async def generate(
        self,
        message: str,
        *,
        response_schema: type[BaseModel] | None = None,
    ) -> str | BaseModel:
        """Return text, or a validated model when a response schema is supplied."""
        raise NotImplementedError
