from unittest.mock import AsyncMock

import pytest

from app.services.chat_service import ChatService


@pytest.fixture
def mock_llm() -> AsyncMock:
    client = AsyncMock()
    client.generate.return_value = "Test answer"
    return client


@pytest.mark.asyncio
async def test_chat_returns_answer(mock_llm: AsyncMock) -> None:
    service = ChatService(llm_client=mock_llm)
    result = await service.chat(message="Explain NVDA briefly")
    assert result["answer"] == "Test answer"


@pytest.mark.asyncio
async def test_chat_returns_model_name(mock_llm: AsyncMock) -> None:
    service = ChatService(llm_client=mock_llm)
    result = await service.chat(message="Explain NVDA briefly")
    assert "model" in result
    assert isinstance(result["model"], str)


@pytest.mark.asyncio
async def test_chat_includes_message_in_prompt(mock_llm: AsyncMock) -> None:
    service = ChatService(llm_client=mock_llm)
    await service.chat(message="What is NVDA?")
    prompt_sent = mock_llm.generate.call_args[0][0]
    assert "What is NVDA?" in prompt_sent


@pytest.mark.asyncio
async def test_chat_includes_asset_in_prompt_when_provided(mock_llm: AsyncMock) -> None:
    service = ChatService(llm_client=mock_llm)
    await service.chat(message="Tell me more", asset="NVDA")
    prompt_sent = mock_llm.generate.call_args[0][0]
    assert "NVDA" in prompt_sent


@pytest.mark.asyncio
async def test_chat_no_asset_context_when_asset_is_none(mock_llm: AsyncMock) -> None:
    service = ChatService(llm_client=mock_llm)
    await service.chat(message="Hello", asset=None)
    prompt_sent = mock_llm.generate.call_args[0][0]
    assert "Asset:" not in prompt_sent


@pytest.mark.asyncio
async def test_chat_calls_llm_exactly_once(mock_llm: AsyncMock) -> None:
    service = ChatService(llm_client=mock_llm)
    await service.chat(message="Hello")
    mock_llm.generate.assert_awaited_once()
