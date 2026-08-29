# Stock Snapshot v1 Dataset

`stock_snapshot_v1.jsonl` is a versioned synthetic seed dataset for the
production Stock Asset Snapshot workflow. Each line is one independently
validated `StockSnapshotEvalCase`.

## Safety status

Every initial case has:

```json
{
  "provenance": "synthetic_ai_generated",
  "review_status": "pending_manual_review"
}
```

These cases are not validated financial truth and must not be used to establish
a baseline until a human reviewer approves them. Numeric values marked
`SYNTHETIC_FINANCIAL_FIXTURE` exist only to test whether the model responds
consistently to supplied context. Their financial currency and reporting dates
are also synthetic fixture metadata, not captured provider facts.
`debt_to_equity_ratio` values are normalized multiples: `2.0` means debt is
approximately 2x shareholders' equity. They are not Yahoo percentage-style
values.

## Review checklist

For each case verify:

1. The business archetype is coherent.
2. Profile fields describe the same business.
3. Peers are plausible economic comparables or competitors.
4. Synthetic financial values form a plausible shape.
5. Expectations follow from supplied context.
6. Risk themes are structural rather than current-news claims.
7. Forbidden claims are genuinely wrong for the fixture.
8. The case adds distinct benchmark coverage.
9. Real-company statements are stable and not time-sensitive.
10. The case can safely move to `review_status: "approved"`.

Review [stock_snapshot_v1_review.md](stock_snapshot_v1_review.md) alongside the
JSONL. Cases carrying `REVIEW_REAL_COMPANY_FACTS` deserve manual verification;
cases carrying `SYNTHETIC_FINANCIAL_FIXTURE` contain invented frozen numbers.

## Versioning

Do not silently rewrite approved v1 baseline cases. Add explicit regression
cases or create a new dataset version when the contract changes materially.
Future manually curated and production-regression cases may use `human` or
`production_regression` provenance.

The default runner excludes pending and rejected cases:

```bash
uv run python -m evals.asset_snapshot.run
```

`--include-pending` is an explicit developer-only escape hatch and marks reports
as `NON-BASELINE / UNREVIEWED DATASET`. Pending runs must never update a
baseline.
