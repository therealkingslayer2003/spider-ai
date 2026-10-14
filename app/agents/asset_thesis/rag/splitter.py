"""Versioned structure-first splitting with model-tokenized input bounds."""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from time import perf_counter

from app.agents.asset_thesis.rag.identity import make_chunk_id
from app.agents.asset_thesis.rag.observability import (
    current_run_id,
    log_failure_once,
    preview,
    rag_run,
)
from app.domain.schemas.thesis_rag import (
    FilingChunk,
    ParsedFilingBlock,
    ParsedFilingDocument,
)
from app.llm.tokenization import TokenCounter

_SENTENCES = re.compile(r"(?<=[.!?])\s+(?=[A-Z\d(])")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_VALUE = re.compile(r"^(?:[$€£]|[+-]?(?:\d|\(\d)|[—–−-]$|\*\*$)")
_ROW_ID = re.compile(r"^\d+(?:\.\d+)?(?:[A-Z*]|\b)")
_UNIT = re.compile(r"^\(?\s*(?:[$€£]\s*)?in\s+\w+", re.IGNORECASE)
_PERIOD = re.compile(
    r"\b(?:ended|as of|january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b",
    re.IGNORECASE,
)
_CONTINUED = re.compile(r"\bcontinu(?:ed|ation)\b", re.IGNORECASE)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _TableRow:
    text: str
    locator: str
    kind: str
    column: int = 0


@dataclass(frozen=True)
class _TableLayout:
    header: tuple[_TableRow, ...]
    body: tuple[_TableRow, ...]
    width: int
    title: str
    section: tuple[str, ...]


@dataclass(frozen=True)
class SplitterSettings:
    max_tokens: int
    max_chars: int
    overlap_tokens: int
    embedding_max_tokens: int
    embedding_max_chars: int

    def __post_init__(self) -> None:
        if self.max_tokens < 50 or self.max_chars < 200:
            raise ValueError("Chunk limits are too small")
        if not 0 <= self.overlap_tokens < self.max_tokens // 2:
            raise ValueError("Chunk overlap must be less than half the token limit")
        if (
            self.max_tokens > self.embedding_max_tokens
            or self.max_chars > self.embedding_max_chars
        ):
            raise ValueError("Chunk limits cannot exceed embedding input limits")


