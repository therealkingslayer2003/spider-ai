from unittest.mock import AsyncMock

import pytest

from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_chat_service_returns_answer() -> None:
    mock_llm_client = AsyncMock()
    mock_llm_client.generate.return_value = "Test answer"

    service = ChatService(llm_client=mock_llm_client)

    result = await service.chat(message="Explain NVDA briefly")

    assert result["answer"] == "Test answer"
    assert "model" in result
