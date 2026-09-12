from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.core.exceptions import ServiceError
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import (
    AssetSnapshotRequest,
    AssetType,
)
from app.domain.schemas.asset_snapshot_evidence import (
    AssetSnapshotEvidence,
    AssetSnapshotRunResult,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.infrastructure.db.dao import SnapshotResearchArtifactDao
from app.infrastructure.db.database import Database
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.snapshot_artifact_persistence_service import (
    SnapshotArtifactPersistenceService,
)
from tests.test_asset_snapshot_context_tools import make_profile
from tests.test_database import make_evidence, make_snapshot, table_counts


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(tmp_path / "spider-ai.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_atomic_snapshot_persistence_rolls_back_on_subtype_failure(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SnapshotArtifactPersistenceService(database)

    async def fail_create(*_args, **_kwargs):
        raise RuntimeError("subtype insert failed")

    monkeypatch.setattr(SnapshotResearchArtifactDao, "create", fail_create)

    with pytest.raises(RuntimeError, match="subtype insert failed"):
        await service.persist(make_snapshot(), make_evidence())

    assert await table_counts(database) == {
        "asset_type": 0,
        "asset": 0,
        "evidence": 0,
        "research_artifact": 0,
        "snapshot_research_artifact": 0,
    }


@pytest.mark.asyncio
async def test_successful_asset_snapshot_is_persisted_after_validation(
    database: Database,
) -> None:
    snapshot = make_snapshot()
    evidence = make_evidence()
    evidence.company_peers_context = CompanyPeersContext(
        asset="NVDA",
        provider="fmp",
        peers=[CompanyPeer(ticker="AMD", profile=make_profile("AMD"))],
    )
    runner = AsyncMock(spec=AssetSnapshotGraphRunner)
    runner.run_result.return_value = AssetSnapshotRunResult(
        snapshot=snapshot,
        evidence=evidence,
    )
    persistence = SnapshotArtifactPersistenceService(
        database,
        model="llama3.1:8b",
        prompt_version="stock_snapshot_v1",
    )
    service = AssetSnapshotService(runner, persistence)

    result = await service.get_snapshot(
        AssetSnapshotRequest(asset="NVDA", asset_type=AssetType.STOCK)
    )

    async with database.session_factory() as session:
        stored = await SnapshotResearchArtifactDao(session).get_latest_for_asset(
            "NVDA",
            "stock",
        )

    assert result == snapshot
    assert stored is not None
    assert stored.snapshot == snapshot
    assert stored.evidence == evidence
    assert stored.model == "llama3.1:8b"
    assert stored.prompt_version == "stock_snapshot_v1"


@pytest.mark.asyncio
async def test_failed_generation_is_not_persisted(database: Database) -> None:
    runner = AsyncMock(spec=AssetSnapshotGraphRunner)
    runner.run_result.side_effect = ServiceError("generation failed")
    service = AssetSnapshotService(
        runner,
        SnapshotArtifactPersistenceService(database),
    )

    with pytest.raises(ServiceError, match="generation failed"):
        await service.get_snapshot(
            AssetSnapshotRequest(asset="NVDA", asset_type=AssetType.STOCK)
        )

    assert await table_counts(database) == {
        "asset_type": 0,
        "asset": 0,
        "evidence": 0,
        "research_artifact": 0,
        "snapshot_research_artifact": 0,
    }


@pytest.mark.asyncio
async def test_persistence_failure_becomes_controlled_service_error() -> None:
    snapshot = make_snapshot()
    evidence = make_evidence()
    runner = AsyncMock(spec=AssetSnapshotGraphRunner)
    runner.run_result.return_value = AssetSnapshotRunResult(
        snapshot=snapshot,
        evidence=evidence,
    )
    persistence = AsyncMock(spec=SnapshotArtifactPersistenceService)
    persistence.persist.side_effect = RuntimeError("database unavailable")
    service = AssetSnapshotService(runner, persistence)

    with pytest.raises(ServiceError, match="persistence failed"):
        await service.get_snapshot(
            AssetSnapshotRequest(asset="NVDA", asset_type=AssetType.STOCK)
        )


@pytest.mark.asyncio
async def test_runner_returns_exact_normalized_evidence() -> None:
    snapshot = make_snapshot()
    evidence = AssetSnapshotEvidence(
        asset_profile_context=AssetProfileContext(
            asset="NVDA",
            asset_type=AssetType.STOCK,
            name="NVIDIA Corporation",
            sector="Technology",
            industry="Semiconductors",
            business_summary="Designs GPUs.",
            exchange="NASDAQ",
            currency="USD",
            country="United States",
            provider="yfinance",
        ),
        data_scope=snapshot.data_scope,
    )
    router_graph = AsyncMock()
    router_graph.ainvoke.return_value = {
        "validated_output": snapshot,
        "evidence": evidence,
        "error": None,
    }
    runner = AssetSnapshotGraphRunner(router_graph)

    result = await runner.run_result(
        AssetSnapshotRequest(asset="NVDA", asset_type=AssetType.STOCK)
    )

    assert result.snapshot == snapshot
    assert result.evidence == evidence


@pytest.mark.asyncio
async def test_persisted_snapshot_survives_database_restart(tmp_path: Path) -> None:
    path = tmp_path / "spider-ai.db"
    snapshot = make_snapshot()
    evidence = make_evidence()
    first_database = Database(path)
    await SnapshotArtifactPersistenceService(first_database).persist(
        snapshot,
        evidence,
    )
    await first_database.close()

    reopened_database = Database(path)
    try:
        await reopened_database.initialize()
        async with reopened_database.session_factory() as session:
            restored = await SnapshotResearchArtifactDao(session).get_latest_for_asset(
                "NVDA", "stock"
            )

        assert restored is not None
        assert restored.snapshot == snapshot
        assert restored.evidence == evidence
    finally:
        await reopened_database.close()
