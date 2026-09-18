import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_ollama import ChatOllama
from pydantic import BaseModel, field_validator

from app.agents.asset_snapshot.router.graph import AssetSnapshotRouterGraph
from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.agents.asset_snapshot.stock.graph import StockSnapshotSubgraph
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_snapshot import StockAssetSnapshot
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from evals.asset_snapshot.eval_llm import EvalOllamaClient
from tests.test_graph import (
    llm_response,
    make_empty_fundamentals,
    make_empty_peers,
    make_profile,
    make_request,
)


def model_result(content: str) -> ChatResult:
    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


@pytest.fixture
def model_call(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    # Keep LangChain's schema binding and parser real; mock only model I/O.
    call = AsyncMock()
    monkeypatch.setattr(ChatOllama, "_agenerate", call)
    return call


@pytest.fixture(params=["production", "eval"])
def client(request):
    if request.param == "production":
        return OllamaChatClient()
    return EvalOllamaClient(model="test-judge", base_url="http://localhost:11434")


@pytest.mark.asyncio
async def test_plain_generation_remains_unstructured(client, model_call):
    model_call.return_value = model_result("An ordinary chat answer.")

    assert await client.generate("Hello") == "An ordinary chat answer."
    model_call.assert_awaited_once()
    assert "format" not in model_call.await_args.kwargs


@pytest.mark.asyncio
async def test_plain_generation_does_not_retry(client, model_call):
    model_call.side_effect = OutputParserException("error outside structured mode")

    with pytest.raises(OutputParserException):
        await client.generate("Hello")
    model_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_structured_generation_binds_schema_and_validates(client, model_call):
    model_call.return_value = model_result(llm_response())

    result = await client.generate("Snapshot", response_schema=StockAssetSnapshot)

    assert isinstance(result, StockAssetSnapshot)
    assert result.asset == "NVDA"
    model_call.assert_awaited_once()
    assert (
        model_call.await_args.kwargs["format"] == StockAssetSnapshot.model_json_schema()
    )
    messages = model_call.await_args.args[0]
    assert len(messages) == 1
    assert messages[0].content == "Snapshot"


@pytest.mark.asyncio
async def test_structured_generation_returns_model_without_json_reserialization(
    client, model_call, monkeypatch
):
    model_call.return_value = model_result(llm_response())
    monkeypatch.setattr(client._settings, "app_log_llm_outputs", False)

    def unexpected_serialization(*args, **kwargs):
        raise AssertionError("Structured output must remain a Pydantic model")

    monkeypatch.setattr(StockAssetSnapshot, "model_dump_json", unexpected_serialization)

    result = await client.generate("Snapshot", response_schema=StockAssetSnapshot)

    assert isinstance(result, StockAssetSnapshot)
    assert result.asset == "NVDA"


@pytest.mark.asyncio
async def test_structured_output_preview_does_not_change_the_return_type(
    client, model_call, monkeypatch, caplog
):
    model_call.return_value = model_result(llm_response())
    monkeypatch.setattr(client._settings, "app_log_llm_outputs", True)
    caplog.set_level("DEBUG")

    result = await client.generate("Snapshot", response_schema=StockAssetSnapshot)

    assert isinstance(result, StockAssetSnapshot)
    assert "NVDA" in caplog.text


@pytest.mark.asyncio
async def test_structured_parser_normalizes_materiality(client, model_call):
    payload = json.loads(llm_response())
    payload["structural_drivers"][0]["materiality"] = "High"
    payload["structural_risks"][0]["materiality"] = "Medium"
    model_call.return_value = model_result(json.dumps(payload))

    result = await client.generate("Snapshot", response_schema=StockAssetSnapshot)

    assert result.structural_drivers[0].materiality == "high"
    assert result.structural_risks[0].materiality == "medium"
    model_call.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_output",
    [
        "This is prose, not JSON.",
        '{"asset": "NVDA"}',
        llm_response().replace('"asset_type": "stock"', '"asset_type": "Company"'),
        json.dumps({"snapshot": json.loads(llm_response())}),
        "[]",
    ],
    ids=[
        "non-json",
        "missing-fields",
        "invalid-enum",
        "incorrect-wrapper",
        "root-type",
    ],
)
async def test_structured_generation_propagates_validation_errors_without_retry(
    client, model_call, invalid_output
):
    prompt = "Snapshot instructions\nProvider context: NVIDIA designs GPUs."
    model_call.side_effect = [
        model_result(invalid_output),
        model_result(llm_response()),
    ]

    with pytest.raises(OutputParserException):
        await client.generate(prompt, response_schema=StockAssetSnapshot)
    model_call.assert_awaited_once()
    assert (
        model_call.await_args.kwargs["format"] == StockAssetSnapshot.model_json_schema()
    )
    messages = model_call.await_args.args[0]
    assert len(messages) == 1
    assert messages[0].content == prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing-field", "invalid-literal", "wrong-type"])
