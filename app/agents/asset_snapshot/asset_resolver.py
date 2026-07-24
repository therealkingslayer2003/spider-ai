import re

from app.domain.schemas.asset_resolution import AmbiguousAssetResolution
from app.domain.schemas.asset_snapshot import AssetType
from app.llm.base import BaseChatModelClient
from app.llm.json_parser import parse_llm_json

_TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
_COMMON_COMPANY_NAMES = {
    "APPLE",
    "MICROSOFT",
    "NVIDIA",
}


def resolve_deterministic_asset(asset: str, asset_type: AssetType) -> str | None:
    if asset_type not in {AssetType.STOCK, AssetType.ETF}:
        return None

    normalized_asset = asset.strip().upper()

    if is_ticker_like_asset(normalized_asset):
        return normalized_asset

    for separator in ("(", " ", "/", ":"):
        candidate = normalized_asset.split(separator, maxsplit=1)[0].strip()

        if is_ticker_like_asset(candidate):
            return candidate

    return None


def should_resolve_ambiguous_asset(asset: str, asset_type: AssetType) -> bool:
    if asset_type not in {AssetType.STOCK, AssetType.ETF}:
        return False

    normalized_asset = asset.strip().upper()

    if " " in normalized_asset:
        return True

    if normalized_asset in _COMMON_COMPANY_NAMES:
        return True

    return not is_ticker_like_asset(normalized_asset)


def is_ticker_like_asset(asset: str) -> bool:
    return bool(_TICKER_PATTERN.fullmatch(asset.strip().upper()))


def normalize_resolved_asset(asset: str | None) -> str | None:
    if asset is None:
        return None

    normalized_asset = asset.strip().upper()

    if not is_ticker_like_asset(normalized_asset):
        return None

    return normalized_asset


async def resolve_ambiguous_asset(
    asset: str,
    asset_type: AssetType,
    llm: BaseChatModelClient,
) -> AmbiguousAssetResolution:
    prompt = _build_resolution_prompt(asset=asset, asset_type=asset_type)
    raw_response = await llm.generate(prompt)
    data = parse_llm_json(raw_response)
    return AmbiguousAssetResolution.model_validate(data)


def _build_resolution_prompt(asset: str, asset_type: AssetType) -> str:
    return f"""
Resolve this potentially ambiguous asset input to a likely public market ticker.

Rules:
- Return only valid JSON.
- Do not include markdown.
- If unsure, keep the original asset and use low confidence.
- This resolution is only a pre-check; market data tools will still be called.

Input asset: {asset}
Asset type: {asset_type.value}

Required JSON schema:
{{
  "original_asset": "string",
  "resolved_asset": "string or null",
  "confidence": 0.0,
  "reasoning": "string"
}}
""".strip()
