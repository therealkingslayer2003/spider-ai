import gzip
import hashlib
import re

import pytest
from bs4 import BeautifulSoup, Tag

from app.agents.asset_thesis.rag.html_parser import SecHtmlFilingParser
from app.agents.asset_thesis.rag.identity import make_corpus_id, make_index_version
from app.agents.asset_thesis.rag.splitter import (
    SecFilingChunkSplitter,
    SplitterSettings,
)
from tests.rag.test_thesis_rag_ingestion import (
    AS_OF,
    FIXTURE,
    filing,
    splitter,
    token_counter,
)


def _document(raw: bytes):
    return filing().model_copy(
        update={"content_sha256": hashlib.sha256(raw).hexdigest()}
    )


@pytest.mark.asyncio
async def test_nested_tables_keep_reading_order_and_original_locators() -> None:
    raw = b"""<html><body>
      <div hidden>Removed before parsing</div>
      <div>Part I</div><div>Item 1. Statements</div><div>Note 3. Revenue</div>
      <ix:nonnumeric><div>Before table 202<span>6</span>.</div>
        <table><tr><td>Before nested
          <table><tr><td colspan="2">Period</td><td>Value</td></tr>
                 <tr><td>2026</td><td></td><td>12</td></tr></table>
          After nested</td></tr><tr><td>Later outer row</td></tr></table>
        <div>After table.</div></ix:nonnumeric>
    </body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    texts = [block.text for block in parsed.blocks]
    before = next(i for i, text in enumerate(texts) if "Before table" in text)
    outer_before = next(i for i, text in enumerate(texts) if "Before nested" in text)
    inner = next(i for i, text in enumerate(texts) if "Period | Value" in text)
    outer_after = next(i for i, text in enumerate(texts) if "After nested" in text)
    later = next(i for i, text in enumerate(texts) if "Later outer row" in text)
    after = next(i for i, text in enumerate(texts) if "After table" in text)
    assert before < outer_before < inner < outer_after <= later < after
    assert texts[outer_after].index("After nested") < texts[later].index(
        "Later outer row"
    )
    assert texts[before] == "Before table 2026."
    assert all(
        "Period | Value" not in text for text in texts if "Before nested" in text
    )
    assert "div:nth-of-type(2)" in parsed.blocks[0].source_locator
    assert all(block.source_locator != "body:nth-of-type(1)" for block in parsed.blocks)
    assert all(
        len(block.table_rows) == len(block.text.splitlines())
        for block in parsed.blocks
        if block.kind == "table"
    )
    inner_row = next(
        row
        for block in parsed.blocks
        for row in block.table_rows
        if any(cell.text == "2026" for cell in row.cells)
    )
    assert [(cell.column, cell.text) for cell in inner_row.cells] == [
        (0, "2026"),
        (1, ""),
        (2, "12"),
    ]
    header_row = next(
        row
        for block in parsed.blocks
        for row in block.table_rows
        if any(cell.text == "Period" for cell in row.cells)
    )
    assert header_row.cells[0].colspan == 2


@pytest.mark.asyncio
async def test_table_rowspan_keeps_column_position() -> None:
    raw = (
        b"<html><body><table>"
        b"<tr><td rowspan='2'>Group</td><td>First</td></tr>"
        b"<tr><td>Second</td></tr>"
        b"</table></body></html>"
    )
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    table = next(block for block in parsed.blocks if block.kind == "table")
    assert table.table_rows[0].cells[0].rowspan == 2
    assert table.table_rows[1].cells[0].column == 1


@pytest.mark.asyncio
async def test_page_furniture_does_not_break_note_or_remove_repeated_content() -> None:
    raw = b"""<html><body>
      <div>PART I</div><div>ITEM 1. Statements</div>
      <div><b>Note 14. Legal and Regulatory Proceedings</b></div>
      <p>Repeated substantive sentence.</p>
      <div>1 MASTERCARD JUNE 30, 2026 FORM 10-Q</div><hr>
      <div>PART I</div><div>ITEM 1. Statements</div>
      <div><b>United States</b></div><p>Repeated substantive sentence.</p>
      <div>2 MASTERCARD JUNE 30, 2026 FORM 10-Q</div><hr>
      <div>PART I</div><div>ITEM 1. Statements</div><p>Continued case details.</p>
    </body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    texts = [block.text for block in parsed.blocks]
    assert texts.count("Repeated substantive sentence.") == 2
    assert not any("MASTERCARD JUNE" in text for text in texts)
    assert texts.count("PART I") == 1
    assert texts.count("ITEM 1. Statements") == 1
    continued = next(block for block in parsed.blocks if "Continued case" in block.text)
    assert continued.section_path == [
        "PART I",
        "ITEM 1. Statements",
        "Note 14. Legal and Regulatory Proceedings",
        "United States",
    ]
    chunks = await splitter().split(parsed)
    assert not any(
        chunk.text.strip() in {"PART I", "ITEM 1. Statements"} for chunk in chunks
    )


