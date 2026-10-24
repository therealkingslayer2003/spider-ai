"""Versioned SEC filing corpus and evidence contracts for Thesis Mode."""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    FiniteFloat,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from app.domain.schemas.asset_thesis import ThesisClaim

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


class ParsedFilingTableCell(BaseModel):
    column: int = Field(ge=0)
    colspan: int = Field(ge=1)
    rowspan: int = Field(ge=1)
    text: str
    source_locator: Text


class ParsedFilingTableRow(BaseModel):
    source_locator: Text
    cells: list[ParsedFilingTableCell]


class ParsedFilingBlock(BaseModel):
    order: int = Field(ge=0)
    kind: Literal["heading", "paragraph", "table"] = "paragraph"
    text: Text
    section_path: list[Text] = Field(default_factory=list)
    source_locator: Text
    table_rows: list[ParsedFilingTableRow] = Field(default_factory=list)


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

    @model_validator(mode="after")
    def ready_requires_index_version(self) -> "FilingCorpusManifest":
        if self.status == "ready" and self.index_version is None:
            raise ValueError("A ready filing corpus requires an index version")
        return self


class FilingCorpusVersion(BaseModel):
    corpus_id: Text
    index_version: Text


class FilingRetrievalRequest(BaseModel):
    """Internal research-run selection; never part of the public user request."""

    research_id: Text
    question: Text
    asset: Text
    issuer_cik: Cik
    as_of: AwareDatetime
    corpus: FilingCorpusVersion
    top_k: int = Field(gt=0)


class FilingEvidenceSource(BaseModel):
    document: FilingDocumentVersion
    accession_number: Text
    filename: Text
    form: FilingForm
    exhibit_type: Text | None = None
    source_url: HttpUrl
    published_at: AwareDatetime
    report_period_end: date | None = None
    section_path: list[Text] = Field(default_factory=list)
    source_locator: Text


class FilingEvidenceExcerpt(BaseModel):
    rank: int = Field(ge=1)
    chunk_id: Text
    text: Text
    source: FilingEvidenceSource
    retrieval_distance: FiniteFloat | None = None


class FilingVectorMatch(BaseModel):
    chunk_id: Text
    distance: FiniteFloat


class FilingEvidenceBundle(BaseModel):
    request: FilingRetrievalRequest
    parser_version: Text
    splitter_version: Text
    embedding_version: Text
    ranking_version: Text = "dense-v1"
    excerpts: list[FilingEvidenceExcerpt] = Field(min_length=1)


class FilingContextBudget(BaseModel):
    count_kind: Literal["local_tokenizer", "estimated"]
    counter_version: Text
    model_context_window_tokens: int = Field(gt=0)
    reserved_output_tokens: int = Field(gt=0)
    safety_margin_tokens: int = Field(ge=0)
    input_limit_tokens: int = Field(gt=0)
    prompt_tokens_estimated: int = Field(ge=0)
    context_tokens_estimated: int = Field(ge=0)
    remaining_input_tokens_estimated: int = Field(ge=0)
    deduplicated_chunks: int = Field(ge=0)
    budget_excluded_chunks: int = Field(ge=0)


class FilingPackedContext(BaseModel):
    request: FilingRetrievalRequest
    embedding_version: Text
    prompt_version: Text
    formatted_context: str
    citations: dict[str, FilingEvidenceExcerpt]
    included_chunk_ids: list[Text]
    excluded_chunk_ids: list[Text]
    budget: FilingContextBudget


class FilingResearchAnswer(BaseModel):
    status: Literal["answered", "partial_evidence", "insufficient_evidence"] = Field(
        description="Answered, partly answered, or no supported answer."
    )
    answer: ThesisClaim | None = Field(
        default=None, description="Direct, cited answer to the research question."
    )
    supported_claims: list[ThesisClaim] = Field(
        default_factory=list,
        description=(
            "Additional distinct sourced facts needed for the answer; may be empty."
        ),
    )
    interpretations: list[ThesisClaim] = Field(
        default_factory=list,
        description="Only material analysis beyond source facts; may be empty.",
    )
    assumptions: list[ThesisClaim] = Field(
        default_factory=list,
        description=(
            "Only material analytical premises, never reported labels or periods; "
            "may be empty."
        ),
    )
    uncertainties: list[ThesisClaim] = Field(
        default_factory=list,
        description=(
            "Only unresolved uncertainty material to the question; may be empty."
        ),
    )
    missing_data: list[ThesisClaim] = Field(
        default_factory=list,
        description=(
            "Only a missing requested fact or component; empty for a complete answer."
        ),
    )

    @model_validator(mode="after")
    def validate_support(self) -> "FilingResearchAnswer":
        if self.status in {"answered", "partial_evidence"}:
            if self.answer is None and self.supported_claims:
                # A valid lead claim is a deterministic answer when the model
                # omits the optional summary field.
                self.answer = self.supported_claims[0]
            if self.answer is None or not self.answer.evidence_ids:
                raise ValueError("An answered research question needs a cited answer")
            if any(not claim.evidence_ids for claim in self.supported_claims):
                raise ValueError("Supported factual claims require evidence IDs")
            if self.status == "answered" and self.missing_data:
                raise ValueError("Missing requested data requires partial_evidence")
            if self.status == "partial_evidence" and not self.missing_data:
                raise ValueError("Partial evidence must identify missing data")
        elif (
            self.answer is not None
            or self.supported_claims
            or self.interpretations
            or self.assumptions
            or self.uncertainties
            or not self.missing_data
        ):
            raise ValueError("Insufficient evidence needs missing data, not facts")
        claims = [
            *self.supported_claims,
            *self.interpretations,
            *self.assumptions,
            *self.uncertainties,
            *self.missing_data,
        ]
        if self.answer is not None:
            claims.append(self.answer)
        for claim in claims:
            inline_ids = set(re.findall(r"\bE[1-9]\d*\b", claim.text))
            if not inline_ids.issubset(claim.evidence_ids):
                raise ValueError(
                    "Inline evidence labels must also appear in evidence_ids"
                )
        return self


class FilingGenerationResult(BaseModel):
    request: FilingRetrievalRequest
    answer: FilingResearchAnswer
    references: dict[str, FilingEvidenceSource]
    model_version: Text
    prompt_version: Text
    estimated_prompt_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)


class FilingRagRun(BaseModel):
    """Self-contained stage outputs for later offline inspection and evaluation."""

    retrieval: FilingEvidenceBundle
    context: FilingPackedContext
    generation: FilingGenerationResult
