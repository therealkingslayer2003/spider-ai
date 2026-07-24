from langgraph.graph import END, START, StateGraph

from app.agents.asset_snapshot.stock.nodes import (
    ambiguous_asset_resolution_node,
    company_fundamentals_node,
    company_peers_node,
    company_profile_node,
    generate_stock_snapshot_node,
    validate_stock_snapshot_node,
)
from app.agents.asset_snapshot.stock.state import StockSnapshotState
from app.agents.asset_snapshot.tools import (
    CompanyFundamentalsTool,
    CompanyPeersTool,
    CompanyProfileTool,
)
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.feature_snapshot_prompt_builder import StockSnapshotPromptBuilder


class StockSnapshotSubgraph:
    def __init__(
        self,
        company_profile_tool: CompanyProfileTool,
        company_peers_tool: CompanyPeersTool,
        company_fundamentals_tool: CompanyFundamentalsTool,
        prompt_builder: StockSnapshotPromptBuilder,
        llm_client: OllamaChatClient,
    ) -> None:
        self._company_profile_tool = company_profile_tool
        self._company_peers_tool = company_peers_tool
        self._company_fundamentals_tool = company_fundamentals_tool
        self._prompt_builder = prompt_builder
        self._llm_client = llm_client
        self.graph = self._build_graph()

    def _build_graph(self):
        async def ambiguous_asset_resolution_wrapper(state: StockSnapshotState):
            return await ambiguous_asset_resolution_node(state, self._llm_client)

        async def company_profile_wrapper(state: StockSnapshotState):
            return await company_profile_node(state, self._company_profile_tool)

        async def company_peers_wrapper(state: StockSnapshotState):
            return await company_peers_node(state, self._company_peers_tool)

        async def company_fundamentals_wrapper(state: StockSnapshotState):
            return await company_fundamentals_node(
                state,
                self._company_fundamentals_tool,
            )

        async def generate_stock_snapshot_wrapper(state: StockSnapshotState):
            return await generate_stock_snapshot_node(
                state,
                self._llm_client,
                self._prompt_builder,
            )

        graph = StateGraph(StockSnapshotState)
        graph.add_node(
            "ambiguous_asset_resolution",
            ambiguous_asset_resolution_wrapper,
        )
        graph.add_node("company_profile", company_profile_wrapper)
        graph.add_node("company_peers", company_peers_wrapper)
        graph.add_node("company_fundamentals", company_fundamentals_wrapper)
        graph.add_node("generate_stock_snapshot", generate_stock_snapshot_wrapper)
        graph.add_node("validate_stock_snapshot", validate_stock_snapshot_node)

        graph.add_edge(START, "ambiguous_asset_resolution")
        graph.add_edge("ambiguous_asset_resolution", "company_profile")
        graph.add_edge("company_profile", "company_peers")
        graph.add_edge("company_peers", "company_fundamentals")
        graph.add_edge("company_fundamentals", "generate_stock_snapshot")
        graph.add_edge("generate_stock_snapshot", "validate_stock_snapshot")
        graph.add_edge("validate_stock_snapshot", END)

        return graph.compile()

    async def ainvoke(self, state: StockSnapshotState) -> StockSnapshotState:
        return await self.graph.ainvoke(state)