class SecFilingChunkSplitter:
    def __init__(self, settings: SplitterSettings, token_counter: TokenCounter) -> None:
        self.settings = settings
        self._token_counter = token_counter
        digest = hashlib.sha256(
            json.dumps(
                {"settings": settings.__dict__, "tokenizer": token_counter.version},
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
        self.version = f"sec-structure-v4-{digest}"

    async def split(self, document: ParsedFilingDocument) -> list[FilingChunk]:
        with rag_run() as run_id:
            started = perf_counter()
            document_id = document.document.document_id
            logger.info(
                "thesis_rag.split.start run_id=%s document_id=%s blocks=%d "
                "splitter_version=%s",
                run_id,
                document_id,
                len(document.blocks),
                self.version,
            )
            try:
                chunks = await asyncio.to_thread(self._split, document)
            except Exception:
                log_failure_once(logger, "split", ids=f"document_id={document_id}")
                raise
            logger.info(
                "thesis_rag.split.done run_id=%s document_id=%s chunks=%d "
                "text_tokens=%d duration_ms=%.1f",
                run_id,
                document_id,
                len(chunks),
                sum(chunk.token_count for chunk in chunks),
                (perf_counter() - started) * 1000,
            )
            return chunks

    def _fits(self, text: str) -> bool:
        return (
            len(text) <= self.settings.max_chars
            and self._token_counter.count_text(text) <= self.settings.max_tokens
            and len(self._token_counter.format_embedding_input(text, "document"))
            <= self.settings.embedding_max_chars
            and self._token_counter.count_embedding_input(text, "document")
            <= self.settings.embedding_max_tokens
        )

    def _pieces(self, text: str, prefix: str = "") -> list[str]:
        def fits_first(piece: str) -> bool:
            candidate = f"{prefix}\n{piece}" if prefix and not pieces else piece
            return self._fits(candidate)

        pieces: list[str] = []
        if self._fits(f"{prefix}\n{text}" if prefix else text):
            return [text]
        for sentence in _SENTENCES.split(text):
            if fits_first(sentence):
                pieces.append(sentence)
                continue
            words = sentence.split()
            current = ""
            for word in words:
                candidate = f"{current} {word}".strip()
                if not fits_first(candidate):
                    if not current:
                        raise ValueError(
                            "A filing contains an indivisible overlong token"
                        )
                    pieces.append(current)
                    current = word
                    if not fits_first(current):
                        raise ValueError(
                            "A filing contains an indivisible overlong token"
                        )
                else:
                    current = candidate
            if current:
                pieces.append(current)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "thesis_rag.split.pieces run_id=%s input_chars=%d pieces=%d preview=%r",
                current_run_id(),
                len(text),
                len(pieces),
                preview(text),
            )
        return pieces

    @staticmethod
    def _is_data_row(cells: list[str]) -> bool:
        if not cells:
            return False
        if len(cells) == 1 and _VALUE.match(cells[0]):
            return not bool(_YEAR.fullmatch(cells[0]))
        if len(cells) > 1 and _ROW_ID.match(cells[0]) and not _YEAR.fullmatch(cells[0]):
            return True
        values = [cell for cell in cells[1:] if _VALUE.match(cell)]
        return bool(values) and not all(_YEAR.fullmatch(cell) for cell in values)

    @staticmethod
    def _table_layout(block: ParsedFilingBlock) -> _TableLayout:
        lines = block.text.splitlines()
        details = block.table_rows
        if details and len(details) != len(lines):
            raise ValueError("Table row provenance does not match table content")
        header: list[_TableRow] = []
        body: list[_TableRow] = []
        width = 0
        started = False
        header_context = False
        for index, line in enumerate(lines):
            if details:
                detail = details[index]
                visible = [cell for cell in detail.cells if cell.text]
                cells = [cell.text for cell in visible]
                column = visible[0].column if visible else 0
                width = max(
                    width,
                    max(
                        (cell.column + cell.colspan for cell in detail.cells),
                        default=0,
                    ),
                )
                locator = detail.source_locator
            else:
                cells = [cell.strip() for cell in line.split(" | ")]
                column = 0
                width = max(width, len(cells))
                locator = f"{block.source_locator}/row:{index + 1}"
            single = len(cells) == 1
            data = SecFilingChunkSplitter._is_data_row(cells)
            group = (
                single
                and not data
                and (
                    line.endswith(":")
                    or (started or header_context)
                    and not _UNIT.match(line)
                    and not _PERIOD.search(line)
                    and not _YEAR.fullmatch(line)
                )
            )
            if group:
                started = True
                body.append(_TableRow(line, locator, "group", column))
            elif data or started:
                started = True
                body.append(_TableRow(line, locator, "data", column))
            else:
                header.append(_TableRow(line, locator, "header", column))
                header_context |= bool(
                    _UNIT.match(line)
                    or _PERIOD.search(line)
                    or len(cells) > 1
                    or all(_YEAR.fullmatch(cell) for cell in cells)
                )
        # Text-only tables still have records after their first label row.
        if not body and len(header) > 1:
            body = [
                _TableRow(row.text, row.locator, "data", row.column)
                for row in header[1:]
            ]
            header = header[:1]
        for index, row in enumerate(body):
            if row.kind != "group":
                continue
            following = body[index + 1] if index + 1 < len(body) else None
            if following is None or (
                following.kind == "group" and following.column <= row.column
            ):
                body[index] = _TableRow(row.text, row.locator, "data", row.column)
        title = ""
        if header:
            first = header[0].text
            if (
                " | " not in first
                and not _PERIOD.search(first)
                and not _UNIT.match(first)
            ):
                title = first
        return _TableLayout(
            tuple(header), tuple(body), width, title, tuple(block.section_path)
        )

    @staticmethod
    def _continuation_header(
        previous: _TableLayout | None,
        current: _TableLayout,
        continuation_marker: bool,
    ) -> tuple[_TableRow, ...]:
        if (
            previous is None
            or not previous.header
            or previous.section != current.section
        ):
            return current.header
        if previous.width != current.width:
            return current.header
        title = re.sub(r"\s*\(?continued\)?\s*$", "", current.title, flags=re.I)
        matching_title = bool(
            title and previous.title and title.casefold() == previous.title.casefold()
        )
        explicitly_continued = continuation_marker or bool(
            current.title and _CONTINUED.search(current.title)
        )
        if not explicitly_continued or (title and current.title and not matching_title):
            return current.header
        current_rest = [row.text for row in current.header if row.text != current.title]
        previous_rest = [
            row.text for row in previous.header if row.text != previous.title
        ]
        if current_rest and not all(row in previous_rest for row in current_rest):
            return current.header
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "thesis_rag.split.table_continuation run_id=%s width=%d title=%r",
                current_run_id(),
                current.width,
                previous.title,
            )
        if current.title and matching_title:
            return (current.header[0], *previous.header[1:])
        return previous.header

    def _table_units(
        self,
        block: ParsedFilingBlock,
        header: tuple[_TableRow, ...],
        body: tuple[_TableRow, ...],
        heading: str = "",
        heading_locator: str = "",
    ) -> list[tuple[str, str]]:
        units: list[tuple[str, str]] = []
        groups: list[_TableRow] = []
        pending_groups: list[_TableRow] = []
        prefix_rows = [row.text for row in header]
        prefix_refs = [row.locator for row in header]
        content_rows: list[tuple[str, str]] = []
        has_data = False

        def prefix() -> list[str]:
            return ([heading] if heading and not units else []) + prefix_rows

        def text_with(rows: list[tuple[str, str]]) -> str:
            return "\n".join([*prefix(), *(text for text, _ in rows)])

        def flush() -> None:
            nonlocal has_data
            if not has_data:
                return
            text = text_with(content_rows)
            refs = list(
                dict.fromkeys(
                    [
                        *([heading_locator] if heading and not units else []),
                        *prefix_refs,
                        *(ref for _, ref in content_rows),
                    ]
                )
            )
            units.append((text, ";".join(refs) or block.source_locator))
            content_rows.clear()
            has_data = False

        for row in body:
            if row.kind == "group":
                groups = [group for group in groups if group.column < row.column]
                groups.append(row)
                pending_groups = [
                    group for group in pending_groups if group.column < row.column
                ]
                pending_groups.append(row)
                continue
            context = [(group.text, group.locator) for group in groups]
            if not has_data:
                content_rows = context.copy()
            additions = (
                [(group.text, group.locator) for group in pending_groups]
                if has_data
                else []
            )
            label, separator, detail = row.text.partition(" | ")
            row_prefix = "\n".join([*prefix(), *(text for text, _ in context)])
            if separator and len(label) < 100:
                fragment_prefix = f"{row_prefix}\n{label} |"
                fragments = [
                    f"{label} | {piece}"
                    for piece in self._pieces(detail, prefix=fragment_prefix)
                ]
            else:
                fragments = self._pieces(row.text, prefix=row_prefix)
            for fragment in fragments:
                candidate_rows = [*content_rows, *additions, (fragment, row.locator)]
                if not self._fits(text_with(candidate_rows)):
                    flush()
                    content_rows = context.copy()
                    additions = []
                    candidate_rows = [*content_rows, (fragment, row.locator)]
                    if not self._fits(text_with(candidate_rows)):
                        raise ValueError(
                            "Table row and required context exceed chunk limits"
                        )
                content_rows = candidate_rows
                has_data = True
                additions = []
            pending_groups.clear()
        flush()
        if not units:
            only_context = "\n".join([*prefix(), *(row.text for row in body)])
            if not self._fits(only_context):
                raise ValueError("Table header exceeds chunk limits")
            refs = [*([heading_locator] if heading else []), *prefix_refs]
            units.append((only_context, ";".join(refs) or block.source_locator))
        return units

    def _split(self, document: ParsedFilingDocument) -> list[FilingChunk]:
        chunks: list[FilingChunk] = []
        pending = ""
        first_locator = ""
        last_locator = ""
        section: list[str] = []
        heading = ""
        heading_locator = ""
        previous_unit = ""
        previous_locator = ""
        previous_table: _TableLayout | None = None
        continuation_marker = False

        def emit(value: str, locator: str, path: list[str]) -> None:
            if not self._fits(value):
                raise ValueError("A filing chunk exceeds configured limits")
            position = len(chunks)
            chunks.append(
                FilingChunk(
                    chunk_id=make_chunk_id(
                        document.document,
                        parser_version=document.parser_version,
                        splitter_version=self.version,
                        position=position,
                        source_locator=locator,
                        text=value,
                    ),
                    document=document.document,
                    text=value,
                    section_path=path.copy(),
                    position=position,
                    source_locator=locator,
                    token_count=self._token_counter.count_text(value),
                    parser_version=document.parser_version,
                    splitter_version=self.version,
                )
            )
            if logger.isEnabledFor(logging.DEBUG):
                chunk = chunks[-1]
                logger.debug(
                    "thesis_rag.split.chunk run_id=%s document_id=%s "
                    "chunk_id=%s position=%d chars=%d text_tokens=%d preview=%r",
                    current_run_id(),
                    document.document.document_id,
                    chunk.chunk_id,
                    chunk.position,
                    len(chunk.text),
                    chunk.token_count,
                    preview(chunk.text),
                )

        def flush() -> None:
            nonlocal pending
            if not pending:
                return
            locator = (
                first_locator
                if first_locator == last_locator
                else f"{first_locator}..{last_locator}"
            )
            emit(pending, locator, section)
            pending = ""

        for block in document.blocks:
            if block.kind == "heading":
                previous_table = None
                continuation_marker = False
                flush()
                previous_unit = ""
                previous_locator = ""
                heading = f"{heading}\n{block.text}" if heading else block.text
                heading_locator = heading_locator or block.source_locator
                section = block.section_path.copy()
                continue
            if block.section_path != section:
                flush()
                previous_unit = previous_locator = ""
                heading = heading_locator = ""
                section = block.section_path.copy()
            if block.kind == "table":
                flush()
                layout = self._table_layout(block)
                header = self._continuation_header(
                    previous_table, layout, continuation_marker
                )
                for value, locator in self._table_units(
                    block, header, layout.body, heading, heading_locator
                ):
                    emit(value, locator, section)
                heading = heading_locator = ""
                previous_unit = previous_locator = ""
                previous_table = layout
                continuation_marker = False
                continue
            if previous_table is not None:
                if len(block.text) < 160 and _CONTINUED.search(block.text):
                    continuation_marker = True
                else:
                    previous_table = None
                    continuation_marker = False
            for unit in self._pieces(block.text, prefix=heading if not pending else ""):
                candidate = "\n".join(
                    value for value in (pending or heading, unit) if value
                )
                if not self._fits(candidate):
                    prior_unit, prior_locator = previous_unit, previous_locator
                    flush()
                    # Overlap repeats the last short, complete sentence/row only.
                    if (
                        prior_unit
                        and self._token_counter.count_text(prior_unit)
                        <= self.settings.overlap_tokens
                        and self._fits(f"{prior_unit}\n{unit}")
                    ):
                        pending = f"{prior_unit}\n{unit}"
                        first_locator = prior_locator
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "thesis_rag.split.overlap run_id=%s document_id=%s "
                                "text_tokens=%d",
                                current_run_id(),
                                document.document.document_id,
                                self._token_counter.count_text(prior_unit),
                            )
                    else:
                        pending = unit
                        first_locator = block.source_locator
                else:
                    if not pending:
                        first_locator = heading_locator or block.source_locator
                    pending = candidate
                last_locator = block.source_locator
                heading = heading_locator = ""
                previous_unit = unit
                previous_locator = block.source_locator
        flush()
        if heading:
            if chunks and self._fits(f"{chunks[-1].text}\n{heading}"):
                last = chunks.pop()
                emit(
                    f"{last.text}\n{heading}",
                    f"{last.source_locator}..{heading_locator}",
                    section,
                )
            else:
                raise ValueError("A filing ends with an unattached heading")
        if not chunks:
            raise ValueError("A parsed SEC document produced no chunks")
        return chunks
