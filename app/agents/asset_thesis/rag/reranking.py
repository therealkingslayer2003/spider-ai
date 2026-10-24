"""Small lexical complement to dense filing search over a bounded candidate set."""

import math
import re
from collections.abc import Mapping, Sequence

from app.domain.schemas.thesis_rag import FilingChunk, FilingVectorMatch

_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_QUESTION_FILLER = frozenset(
    {
        "a", "an", "are", "by", "company", "did", "during", "for", "from",
        "how", "in", "is", "much", "of", "reported", "the", "to", "was",
        "were", "what",
    }
)


def _terms(text: str) -> list[str]:
    return [
        word for word in _WORDS.findall(text.casefold()) if word not in _QUESTION_FILLER
    ]


class LexicalFilingReranker:
    """Favor metric/period overlap while keeping dense rank as a tie-breaker."""

    version = "dense-lexical-v1"

    def rerank(
        self,
        question: str,
        dense_matches: Sequence[FilingVectorMatch],
        chunks: Mapping[str, FilingChunk],
    ) -> list[FilingVectorMatch]:
        query = _terms(question)
        if not query or len(dense_matches) < 2:
            return list(dense_matches)
        unique_query = set(query)
        sequences = [_terms(chunks[item.chunk_id].text) for item in dense_matches]
        term_sets = [set(sequence) for sequence in sequences]
        count = len(dense_matches)
        weights = {
            term: math.log(
                (count + 1) / (1 + sum(term in terms for terms in term_sets))
            ) + 1
            for term in unique_query
        }
        total_weight = sum(weights.values())
        phrases = [
            (first, second)
            for first, second in zip(query, query[1:])
            if not (first.isdigit() and second.isdigit())
        ]
        scored = []
        for dense_rank, (match, sequence, terms) in enumerate(
            zip(dense_matches, sequences, term_sets, strict=True), start=1
        ):
            term_coverage = sum(weights[t] for t in unique_query & terms) / total_weight
            adjacent = set(zip(sequence, sequence[1:]))
            phrase_coverage = (
                sum(phrase in adjacent for phrase in phrases) / len(phrases)
                if phrases else 0
            )
            dense_prior = 1 - (dense_rank - 1) / count
            score = 0.65 * term_coverage + 0.25 * phrase_coverage + 0.10 * dense_prior
            scored.append((score, dense_rank, match))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored]
