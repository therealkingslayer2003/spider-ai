import json
from collections import Counter
from pathlib import Path

import pytest

from evals.asset_snapshot.dataset import (
    DEFAULT_DATASET_PATH,
    EvalDatasetError,
    dataset_status_counts,
    load_dataset,
    select_cases,
)


def test_stock_snapshot_v1_dataset_is_valid_and_review_statuses_are_counted() -> None:
    cases = load_dataset()
    counts = dataset_status_counts(cases)

    assert len(cases) == 27
    assert len({case.id for case in cases}) == 27
    assert {case.metadata.provenance for case in cases} == {"synthetic_ai_generated"}
    assert sum(counts.values()) == len(cases)


def test_stock_snapshot_v1_has_declared_case_mix_and_review_flags() -> None:
    cases = load_dataset()

    assert Counter(case.metadata.case_kind for case in cases) == {
        "normal": 16,
        "fallback": 5,
        "contrast": 5,
        "adversarial": 1,
    }
    for case in cases:
        if case.metadata.entity_kind == "real":
            assert "REVIEW_REAL_COMPANY_FACTS" in case.metadata.flags

        fundamentals = case.fundamentals_fixture
        has_numeric_fixture = fundamentals is not None and any(
            value is not None
            for value in (
                fundamentals.market_cap,
                fundamentals.operating_margin,
                fundamentals.debt_to_equity,
                fundamentals.revenue,
                fundamentals.revenue_growth,
            )
        )
        if has_numeric_fixture and case.metadata.entity_kind == "fictional":
            assert "SYNTHETIC_FINANCIAL_FIXTURE" in case.metadata.flags


def test_pending_cases_are_excluded_by_default() -> None:
    case = load_dataset()[0].model_copy(deep=True)
    case.metadata.review_status = "pending_manual_review"

    assert select_cases([case]) == []


def test_pending_cases_require_explicit_selection() -> None:
    case = load_dataset()[0].model_copy(deep=True)
    case.metadata.review_status = "pending_manual_review"
    cases = select_cases([case], include_pending=True)

    assert [selected.id for selected in cases] == [case.id]


def test_category_and_case_filters_apply() -> None:
    cases = load_dataset()

    payments = select_cases(
        cases,
        include_pending=True,
        category="payments",
    )
    one_case = select_cases(
        cases,
        include_pending=True,
        case_ids=["ma_payment_network_001"],
    )

    assert {case.id for case in payments} == {
        "ma_payment_network_001",
        "novapay_network_001",
    }
    assert [case.id for case in one_case] == ["ma_payment_network_001"]


def test_multiple_case_filter_preserves_dataset_order_and_deduplicates() -> None:
    selected = select_cases(
        load_dataset(),
        include_pending=True,
        case_ids=[
            "cloudx_saas_001",
            "ma_payment_network_001",
            "cloudx_saas_001",
        ],
    )

    assert [case.id for case in selected] == [
        "ma_payment_network_001",
        "cloudx_saas_001",
    ]


def test_approved_case_is_selected_by_default(tmp_path: Path) -> None:
    raw_case = json.loads(DEFAULT_DATASET_PATH.read_text().splitlines()[0])
    raw_case["metadata"]["review_status"] = "approved"
    dataset_path = tmp_path / "approved.jsonl"
    dataset_path.write_text(json.dumps(raw_case) + "\n", encoding="utf-8")

    selected = select_cases(load_dataset(dataset_path))

    assert [case.id for case in selected] == ["ma_payment_network_001"]


def test_unknown_review_status_fails_validation(tmp_path: Path) -> None:
    raw_case = json.loads(DEFAULT_DATASET_PATH.read_text().splitlines()[0])
    raw_case["metadata"]["review_status"] = "unverified"
    dataset_path = tmp_path / "invalid.jsonl"
    dataset_path.write_text(json.dumps(raw_case) + "\n", encoding="utf-8")

    with pytest.raises(EvalDatasetError, match="review_status"):
        load_dataset(dataset_path)


def test_misaligned_fixture_asset_fails_validation(tmp_path: Path) -> None:
    raw_case = json.loads(DEFAULT_DATASET_PATH.read_text().splitlines()[0])
    raw_case["profile_fixture"]["asset"] = "WRONG"
    dataset_path = tmp_path / "misaligned.jsonl"
    dataset_path.write_text(json.dumps(raw_case) + "\n", encoding="utf-8")

    with pytest.raises(EvalDatasetError, match="does not match"):
        load_dataset(dataset_path)
