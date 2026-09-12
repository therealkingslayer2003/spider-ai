import logging
from dataclasses import dataclass, field

from app.agents.asset_snapshot.router.graph import AssetSnapshotRouterGraph
from app.agents.asset_snapshot.runner import AssetSnapshotGraphRunner
from app.agents.asset_snapshot.stock.graph import StockSnapshotSubgraph
from app.agents.asset_snapshot.tools import (
    CompanyFundamentalsTool,
    CompanyPeersTool,
    CompanyProfileTool,
)
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeersContext
from app.llm.base import BaseChatModelClient
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder
from evals.asset_snapshot.models import StockSnapshotEvalCase

logger = logging.getLogger(__name__)


@dataclass
class FrozenCompanyProfileProvider:
    fixture: AssetProfileContext | None
    calls: int = 0
    peer_profiles: dict[str, AssetProfileContext] = field(default_factory=dict)

    async def get_company_profile(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        self.calls += 1
        if asset_type is AssetType.STOCK and asset.upper() in self.peer_profiles:
            return self.peer_profiles[asset.upper()].model_copy(deep=True)
        if self.fixture is None:
            logger.debug(
                "eval.frozen.profile.result asset=%s asset_type=%s result=missing "
                "calls=%s",
                asset,
                asset_type.value,
                self.calls,
            )
            return None
        if (
            asset.upper() != self.fixture.asset.upper()
            or asset_type is not AssetType.STOCK
        ):
            logger.warning(
                "eval.frozen.profile.result asset=%s asset_type=%s "
                "fixture_asset=%s result=mismatch calls=%s",
                asset,
                asset_type.value,
                self.fixture.asset,
                self.calls,
            )
            return None
        logger.debug(
            "eval.frozen.profile.result asset=%s asset_type=%s result=hit "
            "provider=%s calls=%s",
            asset,
            asset_type.value,
            self.fixture.provider,
            self.calls,
        )
        return self.fixture.model_copy(deep=True)


@dataclass
class FrozenCompanyPeersProvider:
    fixture: CompanyPeersContext | None
    request_asset: str
    calls: int = 0

    async def get_company_peers(
        self,
        asset_profile: AssetProfileContext | None = None,
    ) -> CompanyPeersContext:
        self.calls += 1
        if self.fixture is not None:
            logger.debug(
                "eval.frozen.peers.result asset=%s result=hit peer_count=%s "
                "provider=%s calls=%s",
                self.fixture.asset,
                len(self.fixture.peers),
                self.fixture.provider,
                self.calls,
            )
            context = self.fixture.model_copy(deep=True)
            for peer in context.peers:
                peer.profile = None
            return context
        logger.debug(
            "eval.frozen.peers.result asset=%s result=empty calls=%s",
            self.request_asset,
            self.calls,
        )
        return CompanyPeersContext(
            asset=self.request_asset,
            provider="frozen_eval_unavailable",
            peers=[],
        )


@dataclass
class FrozenFundamentalsProvider:
    fixture: CompanyFundamentalsContext | None
    request_asset: str
    calls: int = 0

    async def get_fundamentals(
        self,
        asset_profile: AssetProfileContext | None = None,
    ) -> CompanyFundamentalsContext:
        self.calls += 1
        if self.fixture is not None:
            logger.debug(
                "eval.frozen.fundamentals.result asset=%s result=hit signals=%s "
                "provider=%s calls=%s",
                self.fixture.asset,
                _financial_signal_count(self.fixture),
                self.fixture.provider,
                self.calls,
            )
            return self.fixture.model_copy(deep=True)
        logger.debug(
            "eval.frozen.fundamentals.result asset=%s result=empty calls=%s",
            self.request_asset,
            self.calls,
        )
        return CompanyFundamentalsContext(
            asset=self.request_asset,
            provider="frozen_eval_unavailable",
        )


@dataclass
class FrozenExecution:
    runner: AssetSnapshotGraphRunner
    profile_provider: FrozenCompanyProfileProvider
    peers_provider: FrozenCompanyPeersProvider
    fundamentals_provider: FrozenFundamentalsProvider


def build_frozen_execution(
    case: StockSnapshotEvalCase,
    llm_client: BaseChatModelClient,
) -> FrozenExecution:
    logger.info(
        "eval.frozen.execution.build case_id=%s asset=%s profile_fixture=%s "
        "peer_count=%s financial_signals=%s",
        case.id,
        case.request.asset,
        case.profile_fixture is not None,
        len(case.peers_fixture.peers) if case.peers_fixture else 0,
        _financial_signal_count(case.fundamentals_fixture),
    )
    profile_provider = FrozenCompanyProfileProvider(
        case.profile_fixture,
        peer_profiles={
            peer.profile.asset.upper(): peer.profile
            for peer in case.peers_fixture.peers
            if peer.profile is not None
        }
        if case.peers_fixture
        else {},
    )
    peers_provider = FrozenCompanyPeersProvider(
        fixture=case.peers_fixture,
        request_asset=case.request.asset,
    )
    fundamentals_provider = FrozenFundamentalsProvider(
        fixture=case.fundamentals_fixture,
        request_asset=case.request.asset,
    )

    profile_tool = CompanyProfileTool(
        primary_provider=profile_provider,
        fallback_provider=None,
    )
    stock_subgraph = StockSnapshotSubgraph(
        company_profile_tool=profile_tool,
        company_peers_tool=CompanyPeersTool(
            provider=peers_provider, profile_tool=profile_tool
        ),
        company_fundamentals_tool=CompanyFundamentalsTool(
            provider=fundamentals_provider
        ),
        prompt_builder=StockSnapshotPromptBuilder(),
        llm_client=llm_client,
    )
    router = AssetSnapshotRouterGraph(stock_snapshot_subgraph=stock_subgraph)
    return FrozenExecution(
        runner=AssetSnapshotGraphRunner(router_graph=router),
        profile_provider=profile_provider,
        peers_provider=peers_provider,
        fundamentals_provider=fundamentals_provider,
    )


def _financial_signal_count(
    fundamentals: CompanyFundamentalsContext | None,
) -> int:
    if fundamentals is None:
        return 0
    return sum(
        value is not None
        for value in (
            fundamentals.revenue,
            fundamentals.revenue_growth,
            fundamentals.operating_margin,
            fundamentals.debt_to_equity_ratio,
        )
    )
