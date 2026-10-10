from datetime import UTC, datetime

import httpx
import pytest

from app.market_data.sec_edgar_provider import (
    SecEdgarClient,
    filing_available,
    select_filings,
)


def filing(form: str, filed: str, number: int) -> dict[str, str]:
    return {
        "form": form,
        "filingDate": filed,
        "acceptanceDateTime": f"{filed}T10:00:00",
        "accessionNumber": f"0000000123-26-{number:06d}",
        "primaryDocument": f"report{number}.htm",
    }


def test_selection_uses_acceptance_time_annual_anchor_and_90_day_window():
    as_of = datetime(2026, 10, 1, 13, tzinfo=UTC)
    rows = [
        filing("10-K", "2026-02-01", 1),
        filing("10-Q", "2026-01-01", 2),
        filing("10-Q", "2026-05-01", 3),
        filing("8-K", "2026-06-01", 4),
        filing("8-K", "2026-09-20", 5),
        filing("8-K", "2026-10-01", 6),
    ]

    assert not filing_available(rows[-1], as_of)
    selected = select_filings(rows, as_of)
    assert selected["latest_10k"] == rows[0]
    assert selected["subsequent_10q"] == rows[2]
    assert selected["recent_8k"] == [rows[4]]


@pytest.mark.asyncio
async def test_numeric_cik_needs_no_ticker_lookup():
    class OfflineSec(SecEdgarClient):
        async def _get(self, url: str):
            raise AssertionError("Ticker lookup was not expected")

    assert await OfflineSec("Research contact@example.com").resolve_cik("123") == (
        "0000000123"
    )


@pytest.mark.asyncio
async def test_exhibit_index_finds_prefixed_html_files():
    class OfflineSec(SecEdgarClient):
        async def _get(self, url: str):
            return {
                "directory": {
                    "item": [
                        {"name": "d123ex991.htm"},
                        {"name": "report.htm"},
                        {"name": "ex101.xml"},
                    ]
                }
            }

    urls = await OfflineSec("Research contact@example.com").html_exhibits(
        "0000000123", "0000000123-26-000003"
    )
    assert len(urls) == 1
    assert urls[0].endswith("/d123ex991.htm")


@pytest.mark.asyncio
async def test_document_keeps_original_response_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b"<html>non-UTF8 \xff</html>"

    class OfflineHttpClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str):
            return httpx.Response(200, request=httpx.Request("GET", url), content=raw)

    monkeypatch.setattr(httpx, "AsyncClient", OfflineHttpClient)
    assert (
        await SecEdgarClient("Research contact@example.com").document(
            "https://www.sec.gov/test.htm"
        )
        == raw
    )
