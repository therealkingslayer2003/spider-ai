"""Parent Thesis workflow topology and explicit child-state boundaries."""

from datetime import UTC, datetime
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.agents.asset_thesis.state import (
    PreparedThesisData,
    ThesisAssetOverviewState,
    ThesisCatalystsState,
    ThesisDataPreparationState,
    ThesisState,
)
from app.agents.asset_thesis.subgraphs import (
    ThesisAssetOverviewGraph,
    ThesisCatalystsGraph,
    ThesisDataPreparationGraph,
)
from app.core.exceptions import AssetThesisNotImplementedError, ServiceError
from app.domain.schemas.asset_thesis import ThesisAssetOverview, ThesisCatalyst


class AssetThesisGraph:
    def __init__(
        self,
        data_preparation: ThesisDataPreparationGraph | None = None,
        asset_overview: ThesisAssetOverviewGraph | None = None,
        catalysts: ThesisCatalystsGraph | None = None,
    ) -> None:
        self._data_preparation = data_preparation or ThesisDataPreparationGraph()
        self._asset_overview = asset_overview or ThesisAssetOverviewGraph()
        self._catalysts = catalysts or ThesisCatalystsGraph()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(ThesisState)
        graph.add_node("initialize_research", self.initialize_research)
        graph.add_node("prepare_data", self.prepare_data)
        graph.add_node("asset_overview", self.run_asset_overview)
        graph.add_node("valuation", self.valuation)
        graph.add_node("current_catalysts", self.run_current_catalysts)
        graph.add_node(
            "thesis_risks_and_invalidation", self.thesis_risks_and_invalidation
        )
        graph.add_node("short_thesis_overview", self.short_thesis_overview)
        graph.add_node("assemble_and_validate", self.assemble_and_validate)
        graph.add_node("persist_thesis", self.persist_thesis)

        graph.add_edge(START, "initialize_research")
        graph.add_edge("initialize_research", "prepare_data")
        for branch in ("asset_overview", "valuation", "current_catalysts"):
            graph.add_edge("prepare_data", branch)
        graph.add_edge(
            ["asset_overview", "valuation", "current_catalysts"],
            "thesis_risks_and_invalidation",
        )
        graph.add_edge("thesis_risks_and_invalidation", "short_thesis_overview")
        graph.add_edge("short_thesis_overview", "assemble_and_validate")
        graph.add_edge("assemble_and_validate", "persist_thesis")
        graph.add_edge("persist_thesis", END)
        return graph.compile()

    async def ainvoke(self, state: ThesisState) -> ThesisState:
        return await self.graph.ainvoke(state)

    async def initialize_research(self, state: ThesisState) -> ThesisState:
        research_id = state.get("research_id")
        as_of = state.get("as_of")
        if (research_id is None) != (as_of is None):
            raise ServiceError("Research ID and as_of must be initialized together.")
        if research_id is not None and not research_id.strip():
            raise ServiceError("Research ID must not be empty.")
        if as_of is not None and as_of.utcoffset() is None:
            raise ServiceError("Research as_of must have a timezone.")
        return {
            "asset": state["request"].asset,
            "research_id": research_id if research_id is not None else uuid4().hex,
            "as_of": as_of if as_of is not None else datetime.now(UTC),
        }

    async def prepare_data(self, state: ThesisState) -> ThesisState:
        child_input: ThesisDataPreparationState = {
            "asset": state["asset"],
            "research_id": state["research_id"],
            "as_of": state["as_of"],
        }
        child_output = await self._data_preparation.ainvoke(child_input)
        prepared_data = child_output.get("prepared_data")
        if not isinstance(prepared_data, PreparedThesisData):
            raise ServiceError("Thesis data preparation produced no valid result.")
        return {"prepared_data": prepared_data}

    async def run_asset_overview(self, state: ThesisState) -> ThesisState:
        child_input: ThesisAssetOverviewState = {
            "asset": state["asset"],
            "as_of": state["as_of"],
            "prepared_data": state["prepared_data"],
        }
        snapshot_context = state["request"].snapshot_context
        if snapshot_context is not None:
            child_input["snapshot_context"] = snapshot_context
        child_output = await self._asset_overview.ainvoke(child_input)
        overview = child_output.get("result")
        if not isinstance(overview, ThesisAssetOverview):
            raise ServiceError("Thesis asset overview produced no valid result.")
        return {"asset_overview": overview}

    async def run_current_catalysts(self, state: ThesisState) -> ThesisState:
        child_input: ThesisCatalystsState = {
            "asset": state["asset"],
            "as_of": state["as_of"],
            "prepared_data": state["prepared_data"],
        }
        child_output = await self._catalysts.ainvoke(child_input)
        catalysts = child_output.get("result")
        if not isinstance(catalysts, list) or any(
            not isinstance(catalyst, ThesisCatalyst) for catalyst in catalysts
        ):
            raise ServiceError("Thesis catalysts produced no valid result.")
        return {"current_catalysts": catalysts}

    async def valuation(self, state: ThesisState) -> ThesisState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )

    async def thesis_risks_and_invalidation(self, state: ThesisState) -> ThesisState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )

    async def short_thesis_overview(self, state: ThesisState) -> ThesisState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )

    async def assemble_and_validate(self, state: ThesisState) -> ThesisState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )

    async def persist_thesis(self, state: ThesisState) -> ThesisState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )
