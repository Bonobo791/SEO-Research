"""Analysis mart builders for stored runs."""
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md


import logging
from collections.abc import Mapping

import polars as pl

logger = logging.getLogger(__name__)

ANALYSIS_SCHEMA_VERSION = "analysis_mart.v8"

_DEPRECATED_HTML_TAGS_COLUMN = "deprecated_html_tags"
_META_KEYWORDS_CONSISTENCY_COLUMN = "meta_keywords_to_content_consistency"
_TIME_TO_FIRST_BYTE_COLUMN = "time_to_first_byte_ms"
_SITE_SCALE_COLUMN = "site_scale"
_AUTHORITY_PROXY_COLUMN = "authority_proxy"
_DOMAIN_CONTROL_COLUMNS = (_SITE_SCALE_COLUMN, _AUTHORITY_PROXY_COLUMN)
_ANALYSIS_JOIN_KEYS = ["run_id", "target_keyword_id", "canonical_url_hash"]

_BACKENDS = ("bge", "gemini_doc_retrieval", "gemini_semantic_similarity")


def extract_hostname(url_expr: pl.Expr) -> pl.Expr:
    return url_expr.str.extract(r"^https?://([^/]+)", 1)


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
    """
    Build the analysis mart from keyword SERP, page, on-page, and domain feature frames.
    
    Parameters:
        feature_frames (Mapping[str, pl.LazyFrame]): Feature frames keyed by their source names.
    
    Returns:
        pl.LazyFrame: The assembled analysis mart with optional feature columns, similarity rankings, and schema version.
    """
    logger.info("building analysis lazyframe")
    frame = (
        feature_frames["keyword_serp"]
        .join(
            feature_frames["page_features"],
            on=["run_id", "target_keyword_id", "canonical_url_hash"],
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
    )
    frame = _attach_deprecated_html_tags(frame, feature_frames.get("onpage_signals"))
    frame = _attach_meta_keywords_consistency(frame, feature_frames.get("onpage_signals"))
    frame = _attach_time_to_first_byte(frame, feature_frames.get("onpage_signals"))
    frame = _attach_domain_controls(frame, feature_frames.get("domain_features"))
    return (
        frame
        .sort(["target_keyword_id", "serp_rank", "canonical_url_hash"])
        .with_columns(*_rank_columns())
        .with_columns(pl.lit(ANALYSIS_SCHEMA_VERSION).alias("schema_version"))
    )


def _attach_deprecated_html_tags(
    frame: pl.LazyFrame, onpage_signals: pl.LazyFrame | None
) -> pl.LazyFrame:
    if onpage_signals is None or _DEPRECATED_HTML_TAGS_COLUMN not in onpage_signals.collect_schema():
        return frame.with_columns(pl.lit(None).cast(pl.Boolean).alias(_DEPRECATED_HTML_TAGS_COLUMN))
    return frame.join(
        onpage_signals.select([*_ANALYSIS_JOIN_KEYS, _DEPRECATED_HTML_TAGS_COLUMN]),
        on=_ANALYSIS_JOIN_KEYS,
        how="left",
    )


def _attach_meta_keywords_consistency(
    frame: pl.LazyFrame, onpage_signals: pl.LazyFrame | None
) -> pl.LazyFrame:
    if (
        onpage_signals is None
        or _META_KEYWORDS_CONSISTENCY_COLUMN not in onpage_signals.collect_schema()
    ):
        return frame.with_columns(
            pl.lit(None).cast(pl.Float64).alias(_META_KEYWORDS_CONSISTENCY_COLUMN)
        )
    return frame.join(
        onpage_signals.select([*_ANALYSIS_JOIN_KEYS, _META_KEYWORDS_CONSISTENCY_COLUMN]),
        on=_ANALYSIS_JOIN_KEYS,
        how="left",
    )


def _attach_time_to_first_byte(
    frame: pl.LazyFrame, onpage_signals: pl.LazyFrame | None
) -> pl.LazyFrame:
    """
    Add time-to-first-byte data to the analysis frame when available.
    
    Parameters:
        frame (pl.LazyFrame): The analysis frame to enrich.
        onpage_signals (pl.LazyFrame | None): Optional on-page signals containing time-to-first-byte data.
    
    Returns:
        pl.LazyFrame: The frame with a time-to-first-byte column, populated from on-page signals or filled with null values.
    """
    if (
        onpage_signals is None
        or _TIME_TO_FIRST_BYTE_COLUMN not in onpage_signals.collect_schema()
    ):
        return frame.with_columns(
            pl.lit(None).cast(pl.Int64).alias(_TIME_TO_FIRST_BYTE_COLUMN)
        )
    return frame.join(
        onpage_signals.select([*_ANALYSIS_JOIN_KEYS, _TIME_TO_FIRST_BYTE_COLUMN]),
        on=_ANALYSIS_JOIN_KEYS,
        how="left",
    )


def _attach_domain_controls(
    frame: pl.LazyFrame, domain_features: pl.LazyFrame | None
) -> pl.LazyFrame:
    """
    Attach available domain control values to the analysis frame.
    
    Parameters:
        frame (pl.LazyFrame): Analysis rows to enrich.
        domain_features (pl.LazyFrame | None): Optional domain-level feature data.
    
    Returns:
        pl.LazyFrame: The frame with domain control columns attached; unavailable controls are null.
    """
    schema = None if domain_features is None else domain_features.collect_schema()
    present = [
        column for column in _DOMAIN_CONTROL_COLUMNS if schema is not None and column in schema
    ]
    missing = [column for column in _DOMAIN_CONTROL_COLUMNS if column not in present]
    if missing:
        frame = frame.with_columns(
            [pl.lit(None).cast(pl.Float64).alias(column) for column in missing]
        )
    if not present or domain_features is None:
        return frame
    domain_lookup = (
        domain_features.select(["run_id", "domain", *present])
        .unique(["run_id", "domain"])
    )
    return (
        frame.with_columns(
            extract_hostname(pl.col("url")).alias("__domain")
        )
        .join(
            domain_lookup,
            left_on=["run_id", "__domain"],
            right_on=["run_id", "domain"],
            how="left",
        )
        .drop("__domain")
    )
