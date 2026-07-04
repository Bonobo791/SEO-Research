"""Within-keyword relative similarity transforms."""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

_SIMILARITY_SOURCES: Mapping[str, str] = {
    "bge": "bge_raw_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}


def add_within_keyword_similarity_ranks(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Add relative similarity rank, pct, and z columns within each keyword."""

    return frame.with_columns(
        *[
            expression
            for backend, source_column in _SIMILARITY_SOURCES.items()
            for expression in _within_keyword_similarity_expressions(backend, source_column)
        ]
    )


def _within_keyword_similarity_expressions(backend: str, source_column: str) -> list[pl.Expr]:
    score = pl.col(source_column)
    rank = score.rank(method="average", descending=True).over("target_keyword_id")
    count = score.count().over("target_keyword_id")
    mean = score.mean().over("target_keyword_id")
    std = score.std(ddof=1).over("target_keyword_id")
    prefix = f"{backend}_similarity"

    return [
        rank.alias(f"{prefix}_rank"),
        pl.when(score.is_not_null() & (count > 1))
        .then((rank - 1) / (count - 1))
        .otherwise(None)
        .alias(f"{prefix}_pct"),
        pl.when(score.is_not_null() & std.is_not_null() & (std != 0))
        .then((score - mean) / std)
        .otherwise(None)
        .alias(f"{prefix}_z"),
    ]
