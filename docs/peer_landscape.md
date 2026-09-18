# Stock Snapshot Peer Landscape

Provider membership establishes peerhood, not direct competition. The generation
LLM analyzes the target plus compact peer profiles, optionally supplements them
with reliable stable knowledge, classifies the relationship, and explains its
economic relevance. No classifier service, new provider, or extra generation call
is introduced. Five-sentence/1,200-character peer projection and full cached/
persisted provider evidence are unchanged.

## Output Contract

[`PeerRelationship`](../app/domain/schemas/asset_snapshot.py) contains:

```python
class PeerRelationship(BaseModel):
    ticker: str | None = None
    name: str
    peer_type: Literal[
        "direct_competitor", "indirect_competitor", "comparable", "unclear"
    ]
    relationship_area: str
    why_relevant: str
```

`StockAssetSnapshot.peer_landscape` is a required list of these entries.
`StructuralRisk.related_entities` is an independently defaulted empty list of
supplied peer tickers/names connected to the specific risk mechanism.

| Type | Required Support |
|---|---|
| direct_competitor | Substantial overlap in offering and demand/customers/activity/revenue pool |
| indirect_competitor | Different offering that substitutes for the same economic need/activity |
| comparable | Broad economic similarity, but no sufficiently supported competitive mechanism |
| unclear | Neither evidence nor reliable stable knowledge permits confident classification |

Every distinct identifiable supplied peer gets one entry. Preserve identities;
use the ticker as name for a ticker-only peer. Missing enrichment does not remove
the peer or force an uncertain type when reliable stable knowledge is available.
Do not force different types across a list. Supplier, customer, partner and
complementor are not valid types. A peer's business profile alone does not establish
those concrete links to the target.

The optional ticker allows genuinely name-only peers; schema enforcement therefore
cannot prevent the model from omitting a supplied ticker. During stock finalization,
[`restore_peer_tickers`](../app/agents/asset_snapshot/stock/peer_identity.py) restores
missing/blank tickers only when the generated name uniquely matches a supplied name,
an enriched profile name, or a supplied ticker used as the name. Matching ignores
case, whitespace and punctuation, but does not strip legal suffixes, use fuzzy
matching or infer symbols from model knowledge. Ambiguous/unknown identities stay
unresolved; nonempty generated tickers are not overwritten by this missing-value fix.
Restorations and unresolved matches are logged. Classification and analytical text
remain unchanged; source evidence and the incoming model are not mutated. The API
and database receive the finalized snapshot without another LLM or provider call.

Explanations distinguish competition, comparability and uncertainty. Economic
relevance concerns a causal effect on the target, not an invented measured impact.
`why_relevant` combines the relationship basis and its economic significance in
one coherent explanation, including an evidence limitation when needed. It is not
a high/medium/low rating.
Risk references are not copied wholesale from the landscape. The risk contract
remains pressure -> company exposure -> transmission mechanism -> consequence.

`related_entities` is restricted to supplied peers participating in that risk,
not an index of every company named in the prose. Stable knowledge may support a
non-peer mention without adding that entity to this list. Generation emits the
list; finalization does not extract entity names from explanations or perform
Google/Alphabet-style alias resolution. The eval identity grader rejects references
outside the supplied/output peers, but production schema validation alone cannot
enforce that contextual rule. A matching company mention alone also does not prove
material participation in the risk mechanism.

## Knowledge Policy

Priority: supplied target profile -> peer profile/context -> fundamentals -> stable
model knowledge -> conservative analytical inference. Provider evidence wins over
contradictory memory. Supplemental knowledge must be high-confidence, widely
established, persistent and non-obscure. It can explain long-established products,
platforms, activities, competitive relationships and industry structure omitted
from compact context. It is analysis support, not newly retrieved provider evidence.

Memory cannot supply numbers, current metrics/shares, recent contracts,
supplier/customer links, partnerships, regulatory actions or product/news updates.
Time-sensitive relationship claims need provider evidence. Missing metrics are not
negative evidence. Fictional entities have only their authored company facts;
general economic reasoning may interpret them, but not invent their history.

For example, established iOS/Android platform competition may supplement compact
profiles. A recent supplier agreement or a market-share percentage may not.
When support is unreliable, use comparable only if broad similarity is established;
otherwise use unclear and explain the limitation.

## Compatibility

This intentionally replaces `competitive_landscape` and its competitor-specific
fields, and `structural_risks[].related_competitors`. No aliases, dual fields or
automatic deserialization mapping are retained. The request format and endpoint
`POST /api/v1/asset/snapshot` remain unchanged; clients must consume the new output.
The later explanation merge replaces `why_related` plus `economic_relevance` with
one required `why_relevant`. Older two-field JSON likewise needs regeneration or
an explicit offline migration before it can be consumed as the new schema; this
change does not rewrite stored artifacts.

SQLite retains its single `001_initial_schema.sql` migration. The DAO serializes
and validates `StockAssetSnapshot` through `output_json`, so no SQL columns change.
New persisted records use prompt version `stock_snapshot_peer_landscape_v4`.
Existing legacy JSON is left intact and fails validation against the new schema.
Regenerate legacy snapshots for new-schema consumption; a blind migration of
competitor-centric records cannot establish a trustworthy peer_type.
No database file or saved report is deleted or rewritten. Normalized evidence
remains independently readable, including full peer profiles.

## Evals

The existing harness is adapted, not replaced. `PeerCoverageGrader` verifies
acknowledgment, preserved supplied tickers, duplicates and substantive text.
`UnsupportedPeerRelationshipGrader`
verifies allowed identities and reference resolution, not semantic classification.
Numeric grounding remains strict. Existing semantic judges now assess classification,
direct overclaims, justified substitution, comparability/uncertainty, explanation
quality, and meaningful risk connections under the secondary-knowledge policy.
Pairwise judging shares these rules. No extra semantic grader call is added.

The verbose A/B reference is rebased to the same new contract as the compact prompt;
comparing an old schema/policy against a new one would confound prompt compression.
Historical reports remain historical. See [eval usage](../evals/README.md) and the
[dataset revision](../evals/datasets/README.md) for pending cases and review rules.