@pytest.mark.asyncio
async def test_table_context_is_once_per_chunk_and_records_are_not_headers() -> None:
    raw = b"""<html><body><div>Item 6. Exhibits</div>
      <table><tr><td>Exhibit Number</td><td>Exhibit Description</td></tr>
      <tr><td>4.1</td><td>First agreement with meaningful terms
      and 2026 dates.</td></tr>
      <tr><td>4.2</td><td>Second agreement with meaningful terms
      and 2026 dates.</td></tr>
      <tr><td>4.3</td><td>Third agreement with meaningful terms
      and 2026 dates.</td></tr>
      </table></body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    split = SecFilingChunkSplitter(
        SplitterSettings(
            max_tokens=450,
            max_chars=200,
            overlap_tokens=0,
            embedding_max_tokens=450,
            embedding_max_chars=200,
        ),
        token_counter(),
    )
    chunks = await split.split(parsed)
    assert len(chunks) >= 2
    assert all(chunk.text.count("Exhibit Number") == 1 for chunk in chunks)
    assert sum(chunk.text.count("4.1 |") for chunk in chunks) == 1
    assert sum(chunk.text.count("4.2 |") for chunk in chunks) == 1
    assert sum(chunk.text.count("4.3 |") for chunk in chunks) == 1
    assert all(len(chunk.text) <= 200 for chunk in chunks)
    assert all("tr:nth-of-type" in chunk.source_locator for chunk in chunks)
    assert SecHtmlFilingParser.version == "sec-html-v2"
    assert split.version.startswith("sec-structure-v4-")
    new_index = make_index_version(
        embedding_model_version="test",
        parser_version=parsed.parser_version,
        splitter_version=split.version,
    )
    old_index = make_index_version(
        embedding_model_version="test",
        parser_version="sec-html-v1",
        splitter_version=split.version.replace("sec-structure-v4", "sec-structure-v3"),
    )
    assert new_index != old_index

    def corpus(index_version: str) -> str:
        return make_corpus_id(
            asset="MA",
            issuer_cik=filing().issuer_cik,
            as_of=AS_OF,
            documents=[parsed.document],
            index_version=index_version,
        )

    assert corpus(new_index) != corpus(old_index)


@pytest.mark.asyncio
async def test_mastercard_tables_notes_footers_and_locators() -> None:
    with gzip.open(FIXTURE, "rb") as file:
        raw = file.read()
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    chunks = await splitter().split(parsed)
    assert not any(
        block.source_locator == "body:nth-of-type(1)" for block in parsed.blocks
    )
    assert not any(
        "MASTERCARD JUNE 30, 2026 FORM 10-Q" in b.text for b in parsed.blocks
    )
    assert not any(
        chunk.text.strip() in {b.text for b in parsed.blocks if b.kind == "heading"}
        for chunk in chunks
    )

    examples = (
        ("disaggregated net revenue", "Note 3. Revenue"),
        ("customers are generally billed", "Note 3. Revenue"),
        ("components of basic and diluted", "Note 4. Earnings Per Share"),
        ("Debt consisted of the following", "Note 9. Debt"),
        (
            "products and services, resulting",
            "Note 14. Legal and Regulatory Proceedings",
        ),
    )
    for text, note in examples:
        block = next(block for block in parsed.blocks if text in block.text)
        assert block.kind == "paragraph"
        assert note in block.section_path
        assert block.source_locator.startswith("body:nth-of-type(1) > ")
    assert any(
        block.kind == "table"
        and "Payment network" in block.text
        and "(in millions)" in block.text
        and "Note 3. Revenue" in block.section_path
        for block in parsed.blocks
    )
    assert any(
        block.kind == "paragraph"
        and block.text.startswith("1 Americas includes")
        and "Note 3. Revenue" in block.section_path
        for block in parsed.blocks
    )
    operations = [
        chunk
        for chunk in chunks
        if "Consolidated Statements of Operations (Unaudited)" in chunk.text
    ]
    assert 1 <= len(operations) <= 2
    assert all(
        chunk.text.count("Consolidated Statements of Operations") == 1
        for chunk in operations
    )
    assert all(
        chunk.text.count("2026 | 2025 | 2026 | 2025") == 1 for chunk in operations
    )
    revenue = [
        chunk
        for chunk in chunks
        if "Net revenue by category:" in chunk.text
        and "Net revenue by geographic region:" in chunk.text
    ]
    assert len(revenue) == 1
    assert revenue[0].text.count("Net revenue by category:") == 1
    assert revenue[0].text.count("Net revenue by geographic region:") == 1
    exhibits = [
        chunk
        for chunk in chunks
        if chunk.text.startswith("Exhibit Number | Exhibit Description")
    ]
    assert len(exhibits) > 1
    assert sum(chunk.text.count("4.1 |") for chunk in exhibits) == 1
    assert all(chunk.text.count("Exhibit Number") == 1 for chunk in exhibits)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def _source_tag(soup: BeautifulSoup, locator: str) -> Tag:
    if locator.startswith("#"):
        found = soup.find(id=locator[1:])
        assert isinstance(found, Tag)
        return found
    current: Tag | BeautifulSoup = soup
    for step in locator.split(" > "):
        match = re.fullmatch(r"(.+):nth-of-type\((\d+)\)", step)
        assert match is not None, locator
        name, number = match.group(1), int(match.group(2))
        if name == "body" and current is soup:
            found = soup.body
        else:
            matches = [
                child
                for child in current.children
                if isinstance(child, Tag) and child.name == name
            ]
            found = matches[number - 1]
        assert isinstance(found, Tag)
        current = found
    assert isinstance(current, Tag)
    return current


@pytest.mark.asyncio
async def test_multirow_headers_and_nested_groups_split_without_stale_context() -> None:
    raw = b"""<html><body><table>
      <tr><th colspan='4'>Segment results</th></tr>
      <tr><th colspan='2'></th><th colspan='2'>Years ended December 31</th></tr>
      <tr><th colspan='2'></th><th>2026</th><th>2025</th></tr>
      <tr><td colspan='2'></td><td colspan='2'>(in millions)</td></tr>
      <tr><td>Operations:</td><td colspan='3'></td></tr>
      <tr><td></td><td>Domestic:</td><td colspan='2'></td></tr>
      <tr><td></td><td>Card transaction fees</td><td>120</td><td>110</td></tr>
      <tr><td></td><td>Network service fees</td><td>80</td><td>70</td></tr>
      <tr><td></td><td>Regional network maintenance fees</td><td>40</td><td>35</td></tr>
      <tr><td></td><td>Interchange processing services</td><td>30</td><td>25</td></tr>
      <tr><td>Other</td><td colspan='3'></td></tr>
      <tr><td></td><td>Licensing fees</td><td>35</td><td>30</td></tr>
      <tr><td></td><td>Processing fees</td><td>22</td><td>20</td></tr>
    </table></body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    small = SecFilingChunkSplitter(
        SplitterSettings(450, 200, 0, 450, 200), token_counter()
    )
    chunks = await small.split(parsed)
    assert len(chunks) > 1
    for chunk in chunks:
        assert "Segment results" in chunk.text
        assert "Years ended December 31" in chunk.text
        assert "2026 | 2025" in chunk.text
        assert "(in millions)" in chunk.text
        assert len(chunk.text) <= 200
    assert sum(chunk.text.count("Card transaction fees") for chunk in chunks) == 1
    assert sum(chunk.text.count("Licensing fees") for chunk in chunks) == 1
    later = next(chunk for chunk in chunks if "Licensing fees" in chunk.text)
    assert "\nOther\n" in later.text
    assert "Operations:" not in later.text
    assert "Domestic:" not in later.text
    domestic = next(chunk for chunk in chunks if "Network service fees" in chunk.text)
    assert "Operations:" in domestic.text
    assert "Domestic:" in domestic.text

    source = BeautifulSoup(raw, "html.parser")
    for chunk in chunks:
        for reference in chunk.source_locator.split(";"):
            for endpoint in reference.split(".."):
                assert _source_tag(source, endpoint).name == "tr"


