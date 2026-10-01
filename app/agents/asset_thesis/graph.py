from app.agents.asset_thesis.state import ThesisState
from app.core.exceptions import AssetThesisNotImplementedError


class AssetThesisGraph:
    """Parent graph boundary; phase 2 will compile the workflow here."""

    async def ainvoke(self, state: ThesisState) -> ThesisState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )
