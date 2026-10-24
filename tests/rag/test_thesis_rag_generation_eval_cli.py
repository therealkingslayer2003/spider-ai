"""Evaluate chat generation on fixed, verified filing excerpts without retrieval.

Run ``.venv/bin/python -m tests.rag.test_thesis_rag_generation_eval_cli
--fixture MA --case direct_net_revenue``. Requires the configured Ollama chat model.
"""

import argparse
import asyncio
import hashlib
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from app.api.dependencies import (
    get_filing_analytical_generator,
    get_filing_context_builder,
)
from app.domain.schemas.thesis_rag import (
    FilingCorpusVersion,
    FilingDocumentVersion,
    FilingEvidenceBundle,
    FilingEvidenceExcerpt,
    FilingEvidenceSource,
    FilingRetrievalRequest,
)
from tests.rag.test_inspect_thesis_rag_cli import FIXTURE_ROOT, _load_fixture


class FixedEvidence(BaseModel):
    text: str
    section_path: list[str]
    source_locator: str


class GenerationCase(BaseModel):
    name: str
    question: str
    evidence_keys: list[str]
    expected_status: str
    expected_answer_contains: str | None
    expected_empty_fields: list[
        Literal[
            "supported_claims",
            "interpretations",
            "assumptions",
            "uncertainties",
            "missing_data",
        ]
    ]


class GenerationCases(BaseModel):
    evidence: dict[str, FixedEvidence]
    cases: list[GenerationCase]


async def _run(fixture_name: str, case_name: str) -> dict[str, object]:
    path = FIXTURE_ROOT / fixture_name / "generation_cases.json"
    fixture_cases = GenerationCases.model_validate_json(path.read_text())
    case = next((item for item in fixture_cases.cases if item.name == case_name), None)
    if case is None:
        raise ValueError(f"Unknown generation case: {case_name}")
    fixture, document, raw = _load_fixture(fixture_name)
    version = FilingDocumentVersion(
        document_id=document.document_id,
        content_sha256=hashlib.sha256(raw).hexdigest(),
    )
    request = FilingRetrievalRequest(
        research_id=uuid4().hex,
        question=case.question,
        asset=fixture.asset,
        issuer_cik=fixture.issuer_cik,
        as_of=fixture.as_of,
        corpus=FilingCorpusVersion(
            corpus_id="fixed-evidence-evaluation", index_version="fixed-v1"
        ),
        top_k=len(case.evidence_keys),
    )
    excerpts = [
        FilingEvidenceExcerpt(
            rank=rank,
            chunk_id=f"fixed-{key}",
            text=fixture_cases.evidence[key].text,
            source=FilingEvidenceSource(
                document=version,
                accession_number=document.accession_number,
                filename=document.filename,
                form=document.form,
                source_url=document.source_url,
                published_at=document.published_at,
                report_period_end=document.report_period_end,
                section_path=fixture_cases.evidence[key].section_path,
                source_locator=fixture_cases.evidence[key].source_locator,
            ),
        )
        for rank, key in enumerate(case.evidence_keys, start=1)
    ]
    bundle = FilingEvidenceBundle(
        request=request,
        parser_version="fixed-context-v1",
        splitter_version="fixed-context-v1",
        embedding_version="no-retrieval",
        ranking_version="fixed",
        excerpts=excerpts,
    )
    packed = get_filing_context_builder().build(bundle, task="answer")
    result = await get_filing_analytical_generator().generate(packed, task="answer")
    answer_text = result.answer.answer.text if result.answer.answer else ""
    status_matches = result.answer.status == case.expected_status
    answer_contains_expected = (
        case.expected_answer_contains in answer_text
        if case.expected_answer_contains else result.answer.answer is None
    )
    unexpected_fields = [
        field for field in case.expected_empty_fields if getattr(result.answer, field)
    ]
    return {
        "case": case.name,
        "question": case.question,
        "evidence_keys": case.evidence_keys,
        "expected_status": case.expected_status,
        "expected_answer_contains": case.expected_answer_contains,
        "status_matches": status_matches,
        "answer_contains_expected": answer_contains_expected,
        "unexpected_narrative_fields": unexpected_fields,
        "passed": status_matches and answer_contains_expected and not unexpected_fields,
        "context_chars": len(packed.formatted_context),
        "prompt_tokens_estimated": packed.budget.prompt_tokens_estimated,
        "prompt_version": result.prompt_version,
        "answer": result.answer.model_dump(mode="json"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--case", required=True)
    args = parser.parse_args()
    report = asyncio.run(_run(args.fixture, args.case))
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)
