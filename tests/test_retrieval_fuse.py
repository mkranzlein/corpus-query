"""Tests for reciprocal rank fusion."""

from __future__ import annotations

from corpus_query.retrieval.fuse import RRF_RANK_CONSTANT, reciprocal_rank_fusion


def test_a_chunk_found_by_both_rankings_places_higher_than_either_alone():
    lexical = [1, 2, 3]
    dense = [2, 4, 5]

    fused = reciprocal_rank_fusion([lexical, dense])
    ids = [chunk_id for chunk_id, _ in fused]

    # 2 is second in both rankings; every id found by only one ranking
    # should rank behind it.
    assert ids[0] == 2


def test_a_chunk_found_by_only_one_ranking_still_places():
    lexical = [1, 2, 3]
    dense: list[int] = []

    fused = reciprocal_rank_fusion([lexical, dense])

    assert [chunk_id for chunk_id, _ in fused] == [1, 2, 3]


def test_fused_score_matches_the_rrf_formula():
    lexical = [10, 20]
    dense = [20, 10]
    k = RRF_RANK_CONSTANT

    fused = dict(reciprocal_rank_fusion([lexical, dense], k=k))

    assert fused[10] == 1 / (k + 1) + 1 / (k + 2)
    assert fused[20] == 1 / (k + 2) + 1 / (k + 1)


def test_a_smaller_rank_constant_sharpens_the_effect_of_rank_one():
    lexical = [1, 2]
    dense = [3, 4]

    fused_default = dict(reciprocal_rank_fusion([lexical, dense]))
    fused_small_k = dict(reciprocal_rank_fusion([lexical, dense], k=1))

    # With a small k, being rank 1 rather than rank 2 in a ranking is worth
    # relatively more of the fused score.
    default_ratio = fused_default[1] / fused_default[2]
    small_k_ratio = fused_small_k[1] / fused_small_k[2]
    assert small_k_ratio > default_ratio


def test_empty_rankings_produce_no_fused_results():
    assert reciprocal_rank_fusion([[], []]) == []


def test_a_single_ranking_is_returned_in_its_own_order():
    fused = reciprocal_rank_fusion([[5, 1, 3]])

    assert [chunk_id for chunk_id, _ in fused] == [5, 1, 3]
