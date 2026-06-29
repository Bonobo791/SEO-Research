"""Analysis mart builders for stored runs."""

from collections.abc import Mapping

import polars as pl

ANALYSIS_SCHEMA_VERSION = "analysis_mart.v1"


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
        .with_columns(pl.lit(ANALYSIS_SCHEMA_VERSION).alias("schema_version"))
        .sort(["target_keyword_id", "serp_rank", "canonical_url_hash"])
    )
