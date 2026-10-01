"""Typed child graph boundaries; their workflows arrive in later phases."""

from app.agents.asset_thesis.state import (
    ThesisAssetOverviewState,
    ThesisCatalystsState,
    ThesisDataPreparationState,
)
from app.core.exceptions import AssetThesisNotImplementedError


class ThesisDataPreparationGraph:
    async def ainvoke(
        self, state: ThesisDataPreparationState
    ) -> ThesisDataPreparationState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )


class ThesisAssetOverviewGraph:
    async def ainvoke(
        self, state: ThesisAssetOverviewState
    ) -> ThesisAssetOverviewState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )


class ThesisCatalystsGraph:
    async def ainvoke(self, state: ThesisCatalystsState) -> ThesisCatalystsState:
        raise AssetThesisNotImplementedError(
            "Asset thesis research is not implemented yet."
        )
