"""Versioned SEC filing corpus and evidence contracts for Thesis Mode."""

from datetime import date
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    FiniteFloat,
    HttpUrl,
    StringConstraints,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Cik = Annotated[str, StringConstraints(pattern=r"^\d{10}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
FilingForm = Literal["10-K", "10-Q", "8-K"]


class FilingDocument(BaseModel):
    """One SEC HTML file; an exhibit is a separate document in the same filing."""

    document_id: Text
    issuer_cik: Cik
    accession_number: Text
    filename: Text
    form: FilingForm
    exhibit_type: Text | None = None
    source_url: HttpUrl
    published_at: AwareDatetime
    report_period_end: date | None = None
    raw_file_ref: Text | None = None
    content_sha256: Sha256 | None = None


class FilingDocumentVersion(BaseModel):
    document_id: Text
    content_sha256: Sha256


class ParsedFilingBlock(BaseModel):
    order: int = Field(ge=0)
    text: Text
    section_path: list[Text] = Field(default_factory=list)
    source_locator: Text


class ParsedFilingDocument(BaseModel):
    document: FilingDocumentVersion
    parser_version: Text
    blocks: list[ParsedFilingBlock]


class FilingChunk(BaseModel):
    chunk_id: Text
    document: FilingDocumentVersion
    text: Text
    section_path: list[Text] = Field(default_factory=list)
    position: int = Field(ge=0)
    source_locator: Text
    token_count: int = Field(gt=0)
    parser_version: Text
    splitter_version: Text


class FilingCorpusManifest(BaseModel):
    """Reusable corpus selection; research runs reference its ID and version."""

    corpus_id: Text
    asset: Text
    issuer_cik: Cik
    as_of: AwareDatetime
    documents: list[FilingDocumentVersion]
    index_version: Text | None = None
    status: Literal["selected", "indexing", "ready", "failed"]


class FilingCorpusVersion(BaseModel):
    corpus_id: Text
    index_version: Text


class FilingEvidenceSource(BaseModel):
    document: FilingDocumentVersion
    accession_number: Text
    filename: Text
    form: FilingForm
    exhibit_type: Text | None = None
    source_url: HttpUrl
    published_at: AwareDatetime
    report_period_end: date | None = None
    source_locator: Text


class FilingEvidenceExcerpt(BaseModel):
    chunk_id: Text
    text: Text
    source: FilingEvidenceSource
    retrieval_score: FiniteFloat | None = None


class FilingVectorMatch(BaseModel):
    chunk_id: Text
    score: FiniteFloat


class FilingEvidenceBundle(BaseModel):
    query: Text
    corpus: FilingCorpusVersion
    excerpts: list[FilingEvidenceExcerpt]
