from fastapi import HTTPException, status

from app.domain.schemas.asset_snapshot import AssetType


class LLMUnavailableError(Exception):
    """Raised when the LLM backend is unreachable or returns an error."""


class ServiceError(Exception):
    """Raised for unrecoverable service-layer errors."""


class UnsupportedAssetTypeError(Exception):
    def __init__(self, asset_type: AssetType) -> None:
        self.asset_type = asset_type
        super().__init__(
            f"Asset Snapshot does not currently support asset_type={asset_type.value}"
        )


def llm_unavailable_handler() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="LLM service is currently unavailable. Please try again later.",
    )
