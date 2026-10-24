"""Deterministic, citation-preserving packing for a chat-model input budget."""

import logging
import re
from time import perf_counter

from app.agents.asset_thesis.rag.observability import log_failure_once, rag_run
from app.domain.schemas.thesis_rag import (
    FilingContextBudget,
    FilingEvidenceBundle,
    FilingEvidenceExcerpt,
    FilingPackedContext,
)
from app.llm.prompts.thesis_filing_prompt_builder import (
    AnalysisTask,
    ThesisFilingPromptBuilder,
)
from app.llm.tokenization import ChatTokenCounter

logger = logging.getLogger(__name__)
_WHITESPACE = re.compile(r"\s+")


class SecFilingContextBuilder:
    def __init__(
        self,
        counter: ChatTokenCounter,
        prompts: ThesisFilingPromptBuilder,
        *,
        context_window_tokens: int,
        reserved_output_tokens: int,
        safety_margin_tokens: int,
    ) -> None:
        if (
            context_window_tokens <= 0
            or reserved_output_tokens <= 0
            or safety_margin_tokens < 0
            or reserved_output_tokens + safety_margin_tokens >= context_window_tokens
        ):
            raise ValueError("Invalid Thesis generation token budget")
        self._counter = counter
        self._prompts = prompts
        self._window = context_window_tokens
        self._output_reserve = reserved_output_tokens
        self._margin = safety_margin_tokens

    def build(
        self, retrieved: FilingEvidenceBundle, *, task: AnalysisTask
    ) -> FilingPackedContext:
        request = retrieved.request
        with rag_run(request.research_id) as run_id:
            started = perf_counter()
            logger.info(
                "thesis_rag.context.start run_id=%s corpus_id=%s retrieved=%d",
                run_id,
                request.corpus.corpus_id,
                len(retrieved.excerpts),
            )
            try:
                result = self._build(retrieved, task)
            except Exception:
                log_failure_once(
                    logger,
                    "context",
                    ids=f"corpus_id={request.corpus.corpus_id}",
                )
                raise
            logger.info(
                "thesis_rag.context.done run_id=%s included=%d excluded=%d "
                "prompt_tokens_estimated=%d remaining_tokens_estimated=%d "
                "duration_ms=%.1f",
                run_id,
                len(result.included_chunk_ids),
                len(result.excluded_chunk_ids),
                result.budget.prompt_tokens_estimated,
                result.budget.remaining_input_tokens_estimated,
                (perf_counter() - started) * 1000,
            )
            return result

    def _build(
        self, retrieved: FilingEvidenceBundle, task: AnalysisTask
    ) -> FilingPackedContext:
        request = retrieved.request
        input_limit = self._window - self._output_reserve - self._margin
        base_prompt = self._prompts.build(
            task=task, request=request, formatted_context=""
        )
        base_tokens = self._counter.count_prompt(base_prompt)
        if base_tokens > input_limit:
            raise ValueError("Thesis instructions and question exceed input budget")

        citations: dict[str, FilingEvidenceExcerpt] = {}
        included: list[str] = []
        excluded: list[str] = []
        parts: list[str] = []
        seen_ids: set[str] = set()
        seen_text: set[str] = set()
        deduplicated = 0
        budget_excluded = 0
        prompt_tokens = base_tokens
        for item in retrieved.excerpts:
            canonical_text = _WHITESPACE.sub(" ", item.text).strip()
            if item.chunk_id in seen_ids or canonical_text in seen_text:
                deduplicated += 1
                if item.chunk_id not in included and item.chunk_id not in excluded:
                    excluded.append(item.chunk_id)
                continue
            seen_ids.add(item.chunk_id)
            seen_text.add(canonical_text)
            citation_id = f"E{len(citations) + 1}"
            part = self._prompts.format_excerpt(citation_id, item)
            candidate = "\n\n".join([*parts, part])
            candidate_tokens = self._counter.count_prompt(
                self._prompts.build(
                    task=task, request=request, formatted_context=candidate
                )
            )
            if candidate_tokens > input_limit:
                budget_excluded += 1
                excluded.append(item.chunk_id)
                continue
            parts.append(part)
            citations[citation_id] = item
            included.append(item.chunk_id)
            prompt_tokens = candidate_tokens

        context_text = "\n\n".join(parts)
        return FilingPackedContext(
            request=request,
            embedding_version=retrieved.embedding_version,
            prompt_version=self._prompts.version,
            formatted_context=context_text,
            citations=citations,
            included_chunk_ids=included,
            excluded_chunk_ids=excluded,
            budget=FilingContextBudget(
                count_kind=self._counter.count_kind,
                counter_version=self._counter.version,
                model_context_window_tokens=self._window,
                reserved_output_tokens=self._output_reserve,
                safety_margin_tokens=self._margin,
                input_limit_tokens=input_limit,
                prompt_tokens_estimated=prompt_tokens,
                context_tokens_estimated=self._counter.count_text(context_text),
                remaining_input_tokens_estimated=input_limit - prompt_tokens,
                deduplicated_chunks=deduplicated,
                budget_excluded_chunks=budget_excluded,
            ),
        )
