import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.domain.schemas.asset_profile_context import AssetProfileContext
from app.domain.schemas.asset_snapshot import AssetType
from app.domain.schemas.company_fundamentals_context import (
    CompanyFundamentalsContext,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.market_data.cache import InMemoryTTLCache

logger = logging.getLogger(__name__)

DEFAULT_FMP_BASE_URL = "https://financialmodelingprep.com/stable"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0


class FmpProvider:
    def __init__(
        self,
        api_key: str | None = None,
        enabled: bool | None = None,
        base_url: str | None = None,
        cache: InMemoryTTLCache | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()

        configured_api_key = api_key if api_key is not None else settings.fmp_api_key
        configured_base_url = base_url or settings.fmp_base_url or DEFAULT_FMP_BASE_URL

        self._api_key = self._normalize_api_key(configured_api_key)
        self._enabled = enabled if enabled is not None else settings.fmp_enabled
        self._base_url = self._normalize_base_url(configured_base_url)
        self._cache = cache or InMemoryTTLCache()
        self._client = client

        # Set only when the response explicitly indicates
        # that the API key itself is invalid or missing.
        self._authentication_failed = False

    @property
    def is_configured(self) -> bool:
        return bool(self._enabled and self._api_key and not self._authentication_failed)

    async def get_company_profile(
        self,
        asset: str,
        asset_type: AssetType,
    ) -> AssetProfileContext | None:
        if asset_type != AssetType.STOCK or not self.is_configured:
            return None

        symbol = self._normalize_symbol(asset)
        if not symbol:
            return None

        cache_key = f"fmp:profile:{symbol}:{asset_type.value}"
        cached = self._cache.get(cache_key)

        if isinstance(cached, AssetProfileContext):
            return cached

        rows = await self._get_list(
            path="/profile",
            params={"symbol": symbol},
        )
        if not rows:
            return None

        profile = self._normalize_profile(
            asset=symbol,
            asset_type=asset_type,
            row=rows[0],
        )

        if profile is not None:
            self._cache.set(cache_key, profile)

        return profile

    async def get_company_peers(
        self,
        asset_profile: AssetProfileContext | None = None,
    ) -> CompanyPeersContext:
        symbol = (
            self._normalize_symbol(asset_profile.asset)
            if asset_profile is not None
            else ""
        )

        if not symbol or not self.is_configured:
            return self._empty_peers(symbol)

        cache_key = f"fmp:peers:{symbol}"
        cached = self._cache.get(cache_key)

        if isinstance(cached, CompanyPeersContext):
            return cached

        rows = await self._get_list(
            path="/stock-peers",
            params={"symbol": symbol},
        )

        context = self._normalize_peers(
            asset=symbol,
            rows=rows,
        )

        if rows:
            self._cache.set(cache_key, context)

        return context

    async def get_fundamentals(
        self,
        asset_profile: AssetProfileContext | None = None,
    ) -> CompanyFundamentalsContext:
        symbol = (
            self._normalize_symbol(asset_profile.asset)
            if asset_profile is not None
            else ""
        )

        # Asset Snapshot v1 intentionally does not use FMP premium financial
        # endpoints. FMP remains limited to profile fallback and peer context.
        return self._empty_fundamentals(symbol)

    @property
    def _provider_name(self) -> str:
        return "fmp" if self.is_configured else "fmp_unavailable"

    def _empty_peers(self, asset: str) -> CompanyPeersContext:
        return CompanyPeersContext(
            asset=asset,
            provider=self._provider_name,
            peers=[],
        )

    def _empty_fundamentals(
        self,
        asset: str,
    ) -> CompanyFundamentalsContext:
        return CompanyFundamentalsContext(
            asset=asset,
            provider=self._provider_name,
        )

    async def _get_list(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> list[Mapping[str, Any]]:
        if not self.is_configured:
            return []

        url = f"{self._base_url}/{path.lstrip('/')}"

        request_params: dict[str, Any] = dict(params or {})
        request_params["apikey"] = self._api_key

        try:
            response = await self._send_get_request(
                url=url,
                params=request_params,
            )
        except httpx.TimeoutException:
            logger.warning(
                "fmp_provider.request_timeout path=%s",
                path,
            )
            return []
        except httpx.HTTPError as exc:
            logger.warning(
                "fmp_provider.http_error path=%s error_type=%s",
                path,
                type(exc).__name__,
            )
            return []
        except Exception as exc:
            logger.warning(
                "fmp_provider.request_failed path=%s error_type=%s",
                path,
                type(exc).__name__,
            )
            return []

        if response.status_code in {401, 403}:
            response_body = self._safe_response_body(response)

            if self._is_api_key_authentication_failure(response):
                self._authentication_failed = True

            logger.warning(
                "fmp_provider.access_denied "
                "status=%s path=%s authentication_failed=%s body=%s",
                response.status_code,
                path,
                self._authentication_failed,
                response_body,
            )
            return []

        if response.status_code == 429:
            logger.warning(
                "fmp_provider.rate_limited path=%s body=%s",
                path,
                self._safe_response_body(response),
            )
            return []

        if response.status_code == 402:
            logger.warning(
                "fmp_provider.subscription_restricted path=%s body=%s",
                path,
                self._safe_response_body(response),
            )
            return []

        if response.status_code >= 400:
            logger.warning(
                "fmp_provider.request_failed status=%s path=%s body=%s",
                response.status_code,
                path,
                self._safe_response_body(response),
            )
            return []

        try:
            data = response.json()
        except ValueError:
            logger.warning(
                "fmp_provider.invalid_json path=%s",
                path,
            )
            return []

        if self._is_error_payload(data):
            logger.warning(
                "fmp_provider.error_payload path=%s payload=%s",
                path,
                self._truncate_for_log(data),
            )
            return []

        return self._extract_rows(data)

    async def _send_get_request(
        self,
        url: str,
        params: Mapping[str, Any],
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(
                url,
                params=params,
                timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
            )

        async with httpx.AsyncClient() as client:
            return await client.get(
                url,
                params=params,
                timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
            )

    def _normalize_profile(
        self,
        asset: str,
        asset_type: AssetType,
        row: Mapping[str, Any],
    ) -> AssetProfileContext | None:
        if not any(
            self._clean_string(row.get(key))
            for key in (
                "companyName",
                "sector",
                "industry",
                "description",
            )
        ):
            return None

        return AssetProfileContext(
            asset=asset,
            asset_type=asset_type,
            name=self._clean_string(row.get("companyName")),
            sector=self._clean_string(row.get("sector")),
            industry=self._clean_string(row.get("industry")),
            business_summary=self._clean_string(row.get("description")),
            exchange=(
                self._clean_string(row.get("exchangeShortName"))
                or self._clean_string(row.get("exchange"))
                or self._clean_string(row.get("exchangeFullName"))
            ),
            currency=self._clean_string(row.get("currency")),
            country=self._clean_string(row.get("country")),
            website=self._clean_string(row.get("website")),
            provider="fmp",
            fetched_at=datetime.now(UTC),
        )

    def _normalize_peers(
        self,
        asset: str,
        rows: list[Mapping[str, Any]],
    ) -> CompanyPeersContext:
        peers: list[CompanyPeer] = []
        seen: set[str] = set()

        def add_peer(
            ticker: str | None,
            name: str | None,
        ) -> None:
            normalized_ticker = (
                self._normalize_symbol(ticker) if ticker is not None else None
            )
            normalized_name = self._clean_string(name)

            # Do not include the requested company as its own peer.
            if normalized_ticker == asset:
                return

            identity = normalized_ticker or (
                normalized_name.lower() if normalized_name else None
            )
            if identity is None or identity in seen:
                return

            seen.add(identity)

            peers.append(
                CompanyPeer(
                    ticker=normalized_ticker,
                    name=normalized_name,
                    provider="fmp",
                )
            )

        for row in rows:
            raw_peers = row.get("peersList") or row.get("peers")

            # Support response shapes containing a nested peers list.
            if raw_peers is not None:
                if isinstance(raw_peers, str):
                    for raw_ticker in raw_peers.split(","):
                        add_peer(
                            ticker=raw_ticker,
                            name=None,
                        )

                elif isinstance(raw_peers, list):
                    for item in raw_peers:
                        if isinstance(item, str):
                            add_peer(
                                ticker=item,
                                name=None,
                            )

                        elif isinstance(item, Mapping):
                            add_peer(
                                ticker=self._clean_string(
                                    item.get("symbol") or item.get("ticker")
                                ),
                                name=self._clean_string(
                                    item.get("companyName") or item.get("name")
                                ),
                            )

                continue

            # Support response shapes where every returned row is one peer.
            add_peer(
                ticker=self._clean_string(row.get("symbol") or row.get("ticker")),
                name=self._clean_string(row.get("companyName") or row.get("name")),
            )

        return CompanyPeersContext(
            asset=asset,
            provider="fmp",
            peers=peers,
        )

    @staticmethod
    def _extract_rows(data: Any) -> list[Mapping[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, Mapping)]

        if isinstance(data, Mapping):
            nested_data = data.get("data")

            if isinstance(nested_data, list):
                return [item for item in nested_data if isinstance(item, Mapping)]

            return [data]

        return []

    @staticmethod
    def _is_error_payload(data: Any) -> bool:
        if not isinstance(data, Mapping):
            return False

        lowered_keys = {str(key).strip().lower() for key in data}

        return bool(
            lowered_keys.intersection(
                {
                    "error",
                    "error message",
                    "errormessage",
                }
            )
        )

    @staticmethod
    def _is_api_key_authentication_failure(
        response: httpx.Response,
    ) -> bool:
        if response.status_code == 401:
            return True

        if response.status_code != 403:
            return False

        body = response.text.lower()

        authentication_markers = (
            "invalid api key",
            "missing api key",
            "invalid apikey",
            "missing apikey",
            "api key is invalid",
            "apikey is invalid",
        )

        return any(marker in body for marker in authentication_markers)

    @staticmethod
    def _safe_response_body(
        response: httpx.Response,
    ) -> str:
        return response.text.replace("\n", " ").replace("\r", " ").strip()[:300]

    @staticmethod
    def _truncate_for_log(value: Any) -> str:
        return str(value).replace("\n", " ").strip()[:300]

    @staticmethod
    def _normalize_api_key(value: Any) -> str:
        if value is None:
            return ""

        get_secret_value = getattr(value, "get_secret_value", None)

        if callable(get_secret_value):
            value = get_secret_value()

        return str(value).strip()

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        normalized = value.rstrip("/")
        if normalized.endswith("/api/v3"):
            return f"{normalized[: -len('/api/v3')]}/stable"
        return normalized

    @staticmethod
    def _normalize_symbol(value: str | None) -> str:
        if not value:
            return ""

        return value.strip().upper()

    @staticmethod
    def _clean_string(value: Any) -> str | None:
        if not isinstance(value, str):
            return None

        cleaned = value.strip()
        return cleaned or None
