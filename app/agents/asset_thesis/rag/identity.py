import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime

from app.domain.schemas.thesis_rag import FilingDocumentVersion


def _key(prefix: str, parts: object) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()}"


def make_document_id(issuer_cik: str, accession: str, filename: str) -> str:
    """A filing's primary document and each exhibit have different identities."""
    return _key("sec-doc", [issuer_cik, accession, filename])


def make_chunk_id(
    document: FilingDocumentVersion,
    *,
    parser_version: str,
    splitter_version: str,
    position: int,
    source_locator: str,
    text: str,
) -> str:
    return _key(
        "sec-chunk",
        [
            document.document_id,
            document.content_sha256,
            parser_version,
            splitter_version,
            position,
            source_locator,
            text,
        ],
    )


def make_corpus_id(
    *,
    asset: str,
    issuer_cik: str,
    as_of: datetime,
    documents: Sequence[FilingDocumentVersion],
    index_version: str,
) -> str:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Corpus as_of must be timezone-aware")
    if index_version is None or not index_version.strip():
        raise ValueError("Corpus identity requires an index version")
    refs = sorted((item.document_id, item.content_sha256) for item in documents)
    return _key(
        "sec-corpus",
        [
            asset.strip().upper(),
            issuer_cik,
            as_of.astimezone(UTC).isoformat(),
            refs,
            index_version.strip(),
        ],
    )


def make_index_version(
    *, embedding_model_version: str, parser_version: str, splitter_version: str
) -> str:
    return _key(
        "sec-index",
        [embedding_model_version, parser_version, splitter_version],
    )
