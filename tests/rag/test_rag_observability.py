import gzip
import json
import logging
from argparse import Namespace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.agents.asset_thesis.rag.chroma_index import ChromaFilingVectorIndex
from app.agents.asset_thesis.rag.html_parser import SecHtmlFilingParser
from app.agents.asset_thesis.rag.observability import rag_run
from app.agents.asset_thesis.rag.raw_store import FileRawFilingStore
from app.agents.asset_thesis.rag.services import SecFilingIngestionService
from app.agents.asset_thesis.rag.storage import FilingCorpusStorageService
from app.core.config import Settings
from app.infrastructure.db.database import Database
from app.infrastructure.db.filing_metadata_repository import SqlFilingMetadataRepository
from tests.rag import test_inspect_thesis_rag_cli as cli
from tests.rag.test_thesis_rag_ingestion import (
    FakeEncoder,
    embeddings,
    filing,
    splitter,
)


def test_debug_dump_root_is_under_tests_rag() -> None:
    expected = Path(cli.__file__).resolve().parent / "rag_pipeline_test_runs"
    assert cli.DUMP_ROOT == expected


def test_inspection_fixture_loads_metadata_and_gzipped_html() -> None:
    metadata, document, raw = cli._load_fixture("MA")
    assert metadata.asset == "MA"
    assert metadata.as_of > document.published_at
    assert document == filing()
    assert b"<html" in raw


def test_inspection_fixture_rejects_path_escape() -> None:
    with pytest.raises(ValueError, match="one folder"):
        cli._load_fixture("../MA")


