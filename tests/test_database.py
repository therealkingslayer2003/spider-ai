from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import (
    AssetType,
    CompetitivePeer,
    StockAssetSnapshot,
    StructuralDriver,
    StructuralRisk,
)
from app.domain.schemas.asset_snapshot_evidence import AssetSnapshotEvidence
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.infrastructure.db.dao import (
    AssetDao,
    AssetTypeDao,
    EvidenceDao,
    ResearchArtifactDao,
    SnapshotResearchArtifactDao,
)
from app.infrastructure.db.database import Database
from app.infrastructure.db.models import (
    AssetModel,
    AssetTypeModel,
    EvidenceModel,
    ResearchArtifactModel,
    SnapshotResearchArtifactModel,
)


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(tmp_path / "nested" / "spider-ai.db")
    await database.initialize()
    yield database
    await database.close()


def make_snapshot(summary: str = "GPU platform company.") -> StockAssetSnapshot:
    return StockAssetSnapshot(
        asset="NVDA",
        asset_type=AssetType.STOCK,
        summary=summary,
        business_or_asset_profile="Designs accelerated computing platforms.",
        market_context="Operates in semiconductors.",
        competitive_landscape=[
            CompetitivePeer(
                ticker="AMD",
                name="Advanced Micro Devices",
                competition_area="Accelerators",
                why_competitor="Competes for compute workloads.",
                why_it_matters="Can pressure share and pricing.",
            )
        ],
        structural_drivers=[
            StructuralDriver(
                title="AI demand",
                explanation="AI workloads increase accelerator demand.",
                materiality="high",
            )
        ],
        structural_risks=[
            StructuralRisk(
                title="Foundry concentration",
                explanation="Supply constraints can limit shipments.",
                materiality="high",
                related_competitors=["AMD"],
            )
        ],
        data_scope="profile_with_peers_and_financial_signals",
    )


def make_evidence() -> AssetSnapshotEvidence:
    return AssetSnapshotEvidence(
        asset_profile_context=AssetProfileContext(
            asset="NVDA",
            asset_type=AssetType.STOCK,
            name="NVIDIA Corporation",
            sector="Technology",
            industry="Semiconductors",
            business_summary="Designs accelerated computing platforms.",
            exchange="NASDAQ",
            currency="USD",
            country="United States",
            provider="yfinance",
        ),
        company_peers_context=CompanyPeersContext(
            asset="NVDA",
            provider="fmp",
            peers=[
                CompanyPeer(
                    ticker="AMD",
                    name="Advanced Micro Devices",
                    provider="fmp",
                )
            ],
        ),
        company_fundamentals_context=CompanyFundamentalsContext(
            asset="NVDA",
            provider="yfinance",
            revenue=100.0,
            debt_to_equity_ratio=0.5,
        ),
        data_scope="profile_with_peers_and_financial_signals",
    )


@pytest.mark.asyncio
async def test_database_initialization_creates_file_schema_and_pragmas(
    tmp_path: Path,
) -> None:
    path = tmp_path / "application-data" / "spider-ai.db"
    database = Database(path)

    try:
        await database.initialize()
        await database.initialize()

        assert path.exists()
        async with database.engine.connect() as connection:
            tables = {
                row[0]
                for row in (
                    await connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type = 'table'")
                    )
                ).all()
            }
            foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
            journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
            busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))
            applied_migrations = await connection.scalar(
                text("SELECT COUNT(*) FROM schema_migration")
            )
            indexes = {
                row[0]
                for row in (
                    await connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type = 'index'")
                    )
                ).all()
            }

        assert {
            "schema_migration",
            "asset_type",
            "asset",
            "research_artifact",
            "evidence",
            "snapshot_research_artifact",
        } <= tables
        assert foreign_keys == 1
        assert str(journal_mode).lower() == "wal"
        assert busy_timeout == 5000
        assert applied_migrations == 1
        assert "ix_research_artifact_asset_created_at" in indexes
        assert "ix_evidence_asset_created_at" in indexes
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_asset_type_and_asset_daos_get_or_create(
    database: Database,
) -> None:
    async with database.session_factory() as session, session.begin():
        asset_type_dao = AssetTypeDao(session)
        asset_dao = AssetDao(session)

        stock = await asset_type_dao.get_or_create("stock", "Public stock")
        same_stock = await asset_type_dao.get_or_create("STOCK")
        asset = await asset_dao.get_or_create(stock.id, "nvda")
        same_asset = await asset_dao.get_or_create(stock.id, "NVDA")

        assert stock.id == same_stock.id
        assert asset.id == same_asset.id
        assert asset.name == "NVDA"
        assert await asset_dao.get(asset.id) is asset


@pytest.mark.asyncio
async def test_evidence_dao_round_trips_normalized_contexts(
    database: Database,
) -> None:
    evidence = make_evidence()

    async with database.session_factory() as session, session.begin():
        asset_type = await AssetTypeDao(session).get_or_create("stock")
        asset = await AssetDao(session).get_or_create(asset_type.id, "NVDA")
        evidence_model = await EvidenceDao(session).create(asset.id, evidence)
        restored = await EvidenceDao(session).get_by_id(evidence_model.id)

        assert restored == evidence
        assert restored is not None
        assert restored.asset_profile_context is not None
        assert restored.asset_profile_context.provider == "yfinance"
        assert restored.company_peers_context is not None
        assert restored.company_peers_context.provider == "fmp"


