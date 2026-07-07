"""Analysis mart builders for stored runs."""

from collections.abc import Mapping

import polars as pl

ANALYSIS_SCHEMA_VERSION = "analysis_mart.v2"

_BACKENDS = ("bge", "gemini_doc_retrieval", "gemini_semantic_similarity")


def _rank_columns() -> list[pl.Expr]:
    """Within-keyword rank, percentile, and z-score for each similarity backend."""
    columns: list[pl.Expr] = []
    for backend in _BACKENDS:
        score_col = f"{backend}_normalized_score"
        rank_col = f"{backend}_rank"
        pct_col = f"{backend}_pct"
        z_col = f"{backend}_z"

        rank = pl.col(score_col).rank(method="ordinal", descending=True).over("target_keyword_id").cast(pl.Int64)
        n = pl.col(score_col).count().over("target_keyword_id")

        columns.extend([
            rank.alias(rank_col),
            pl.when(n == 1).then(0.0).otherwise(((rank - 1) / (n - 1)).cast(pl.Float64)).alias(pct_col),
            pl.when(
                (pl.col(score_col).std(ddof=1).over("target_keyword_id") == 0)
                | (n < 2)
            ).then(None).otherwise(
                (pl.col(score_col) - pl.col(score_col).mean().over("target_keyword_id"))
                / pl.col(score_col).std(ddof=1).over("target_keyword_id")
            ).alias(z_col),
        ])
    return columns


def build_analysis_lazyframe(feature_frames: Mapping[str, pl.LazyFrame]) -> pl.LazyFrame:
    return (
        feature_frames["keyword_serp"]
        .join(
            feature_frames["page_features"],
            on=["run_id", "target_keyword_id", "canonical_url_hash", "url"],
            how="left",
            suffix="_page",
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "keyword_order",
                "source_response_id",
                "serp_item_id",
                "page_id",
                "response_id",
                "canonical_url_hash",
                "url",
                "serp_rank",
                "title",
                "description",
                "page_text_length",
                "bge_raw_score",
                "bge_normalized_score",
                "gemini_doc_retrieval_raw_score",
                "gemini_doc_retrieval_normalized_score",
                "gemini_semantic_similarity_raw_score",
                "gemini_semantic_similarity_normalized_score",
            ]
        )
        .sort(["target_keyword_id", "serp_rank", "canonical_url_hash"])
        .with_columns(*_rank_columns())
        .with_columns(pl.lit(ANALYSIS_SCHEMA_VERSION).alias("schema_version"))
    )
