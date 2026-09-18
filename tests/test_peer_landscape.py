import json
from typing import get_args
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_asset_snapshot_service
from app.domain.schemas.asset_snapshot import (
    PeerRelationship,
    StockAssetSnapshot,
    StructuralRisk,
)
from app.domain.schemas.company_peer_context import CompanyPeer, CompanyPeersContext
from app.llm.prompts.feature_snapshot_prompt import ASSET_SNAPSHOT_PROMPT
from app.main import create_app
from evals.asset_snapshot.dataset import load_dataset
from evals.asset_snapshot.graders import (
    PeerCoverageGrader,
    UnsupportedNumericClaimGrader,
    UnsupportedPeerRelationshipGrader,
)
from evals.asset_snapshot.judge import default_semantic_graders
from evals.asset_snapshot.original_feature_prompt import (
    ASSET_SNAPSHOT_PROMPT as VERBOSE_PROMPT,
)
from evals.asset_snapshot.pairwise import _PAIRWISE_RULES
from tests.test_asset_snapshot_api import SuccessfulAssetSnapshotService
from tests.test_database import make_snapshot

PEER_TYPES = ("direct_competitor", "indirect_competitor", "comparable", "unclear")


def relationship(peer_type="unclear", ticker="CARD"):
    return PeerRelationship(
        ticker=ticker,
        name=ticker,
        peer_type=peer_type,
        relationship_area="Payment operations; specific overlap requires support.",
        why_relevant=(
            "Provider-reported peer; relationship needs economic evidence and "
            "impact requires a defensible target-specific mechanism."
        ),
    )


@pytest.mark.parametrize("peer_type", PEER_TYPES)
def test_schema_round_trip_accepts_each_peer_type(peer_type):
    peer = relationship(peer_type)
    assert PeerRelationship.model_validate_json(peer.model_dump_json()) == peer
    assert peer.peer_type == peer_type
    assert set(peer.model_dump()) == {
        "ticker",
        "name",
        "peer_type",
        "relationship_area",
        "why_relevant",
    }


@pytest.mark.parametrize(
    "peer_type", ["supplier", "customer", "partner", "complementor", "competitor", None]
)
def test_peer_type_rejects_unsupported_values(peer_type):
    with pytest.raises(ValidationError):
        relationship(peer_type)


def test_peer_type_is_required_and_enum_is_exact():
    data = relationship().model_dump()
    del data["peer_type"]
    with pytest.raises(ValidationError, match="peer_type"):
        PeerRelationship.model_validate(data)
    assert set(get_args(PeerRelationship.model_fields["peer_type"].annotation)) == set(
        PEER_TYPES
    )


def test_combined_explanation_is_required_and_replaces_both_legacy_fields():
    explanation = (
        "Both networks compete for payment transactions; switching activity to "
        "the peer can reduce the target's processing fees."
    )
    data = relationship().model_dump()
    data["why_relevant"] = explanation
    parsed = PeerRelationship.model_validate(data)
    assert parsed.why_relevant == explanation
    assert {"why_related", "economic_relevance"}.isdisjoint(
        PeerRelationship.model_fields
    )
    del data["why_relevant"]
    data.update(why_related="Same payment activity.", economic_relevance="Lower fees.")
    with pytest.raises(ValidationError, match="why_relevant"):
        PeerRelationship.model_validate(data)


@pytest.mark.parametrize("rating", ["low", "medium", "high", " HIGH "])
def test_combined_explanation_cannot_be_a_bare_rating_in_evals(rating):
    case, output = four_type_case_and_output()
    output.peer_landscape[0].why_relevant = rating
    result = PeerCoverageGrader().grade(case, output)
    assert not result.passed
    assert "Placeholder-only relationship fields" in result.reason


