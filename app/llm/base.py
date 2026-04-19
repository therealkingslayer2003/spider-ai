from abc import ABC, abstractmethod


class BaseChatModelClient(ABC):
    @abstractmethod
    async def generate(self, message: str) -> str:
        raise NotImplementedError