@pytest.mark.asyncio
async def test_research_and_snapshot_daos_restore_latest_aggregate(
    database: Database,
) -> None:
    evidence = make_evidence()
    first_snapshot = make_snapshot("First snapshot")
    latest_snapshot = make_snapshot("Latest snapshot")

    async with database.session_factory() as session, session.begin():
        asset_type = await AssetTypeDao(session).get_or_create("stock")
        asset = await AssetDao(session).get_or_create(asset_type.id, "NVDA")
        research_dao = ResearchArtifactDao(session)
        snapshot_dao = SnapshotResearchArtifactDao(session)

        first_evidence = await EvidenceDao(session).create(asset.id, evidence)
        first_artifact = await research_dao.create(
            asset.id,
            model="llama3.1:8b",
            prompt_version="stock_snapshot_v1",
        )
        first_subtype = await snapshot_dao.create(
            first_artifact.id,
            first_evidence.id,
            first_snapshot,
        )

        latest_evidence = await EvidenceDao(session).create(asset.id, evidence)
        latest_artifact = await research_dao.create(asset.id)
        await snapshot_dao.create(
            latest_artifact.id,
            latest_evidence.id,
            latest_snapshot,
        )

        restored_first = await snapshot_dao.get_by_research_artifact_id(
            first_artifact.id
        )
        restored_latest = await snapshot_dao.get_latest_for_asset("NVDA", "stock")

        assert first_subtype.research_artifact_id == first_artifact.id
        assert first_subtype.evidence_id == first_evidence.id
        assert restored_first is not None
        assert restored_first.snapshot == first_snapshot
        assert restored_first.evidence == evidence
        assert restored_latest is not None
        assert restored_latest.snapshot == latest_snapshot
        assert await research_dao.get_by_id(first_artifact.id) is first_artifact
        assert await research_dao.get_latest_for_asset(asset.id) is latest_artifact


@pytest.mark.asyncio
async def test_foreign_keys_reject_invalid_and_history_deletes(
    database: Database,
) -> None:
    async with database.session_factory() as session:
        session.add(AssetModel(asset_type_id=999, name="INVALID"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_evidence_can_back_only_one_snapshot_artifact(
    database: Database,
) -> None:
    async with database.session_factory() as session, session.begin():
        asset_type = await AssetTypeDao(session).get_or_create("stock")
        asset = await AssetDao(session).get_or_create(asset_type.id, "NVDA")
        evidence = await EvidenceDao(session).create(asset.id, make_evidence())
        first_artifact = await ResearchArtifactDao(session).create(asset.id)
        await SnapshotResearchArtifactDao(session).create(
            first_artifact.id,
            evidence.id,
            make_snapshot(),
        )

    async with database.session_factory() as session:
        second_artifact = ResearchArtifactModel(asset_id=asset.id)
        session.add(second_artifact)
        await session.flush()
        session.add(
            SnapshotResearchArtifactModel(
                research_artifact_id=second_artifact.id,
                evidence_id=evidence.id,
                output_json=make_snapshot().model_dump_json(),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with database.session_factory() as session, session.begin():
        asset_type = await AssetTypeDao(session).get_or_create("stock")
        asset = await AssetDao(session).get_or_create(asset_type.id, "NVDA")
        evidence = await EvidenceDao(session).create(asset.id, make_evidence())
        artifact = await ResearchArtifactDao(session).create(asset.id)
        await SnapshotResearchArtifactDao(session).create(
            artifact.id,
            evidence.id,
            make_snapshot(),
        )

    async with database.session_factory() as session:
        persisted_asset = await session.get(AssetModel, asset.id)
        assert persisted_asset is not None
        await session.delete(persisted_asset)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_schema_has_no_artifact_type_or_claim_tables(
    database: Database,
) -> None:
    async with database.engine.connect() as connection:
        research_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(research_artifact)"))
            ).all()
        }
        tables = {
            row[0]
            for row in (
                await connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'")
                )
            ).all()
        }
        snapshot_columns = {
            row[1]
            for row in (
                await connection.execute(
                    text("PRAGMA table_info(snapshot_research_artifact)")
                )
            ).all()
        }

    assert "artifact_type" not in research_columns
    assert "claim" not in tables
    assert "rationale" not in snapshot_columns


async def table_counts(database: Database) -> dict[str, int]:
    models = (
        AssetTypeModel,
        AssetModel,
        EvidenceModel,
        ResearchArtifactModel,
        SnapshotResearchArtifactModel,
    )
    async with database.session_factory() as session:
        return {
            model.__tablename__: int(
                await session.scalar(select(func.count()).select_from(model)) or 0
            )
            for model in models
        }


def test_application_lifespan_initializes_fresh_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import dependencies
    from app.core.config import get_settings
    from app.main import create_app

    path = tmp_path / "lifespan" / "spider-ai.db"
    monkeypatch.setenv("SPIDER_AI_DB_PATH", str(path))
    get_settings.cache_clear()
    dependencies.get_database.cache_clear()

    try:
        with TestClient(create_app()) as client:
            assert client.get("/api/v1/health").status_code == 200
        assert path.exists()
    finally:
        dependencies.get_database.cache_clear()
        get_settings.cache_clear()
