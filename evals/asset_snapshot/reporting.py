import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from evals.asset_snapshot.models import EvalCaseResult, StockSnapshotEvalReport

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
        _append_case(lines, case)

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


def _append_case(lines: list[str], case: EvalCaseResult) -> None:
    deterministic_passes = sum(result.passed for result in case.deterministic_metrics)
    deterministic_total = len(case.deterministic_metrics)
    deterministic_score = (
        f"{deterministic_passes}/{deterministic_total} "
        f"({deterministic_passes / deterministic_total:.1%})"
        if deterministic_total
        else "not run"
    )
    semantic_average = (
        sum(result.score for result in case.semantic_metrics)
        / len(case.semantic_metrics)
        if case.semantic_metrics
        else None
    )
    semantic_completed = len(case.semantic_metrics)
    semantic_expected = case.semantic_metrics_expected
    semantic_score = (
        f"{semantic_average:.2f} / 2 "
        f"({semantic_completed}/{semantic_expected or semantic_completed} graded)"
        if semantic_average is not None
        else (
            f"unavailable (0/{semantic_expected} graded)"
            if semantic_expected
            else "not run"
        )
    )
    lines.extend(
        [
            f"### {case.case_id}",
            "",
            f"- Category: `{case.category}`",
            f"- Review status: `{case.review_status}`",
            f"- Latency: `{case.latency_seconds:.3f}s`",
            f"- Deterministic score: `{deterministic_score}`",
            f"- Semantic score: `{semantic_score}`",
            f"- Failure labels: `{', '.join(case.failure_labels) or 'none'}`",
            f"- Error: `{_markdown_cell(case.error) if case.error else 'none'}`",
            "",
            "#### Core LLM output",
            "",
        ]
    )
    if case.output is None:
        lines.extend(["No validated snapshot was produced.", ""])
    else:
        lines.extend(
            [
                f"- Data scope: `{case.output.data_scope}`",
                f"- Structural drivers: `{len(case.output.structural_drivers)}`",
                f"- Structural risks: `{len(case.output.structural_risks)}`",
                f"- Competitive peers: `{len(case.output.competitive_landscape)}`",
                "",
                "**Summary**",
                "",
                *_blockquote(case.output.summary),
                "",
            ]
        )

    lines.extend(
        [
            "#### Deterministic scores",
            "",
            "| Metric | Score | Status | Failure labels | Reason |",
            "|---|---:|---|---|---|",
        ]
    )
    if case.deterministic_metrics:
        for deterministic_result in case.deterministic_metrics:
            failure_labels = _markdown_cell(
                ", ".join(deterministic_result.failure_labels) or "none"
            )
            lines.append(
                f"| `{deterministic_result.metric}` | "
                f"{deterministic_result.score:.2f} | "
                f"{'pass' if deterministic_result.passed else 'fail'} | "
                f"{failure_labels} | "
                f"{_markdown_cell(deterministic_result.reason)} |"
            )
    else:
        lines.append("| Not run | n/a | n/a | none | none |")

    lines.extend(
        [
            "",
            "#### Semantic judge scores",
            "",
            "| Metric | Score | Failure labels | Reason |",
            "|---|---:|---|---|",
        ]
    )
    if case.semantic_metrics:
        for semantic_result in case.semantic_metrics:
            failure_labels = _markdown_cell(
                ", ".join(semantic_result.failure_labels) or "none"
            )
            lines.append(
                f"| `{semantic_result.metric}` | {semantic_result.score} / 2 | "
                f"{failure_labels} | "
                f"{_markdown_cell(semantic_result.reason)} |"
            )
        lines.extend(["", "#### Judge evidence from core LLM output", ""])
        for semantic_result in case.semantic_metrics:
            failure_suffix = (
                f" - {', '.join(semantic_result.failure_labels)}"
                if semantic_result.failure_labels
                else ""
            )
            lines.append(
                f"**`{semantic_result.metric}` ({semantic_result.score} / 2)"
                f"{failure_suffix}**"
            )
            lines.append("")
            for evidence in semantic_result.evidence:
                lines.append(f"- Source field: `{evidence.field_path}`")
                lines.extend(_blockquote(evidence.quote, indent="  "))
            lines.append("")
    else:
        lines.extend(["| Not run | n/a | none | none |", ""])


def _markdown_cell(value: str | None) -> str:
    if not value:
        return "none"
    return " ".join(value.split()).replace("|", "\\|")


def _blockquote(value: str, indent: str = "") -> list[str]:
    return [f"{indent}> {line}" for line in value.splitlines() or [""]]
