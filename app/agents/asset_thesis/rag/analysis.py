"""Structured, cited Thesis generation from a packed filing context."""

import logging
from datetime import datetime
from time import perf_counter

from app.agents.asset_thesis.rag.observability import log_failure_once, rag_run
from app.domain.schemas.asset_thesis import FilingEvidence, ThesisClaim
from app.domain.schemas.thesis_rag import (
    FilingEvidenceBundle,
    FilingGenerationResult,
    FilingPackedContext,
    FilingResearchAnswer,
)
from app.llm.base import BaseChatModelClient
from app.llm.prompts.thesis_filing_prompt_builder import (
    AnalysisTask,
    ThesisFilingPromptBuilder,
)
from app.llm.tokenization import ChatTokenCounter

logger = logging.getLogger(__name__)


class SecFilingAnalyticalGenerator:
    """Only packed E-citations may support generated filing facts."""

    def __init__(
        self,
        llm: BaseChatModelClient,
        prompts: ThesisFilingPromptBuilder,
        counter: ChatTokenCounter,
        *,
        model_version: str,
    ) -> None:
        if not model_version.strip():
            raise ValueError("The chat model version is required")
        self._llm = llm
        self._prompts = prompts
        self._counter = counter
        self._model_version = model_version

    async def generate(
        self, context: FilingPackedContext, *, task: AnalysisTask
    ) -> FilingGenerationResult:
        request = context.request
        with rag_run(request.research_id) as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.generate.start run_id=%s corpus_id=%s citations=%d "
                "prompt_tokens_estimated=%d reserved_output_tokens=%d model=%s",
                run_id,
                request.corpus.corpus_id,
                len(context.citations),
                context.budget.prompt_tokens_estimated,
                context.budget.reserved_output_tokens,
                self._model_version,
            )
            try:
                if context.prompt_version != self._prompts.version:
                    raise ValueError("Packed context uses another prompt version")
                if context.budget.counter_version != self._counter.version:
                    raise ValueError("Packed context uses another chat token counter")
                if not context.citations:
                    response = FilingResearchAnswer(
                        status="insufficient_evidence",
                        missing_data=[
                            ThesisClaim(
                                text=(
                                    "No selected SEC filing excerpts were retrieved "
                                    "or fit the generation input budget."
                                ),
                                evidence_ids=[],
                            )
                        ],
                    )
                else:
                    prompt = self._prompts.build(
                        task=task,
                        request=request,
                        formatted_context=context.formatted_context,
                    )
                    response = await self._llm.generate(
                        prompt, response_schema=FilingResearchAnswer
                    )
                allowed = set(context.citations)
                used = self._cited_ids(response)
                if not used.issubset(allowed):
                    raise ValueError(
                        "Generated answer cites unavailable evidence IDs: "
                        + ", ".join(sorted(used - allowed))
                    )
                references = {
                    citation_id: item.source
                    for citation_id, item in context.citations.items()
                }
                result = FilingGenerationResult(
                    request=request,
                    answer=response,
                    references=references,
                    model_version=self._model_version,
                    prompt_version=self._prompts.version,
                    estimated_prompt_tokens=context.budget.prompt_tokens_estimated,
                    estimated_output_tokens=self._counter.count_text(
                        response.model_dump_json()
                    ),
                )
            except Exception:
                log_failure_once(
                    logger,
                    "generate",
                    ids=f"corpus_id={request.corpus.corpus_id}",
                )
                raise
            logger.info(
                "thesis_rag.generate.done run_id=%s status=%s cited=%d "
                "prompt_tokens_estimated=%d output_tokens_estimated=%d "
                "duration_ms=%.1f",
                run_id,
                response.status,
                len(used),
                context.budget.prompt_tokens_estimated,
                result.estimated_output_tokens,
                (perf_counter() - started) * 1000,
            )
            return result

    @staticmethod
    def _cited_ids(answer: FilingResearchAnswer) -> set[str]:
        claims = [
            *answer.supported_claims,
            *answer.interpretations,
            *answer.assumptions,
            *answer.uncertainties,
            *answer.missing_data,
        ]
        if answer.answer is not None:
            claims.append(answer.answer)
        return {citation for claim in claims for citation in claim.evidence_ids}


def filing_evidence_sources(
    bundle: FilingEvidenceBundle, *, retrieved_at: datetime
) -> list[FilingEvidence]:
    """Project retrieved chunks to stable public source IDs for later assembly."""
    return [
        FilingEvidence(
            evidence_id=item.chunk_id,
            url=str(item.source.source_url),
            retrieved_at=retrieved_at,
            form=item.source.form,
            accession_number=item.source.accession_number,
            filed_on=item.source.published_at.date(),
            passage_locator=item.source.source_locator,
            excerpt=item.text,
            exhibit=item.source.exhibit_type,
        )
        for item in bundle.excerpts
    ]