@pytest.mark.asyncio
async def test_small_grouped_table_stays_together() -> None:
    raw = b"""<html><body><table>
      <tr><td>2026</td><td>2025</td></tr>
      <tr><td>(in millions)</td></tr>
      <tr><td>Revenue:</td></tr><tr><td>Fees</td><td>12</td><td>10</td></tr>
      <tr><td>Costs:</td></tr><tr><td>Operations</td><td>6</td><td>5</td></tr>
    </table></body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    chunks = await splitter().split(parsed)
    assert len(chunks) == 1
    assert chunks[0].text.count("Revenue:") == 1
    assert chunks[0].text.count("Costs:") == 1
    assert chunks[0].text.index("Revenue:") < chunks[0].text.index("Costs:")


@pytest.mark.asyncio
async def test_trailing_single_cell_row_is_preserved() -> None:
    raw = b"""<html><body><table>
      <tr><td>Metric</td><td>2026</td></tr>
      <tr><td>Revenue</td><td>10</td></tr>
      <tr><td>Footnote reference</td></tr>
    </table></body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    chunks = await splitter().split(parsed)
    assert len(chunks) == 1
    assert chunks[0].text.endswith("Footnote reference")


@pytest.mark.asyncio
async def test_separate_tables_inherit_headers_with_continuation_evidence() -> None:
    raw = b"""<html><body>
      <table><tr><th colspan='3'>Contract balances</th></tr>
      <tr><th>Account</th><th>2026</th><th>2025</th></tr>
      <tr><td colspan='3'>(in millions)</td></tr>
      <tr><td>Receivables</td><td>10</td><td>9</td></tr></table>
      <table><tr><th colspan='3'>Contract balances (continued)</th></tr>
      <tr><td>Prepayments</td><td>8</td><td>7</td></tr></table>
      <table><tr><th colspan='3'>Operating expenses</th></tr>
      <tr><td>Payroll</td><td>4</td><td>3</td></tr></table>
    </body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    chunks = await splitter().split(parsed)
    continued = next(chunk for chunk in chunks if "Prepayments" in chunk.text)
    unrelated = next(chunk for chunk in chunks if "Payroll" in chunk.text)
    assert "Contract balances (continued)" in continued.text
    assert "Account | 2026 | 2025" in continued.text
    assert "(in millions)" in continued.text
    assert "Receivables" not in continued.text
    assert "Contract balances" not in unrelated.text
    assert "Account | 2026 | 2025" not in unrelated.text
    assert "Operating expenses" in unrelated.text
    original = BeautifulSoup(raw, "html.parser")
    for reference in continued.source_locator.split(";"):
        assert _source_tag(original, reference).name == "tr"


@pytest.mark.asyncio
async def test_continuation_marker_requires_matching_columns_and_section() -> None:
    raw = b"""<html><body><div>Item 1. Results</div>
      <table><tr><td>Measure</td><td>2026</td><td>2025</td></tr>
      <tr><td>Revenue</td><td>10</td><td>9</td></tr></table>
      <p>Table continued</p>
      <table><tr><td>Costs</td><td>8</td><td>7</td></tr></table>
      <p>Table continued</p>
      <table><tr><td>Other</td><td>5</td></tr></table>
      <div>Item 2. Risks</div>
      <table><tr><td>Risk</td><td>2026</td><td>2025</td></tr>
      <tr><td>Losses</td><td>2</td><td>1</td></tr></table>
    </body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    chunks = await splitter().split(parsed)
    continued = next(chunk for chunk in chunks if "Costs | 8 | 7" in chunk.text)
    incompatible = next(chunk for chunk in chunks if "Other | 5" in chunk.text)
    different_section = next(chunk for chunk in chunks if "Losses" in chunk.text)
    assert "Measure | 2026 | 2025" in continued.text
    assert "Measure | 2026 | 2025" not in incompatible.text
    assert "Measure | 2026 | 2025" not in different_section.text


@pytest.mark.asyncio
async def test_continuation_marker_does_not_override_a_different_table_title() -> None:
    raw = b"""<html><body>
      <table><tr><th colspan='3'>Contract balances</th></tr>
      <tr><th>Account</th><th>2026</th><th>2025</th></tr>
      <tr><td>Receivables</td><td>10</td><td>9</td></tr></table>
      <p>Table continued</p>
      <table><tr><th colspan='3'>Operating expenses</th></tr>
      <tr><td>Payroll</td><td>4</td><td>3</td></tr></table>
    </body></html>"""
    parsed = await SecHtmlFilingParser().parse(_document(raw), raw)
    chunks = await splitter().split(parsed)
    unrelated = next(chunk for chunk in chunks if "Payroll" in chunk.text)
    assert "Operating expenses" in unrelated.text
    assert "Contract balances" not in unrelated.text
    assert "Account | 2026 | 2025" not in unrelated.text