async def test_nested_validation_errors_propagate_without_retry(
    client, model_call, failure
):
    payload = json.loads(llm_response())
    if failure == "missing-field":
        del payload["peer_landscape"][0]["why_relevant"]
    elif failure == "invalid-literal":
        payload["structural_risks"][0]["materiality"] = "critical"
    else:
        payload["peer_landscape"][0]["why_relevant"] = 123
    raw_response = f"```json\n{json.dumps(payload, indent=2)}\n```"
    model_call.side_effect = [model_result(raw_response), model_result(llm_response())]

    with pytest.raises(OutputParserException):
        await client.generate("Snapshot", response_schema=StockAssetSnapshot)
    model_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_validator_programming_error_propagates_without_retry(client, model_call):
    class BrokenValidator(BaseModel):
        value: str

        @field_validator("value")
        @classmethod
        def broken(cls, value: str) -> str:
            raise TypeError("validator implementation error")

    model_call.return_value = model_result('{"value": "example"}')

    with pytest.raises(TypeError, match="validator implementation error"):
        await client.generate("Example", response_schema=BrokenValidator)
    model_call.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [TimeoutError("offline"), RuntimeError("unsupported")],
)
async def test_structured_generation_does_not_retry_unrelated_errors(
    client, model_call, error
):
    model_call.side_effect = error

    with pytest.raises(type(error)):
        await client.generate("Snapshot", response_schema=StockAssetSnapshot)
    model_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelling_generation_propagates_without_retry(client, model_call):
    started = asyncio.Event()

    async def wait_for_cancellation(*args, **kwargs):
        started.set()
        await asyncio.Future()

    model_call.side_effect = wait_for_cancellation
    task = asyncio.create_task(
        client.generate("Snapshot", response_schema=StockAssetSnapshot)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    model_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_schema_valid_output_is_not_retried_for_semantic_issues(
    client, model_call
):
    payload = json.loads(llm_response())
    payload["peer_landscape"] = []
    model_call.return_value = model_result(json.dumps(payload))

    result = await client.generate("Snapshot", response_schema=StockAssetSnapshot)

    assert result.peer_landscape == []
    model_call.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_output", [True, False])
async def test_graph_single_generation_and_controlled_failure_without_rerunning_tools(
    model_call, valid_output
):
    model_call.return_value = model_result(
        llm_response() if valid_output else "not JSON"
    )
    profile_tool = AsyncMock(run=AsyncMock(return_value=make_profile()))
    peers_tool = AsyncMock(run=AsyncMock(return_value=make_empty_peers()))
    fundamentals_tool = AsyncMock(run=AsyncMock(return_value=make_empty_fundamentals()))
    subgraph = StockSnapshotSubgraph(
        company_profile_tool=profile_tool,
        company_peers_tool=peers_tool,
        company_fundamentals_tool=fundamentals_tool,
        prompt_builder=StockSnapshotPromptBuilder(),
        llm_client=OllamaChatClient(),
    )
    runner = AssetSnapshotGraphRunner(AssetSnapshotRouterGraph(subgraph))

    if valid_output:
        result = await runner.run(make_request())
        assert isinstance(result, StockAssetSnapshot)
        assert result.asset == "NVDA"
        assert result.data_scope == "profile_only"
    else:
        with pytest.raises(ServiceError, match="Asset snapshot generation failed"):
            await runner.run(make_request())

    model_call.assert_awaited_once()
    original_prompt = model_call.await_args_list[0].args[0][0].content
    assert "Designs GPUs" in original_prompt
    profile_tool.run.assert_awaited_once()
    peers_tool.run.assert_awaited_once()
    fundamentals_tool.run.assert_awaited_once()