@pytest.mark.asyncio
async def test_stage_logs_have_levels_run_id_and_one_traceback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.agents.asset_thesis.rag.html_parser as parser_module
    import app.agents.asset_thesis.rag.splitter as splitter_module

    raw = b"<html><body><p>Revenue increased in the quarter.</p></body></html>"
    parser = SecHtmlFilingParser()
    counter_splitter = splitter()
    encoder = FakeEncoder()
    embedder = embeddings(encoder)
    service = SecFilingIngestionService(None, parser, counter_splitter, embedder)

    def unexpected_preview(*_args: object) -> str:
        raise AssertionError("debug preview evaluated at INFO")

    with caplog.at_level(logging.INFO), rag_run("research-log-1"):
        monkeypatch.setattr(parser_module, "preview", unexpected_preview)
        monkeypatch.setattr(splitter_module, "preview", unexpected_preview)
        await service.inspect_document(filing(), raw)
    info = [record.getMessage() for record in caplog.records]
    assert any("thesis_rag.parse.start run_id=research-log-1" in line for line in info)
    assert any("thesis_rag.split.done run_id=research-log-1" in line for line in info)
    assert not any(".sample " in line or ".chunk " in line for line in info)

    monkeypatch.undo()
    caplog.clear()
    with caplog.at_level(logging.DEBUG), rag_run("research-log-2"):
        await service.inspect_document(filing(), raw)
    debug = [record.getMessage() for record in caplog.records]
    assert any(
        "thesis_rag.parse.sample run_id=research-log-2" in line for line in debug
    )
    assert any("thesis_rag.split.chunk run_id=research-log-2" in line for line in debug)
    assert any("preview=" in line for line in debug)

    database = Database(tmp_path / "filings.db")
    encoder.fail_at = 1
    indexing = SecFilingIngestionService(
        FilingCorpusStorageService(
            FileRawFilingStore(tmp_path / "raw"),
            SqlFilingMetadataRepository(database),
            ChromaFilingVectorIndex(tmp_path / "chroma"),
        ),
        parser,
        counter_splitter,
        embedder,
    )
    caplog.clear()
    try:
        with caplog.at_level(logging.ERROR), rag_run("research-failure"):
            with pytest.raises(RuntimeError, match="transient embedding failure"):
                await indexing.ingest_documents(
                    asset="MA",
                    as_of=datetime(2026, 7, 31, tzinfo=UTC),
                    documents=[(filing(), raw)],
                )
        failures = [
            record
            for record in caplog.records
            if record.levelno == logging.ERROR
            and record.getMessage().startswith("thesis_rag.")
        ]
        assert len(failures) == 1
        assert failures[0].exc_info is not None
        assert "thesis_rag.embed.failed" in failures[0].getMessage()
        assert "run_id=research-failure" in failures[0].getMessage()
        assert "batch_id=0" in failures[0].getMessage()
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_debug_dumps_are_opt_in_and_isolated_per_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture_dir = tmp_path / "fixtures/sec/MA"
    fixture_dir.mkdir(parents=True)
    raw_file = fixture_dir / "filing.html.gz"
    with gzip.open(raw_file, "wb") as file:
        file.write(b"<html><body><p>Revenue rose.</p></body></html>")
    dump_root = tmp_path / "tests/rag/rag_pipeline_test_runs"
    settings = Settings(
        _env_file=None,
        spider_ai_db_path=tmp_path / "filings.db",
        spider_ai_sec_filings_path=tmp_path / "raw",
        spider_ai_chroma_path=tmp_path / "chroma",
        ollama_embedding_expected_dimensions=4,
    )
    monkeypatch.setattr(cli, "DUMP_ROOT", dump_root)
    monkeypatch.setattr(cli, "FIXTURE_ROOT", fixture_dir.parent)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cli,
        "_processing_components",
        lambda _settings: (splitter(), embeddings(FakeEncoder())),
    )
    source = filing()
    (fixture_dir / "metadata.json").write_text(
        json.dumps(
            {
                "asset": "MA",
                "html_file": raw_file.name,
                "issuer_cik": source.issuer_cik,
                "accession_number": source.accession_number,
                "filename": source.filename,
                "form": source.form,
                "source_url": str(source.source_url) + "?secret=never-dump",
                "published_at": source.published_at.isoformat(),
                "report_period_end": date(2026, 6, 30).isoformat(),
                "as_of": datetime(2026, 7, 31, tzinfo=UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(
        fixture="MA",
        show=0,
        index=False,
        dump_debug=False,
        verify_cold_warm=False,
    )
    await cli._run(args)
    assert not dump_root.exists()
    args.dump_debug = True
    with pytest.raises(ValueError, match="requires --index"):
        await cli._run(args)
    assert not dump_root.exists()

    args.index = True
    rag_logger = logging.getLogger("app.agents.asset_thesis.rag")
    original_level = rag_logger.level
    original_handlers = list(rag_logger.handlers)
    with caplog.at_level(logging.INFO):
        await cli._run(args)
        await cli._run(args)
    assert rag_logger.level == original_level
    assert rag_logger.handlers == original_handlers
    info = [record.getMessage() for record in caplog.records]
    assert any("thesis_rag.publish.done" in line for line in info)
    assert any(
        "thesis_rag.corpus_lookup.done" in line and "cache_hit=True" in line
        for line in info
    )
    directories = sorted(dump_root.iterdir())
    assert len(directories) == 2
    assert directories[0].name != directories[1].name
    for directory in directories:
        assert {item.name for item in directory.iterdir()} == {
            "document.json",
            "parsed_blocks.json",
            "chunks.json",
            "pipeline.log",
            "summary.json",
        }
        document = json.loads((directory / "document.json").read_text())
        summary = json.loads((directory / "summary.json").read_text())
        pipeline_log = (directory / "pipeline.log").read_text()
        assert "secret" not in (directory / "document.json").read_text()
        assert "secret" not in pipeline_log
        assert "thesis_rag.parse.start" in pipeline_log
        assert "thesis_rag.split.chunk" in pipeline_log
        assert "thesis_rag.corpus_lookup.done" in pipeline_log
        assert f"run_id={directory.name}" in pipeline_log
        assert (
            "run_id=" + next(other.name for other in directories if other != directory)
            not in pipeline_log
        )
        assert document["raw_bytes"] > 0
        assert document["raw_file_ref"].startswith("sha256/")
        assert summary["run_id"] == directory.name
        assert summary["status"] == "completed"
        assert summary["chunks"] >= 1
        assert summary["embedding"]["chunks"] in {0, summary["chunks"]}
        assert "vectors" not in summary["embedding"]
    assert sorted(
        json.loads((directory / "summary.json").read_text())["embedding"]["calls"]
        for directory in directories
    ) == [0, 1]
    for directory in directories:
        summary = json.loads((directory / "summary.json").read_text())
        assert summary["existing_chunks"] + summary["newly_processed_chunks"] == 1
        assert summary["cache_hit"] == (summary["embedding"]["calls"] == 0)

    database = Database(settings.spider_ai_db_path)
    try:
        corpus_id = json.loads((directories[0] / "summary.json").read_text())[
            "corpus_id"
        ]
        ready = await SqlFilingMetadataRepository(database).get_ready_manifest(
            corpus_id
        )
        assert ready is not None
        with caplog.at_level(logging.DEBUG), rag_run("research-search"):
            vector = await embeddings(FakeEncoder()).embed_query("Revenue")
            matches = await ChromaFilingVectorIndex(
                settings.spider_ai_chroma_path
            ).search(ready, vector, 1)
        debug = [record.getMessage() for record in caplog.records]
        assert any(
            "thesis_rag.embed_query.input run_id=research-search" in line
            and "Revenue" in line
            for line in debug
        )
        assert any(
            "thesis_rag.search.matches run_id=research-search" in line
            and matches[0].chunk_id in line
            and "chunk_distances=" in line
            for line in debug
        )
    finally:
        await database.close()

    with gzip.open(raw_file, "wb") as file:
        file.write(b"<html><body><p>Revenue fell.</p></body></html>")
    failing_encoder = FakeEncoder()
    failing_encoder.fail_at = 1
    monkeypatch.setattr(
        cli,
        "_processing_components",
        lambda _settings: (splitter(), embeddings(failing_encoder)),
    )
    with pytest.raises(RuntimeError, match="transient embedding failure"):
        await cli._run(args)
    failure_directory = (set(dump_root.iterdir()) - set(directories)).pop()
    failed = json.loads((failure_directory / "summary.json").read_text())
    failure_log = (failure_directory / "pipeline.log").read_text()
    assert failed["status"] == "failed"
    assert failed["embedding"]["status"] == "failed"
    assert failed["embedding"]["chunks"] >= 1
    assert "vectors" not in failed["embedding"]
    assert failure_log.count("transient embedding failure") >= 1
    assert failure_log.count("Traceback (most recent call last):") == 1
    assert rag_logger.level == original_level
    assert rag_logger.handlers == original_handlers

    args.verify_cold_warm = True
    app_db_mtime = settings.spider_ai_db_path.stat().st_mtime_ns
    monkeypatch.setattr(
        cli,
        "_processing_components",
        lambda _settings: (splitter(), embeddings(FakeEncoder())),
    )
    await cli._run(args)
    verification_dir = (
        set(dump_root.iterdir()) - set(directories) - {failure_directory}
    ).pop()
    verified = json.loads((verification_dir / "summary.json").read_text())
    assert verified["cold_warm_verification"]["verified"] is True
    assert verified["cold_warm_verification"]["cold"]["embedding_calls"] == 1
    assert verified["cold_warm_verification"]["cold"]["upsert_calls"] == 1
    assert verified["cold_warm_verification"]["cold"]["vector_count"] == 1
    assert verified["cold_warm_verification"]["warm"]["additional_embedding_calls"] == 0
    assert verified["cold_warm_verification"]["warm"]["additional_upsert_calls"] == 0
    assert (
        verified["cold_warm_verification"]["warm"]["sql_rows"]
        == verified["cold_warm_verification"]["cold"]["sql_rows"]
    )
    assert settings.spider_ai_db_path.stat().st_mtime_ns == app_db_mtime
    assert not (verification_dir / "chroma").exists()
