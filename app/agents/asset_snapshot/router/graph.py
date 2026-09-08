from langgraph.graph import END, START, StateGraph

from app.agents.asset_snapshot.router.routing import (
    finalize_router_result,
    route_asset_type,
    selected_asset_type_route,
    unsupported_asset_type_node,
)
from app.agents.asset_snapshot.router.state import AssetSnapshotRouterState
from app.agents.asset_snapshot.stock.graph import StockSnapshotSubgraph
from app.domain.schemas.asset_snapshot_evidence import AssetSnapshotEvidence


class AssetSnapshotRouterGraph:
    def __init__(self, stock_snapshot_subgraph: StockSnapshotSubgraph) -> None:
        self._stock_snapshot_subgraph = stock_snapshot_subgraph
        self.graph = self._build_graph()

    def _build_graph(self):
        async def stock_snapshot_node(
            state: AssetSnapshotRouterState,
        ) -> AssetSnapshotRouterState:
            stock_state = await self._stock_snapshot_subgraph.ainvoke(
                {
                    "request": state["request"],
                    "errors": [],
                }
            )
            errors = stock_state.get("errors", [])
            validated_output = stock_state.get("validated_output")
            evidence = None

            if validated_output is not None:
                evidence = AssetSnapshotEvidence(
                    asset_profile_context=stock_state.get("asset_profile_context"),
                    company_peers_context=stock_state.get("company_peers_context"),
                    company_fundamentals_context=stock_state.get(
                        "company_fundamentals_context"
                    ),
                    data_scope=stock_state.get("data_scope")
                    or validated_output.data_scope,
                )
            return {
                "validated_output": validated_output,
                "evidence": evidence,
                "error": "; ".join(errors) if errors else None,
            }

        graph = StateGraph(AssetSnapshotRouterState)
        graph.add_node("route_asset_type", route_asset_type)
        graph.add_node("stock_snapshot_node", stock_snapshot_node)
        graph.add_node("unsupported_asset_type", unsupported_asset_type_node)
        graph.add_node("finalize_router_result", finalize_router_result)

        graph.add_edge(START, "route_asset_type")
        graph.add_conditional_edges(
            "route_asset_type",
            selected_asset_type_route,
            {
                "stock": "stock_snapshot_node",
                "unsupported": "unsupported_asset_type",
            },
        )
        graph.add_edge("stock_snapshot_node", "finalize_router_result")
        graph.add_edge("finalize_router_result", END)

        return graph.compile()

    async def ainvoke(
        self,
        state: AssetSnapshotRouterState,
    ) -> AssetSnapshotRouterState:
        return await self.graph.ainvoke(state)
