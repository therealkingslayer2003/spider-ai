import argparse
import asyncio
import logging
from pathlib import Path
from typing import get_args

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.llm.ollama_client import OllamaChatClient
from app.llm.prompts.company_peer_projection import PeerContextMode
from evals.asset_snapshot.config import get_eval_settings
from evals.asset_snapshot.dataset import (
    DATASET_VERSION,
    DEFAULT_DATASET_PATH,
    dataset_status_counts,
    load_dataset,
    select_cases,
)
from evals.asset_snapshot.eval_llm import EvalOllamaClient
from evals.asset_snapshot.judge import default_semantic_graders
from evals.asset_snapshot.reporting import write_report
from evals.asset_snapshot.runner import StockSnapshotEvaluator

logger = logging.getLogger(__name__)

NO_APPROVED_CASES_MESSAGE = (
    "No approved Stock Snapshot eval cases found.\n"
    "Review evals/datasets/stock_snapshot_v1.jsonl and mark cases as approved "
    "before running semantic evals."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Stock Asset Snapshot evals")
    parser.add_argument("--dataset", default=DATASET_VERSION)
    parser.add_argument(
        "--case",
        dest="case_ids",
        action="append",
        help="case ID to run; repeat this option to select multiple cases",
    )
    parser.add_argument("--category")
    parser.add_argument("--include-pending", action="store_true")
    parser.add_argument("--deterministic-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--peer-context",
        choices=get_args(PeerContextMode),
        default="compact",
        help="peer prompt representation for ablation (default: compact)",
    )
    parser.add_argument("--output", type=Path)
    return parser


async def run_from_args(args: argparse.Namespace) -> int:
    dataset_path = _dataset_path(args.dataset)
    dataset_version = (
        DATASET_VERSION
        if dataset_path.resolve() == DEFAULT_DATASET_PATH.resolve()
        else dataset_path.stem
    )
    logger.info(
        "eval.cli.start dataset=%s case_ids=%s category=%s include_pending=%s "
        "deterministic_only=%s validate_only=%s output=%s peer_context=%s",
        dataset_path,
        args.case_ids,
        args.category,
        args.include_pending,
        args.deterministic_only,
        args.validate_only,
        args.output,
        args.peer_context,
    )
    cases = load_dataset(dataset_path)
    counts = dataset_status_counts(cases)
    if args.validate_only:
        logger.info(
            "eval.cli.validation.success dataset=%s total=%s approved=%s "
            "pending=%s rejected=%s",
            dataset_path,
            len(cases),
            counts["approved"],
            counts["pending_manual_review"],
            counts["rejected"],
        )
        print(
            f"Validated {len(cases)} cases from {dataset_path}: "
            f"{counts['approved']} approved, "
            f"{counts['pending_manual_review']} pending, "
            f"{counts['rejected']} rejected."
        )
        return 0

    selected = select_cases(
        cases,
        include_pending=args.include_pending,
        case_ids=args.case_ids,
        category=args.category,
    )
    if not selected:
        logger.warning(
            "eval.cli.selection.empty dataset=%s approved=%s pending=%s "
            "case_ids=%s category=%s",
            dataset_path,
            counts["approved"],
            counts["pending_manual_review"],
            args.case_ids,
            args.category,
        )
        print(NO_APPROVED_CASES_MESSAGE)
        return 0

    unreviewed_run = any(case.metadata.review_status != "approved" for case in selected)
    if unreviewed_run:
        logger.warning(
            "eval.cli.unreviewed_dataset selected_cases=%s baseline_eligible=false",
            len(selected),
        )
        print("NON-BASELINE / UNREVIEWED DATASET")

    settings = get_settings()
    eval_settings = get_eval_settings()
    generation_client = OllamaChatClient()
    semantic_graders = []
    judge_client = None
    judge_model = "not_run"
    if not args.deterministic_only:
        configured_judge_model = (
            eval_settings.eval_judge_model or settings.ollama_chat_model
        )
        configured_judge_base_url = (
            eval_settings.eval_judge_base_url or settings.ollama_base_url
        )
        judge_client = EvalOllamaClient(
            model=configured_judge_model,
            base_url=configured_judge_base_url,
        )
        judge_model = judge_client.model_name
        semantic_graders = default_semantic_graders(judge_client)

    logger.info(
        "eval.cli.clients.ready generation_model=%s judge_model=%s semantic_graders=%s",
        generation_client.model_name,
        judge_model,
        len(semantic_graders),
    )

    evaluator = StockSnapshotEvaluator(
        generation_client=generation_client,
        semantic_graders=semantic_graders,
        peer_context_mode=args.peer_context,
    )
    report = await evaluator.run(
        selected,
        dataset_version=dataset_version,
        deterministic_only=args.deterministic_only,
    )
    json_path, markdown_path = write_report(report, args.output)
    logger.info(
        "eval.cli.complete dataset=%s cases=%s runtime_seconds=%.3f "
        "json_report=%s markdown_report=%s",
        report.dataset_version,
        report.case_count,
        report.total_runtime_seconds,
        json_path,
        markdown_path,
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


def _dataset_path(value: str) -> Path:
    if value == DATASET_VERSION:
        return DEFAULT_DATASET_PATH
    return Path(value)


def main() -> int:
    configure_logging()
    return asyncio.run(run_from_args(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
