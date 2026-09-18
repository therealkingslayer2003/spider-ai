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
    PeerRelationship,
)
from app.domain.schemas.asset_snapshot_evidence import (
    AssetSnapshotEvidence,
    AssetSnapshotRunResult,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.infrastructure.db.dao import SnapshotResearchArtifactDao
from app.infrastructure.db.database import Database
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from app.services.asset_snapshot_service import AssetSnapshotService
from app.services.snapshot_artifact_persistence_service import (
    SnapshotArtifactPersistenceService,
)
from evals.asset_snapshot.dataset import load_dataset
from evals.asset_snapshot.frozen import build_frozen_execution
from evals.asset_snapshot.graders import PeerCoverageGrader
from tests.test_asset_snapshot_context_tools import make_profile
from tests.test_database import make_evidence, make_snapshot, table_counts
from tests.test_evals_execution import FakeGenerationClient


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(tmp_path / "spider-ai.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_missing_peer_tickers_restored_through_graph_service_and_database(
    database: Database,
) -> None:
    case = next(c for c in load_dataset() if c.id == "aapl_stable_platform_peers_001")
    assert case.peers_fixture is not None
    generated_peers = [
        PeerRelationship(
            ticker=None,
            name=peer.name,
            peer_type="comparable",
            relationship_area="Technology products",
            why_relevant=(
                "Provider-reported peer with broad industry similarities; "
                "a specific causal impact is not established here."
            ),
        )
        for peer in reversed(case.peers_fixture.peers)
    ]
    client = FakeGenerationClient("AAPL", "profile_with_peers", generated_peers)
    execution = build_frozen_execution(case, client)
    service = AssetSnapshotService(
        execution.runner, SnapshotArtifactPersistenceService(database)
    )

    result = await service.get_snapshot(case.request)

    assert [peer.ticker for peer in result.peer_landscape] == ["MSFT", "GOOGL"]
    assert all(peer.ticker is None for peer in generated_peers)
    assert "GOOGL" in client.last_prompt and "MSFT" in client.last_prompt
    assert PeerCoverageGrader().grade(case, result).passed
    assert client.calls == 1
    async with database.session_factory() as session:
        stored = await SnapshotResearchArtifactDao(session).get_latest_for_asset(
            "AAPL", "stock"
        )
    assert stored is not None
    assert stored.snapshot == result
    assert stored.evidence.company_peers_context == case.peers_fixture


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
    peer_profile = evidence.company_peers_context.peers[0].profile
    assert peer_profile is not None
    peer_profile.business_summary = (
        "Designs processors. Supplies computing hardware. "
        "Licenses chip designs. Develops graphics products. Provides support. "
        + "Full canonical evidence preserved in persistence. "
        * 40
    )
    original_evidence = evidence.model_dump_json()
    prompt = StockSnapshotPromptBuilder().build_prompt(
        "NVDA", AssetType.STOCK, company_peers_context=evidence.company_peers_context
    )
    assert "Designs processors." in prompt
    assert "Provides support." in prompt
    assert "Full canonical evidence" not in prompt
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
    assert stored.evidence.model_dump_json() == original_evidence
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
