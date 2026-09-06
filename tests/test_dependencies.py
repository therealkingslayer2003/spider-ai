from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import dependencies
from app.domain.schemas.asset_snapshot import AssetType


@pytest.fixture(autouse=True)
def clear_dependency_caches() -> Iterator[None]:
    dependencies.get_snapshot_artifact_persistence_service.cache_clear()
    dependencies.get_database.cache_clear()
    dependencies.get_optional_fmp_provider.cache_clear()
    dependencies.get_profile_tool.cache_clear()
    yield
    dependencies.get_snapshot_artifact_persistence_service.cache_clear()
    dependencies.get_database.cache_clear()
    dependencies.get_optional_fmp_provider.cache_clear()
    dependencies.get_profile_tool.cache_clear()


def test_optional_fmp_provider_is_none_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MagicMock(fmp_enabled=False, fmp_api_key=None)
    provider_factory = MagicMock()
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(dependencies, "FmpProvider", provider_factory)

    result = dependencies.get_optional_fmp_provider()

    assert result is None
    provider_factory.assert_not_called()


def test_optional_fmp_provider_is_available_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MagicMock()
    settings = MagicMock(
        fmp_enabled=True,
        fmp_api_key="configured-key",
        fmp_cache_ttl_seconds=86_400,
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(
        dependencies,
        "FmpProvider",
        MagicMock(return_value=provider),
    )

    result = dependencies.get_optional_fmp_provider()

    assert result is provider


def test_database_uses_configured_local_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "configured" / "spider-ai.db"
    settings = MagicMock(spider_ai_db_path=path)
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)

    database = dependencies.get_database()

    assert database.path == path.resolve()
    assert path.parent.exists()


@pytest.mark.asyncio
async def test_profile_tool_receives_composed_provider_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = AsyncMock()
    fallback = AsyncMock()
    primary.get_company_profile.return_value = None
    fallback.get_company_profile.return_value = None
    monkeypatch.setattr(dependencies, "get_yfinance_provider", lambda: primary)
    monkeypatch.setattr(dependencies, "get_optional_fmp_provider", lambda: fallback)

    tool = dependencies.get_profile_tool()
    result = await tool.run(asset="AAPL", asset_type=AssetType.STOCK)

    assert result is None
    primary.get_company_profile.assert_awaited_once()
    fallback.get_company_profile.assert_awaited_once()
