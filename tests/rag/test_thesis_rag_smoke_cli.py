"""Isolated live-provider smoke run for Retrieval -> Context -> Generation.

Run with ``.venv/bin/python -m tests.rag.test_thesis_rag_smoke_cli --help``.
This runner writes SQL/raw/Chroma only inside a temporary directory and saves
one JSON report per successful run under tests/rag/rag_retrieval_test_runs/.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.html_parser import SecHtmlFilingParser
from app.agents.asset_thesis.rag.pipeline import SecFilingRagPipeline
from app.agents.asset_thesis.rag.raw_store import FileRawFilingStore
from app.agents.asset_thesis.rag.reranking import LexicalFilingReranker
from app.agents.asset_thesis.rag.retrieval import SecFilingRetrievalService
from app.agents.asset_thesis.rag.services import SecFilingIngestionService
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.api.dependencies import (
    get_filing_analytical_generator,
    get_filing_context_builder,
)
from app.core.config import get_settings
from app.domain.schemas.thesis_rag import (
    FilingCorpusVersion,
    FilingRagRun,
    FilingRetrievalRequest,
)
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from tests.rag.test_inspect_thesis_rag_cli import _load_fixture, _processing_components

REPORT_ROOT = Path(__file__).resolve().parent / "rag_retrieval_test_runs"


def _save_report(
    run: FilingRagRun, *, fixture: str, task: str
) -> tuple[Path, str]:
    report_id = uuid4().hex
    report = {
        "report_id": report_id,
        "created_at": datetime.now(UTC).isoformat(),
        "fixture": fixture,
        "task": task,
        "run": run.model_dump(mode="json"),
    }
    report_json = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORT_ROOT / f"{report_id}.json"
    with path.open("x", encoding="utf-8") as file:
        file.write(report_json)
    return path, report_json


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="MA")
    parser.add_argument("--question", required=True)
    parser.add_argument(
        "--task",
        choices=["answer", "asset_overview", "current_catalysts", "risks"],
        default="answer",
    )
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--research-id")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the same complete JSON report saved to disk",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    fixture, document, raw = _load_fixture(args.fixture)
    top_k = (
        args.top_k if args.top_k is not None else settings.thesis_rag_retrieval_top_k
    )
    with TemporaryDirectory(prefix="thesis_rag_smoke_") as temporary:
        root = Path(temporary)
        database = Database(root / "filings.db")
        try:
            metadata = SqlFilingMetadataRepository(database)
            index = ChromaFilingVectorIndex(root / "chroma")
            parser = SecHtmlFilingParser()
            splitter, embeddings = _processing_components(settings)
            storage = FilingCorpusStorageService(
                FileRawFilingStore(root / "raw"), metadata, index
            )
            ingestion = SecFilingIngestionService(storage, parser, splitter, embeddings)
            corpus = await ingestion.ingest_documents(
                asset=fixture.asset,
                as_of=fixture.as_of,
                documents=[(document, raw)],
            )
            assert corpus.index_version is not None
            request = FilingRetrievalRequest(
                research_id=args.research_id or uuid4().hex,
                question=args.question,
                asset=fixture.asset,
                issuer_cik=fixture.issuer_cik,
                as_of=fixture.as_of,
                corpus=FilingCorpusVersion(
                    corpus_id=corpus.corpus_id,
                    index_version=corpus.index_version,
                ),
                top_k=top_k,
            )
            pipeline = SecFilingRagPipeline(
                SecFilingRetrievalService(
                    metadata,
                    embeddings,
                    index,
                    reranker=(
                        LexicalFilingReranker()
                        if settings.thesis_rag_retrieval_rerank_enabled else None
                    ),
                    candidate_k=settings.thesis_rag_retrieval_candidate_k,
                ),
                get_filing_context_builder(),
                get_filing_analytical_generator(),
            )
            run = await pipeline.run(request, task=args.task)
            report_path, report_json = _save_report(
                run, fixture=args.fixture, task=args.task
            )
            if args.json:
                print(report_json, end="")
            else:
                print(
                    f"research_id={request.research_id} "
                    f"corpus={corpus.corpus_id} "
                    f"retrieved={len(run.retrieval.excerpts)} "
                    f"packed={len(run.context.included_chunk_ids)} "
                    f"status={run.generation.answer.status} "
                    f"prompt_tokens_estimated="
                    f"{run.context.budget.prompt_tokens_estimated} "
                    f"output_tokens_estimated="
                    f"{run.generation.estimated_output_tokens}"
                )
                print(run.generation.answer.model_dump_json(indent=2))
            print(f"Report: {report_path}", file=sys.stderr)
        finally:
            await database.close()


if __name__ == "__main__":
    asyncio.run(_run(_arguments()))