def test_removed_output_fields_have_no_aliases_or_silent_migration():
    assert "competitive_landscape" not in StockAssetSnapshot.model_fields
    assert "related_competitors" not in StructuralRisk.model_fields
    assert (
        not {"competition_area", "why_competitor", "why_it_matters"}
        & PeerRelationship.model_fields.keys()
    )
    legacy = make_snapshot().model_dump(mode="json")
    legacy["competitive_landscape"] = legacy.pop("peer_landscape")
    with pytest.raises(ValidationError, match="peer_landscape"):
        StockAssetSnapshot.model_validate(legacy)


def test_related_entities_has_independent_empty_default_and_accepts_peer_identity():
    args = dict(
        title="Substitution",
        explanation="Alternative rails bypass network fees.",
        materiality="high",
    )
    first, second = StructuralRisk(**args), StructuralRisk(**args)
    assert first.related_entities == second.related_entities == []
    first.related_entities.append("RAIL")
    assert second.related_entities == []
    assert StructuralRisk(**args, related_entities=["RAIL"]).related_entities == [
        "RAIL"
    ]


@pytest.mark.parametrize("peer_type", PEER_TYPES)
def test_api_serializes_peer_relationship_and_risk_reference(peer_type):
    snapshot = make_snapshot()
    snapshot.peer_landscape = [relationship(peer_type, "AMD")]
    app = create_app()
    app.dependency_overrides[get_asset_snapshot_service] = lambda: (
        SuccessfulAssetSnapshotService(snapshot)
    )
    try:
        response = TestClient(app).post(
            "/api/v1/asset/snapshot", json={"asset": "NVDA", "asset_type": "stock"}
        )
        assert response.status_code == 200
        assert response.json() == snapshot.model_dump(mode="json")
        assert response.json()["peer_landscape"][0]["peer_type"] == peer_type
        assert response.json()["structural_risks"][0]["related_entities"] == ["AMD"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("template", [ASSET_SNAPSHOT_PROMPT, VERBOSE_PROMPT])
def test_prompts_share_secondary_knowledge_policy_and_four_type_contract(template):
    prompt = " ".join(template.split())
    for invariant in (
        "Provider evidence is the primary source of truth",
        "Stable model knowledge MAY supplement it",
        "profiles are present or compressed",
        "high-confidence, widely established, structurally persistent",
        "never override contradictory provider evidence",
        "Model memory must not introduce unsupplied numerical claims",
        "recent contracts, supplier/customer relationships, partnerships, "
        "regulatory actions",
        "Time-sensitive relationships require supplied provider evidence",
        "Do not invent facts about fictional entities",
        "Do not force diversity across types",
        "Not necessarily competitors"
        if template == ASSET_SNAPSHOT_PROMPT
        else "They need not be competitors",
    ):
        assert invariant in prompt
    assert all(kind in prompt for kind in PEER_TYPES)
    assert "peer_landscape" in prompt and "related_entities" in prompt


def test_semantic_and_pairwise_judges_use_same_policy_without_more_calls():
    case = next(c for c in load_dataset() if c.id == "aapl_stable_platform_peers_001")
    graders = default_semantic_graders(AsyncMock())
    assert len(graders) == 5
    for prompt in [g._build_prompt(case, make_snapshot()) for g in graders] + [
        _PAIRWISE_RULES
    ]:
        assert "Do not require these claims to occur literally in fixtures" in prompt
        assert "overrides\ncontradictory memory" in prompt
        assert "Model memory cannot supply numerical claims" in prompt
        assert "direct-competition overclaiming" in prompt
        assert "related_entities" in prompt
        assert "Check consistency between peer_type and the explanation" in prompt
        assert "Do not penalize it solely for being empty" in prompt
    context = json.loads(
        graders[0]
        ._build_prompt(case, make_snapshot())
        .split("Evaluation context:\n")[1]
    )
    assert context["entity_kind"] == "real"
    assert context["expectations"]["peer_relationship_guidance"]


def four_type_case_and_output():
    case = next(c for c in load_dataset() if c.id == "novapay_peer_types_001")
    output = make_snapshot()
    output.peer_landscape = [
        relationship("direct_competitor", "CARD"),
        relationship("indirect_competitor", "RAIL"),
        relationship("comparable", "METR"),
        relationship("unclear", "ZZZ"),
    ]
    output.structural_risks[0].related_entities = ["RAIL"]
    return case, output


def test_coverage_preserves_all_peers_including_comparable_and_unclear():
    case, output = four_type_case_and_output()
    assert PeerCoverageGrader().grade(case, output).passed
    assert UnsupportedPeerRelationshipGrader().grade(case, output).passed
    output.peer_landscape.pop()
    assert not PeerCoverageGrader().grade(case, output).passed


def test_duplicate_peer_entries_fail_coverage():
    case, output = four_type_case_and_output()
    output.peer_landscape.append(output.peer_landscape[0])
    result = PeerCoverageGrader().grade(case, output)
    assert not result.passed and "Duplicate" in result.reason


def test_matching_names_do_not_excuse_dropped_supplied_tickers():
    case, output = four_type_case_and_output()
    for supplied, generated in zip(
        case.peers_fixture.peers, output.peer_landscape, strict=True
    ):
        generated.name = supplied.name or supplied.ticker
        generated.ticker = None
    result = PeerCoverageGrader().grade(case, output)
    assert not result.passed
    assert "Supplied peer tickers not preserved" in result.reason
    assert all(ticker in result.reason for ticker in ("CARD", "RAIL", "METR", "ZZZ"))


@pytest.mark.parametrize("entity", ["RAIL", "RailLink", "UNKNOWN", "", "AMD"])
def test_related_entity_references_must_resolve_to_supplied_and_output_peers(entity):
    case, output = four_type_case_and_output()
    output.peer_landscape[1].name = "RailLink"
    output.structural_risks[0].related_entities = [entity]
    assert UnsupportedPeerRelationshipGrader().grade(case, output).passed == (
        entity in {"RAIL", "RailLink"}
    )


def test_membership_check_does_not_pretend_to_validate_classification_semantics():
    case, output = four_type_case_and_output()
    output.peer_landscape[-1].peer_type = "direct_competitor"
    # The semantic judge, not an identity heuristic, must penalize this overclaim.
    assert UnsupportedPeerRelationshipGrader().grade(case, output).passed


@pytest.mark.parametrize(
    "references, passed",
    [
        ([], True),
        (["BABA"], True),
        (["GOOGL"], False),
        (["Microsoft (MSFT)"], False),
    ],
)
def test_risk_prose_does_not_make_outside_entities_eligible_references(
    references, passed
):
    case = next(c for c in load_dataset() if c.id == "amzn_peer_profiles_001")
    case.peers_fixture = CompanyPeersContext(
        asset="AMZN",
        provider="test",
        peers=[CompanyPeer(ticker="BABA", name="Alibaba")],
    )
    output = make_snapshot()
    output.asset = "AMZN"
    output.peer_landscape = [relationship("direct_competitor", "BABA")]
    output.structural_risks[0].explanation = (
        "AWS faces cloud competition from Microsoft Azure, Google Cloud and "
        "Alibaba Cloud; price concessions can reduce its margins."
    )
    output.structural_risks[0].related_entities = references
    result = UnsupportedPeerRelationshipGrader().grade(case, output)
    assert result.passed is passed
    assert output.structural_risks[0].related_entities == references


def test_model_memory_does_not_exempt_numeric_claims():
    case, output = four_type_case_and_output()
    output.summary = "Stable knowledge says operating margin is 75%."
    assert not UnsupportedNumericClaimGrader().grade(case, output).passed


def test_new_frozen_cases_require_review_and_do_not_put_classifications_in_providers():
    cases = [
        c
        for c in load_dataset()
        if c.id in {"novapay_peer_types_001", "aapl_stable_platform_peers_001"}
    ]
    assert len(cases) == 2
    for case in cases:
        assert case.metadata.review_status == "pending_manual_review"
        assert case.expectations.peer_relationship_guidance
        for peer in case.peers_fixture.peers:
            assert "peer_type" not in peer.model_dump()
