"""Deterministic, source-located parsing of SEC Inline XBRL HTML."""

import asyncio
import logging
import re
from collections.abc import Iterator
from time import perf_counter
from typing import Literal

from bs4 import BeautifulSoup, NavigableString, Tag

from app.agents.asset_thesis.rag.observability import (
    log_failure_once,
    preview,
    rag_run,
)
from app.domain.schemas.thesis_rag import (
    FilingDocument,
    FilingDocumentVersion,
    ParsedFilingBlock,
    ParsedFilingDocument,
    ParsedFilingTableCell,
    ParsedFilingTableRow,
)

_PART = re.compile(r"^PART\s+[IVX]+\b", re.IGNORECASE)
_ITEM = re.compile(r"^ITEM\s+\d+[A-Z]?\s*[.\-:]", re.IGNORECASE)
_NOTE = re.compile(r"^NOTE\s+\d+[A-Z]?\s*[.\-:]", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_FOOTER = re.compile(
    r"^(?:(\d{1,4})\s+)?([A-Z][A-Z0-9 &'.,-]+?)\s+"
    r"((?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|"
    r"OCTOBER|NOVEMBER|DECEMBER)\s+\d{1,2},?\s+\d{4})\s+"
    r"FORM\s+(10-[KQ])(?:\s+(\d{1,4}))?$",
    re.IGNORECASE,
)
_BLOCK_TAGS = {"div", "p", "table", "section", "article", "ul", "ol", "li"}
logger = logging.getLogger(__name__)


def _raw_text(tag: Tag) -> str:
    parts: list[str] = []
    for descendant in tag.descendants:
        if isinstance(descendant, NavigableString):
            parts.append(str(descendant))
        elif isinstance(descendant, Tag):
            if descendant.name == "br" or _visual_gap(descendant):
                parts.append(" ")
    return "".join(parts)


def _visual_gap(tag: Tag) -> bool:
    if tag.name == "sup":
        return True
    style = str(tag.get("style", "")).replace(" ", "").lower()
    return bool(re.search(r"(?:padding|margin)-left:(?!0(?:pt|px|em|%;|$))\d", style))


def _text(tag: Tag) -> str:
    return _SPACE.sub(" ", _raw_text(tag)).strip()


def _span(tag: Tag, attribute: str) -> int:
    value = tag.get(attribute)
    if not isinstance(value, str):
        return 1
    try:
        return max(1, int(value))
    except ValueError:
        return 1


class SecHtmlFilingParser:
    version = "sec-html-v2"

    async def parse(
        self, document: FilingDocument, raw_html: bytes
    ) -> ParsedFilingDocument:
        with rag_run() as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.parse.start run_id=%s document_id=%s input_bytes=%d",
                run_id,
                document.document_id,
                len(raw_html),
            )
            try:
                if not raw_html:
                    raise ValueError("SEC HTML is empty")
                if document.content_sha256 is None:
                    raise ValueError("Parse a stored, content-versioned SEC document")
                parsed = await asyncio.to_thread(self._parse, document, raw_html)
            except Exception:
                log_failure_once(
                    logger, "parse", ids=f"document_id={document.document_id}"
                )
                raise
            logger.info(
                "thesis_rag.parse.done run_id=%s document_id=%s blocks=%d "
                "parser_version=%s duration_ms=%.1f",
                run_id,
                document.document_id,
                len(parsed.blocks),
                self.version,
                (perf_counter() - started) * 1000,
            )
            if logger.isEnabledFor(logging.DEBUG):
                first = parsed.blocks[0]
                logger.debug(
                    "thesis_rag.parse.sample run_id=%s document_id=%s "
                    "block_order=%d chars=%d preview=%r",
                    run_id,
                    document.document_id,
                    first.order,
                    len(first.text),
                    preview(first.text),
                )
            return parsed

    def _parse(self, document: FilingDocument, raw_html: bytes) -> ParsedFilingDocument:
        soup = BeautifulSoup(raw_html, "html.parser")
        # Capture original DOM paths before removing hidden and script nodes.
        locators: dict[int, str] = {}

        def locate(parent: Tag | BeautifulSoup, prefix: str = "") -> None:
            counts: dict[str, int] = {}
            for child in parent.children:
                if not isinstance(child, Tag) or child.name is None:
                    continue
                counts[child.name] = counts.get(child.name, 0) + 1
                step = f"{child.name}:nth-of-type({counts[child.name]})"
                path = (
                    prefix
                    if child.name == "html"
                    else f"{prefix} > {step}".lstrip(" >")
                )
                locators[id(child)] = f"#{child['id']}" if child.get("id") else path
                locate(child, path)

        locate(soup)
        for tag in soup.find_all(True):
            if tag.name is None or tag.attrs is None:
                continue
            style = str(tag.get("style", "")).replace(" ", "").lower()
            if (
                tag.name
                in {"head", "script", "style", "ix:header", "ix:hidden", "ix:exclude"}
                or tag.has_attr("hidden")
                or "display:none" in style
                or "visibility:hidden" in style
            ):
                tag.decompose()
        body = soup.body or soup
        blocks: list[ParsedFilingBlock] = []
        part: str | None = None
        item: str | None = None
        note: str | None = None
        subsection: str | None = None
        after_page_break = False
        emitted_at: dict[int, int] = {}

        def emit(
            tag: Tag,
            value: str,
            kind: Literal["heading", "paragraph", "table"],
            table_rows: list[ParsedFilingTableRow] | None = None,
        ) -> None:
            nonlocal part, item, note, subsection, after_page_break
            value = _SPACE.sub(" ", value).strip() if kind != "table" else value.strip()
            if not value:
                return
            if kind != "table":
                if _PART.match(value) and len(value) < 150:
                    if after_page_break and value == part:
                        return
                    if value != part:
                        item, note, subsection = None, None, None
                    part = value
                    kind = "heading"
                elif _ITEM.match(value) and len(value) < 180:
                    if after_page_break and value == item:
                        return
                    if value != item:
                        note, subsection = None, None
                    item, kind = value, "heading"
                elif _NOTE.match(value) and len(value) < 180:
                    note, subsection, kind = value, None, "heading"
                elif (
                    (part is not None or item is not None)
                    and len(value) < 120
                    and any(
                        _text(bold) == value
                        and (
                            bold.name in {"b", "strong"}
                            or "font-weight:700"
                            in str(bold.get("style", "")).replace(" ", "")
                        )
                        for bold in tag.find_all(["span", "b", "strong"])
                    )
                ):
                    subsection = value
                    kind = "heading"
            if kind != "heading":
                after_page_break = False
            section = [
                name for name in (part, item, note, subsection) if name is not None
            ]
            emitted_at[id(tag)] = emitted_at.get(id(tag), 0) + 1
            base_locator = locators[id(tag)]
            locator = (
                base_locator
                if emitted_at[id(tag)] == 1
                else f"{base_locator}/segment:{emitted_at[id(tag)]}"
            )
            blocks.append(
                ParsedFilingBlock(
                    order=len(blocks),
                    kind=kind,
                    text=value,
                    section_path=section,
                    source_locator=locator,
                    table_rows=table_rows or [],
                )
            )

        def cell_items(cell: Tag) -> Iterator[str | Tag]:
            for child in cell.children:
                if isinstance(child, NavigableString):
                    yield str(child)
                elif isinstance(child, Tag):
                    if child.name == "table":
                        yield child
                    elif child.name == "br":
                        yield " "
                    else:
                        if _visual_gap(child):
                            yield " "
                        yield from cell_items(child)

        def walk_table(tag: Tag) -> None:
            rows: list[str] = []
            row_details: list[ParsedFilingTableRow] = []
            rowspans: dict[int, int] = {}

            def flush_rows() -> None:
                if rows:
                    emit(tag, "\n".join(rows), "table", row_details.copy())
                    rows.clear()
                    row_details.clear()

            def add_row(row: Tag, cells: list[ParsedFilingTableCell]) -> None:
                rendered = " | ".join(cell.text for cell in cells if cell.text)
                if rendered:
                    rows.append(rendered)
                    row_details.append(
                        ParsedFilingTableRow(
                            source_locator=locators[id(row)], cells=cells.copy()
                        )
                    )

            for row in tag.find_all("tr"):
                if row.find_parent("table") is not tag:
                    continue
                cells = row.find_all(["td", "th"], recursive=False)
                row_cells: list[ParsedFilingTableCell] = []
                column = 0
                occupied = set(rowspans)
                next_rowspans = {
                    position: remaining - 1
                    for position, remaining in rowspans.items()
                    if remaining > 1
                }
                for cell in cells:
                    colspan = _span(cell, "colspan")
                    rowspan = _span(cell, "rowspan")
                    while any(
                        position in occupied
                        for position in range(column, column + colspan)
                    ):
                        column += 1
                    if rowspan > 1:
                        for position in range(column, column + colspan):
                            next_rowspans[position] = rowspan - 1

                    def add_cell(value: str) -> None:
                        row_cells.append(
                            ParsedFilingTableCell(
                                column=column,
                                colspan=colspan,
                                rowspan=rowspan,
                                text=value,
                                source_locator=locators[id(cell)],
                            )
                        )

                    text_parts: list[str] = []
                    for item in cell_items(cell):
                        if isinstance(item, Tag):
                            value = _SPACE.sub(" ", "".join(text_parts)).strip()
                            if value:
                                add_cell(value)
                            add_row(row, row_cells)
                            flush_rows()
                            walk_table(item)
                            row_cells.clear()
                            text_parts.clear()
                        else:
                            text_parts.append(item)
                    value = _SPACE.sub(" ", "".join(text_parts)).strip()
                    add_cell(value)
                    column += colspan
                add_row(row, row_cells)
                rowspans = next_rowspans
            flush_rows()

        def walk(tag: Tag) -> None:
            nonlocal after_page_break
            if tag.name == "table":
                walk_table(tag)
                return
            if tag.name in {"svg", "img", "noscript"}:
                return
            # Inline XBRL tags remain part of their surrounding paragraph.
            inline: list[str] = []

            def flush() -> None:
                if inline:
                    emit(tag, "".join(inline), "paragraph")
                    inline.clear()

            for child in tag.children:
                if isinstance(child, Tag):
                    if child.name == "hr":
                        flush()
                        after_page_break = True
                    elif child.name in _BLOCK_TAGS or child.find(_BLOCK_TAGS):
                        flush()
                        walk(child)
                    else:
                        value = (" " if _visual_gap(child) else "") + _raw_text(child)
                        if value:
                            inline.append(value)
                elif str(child).strip():
                    inline.append(str(child).strip())
            flush()

        walk(body)
        furniture: dict[tuple[str, str, str], set[str]] = {}
        for block in blocks:
            match = _FOOTER.fullmatch(block.text)
            if match and (page := match.group(1) or match.group(5)):
                key = (match.group(2), match.group(3), match.group(4))
                furniture.setdefault(key, set()).add(page)
        repeated = {key for key, pages in furniture.items() if len(pages) > 1}
        retained: list[ParsedFilingBlock] = []
        for block in blocks:
            match = _FOOTER.fullmatch(block.text)
            if match and (match.group(2), match.group(3), match.group(4)) in repeated:
                continue
            retained.append(block.model_copy(update={"order": len(retained)}))
        blocks = retained
        if not blocks:
            raise ValueError("SEC HTML contains no visible filing content")
        assert document.content_sha256 is not None
        return ParsedFilingDocument(
            document=FilingDocumentVersion(
                document_id=document.document_id,
                content_sha256=document.content_sha256,
            ),
            parser_version=self.version,
            blocks=blocks,
        )
