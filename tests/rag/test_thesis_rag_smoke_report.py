"""Offline checks for the smoke runner's single-file report."""

import json
from pathlib import Path

import pytest

from app.agents.asset_thesis.rag.analysis import SecFilingAnalyticalGenerator
from app.domain.schemas.thesis_rag import FilingRagRun
from app.llm.prompts.thesis_filing_prompt_builder import ThesisFilingPromptBuilder
from tests.rag import test_thesis_rag_smoke_cli as cli
from tests.rag.test_thesis_rag_retrieval_analysis import (
    ANSWER,
    _builder,
    _bundle,
    _ChatCounter,
    _excerpt,
    _Model,
)


@pytest.mark.asyncio
async def test_report_preserves_all_stages_and_separates_repeated_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_root = tmp_path / "tests/rag/rag_retrieval_test_runs"
    monkeypatch.setattr(cli, "REPORT_ROOT", report_root)
    retrieval = _bundle([_excerpt(1, "chunk-1", "Revenue was $1,234")])
    context = _builder().build(retrieval, task="answer")
    generation = await SecFilingAnalyticalGenerator(
        _Model(ANSWER),
        ThesisFilingPromptBuilder(),
        _ChatCounter(),
        model_version="test-chat-v1",
    ).generate(context, task="answer")
    run = FilingRagRun(
        retrieval=retrieval, context=context, generation=generation
    )

    first_path, first_json = cli._save_report(run, fixture="MA", task="answer")
    second_path, _ = cli._save_report(run, fixture="MA", task="answer")

    assert first_path != second_path
    assert sorted(report_root.iterdir()) == sorted([first_path, second_path])
    assert first_path.read_text(encoding="utf-8") == first_json
    report = json.loads(first_json)
    assert report["report_id"] == first_path.stem
    assert report["fixture"] == "MA" and report["task"] == "answer"
    assert report["run"] == run.model_dump(mode="json")
    assert report["run"]["retrieval"]["request"]["question"]
    assert report["run"]["context"]["citations"]["E1"]["chunk_id"] == "chunk-1"
    assert report["run"]["generation"]["answer"]["status"] == "answered"
