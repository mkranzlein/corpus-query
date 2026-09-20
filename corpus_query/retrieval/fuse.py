"""Reciprocal rank fusion.

BM25 scores and cosine similarities live on different, incommensurable
scales — there is no principled way to add a bm25 score to a cosine
similarity and call the sum meaningful. RRF sidesteps the problem by scoring
a chunk on the rank it holds in each ranking rather than on the ranking's raw
scores, so the two halves never have to be made commensurable.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Added to a chunk's rank before it is inverted. Named and documented
#: rather than inlined as a bare 60: a small constant makes rank 1 dominate
#: the fused score, a large one flattens the rankings toward one another.
#: 60 is the value from the original RRF paper (Cormack, Clarke & Buettcher,
#: 2009) and is the conventional default.
RRF_RANK_CONSTANT = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]], k: int = RRF_RANK_CONSTANT
) -> list[tuple[int, float]]:
    """Fuse rankings of chunk ids by reciprocal rank.

    A chunk absent from a ranking simply contributes nothing to its score
    from that ranking, so a chunk found by only one of the halves still
    places, and a chunk found by both places higher than either ranking
    alone would put it.

    Args:
        rankings: One or more rankings of chunk ids, each best-first. A
            chunk may appear at most once within a given ranking.
        k: The rank constant. See :data:`RRF_RANK_CONSTANT`.

    Returns:
        ``(chunk_id, fused_score)`` pairs, best first. Ties keep the order a
        chunk first appears in, across the rankings given.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
