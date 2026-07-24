import os

import httpx
import pytest

from app.agents.asset_snapshot.asset_resolver import (
    normalize_resolved_asset,
    resolve_ambiguous_asset,
)
from app.core.config import get_settings
from app.domain.schemas.asset_snapshot import AssetType
from app.llm.ollama_client import OllamaChatClient

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.live_llm,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_LLM_RESOLVER_TESTS") != "true",
        reason="Set RUN_LIVE_LLM_RESOLVER_TESTS=true to call the configured LLM.",
    ),
]


@pytest.fixture
def live_llm() -> OllamaChatClient:
    _require_configured_ollama_model()
    return OllamaChatClient()


def _require_configured_ollama_model() -> None:
    settings = get_settings()

    try:
        response = httpx.get(
            f"{settings.ollama_base_url.rstrip('/')}/api/tags",
            timeout=2.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(
            "Configured Ollama server is not reachable at "
            f"{settings.ollama_base_url}: {exc}"
        )

    models = {
        model.get("name")
        for model in response.json().get("models", [])
        if isinstance(model, dict)
    }

    if settings.ollama_chat_model not in models:
        pytest.skip(
            f"Configured Ollama model is not available: {settings.ollama_chat_model}"
        )


@pytest.mark.parametrize(
    ("asset", "asset_type", "expected_ticker"),
    [
        ("Apple", AssetType.STOCK, "AAPL"),
        ("Nvidia", AssetType.STOCK, "NVDA"),
        ("Microsoft", AssetType.STOCK, "MSFT"),
        ("Amazon", AssetType.STOCK, "AMZN"),
        ("Meta Platforms", AssetType.STOCK, "META"),
        ("Tesla", AssetType.STOCK, "TSLA"),
        ("Mastercard", AssetType.STOCK, "MA"),
        ("SPDR S&P 500 ETF", AssetType.ETF, "SPY"),
        ("Invesco QQQ Trust", AssetType.ETF, "QQQ"),
    ],
)
async def test_live_llm_resolves_known_assets_accurately(
    live_llm: OllamaChatClient,
    asset: str,
    asset_type: AssetType,
    expected_ticker: str,
) -> None:
    resolution = await resolve_ambiguous_asset(
        asset=asset,
        asset_type=asset_type,
        llm=live_llm,
    )

    normalized_asset = normalize_resolved_asset(resolution.resolved_asset)

    assert resolution.original_asset.upper() == asset.upper()
    assert normalized_asset == expected_ticker
    assert resolution.confidence >= 0.7
    assert resolution.reasoning


@pytest.mark.parametrize(
    ("asset", "asset_type"),
    [
        ("Definitely Not A Real Public Company 98765", AssetType.STOCK),
        ("Imaginary Total Market Rocket Fund", AssetType.ETF),
    ],
)
async def test_live_llm_does_not_confidently_invent_unknown_tickers(
    live_llm: OllamaChatClient,
    asset: str,
    asset_type: AssetType,
) -> None:
    resolution = await resolve_ambiguous_asset(
        asset=asset,
        asset_type=asset_type,
        llm=live_llm,
    )

    normalized_asset = normalize_resolved_asset(resolution.resolved_asset)

    assert normalized_asset is None or resolution.confidence < 0.7
