from app.core.config import get_settings
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.system_prompts import BASE_SYSTEM_PROMPT


class ChatService:
    def __init__(self, llm_client: OllamaChatClient) -> None:
        self._llm_client = llm_client

    async def chat(self, message: str, asset: str | None = None) -> dict:
        user_context = f"Asset: {asset}\n" if asset else ""

        prompt = f"""
                    {BASE_SYSTEM_PROMPT}

                    {user_context}
                    User question:
                    {message}
                """

        answer = await self._llm_client.generate(prompt)

        return {
            "answer": answer,
            "model": get_settings().ollama_chat_model,
        }
