# Stock Snapshot v1 Dataset

`stock_snapshot_v1.jsonl` is a versioned synthetic seed dataset for the
production Stock Asset Snapshot workflow. Each line is one independently
validated `StockSnapshotEvalCase`.

## Peer-landscape revision

The revision is `stock_snapshot_v1_peer_landscape_v2`; the JSONL filename is retained.
There are 32 cases: 30 previously approved cases and two new pending cases.
The output contract now uses `peer_landscape`, required four-way `peer_type`,
`relationship_area`, a combined `why_relevant`, and risk `related_entities`.
This is an intentional schema/grounding-policy revision, not directly comparable
with historical competitor-centric scores.

Input fixtures remain provider facts, not preclassified answers. Existing financial
values and business/risk themes are retained. `enforce_supplied_peers_only` replaces
the old competitor-identity switch; it does not prohibit permitted stable knowledge
about an already supplied peer. `peer_relationship_guidance` provides case-specific
semantic judging expectations without feeding them to generation or providers.
Changed expectations carry `REVIEW_PEER_LANDSCAPE_POLICY`; existing approvals are
preserved, but the revised policy deserves review before adopting a new baseline.

AMZN still requires Etsy/CASY coverage; CASY may be comparable when stable retail
knowledge is reliable, otherwise unclear. Sparse MA peers may be classified using
established payment-network knowledge. Fictional FARM has no established economic
overlap with CloudX: unclear is appropriate, not fabricated software competition.
Provider membership alone does not prove even broad business similarity.

New pending cases:

- `novapay_peer_types_001`: direct card-network overlap, indirect account-to-account
  substitution, broadly comparable payment analytics, and an unidentified peer.
- `aapl_stable_platform_peers_001`: compact GOOGL/MSFT profiles omit mobile/desktop
  platform details that reliable established knowledge can supply. No numerical or
  recent relationship claims are licensed by that allowance.

All profiles are authored fixtures, **not captured vendor responses**. New timestamps
are fixed. Do not interpret plausible real-company text as verified ground truth.

The frozen profile provider serves `peers_fixture.peers[].profile` through the
same enrichment calls as production. `peer_type`, `why_relevant`, and
`relationship_area` contain supported analysis or meaningful evidence limitations,
not prewritten fixture answers or bare placeholders.
Missing profiles remain missing; evals never call live vendors.
The merged explanation retains both relationship reasoning and economic significance
in the semantic rubric. Provider input fixtures and expected economic themes are
unchanged by this merge; they never contained prewritten explanation-field outputs.

This explicitly replaces the previous fixture contract. Old reports remain
historical artifacts and their scores are not directly comparable with this
revision (there are eight deterministic checks and five semantic graders). Human review is required
before using the migrated cases as a new baseline.

## Safety status

Seed cases were originally created with:

```json
{
  "provenance": "synthetic_ai_generated",
  "review_status": "pending_manual_review"
}
```

Current review counts are listed above. Authored fixtures are not validated
financial truth; unreviewed cases must not establish a baseline. Numeric values marked
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
3. Peer classifications follow economic support, not just provider membership.
4. Synthetic financial values form a plausible shape.
5. Expectations respect provider evidence and permitted stable secondary knowledge.
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
