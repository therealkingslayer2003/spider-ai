"""Small independent coordinator retaining all three RAG stage outputs."""

from app.agents.asset_thesis.rag.analysis import SecFilingAnalyticalGenerator
from app.agents.asset_thesis.rag.context_builder import SecFilingContextBuilder
from app.agents.asset_thesis.rag.observability import rag_run
from app.agents.asset_thesis.rag.retrieval import SecFilingRetrievalService
from app.domain.schemas.thesis_rag import FilingRagRun, FilingRetrievalRequest
from app.llm.prompts.thesis_filing_prompt_builder import AnalysisTask


class SecFilingRagPipeline:
    def __init__(
        self,
        retrieval: SecFilingRetrievalService,
        context_builder: SecFilingContextBuilder,
        generation: SecFilingAnalyticalGenerator,
    ) -> None:
        self._retrieval = retrieval
        self._context_builder = context_builder
        self._generation = generation

    async def run(
        self, request: FilingRetrievalRequest, *, task: AnalysisTask = "answer"
    ) -> FilingRagRun:
        with rag_run(request.research_id):
            retrieved = await self._retrieval.retrieve(request)
            context = self._context_builder.build(retrieved, task=task)
            generated = await self._generation.generate(context, task=task)
            return FilingRagRun(
                retrieval=retrieved,
                context=context,
                generation=generated,
            )
