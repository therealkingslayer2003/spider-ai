from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from evals.asset_snapshot.comparison import PromptComparisonReport
from evals.asset_snapshot.models import StockSnapshotEvalReport
from evals.asset_snapshot.reporting import (
    DEFAULT_REPORT_DIR,
    _append_case,
    _markdown_cell,
)


def write_comparison_report(
    report: PromptComparisonReport, output: Path | None = None
) -> tuple[Path, Path]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    name = f"{report.original.dataset_version}_prompt_ab_{timestamp}"
    base = (
        DEFAULT_REPORT_DIR / name
        if output is None
        else (output.with_suffix("") if output.suffix else output / name)
    )
    base.parent.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = base.with_suffix(".json"), base.with_suffix(".md")
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(comparison_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def comparison_markdown(report: PromptComparisonReport) -> str:
    a, b = report.original, report.compressed
    wins = Counter(item.winner for item in report.pairwise if item.status == "judged")
    statuses = Counter(item.status for item in report.pairwise)
    lines = [
        "# Stock Snapshot: Original vs Compressed Feature Prompt",
        "",
        f"- Dataset: `{a.dataset_version}`; cases: `{a.case_count}`",
        f"- Generation model: `{a.generation_model}`; "
        f"judge: `{a.judge_model or 'not run'}`",
        f"- Pairwise judge: `{report.pairwise_judge_model or 'not run'}`",
        f"- Peer representation: `{a.peer_context_mode}`",
        f"- Settings: `{report.runtime_settings}`",
        f"- Fixture SHA256: `{report.selected_fixture_sha256}`",
        f"- Original template SHA256: `{a.feature_prompt_sha256}`",
        f"- Compressed template SHA256: `{b.feature_prompt_sha256}`",
        "- Generation order alternates by case; "
        "pairwise judgments use both A/B orders.",
        "- Counts are characters, not tokens; "
        "smaller prompts do not prove better quality.",
        "",
    ]
    if a.unreviewed_dataset_run or b.unreviewed_dataset_run:
        lines.extend(["> NON-BASELINE / UNREVIEWED DATASET RUN", ""])
    lines.extend(
        [
            "## Aggregate Comparison",
            "",
            "| Measure | Original | Compressed |",
            "|---|---:|---:|",
            f"| Static feature template chars | {a.feature_prompt_chars} | "
            f"{b.feature_prompt_chars} |",
            f"| Generation success | {_success(a)} | {_success(b)} |",
            "| Mean generation seconds (incl. tool orchestration) | "
            f"{_generation_mean(a)} | {_generation_mean(b)} |",
        ]
    )
    for metric in sorted(
        set(a.aggregate.deterministic_pass_rates)
        | set(b.aggregate.deterministic_pass_rates)
    ):
        lines.append(
            f"| {metric} (passes/graded) | {_metric(a, metric, False)} | "
            f"{_metric(b, metric, False)} |"
        )
    for metric in sorted(
        set(a.aggregate.semantic_averages) | set(b.aggregate.semantic_averages)
    ):
        lines.append(
            f"| {metric} (mean / 2; graded/all cases) | {_metric(a, metric, True)} | "
            f"{_metric(b, metric, True)} |"
        )
    lines.extend(
        [
            "",
            "## Pairwise Summary",
            "",
            f"- Original wins: {wins['original']}; "
            f"compressed wins: {wins['compressed']}; ties: {wins['tie']}.",
            f"- Status counts: `{dict(statuses)}`",
            "- Errors, skipped pairs, context mismatches, and order disagreements "
            "are NOT ties or wins.",
            "- A tie does not imply either output meets the quality requirements.",
            "",
            "## Per-Case Comparison",
            "",
            "| Case | Original prompt chars | Compressed prompt chars | "
            "Dynamic chars (O/C) | Generation seconds (O/C) | Pairwise |",
            "|---|---:|---:|---|---|---|",
        ]
    )
    for left, right, pair in zip(a.cases, b.cases, report.pairwise, strict=True):
        lm, rm = left.prompt_measurements, right.prompt_measurements
        lines.append(
            f"| {left.case_id} | {lm.total_prompt_chars if lm else 'n/a'} | "
            f"{rm.total_prompt_chars if rm else 'n/a'} | "
            f"{lm.dynamic_context_chars if lm else 'n/a'}/"
            f"{rm.dynamic_context_chars if rm else 'n/a'} | "
            f"{left.generation_latency_seconds or 0:.3f}/"
            f"{right.generation_latency_seconds or 0:.3f} | "
            f"{pair.winner or pair.status} |"
        )
    for left, right, pair in zip(a.cases, b.cases, report.pairwise, strict=True):
        lines.extend(
            [
                "",
                f"## {left.case_id}: Pairwise Evidence",
                "",
                f"Status: `{pair.status}`; winner: `{pair.winner or 'none'}`",
                "",
            ]
        )
        if pair.error:
            lines.extend([f"Error: {_markdown_cell(pair.error)}", ""])
        for decision, label_a, label_b in (
            (pair.forward, "original", "compressed"),
            (pair.reverse, "compressed", "original"),
        ):
            if decision is None:
                continue
            lines.extend(
                [
                    f"### A={label_a}, B={label_b}",
                    f"Winner: `{decision.winner}`. {_markdown_cell(decision.reason)}",
                    "",
                ]
            )
            for label, evidence in (
                (label_a, decision.evidence_a),
                (label_b, decision.evidence_b),
            ):
                for item in evidence:
                    lines.append(
                        f"- {label}, `{item.field_path}`: {_markdown_cell(item.quote)}"
                    )
        for label, result in (("Original", left), ("Compressed", right)):
            lines.extend(["", f"## {left.case_id}: {label}", ""])
            _append_case(lines, result)
            if result.output is not None:
                lines.extend(
                    [
                        "Full snapshot:",
                        "",
                        "```json",
                        result.output.model_dump_json(indent=2),
                        "```",
                        "",
                    ]
                )
    return "\n".join(lines) + "\n"


def _success(report: StockSnapshotEvalReport) -> str:
    return f"{sum(c.output is not None for c in report.cases)}/{report.case_count}"


def _generation_mean(report: StockSnapshotEvalReport) -> str:
    values = [
        c.generation_latency_seconds
        for c in report.cases
        if c.generation_latency_seconds is not None
    ]
    return f"{mean(values):.3f}" if values else "n/a"


def _metric(report: StockSnapshotEvalReport, metric: str, semantic: bool) -> str:
    if semantic:
        scores = [
            m.score
            for c in report.cases
            for m in c.semantic_metrics
            if m.metric == metric
        ]
        return (
            f"{mean(scores):.2f}; {len(scores)}/{report.case_count}"
            if scores
            else "not graded"
        )
    passed = [
        m.passed
        for c in report.cases
        for m in c.deterministic_metrics
        if m.metric == metric
    ]
    return f"{sum(passed)}/{len(passed)}" if passed else "not graded"
