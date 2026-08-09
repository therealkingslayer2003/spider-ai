import json
import logging
from collections.abc import Collection, Iterable
from pathlib import Path

from pydantic import ValidationError

from evals.asset_snapshot.models import ReviewStatus, StockSnapshotEvalCase

logger = logging.getLogger(__name__)

DATASET_VERSION = "stock_snapshot_v1"
DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "datasets" / f"{DATASET_VERSION}.jsonl"
)


class EvalDatasetError(ValueError):
    """Raised when an evaluation dataset cannot be trusted or parsed."""


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[StockSnapshotEvalCase]:
    cases: list[StockSnapshotEvalCase] = []
    seen_ids: set[str] = set()
    logger.info("eval.dataset.load.start path=%s", path)

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.exception("eval.dataset.load.failed path=%s", path)
        raise EvalDatasetError(f"Unable to read dataset {path}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        try:
            case = StockSnapshotEvalCase.model_validate_json(line)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.error(
                "eval.dataset.case.invalid path=%s line=%s error=%s",
                path,
                line_number,
                exc,
            )
            raise EvalDatasetError(
                f"Invalid eval case at {path}:{line_number}: {exc}"
            ) from exc

        if case.id in seen_ids:
            logger.error(
                "eval.dataset.case.duplicate path=%s line=%s case_id=%s",
                path,
                line_number,
                case.id,
            )
            raise EvalDatasetError(
                f"Duplicate eval case id {case.id!r} at {path}:{line_number}"
            )

        seen_ids.add(case.id)
        cases.append(case)
        logger.debug(
            "eval.dataset.case.loaded case_id=%s category=%s kind=%s "
            "review_status=%s profile_fixture=%s peer_count=%s "
            "fundamentals_fixture=%s",
            case.id,
            case.metadata.category,
            case.metadata.case_kind,
            case.metadata.review_status,
            case.profile_fixture is not None,
            len(case.peers_fixture.peers) if case.peers_fixture else 0,
            case.fundamentals_fixture is not None,
        )

    counts = dataset_status_counts(cases)
    logger.info(
        "eval.dataset.load.success path=%s cases=%s approved=%s pending=%s rejected=%s",
        path,
        len(cases),
        counts["approved"],
        counts["pending_manual_review"],
        counts["rejected"],
    )
    return cases


def select_cases(
    cases: Iterable[StockSnapshotEvalCase],
    *,
    include_pending: bool = False,
    case_ids: Collection[str] | None = None,
    category: str | None = None,
) -> list[StockSnapshotEvalCase]:
    allowed_statuses: set[ReviewStatus] = {"approved"}
    if include_pending:
        allowed_statuses.add("pending_manual_review")
    requested_ids = set(case_ids or ())

    selected = [
        case
        for case in cases
        if case.metadata.review_status in allowed_statuses
        and (not requested_ids or case.id in requested_ids)
        and (category is None or case.metadata.category == category)
    ]
    logger.info(
        "eval.dataset.selection.complete selected=%s include_pending=%s "
        "case_ids=%s category=%s",
        len(selected),
        include_pending,
        sorted(requested_ids),
        category,
    )
    return selected


def dataset_status_counts(
    cases: Iterable[StockSnapshotEvalCase],
) -> dict[ReviewStatus, int]:
    counts: dict[ReviewStatus, int] = {
        "pending_manual_review": 0,
        "approved": 0,
        "rejected": 0,
    }
    for case in cases:
        counts[case.metadata.review_status] += 1
    return counts
