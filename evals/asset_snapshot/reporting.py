import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from evals.asset_snapshot.models import StockSnapshotEvalReport

logger = logging.getLogger(__name__)

DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"


def write_report(
    report: StockSnapshotEvalReport,
    output: Path | None = None,
) -> tuple[Path, Path]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if output is None:
        base_path = DEFAULT_REPORT_DIR / f"{report.dataset_version}_{timestamp}"
    elif output.suffix:
        base_path = output.with_suffix("")
    else:
        base_path = output / f"{report.dataset_version}_{timestamp}"

    base_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = base_path.with_suffix(".json")
    markdown_path = base_path.with_suffix(".md")
    json_content = json.dumps(report.model_dump(mode="json"), indent=2) + "\n"
    markdown_content = _build_markdown(report)
    logger.info(
        "eval.report.write.start dataset=%s cases=%s json_path=%s markdown_path=%s",
        report.dataset_version,
        report.case_count,
        json_path,
        markdown_path,
    )
    try:
        json_path.write_text(json_content, encoding="utf-8")
        markdown_path.write_text(markdown_content, encoding="utf-8")
    except OSError:
        logger.exception(
            "eval.report.write.failed json_path=%s markdown_path=%s",
            json_path,
            markdown_path,
        )
        raise
    logger.info(
        "eval.report.write.success json_bytes=%s markdown_bytes=%s",
        len(json_content.encode("utf-8")),
        len(markdown_content.encode("utf-8")),
    )
    return json_path, markdown_path


def _build_markdown(report: StockSnapshotEvalReport) -> str:
    review_warning = (
        "> **NON-BASELINE / UNREVIEWED DATASET RUN**\n\n"
        if report.unreviewed_dataset_run
        else ""
    )
    lines = [
        f"# {report.dataset_version} Evaluation Report",
        "",
        review_warning.rstrip(),
        "",
        f"- Generated: `{report.generated_at.isoformat()}`",
        f"- Git commit: `{report.git_commit_sha or 'unavailable'}`",
        f"- Generation model: `{report.generation_model}`",
        f"- Judge model: `{report.judge_model or 'not run'}`",
        f"- Cases: `{report.case_count}`",
        f"- Approved cases: `{report.approved_case_count}`",
        f"- Pending cases: `{report.pending_case_count}`",
        f"- Total runtime: `{report.total_runtime_seconds:.3f}s`",
        f"- Average latency: `{report.average_latency_seconds:.3f}s`",
        "",
        "## Deterministic Metrics",
        "",
        "| Metric | Pass rate |",
        "|---|---:|",
    ]
    for metric, pass_rate in sorted(report.aggregate.deterministic_pass_rates.items()):
        lines.append(f"| {metric} | {pass_rate:.1%} |")

    lines.extend(
        [
            "",
            "## Semantic Metrics",
            "",
            "| Metric | Average |",
            "|---|---:|",
        ]
    )
    if report.aggregate.semantic_averages:
        for metric, average in sorted(report.aggregate.semantic_averages.items()):
            lines.append(f"| {metric} | {average:.2f} / 2 |")
    else:
        lines.append("| Not run | n/a |")

    lines.extend(["", "## Cases", ""])
    for case in report.cases:
        metric_failures = [
            result.metric for result in case.deterministic_metrics if not result.passed
        ]
        lines.extend(
            [
                f"### {case.case_id}",
                "",
                f"- Category: `{case.category}`",
                f"- Review status: `{case.review_status}`",
                f"- Latency: `{case.latency_seconds:.3f}s`",
                f"- Failure labels: `{', '.join(case.failure_labels) or 'none'}`",
                f"- Failed deterministic metrics: "
                f"`{', '.join(metric_failures) or 'none'}`",
                f"- Error: `{case.error or 'none'}`",
                "",
            ]
        )

    if report.aggregate.weakest_cases:
        lines.extend(
            [
                "## Weakest Cases",
                "",
                *[f"- `{case_id}`" for case_id in report.aggregate.weakest_cases],
                "",
            ]
        )
    return "\n".join(line for line in lines if line is not None).strip() + "\n"
