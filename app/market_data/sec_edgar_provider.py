import asyncio
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.exceptions import ServiceError


class SecSourceNotFoundError(Exception):
    """The SEC has no resource at this URL; this is a source gap."""


class SecEdgarClient:
    def __init__(
        self, user_agent: str | None, *, requests_per_second: float = 5
    ) -> None:
        if requests_per_second <= 0 or requests_per_second > 10:
            raise ValueError("SEC request rate must be between 0 and 10 per second")
        self._user_agent = (user_agent or "").strip()
        self._interval = 1 / requests_per_second
        self._lock = asyncio.Lock()
        self._next_request = 0.0

    async def _get(self, url: str) -> Any:
        if not self._user_agent:
            raise ServiceError(
                "SEC_USER_AGENT must identify an organization and contact."
            )
        for attempt in range(3):
            async with self._lock:
                delay = self._next_request - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                self._next_request = time.monotonic() + self._interval
            try:
                async with httpx.AsyncClient(
                    headers={
                        "User-Agent": self._user_agent,
                        "Accept-Encoding": "gzip, deflate",
                    },
                    timeout=30,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    try:
                        if url.endswith(".json"):
                            return response.json()
                        return response.text
                    except ValueError as exc:
                        raise ServiceError(f"SEC returned invalid JSON: {url}") from exc
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
            ) as exc:
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code == 404
                ):
                    raise SecSourceNotFoundError(url) from exc
                retryable = not isinstance(
                    exc, httpx.HTTPStatusError
                ) or exc.response.status_code in {429, 500, 502, 503, 504}
                if not retryable or attempt == 2:
                    raise ServiceError(f"SEC request failed: {url}") from exc
                await asyncio.sleep(0.5 * 2**attempt)
        raise AssertionError("unreachable")

    async def resolve_cik(self, asset: str) -> str | None:
        if asset.isdecimal() and 1 <= len(asset) <= 10:
            return asset.zfill(10)
        normalized = asset.upper().replace(".", "-")
        mapping = await self._get(
            "https://www.sec.gov/files/company_tickers_exchange.json"
        )
        fields = mapping.get("fields", [])
        for row in mapping.get("data", []):
            item = dict(zip(fields, row, strict=False))
            if str(item.get("ticker", "")).upper().replace(".", "-") == normalized:
                return str(item["cik"]).zfill(10)
        return None

    async def submissions(self, cik: str, as_of: datetime) -> list[dict[str, Any]]:
        root = await self._get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        filings = root.get("filings", {})
        rows = _columnar_rows(filings.get("recent", {}))
        for archive in filings.get("files", []):
            first = date.fromisoformat(archive["filingFrom"])
            if first > as_of.astimezone(ZoneInfo("America/New_York")).date():
                continue
            historical = await self._get(
                f"https://data.sec.gov/submissions/{archive['name']}"
            )
            rows.extend(_columnar_rows(historical))
        return [row for row in rows if filing_available(row, as_of)]

    async def company_facts(self, cik: str) -> dict[str, Any]:
        try:
            return await self._get(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            )
        except SecSourceNotFoundError:
            return {"facts": {}}

    async def document(self, url: str) -> str:
        return await self._get(url)

    async def html_exhibits(self, cik: str, accession: str) -> list[str]:
        base = archive_base(cik, accession)
        try:
            index = await self._get(f"{base}/index.json")
        except SecSourceNotFoundError:
            return []
        items = index.get("directory", {}).get("item", [])
        return [
            f"{base}/{item['name']}"
            for item in items
            if str(item.get("name", "")).lower().endswith((".htm", ".html"))
            and re.search(r"ex(?:hibit)?[-_ ]?\d", str(item.get("name", "")).lower())
        ]


def _columnar_rows(columns: dict[str, list[Any]]) -> list[dict[str, Any]]:
    count = len(columns.get("accessionNumber", []))
    return [
        {key: values[index] for key, values in columns.items() if index < len(values)}
        for index in range(count)
    ]


def filing_available(row: dict[str, Any], as_of: datetime) -> bool:
    filed = date.fromisoformat(row["filingDate"])
    eastern = ZoneInfo("America/New_York")
    if filed > as_of.astimezone(eastern).date():
        return False
    accepted = row.get("acceptanceDateTime")
    if not accepted:
        # A filing date alone cannot establish same-day availability.
        return filed < as_of.astimezone(eastern).date()
    accepted_at = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
    if accepted_at.tzinfo is None:
        accepted_at = accepted_at.replace(tzinfo=eastern)
    return accepted_at <= as_of


def archive_base(cik: str, accession: str) -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}"
    )


def select_filings(rows: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    eligible = sorted(
        (row for row in rows if filing_available(row, as_of)),
        key=lambda row: (row["filingDate"], row.get("acceptanceDateTime", "")),
        reverse=True,
    )
    annual = next((row for row in eligible if row.get("form") == "10-K"), None)
    quarter = next(
        (
            row
            for row in eligible
            if row.get("form") == "10-Q"
            and annual is not None
            and row["filingDate"] > annual["filingDate"]
        ),
        None,
    )
    cutoff = as_of.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=90)
    events = [
        row
        for row in eligible
        if row.get("form") == "8-K" and row["filingDate"] >= cutoff.isoformat()
    ]
    return {"latest_10k": annual, "subsequent_10q": quarter, "recent_8k": events}
