"""Live dense-retrieval diagnostic on labeled SEC fixture questions.

Run with ``.venv/bin/python -m tests.rag.test_thesis_rag_retrieval_eval_cli
--fixture MA --top-k 16``. SQL, raw HTML, and Chroma stay in a temporary folder.
"""

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.html_parser import SecHtmlFilingParser
from app.agents.asset_thesis.rag.raw_store import FileRawFilingStore
from app.agents.asset_thesis.rag.reranking import LexicalFilingReranker
from app.agents.asset_thesis.rag.retrieval import SecFilingRetrievalService
from app.agents.asset_thesis.rag.services import SecFilingIngestionService
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.core.config import get_settings
from app.domain.schemas.thesis_rag import FilingCorpusVersion, FilingRetrievalRequest
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from tests.rag.test_inspect_thesis_rag_cli import (
    FIXTURE_ROOT,
    _load_fixture,
    _processing_components,
)


class RetrievalCase(BaseModel):
    name: str
    question: str
    relevant_text: list[str] = Field(min_length=1)
    expected_answer: str


def _rank(texts: list[str], required: list[str]) -> int | None:
    return next(
        (
            rank
            for rank, text in enumerate(texts, start=1)
            if all(s in text for s in required)
        ),
        None,
    )


async def _run(
    fixture_name: str, top_k: int, *, rerank: bool = False
) -> dict[str, object]:
    if top_k <= 0:
        raise ValueError("--top-k must be positive")
    cases_path = FIXTURE_ROOT / fixture_name / "retrieval_cases.json"
    cases = [
        RetrievalCase.model_validate(item)
        for item in json.loads(cases_path.read_text(encoding="utf-8"))
    ]
    if not cases:
        raise ValueError("Retrieval evaluation requires at least one labeled case")
    fixture, document, raw = _load_fixture(fixture_name)
    settings = get_settings()
    with TemporaryDirectory(prefix="thesis_rag_retrieval_eval_") as temporary:
        root = Path(temporary)
        database = Database(root / "filings.db")
        try:
            metadata = SqlFilingMetadataRepository(database)
            index = ChromaFilingVectorIndex(root / "chroma")
            splitter, embeddings = _processing_components(settings)
            corpus = await SecFilingIngestionService(
                FilingCorpusStorageService(
                    FileRawFilingStore(root / "raw"), metadata, index
                ),
                SecHtmlFilingParser(),
                splitter,
                embeddings,
            ).ingest_documents(
                asset=fixture.asset,
                as_of=fixture.as_of,
                documents=[(document, raw)],
            )
            assert corpus.index_version is not None
            retriever = SecFilingRetrievalService(
                metadata,
                embeddings,
                index,
                reranker=LexicalFilingReranker() if rerank else None,
                candidate_k=settings.thesis_rag_retrieval_candidate_k,
            )
            results = []
            ranks: list[int | None] = []
            for case in cases:
                request = FilingRetrievalRequest(
                    research_id=uuid4().hex,
                    question=case.question,
                    asset=fixture.asset,
                    issuer_cik=fixture.issuer_cik,
                    as_of=fixture.as_of,
                    corpus=FilingCorpusVersion(
                        corpus_id=corpus.corpus_id,
                        index_version=corpus.index_version,
                    ),
                    top_k=top_k,
                )
                bundle = await retriever.retrieve(request)
                rank = _rank(
                    [item.text for item in bundle.excerpts], case.relevant_text
                )
                ranks.append(rank)
                results.append(
                    {
                        "name": case.name,
                        "question": case.question,
                        "first_relevant_rank": rank,
                        "candidates": [
                            {
                                "rank": item.rank,
                                "chunk_id": item.chunk_id,
                                "distance": item.retrieval_distance,
                                "relevant": all(
                                    value in item.text for value in case.relevant_text
                                ),
                                "preview": item.text[:180],
                            }
                            for item in bundle.excerpts
                        ],
                    }
                )
            return {
                "fixture": fixture_name,
                "embedding_model": settings.ollama_embedding_model,
                "embedding_version": embeddings.version,
                "index_version": corpus.index_version,
                "top_k": top_k,
                "ranking_version": "dense-lexical-v1" if rerank else "dense-v1",
                "coverage_at_k": sum(rank is not None for rank in ranks) / len(ranks),
                "mean_reciprocal_rank": sum(
                    1 / rank for rank in ranks if rank is not None
                )
                / len(ranks),
                "cases": results,
            }
        finally:
            await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--top-k", type=int, required=True)
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(_run(args.fixture, args.top_k, rerank=args.rerank))
    print(json.dumps(report, indent=2))
