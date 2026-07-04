from __future__ import annotations

import polars as pl
import pytest

from seo_rank.data.ranks import add_within_keyword_similarity_ranks


def test_add_within_keyword_similarity_ranks_handles_ties_and_descending_order() -> None:
    frame = pl.DataFrame(
        {
            "target_keyword_id": ["kw-1", "kw-1", "kw-1", "kw-1"],
            "bge_raw_score": [0.9, 0.9, 0.4, 0.1],
            "gemini_doc_retrieval_normalized_score": [0.5, 0.4, 0.3, 0.2],
            "gemini_semantic_similarity_normalized_score": [0.2, 0.2, 0.2, 0.2],
        }
    )

    result = add_within_keyword_similarity_ranks(frame.lazy()).collect()

    assert result["bge_similarity_rank"].to_list() == pytest.approx([1.5, 1.5, 3.0, 4.0])
    assert result["bge_similarity_pct"].to_list() == pytest.approx([1 / 6, 1 / 6, 2 / 3, 1.0])
    assert result["gemini_doc_retrieval_similarity_rank"].to_list() == pytest.approx([1.0, 2.0, 3.0, 4.0])
    assert result["gemini_doc_retrieval_similarity_pct"].to_list() == pytest.approx([0.0, 1 / 3, 2 / 3, 1.0])
    assert result["gemini_semantic_similarity_similarity_rank"].to_list() == pytest.approx([2.5, 2.5, 2.5, 2.5])
    assert result["gemini_semantic_similarity_similarity_pct"].to_list() == pytest.approx([0.5, 0.5, 0.5, 0.5])


def test_add_within_keyword_similarity_ranks_returns_null_pct_and_z_for_singleton_keywords() -> None:
    frame = pl.DataFrame(
        {
            "target_keyword_id": ["kw-1", "kw-2"],
            "bge_raw_score": [0.7, 0.2],
            "gemini_doc_retrieval_normalized_score": [0.4, 0.9],
            "gemini_semantic_similarity_normalized_score": [None, 0.1],
        }
    )

    result = add_within_keyword_similarity_ranks(frame.lazy()).collect()

    assert result["bge_similarity_rank"].to_list() == pytest.approx([1.0, 1.0])
    assert result["bge_similarity_pct"].to_list() == [None, None]
    assert result["bge_similarity_z"].to_list() == [None, None]
    assert result["gemini_doc_retrieval_similarity_pct"].to_list() == [None, None]
    assert result["gemini_doc_retrieval_similarity_z"].to_list() == [None, None]
    assert result["gemini_semantic_similarity_similarity_rank"].to_list() == [None, 1.0]
    assert result["gemini_semantic_similarity_similarity_pct"].to_list() == [None, None]
    assert result["gemini_semantic_similarity_similarity_z"].to_list() == [None, None]


def test_add_within_keyword_similarity_ranks_preserves_null_backend_scores() -> None:
    frame = pl.DataFrame(
        {
            "target_keyword_id": ["kw-1", "kw-1", "kw-1"],
            "bge_raw_score": [0.8, None, 0.2],
            "gemini_doc_retrieval_normalized_score": [0.6, 0.4, None],
            "gemini_semantic_similarity_normalized_score": [0.3, 0.2, 0.1],
        }
    )

    result = add_within_keyword_similarity_ranks(frame.lazy()).collect()

    assert result["bge_similarity_rank"].to_list() == [1.0, None, 2.0]
    assert result["bge_similarity_pct"].to_list() == [0.0, None, 1.0]
    assert result["bge_similarity_z"].to_list() == pytest.approx([0.7071067811865475, None, -0.7071067811865475], nan_ok=False)
    assert result["gemini_doc_retrieval_similarity_rank"].to_list() == [1.0, 2.0, None]
    assert result["gemini_doc_retrieval_similarity_pct"].to_list() == [0.0, 1.0, None]
    assert result["gemini_doc_retrieval_similarity_z"].to_list() == pytest.approx([0.7071067811865475, -0.7071067811865475, None], nan_ok=False)


def test_add_within_keyword_similarity_ranks_handles_full_top_twenty_panel() -> None:
    scores = [float(20 - index) for index in range(20)]
    frame = pl.DataFrame(
        {
            "target_keyword_id": ["kw-1"] * 20,
            "bge_raw_score": scores,
            "gemini_doc_retrieval_normalized_score": scores,
            "gemini_semantic_similarity_normalized_score": scores,
        }
    )

    result = add_within_keyword_similarity_ranks(frame.lazy()).collect()

    assert result["bge_similarity_rank"].to_list() == pytest.approx([float(index) for index in range(1, 21)])
    assert result["bge_similarity_pct"].to_list() == pytest.approx([index / 19 for index in range(20)])
    assert result["gemini_doc_retrieval_similarity_rank"].to_list() == pytest.approx([float(index) for index in range(1, 21)])
    assert result["gemini_semantic_similarity_similarity_rank"].to_list() == pytest.approx([float(index) for index in range(1, 21)])
    assert result["bge_similarity_z"].null_count() == 0
    assert result["gemini_doc_retrieval_similarity_z"].null_count() == 0
    assert result["gemini_semantic_similarity_similarity_z"].null_count() == 0

