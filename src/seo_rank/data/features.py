"""Feature mart builders for stored runs."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from seo_rank.data.marts import build_analysis_lazyframe
from seo_rank.data.normalize import CURATED_VALIDATION_RULES, filter_blocklisted_domain_rows
from seo_rank.data.scans import scan_curated_table
from seo_rank.data.validate import (
    align_lazyframe_schema,
    validate_frame_contract,
    validate_materialized_frame_contract,
)
from seo_rank.domain_blocklist import DomainBlocklist

FEATURE_SCHEMA_VERSION = "feature_marts.v3"
SITE_SCALE_COLUMNS = (
    "images_size",
    "scripts_size",
    "stylesheets_size",
    "total_transfer_size",
    "total_dom_size",
    "internal_links_count",
)
FEATURE_REQUIRED_COLUMNS = {
    "keyword_serp": (
        "run_id",
        "target_keyword_id",
        "target_keyword",
        "keyword_order",
        "source_response_id",
        "serp_item_id",
        "canonical_url_hash",
        "url",
        "serp_rank",
        "title",
        "description",
        "schema_version",
    ),
    "page_features": (
        "run_id",
        "target_keyword_id",
        "target_keyword",
        "page_id",
        "response_id",
        "canonical_url_hash",
        "url",
        "title",
        "page_text_length",
        "bge_raw_score",
        "bge_normalized_score",
        "gemini_doc_retrieval_raw_score",
        "gemini_doc_retrieval_normalized_score",
        "gemini_semantic_similarity_raw_score",
        "gemini_semantic_similarity_normalized_score",
        "schema_version",
    ),
    "passage_features": (
        "run_id",
        "target_keyword_id",
        "target_keyword",
        "page_id",
        "response_id",
        "passage_id",
        "canonical_url_hash",
        "url",
        "source",
        "word_count",
        "passage_text_length",
        "schema_version",
    ),
    "domain_features": (
        "run_id",
        "target_keyword_id",
        "target_keyword",
        "domain_feature_id",
        "domain",
        "serp_item_count",
        "best_serp_rank",
        "worst_serp_rank",
        "site_scale",
        "schema_version",
    ),
    "textrazor_page_metrics": (
        "run_id",
        "target_keyword_id",
        "target_keyword",
        "response_id",
        "canonical_url_hash",
        "url",
        "page_metrics_row_id",
        "textrazor_entity_confidence_score",
        "textrazor_entity_relevance_score",
        "textrazor_topic_score",
        "textrazor_category_score",
        "textrazor_classifier_score",
        "textrazor_entailment_score",
        "textrazor_entailment_prior",
        "textrazor_entailment_context",
        "textrazor_word_count",
        "textrazor_grammar_count",
        "textrazor_sense_count",
        "textrazor_spelling_count",
        "textrazor_relation_count",
        "textrazor_property_count",
        "textrazor_noun_phrase_count",
        "textrazor_entities_present",
        "textrazor_topics_present",
        "textrazor_categories_present",
        "textrazor_entailments_present",
        "textrazor_words_present",
        "textrazor_relations_present",
        "textrazor_properties_present",
        "textrazor_noun_phrases_present",
        "textrazor_page_metrics_complete",
        "schema_version",
    ),
    "entity_signals": (
        "run_id",
        "target_keyword_id",
        "target_keyword",
        "canonical_url_hash",
        "url",
        "serp_rank",
        "entity_id",
        "matched_texts",
        "entity_types",
        "entity_present",
        "entity_mention_count",
        "entity_confidence_mean",
        "entity_relevance_mean",
        "schema_version",
    ),
    "backlinks_analysis": tuple(CURATED_VALIDATION_RULES["backlinks"]["expected_schema"].keys()),
}
ANALYSIS_REQUIRED_COLUMNS = (
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
    "bge_rank",
    "bge_pct",
    "bge_z",
    "gemini_doc_retrieval_raw_score",
    "gemini_doc_retrieval_normalized_score",
    "gemini_doc_retrieval_rank",
    "gemini_doc_retrieval_pct",
    "gemini_doc_retrieval_z",
    "gemini_semantic_similarity_raw_score",
    "gemini_semantic_similarity_normalized_score",
    "gemini_semantic_similarity_rank",
    "gemini_semantic_similarity_pct",
    "gemini_semantic_similarity_z",
    "deprecated_html_tags",
    "meta_keywords_to_content_consistency",
    "time_to_first_byte_ms",
    "site_scale",
    "schema_version",
)

FEATURE_VALIDATION_RULES = {
    "keyword_serp": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "keyword_order": pl.Int64,
            "source_response_id": pl.Utf8,
            "serp_item_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "serp_rank": pl.Int64,
            "title": pl.Utf8,
            "description": pl.Utf8,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("serp_item_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "keyword_order",
            "source_response_id",
            "serp_item_id",
            "canonical_url_hash",
            "url",
            "serp_rank",
            "title",
            "description",
            "schema_version",
        ),
        "bounded_columns": {"serp_rank": (1, 20)},
    },
    "page_features": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "page_id": pl.Utf8,
            "response_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "title": pl.Utf8,
            "page_text_length": pl.UInt32,
            "bge_raw_score": pl.Float64,
            "bge_normalized_score": pl.Float64,
            "gemini_doc_retrieval_raw_score": pl.Float64,
            "gemini_doc_retrieval_normalized_score": pl.Float64,
            "gemini_semantic_similarity_raw_score": pl.Float64,
            "gemini_semantic_similarity_normalized_score": pl.Float64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("page_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "page_id",
            "response_id",
            "canonical_url_hash",
            "url",
            "title",
            "page_text_length",
            "bge_raw_score",
            "bge_normalized_score",
            "gemini_doc_retrieval_raw_score",
            "gemini_doc_retrieval_normalized_score",
            "gemini_semantic_similarity_raw_score",
            "gemini_semantic_similarity_normalized_score",
            "schema_version",
        ),
        "bounded_columns": {
            "page_text_length": (0, None),
            "bge_normalized_score": (0, 1),
            "gemini_doc_retrieval_normalized_score": (0, 1),
            "gemini_semantic_similarity_normalized_score": (0, 1),
        },
    },
    "passage_features": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "page_id": pl.Utf8,
            "response_id": pl.Utf8,
            "passage_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "source": pl.Utf8,
            "word_count": pl.Int64,
            "passage_text_length": pl.UInt32,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("passage_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "page_id",
            "response_id",
            "passage_id",
            "canonical_url_hash",
            "url",
            "source",
            "word_count",
            "passage_text_length",
            "schema_version",
        ),
        "bounded_columns": {
            "word_count": (1, None),
            "passage_text_length": (0, None),
        },
    },
    "domain_features": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "domain_feature_id": pl.Utf8,
            "domain": pl.Utf8,
            "serp_item_count": pl.UInt32,
            "best_serp_rank": pl.Int64,
            "worst_serp_rank": pl.Int64,
            "site_scale": pl.Float64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("domain_feature_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "domain_feature_id",
            "domain",
            "serp_item_count",
            "best_serp_rank",
            "worst_serp_rank",
            "schema_version",
        ),
        "bounded_columns": {
            "serp_item_count": (1, None),
            "best_serp_rank": (1, 20),
            "worst_serp_rank": (1, 20),
        },
    },
    "textrazor_page_metrics": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "page_metrics_row_id": pl.Utf8,
            "textrazor_entity_confidence_score": pl.Float64,
            "textrazor_entity_relevance_score": pl.Float64,
            "textrazor_topic_score": pl.Float64,
            "textrazor_category_score": pl.Float64,
            "textrazor_classifier_score": pl.Float64,
            "textrazor_entailment_score": pl.Float64,
            "textrazor_entailment_prior": pl.Float64,
            "textrazor_entailment_context": pl.Float64,
            "textrazor_word_count": pl.Int64,
            "textrazor_grammar_count": pl.Int64,
            "textrazor_sense_count": pl.Int64,
            "textrazor_spelling_count": pl.Int64,
            "textrazor_relation_count": pl.Int64,
            "textrazor_property_count": pl.Int64,
            "textrazor_noun_phrase_count": pl.Int64,
            "textrazor_entities_present": pl.Boolean,
            "textrazor_topics_present": pl.Boolean,
            "textrazor_categories_present": pl.Boolean,
            "textrazor_entailments_present": pl.Boolean,
            "textrazor_words_present": pl.Boolean,
            "textrazor_relations_present": pl.Boolean,
            "textrazor_properties_present": pl.Boolean,
            "textrazor_noun_phrases_present": pl.Boolean,
            "textrazor_page_metrics_complete": pl.Boolean,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("page_metrics_row_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "canonical_url_hash",
            "url",
            "page_metrics_row_id",
            "textrazor_entities_present",
            "textrazor_topics_present",
            "textrazor_categories_present",
            "textrazor_entailments_present",
            "textrazor_words_present",
            "textrazor_relations_present",
            "textrazor_properties_present",
            "textrazor_noun_phrases_present",
            "textrazor_page_metrics_complete",
            "schema_version",
        ),
        "bounded_columns": {
            "textrazor_entity_confidence_score": (0, None),
            "textrazor_entity_relevance_score": (0, 1),
            "textrazor_topic_score": (0, 1),
            "textrazor_category_score": (0, 1),
            "textrazor_classifier_score": (0, 1),
            "textrazor_entailment_score": (0, None),
            "textrazor_entailment_prior": (0, 1),
            "textrazor_entailment_context": (0, 1),
            "textrazor_word_count": (0, None),
            "textrazor_grammar_count": (0, None),
            "textrazor_sense_count": (0, None),
            "textrazor_spelling_count": (0, None),
            "textrazor_relation_count": (0, None),
            "textrazor_property_count": (0, None),
            "textrazor_noun_phrase_count": (0, None),
        },
    },
    "entity_signals": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "serp_rank": pl.Int64,
            "entity_id": pl.Utf8,
            "matched_texts": pl.List(pl.Utf8),
            "entity_types": pl.List(pl.Utf8),
            "entity_present": pl.Int64,
            "entity_mention_count": pl.Int64,
            "entity_confidence_mean": pl.Float64,
            "entity_relevance_mean": pl.Float64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": (
            "run_id",
            "target_keyword_id",
            "canonical_url_hash",
            "entity_id",
        ),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "canonical_url_hash",
            "url",
            "serp_rank",
            "entity_id",
            "matched_texts",
            "entity_types",
            "entity_present",
            "entity_mention_count",
            "schema_version",
        ),
        "bounded_columns": {
            "serp_rank": (1, 20),
            "entity_present": (0, 1),
            "entity_mention_count": (0, None),
            "entity_confidence_mean": (0, None),
            "entity_relevance_mean": (0, 1),
        },
    },
    "backlinks_analysis": CURATED_VALIDATION_RULES["backlinks"],
    "analysis_mart": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "keyword_order": pl.Int64,
            "source_response_id": pl.Utf8,
            "serp_item_id": pl.Utf8,
            "page_id": pl.Utf8,
            "response_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "serp_rank": pl.Int64,
            "title": pl.Utf8,
            "description": pl.Utf8,
            "page_text_length": pl.UInt32,
            "bge_raw_score": pl.Float64,
            "bge_normalized_score": pl.Float64,
            "bge_rank": pl.Int64,
            "bge_pct": pl.Float64,
            "bge_z": pl.Float64,
            "gemini_doc_retrieval_raw_score": pl.Float64,
            "gemini_doc_retrieval_normalized_score": pl.Float64,
            "gemini_doc_retrieval_rank": pl.Int64,
            "gemini_doc_retrieval_pct": pl.Float64,
            "gemini_doc_retrieval_z": pl.Float64,
            "gemini_semantic_similarity_raw_score": pl.Float64,
            "gemini_semantic_similarity_normalized_score": pl.Float64,
            "gemini_semantic_similarity_rank": pl.Int64,
            "gemini_semantic_similarity_pct": pl.Float64,
            "gemini_semantic_similarity_z": pl.Float64,
            "deprecated_html_tags": pl.Boolean,
            "meta_keywords_to_content_consistency": pl.Float64,
            "time_to_first_byte_ms": pl.Int64,
            "site_scale": pl.Float64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("serp_item_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "keyword_order",
            "source_response_id",
            "serp_item_id",
            "canonical_url_hash",
            "url",
            "serp_rank",
            "title",
            "description",
            "schema_version",
        ),
        "bounded_columns": {
            "serp_rank": (1, 20),
            "page_text_length": (0, None),
            "bge_normalized_score": (0, 1),
            "bge_rank": (1, 20),
            "bge_pct": (0, 1),
            "gemini_doc_retrieval_normalized_score": (0, 1),
            "gemini_doc_retrieval_rank": (1, 20),
            "gemini_doc_retrieval_pct": (0, 1),
            "gemini_semantic_similarity_normalized_score": (0, 1),
            "gemini_semantic_similarity_rank": (1, 20),
            "gemini_semantic_similarity_pct": (0, 1),
            "meta_keywords_to_content_consistency": (0, 1),
            "time_to_first_byte_ms": (0, None),
        },
    },
}

BACKLINKS_ANALYSIS_EXCLUDED_COLUMNS = {
    "run_id",
    "target_keyword_id",
    "target_keyword",
    "response_id",
    "canonical_url_hash",
    "url",
    "schema_version",
    # Supplied by the base analysis mart as robustness controls; excluded here
    # so the backlinks_analysis join does not duplicate them.
    "deprecated_html_tags",
    "meta_keywords_to_content_consistency",
    "time_to_first_byte_ms",
}
BACKLINKS_ANALYSIS_EXTRA_COLUMNS = tuple(
    column
    for column in CURATED_VALIDATION_RULES["backlinks"]["expected_schema"].keys()
    if column not in BACKLINKS_ANALYSIS_EXCLUDED_COLUMNS
)
BACKLINKS_ANALYSIS_REQUIRED_COLUMNS = (
    *ANALYSIS_REQUIRED_COLUMNS,
    *BACKLINKS_ANALYSIS_EXTRA_COLUMNS,
)
BACKLINKS_ANALYSIS_EXPECTED_SCHEMA = {
    **FEATURE_VALIDATION_RULES["analysis_mart"]["expected_schema"],
    **{
        column: CURATED_VALIDATION_RULES["backlinks"]["expected_schema"][column]
        for column in BACKLINKS_ANALYSIS_EXTRA_COLUMNS
    },
}
BACKLINKS_ANALYSIS_BOUNDED_COLUMNS = {
    **FEATURE_VALIDATION_RULES["analysis_mart"]["bounded_columns"],
    "backlinks_count": (0, None),
    "referring_domains_count": (0, None),
    "dofollow_backlinks_count": (0, None),
    "dofollow_referring_domains_count": (0, None),
}
FEATURE_REQUIRED_COLUMNS["backlinks_analysis"] = BACKLINKS_ANALYSIS_REQUIRED_COLUMNS
FEATURE_VALIDATION_RULES["backlinks_analysis"] = {
    "expected_schema": BACKLINKS_ANALYSIS_EXPECTED_SCHEMA,
    "unique_columns": FEATURE_VALIDATION_RULES["analysis_mart"]["unique_columns"],
    "non_null_columns": FEATURE_VALIDATION_RULES["analysis_mart"]["non_null_columns"],
    "bounded_columns": BACKLINKS_ANALYSIS_BOUNDED_COLUMNS,
}

ONPAGE_FEATURES_EXCLUDED_COLUMNS = {
    "run_id",
    "target_keyword_id",
    "target_keyword",
    "response_id",
    "canonical_url_hash",
    "url",
    "deprecated_html_tags",
    "meta_keywords_to_content_consistency",
    "time_to_first_byte_ms",
    "schema_version",
}
ONPAGE_FEATURES_EXTRA_COLUMNS = tuple(
    column
    for column in CURATED_VALIDATION_RULES["onpage_signals"]["expected_schema"].keys()
    if column not in ONPAGE_FEATURES_EXCLUDED_COLUMNS
)
ONPAGE_FEATURES_REQUIRED_COLUMNS = (
    *ANALYSIS_REQUIRED_COLUMNS,
    *ONPAGE_FEATURES_EXTRA_COLUMNS,
)
ONPAGE_FEATURES_EXPECTED_SCHEMA = {
    **FEATURE_VALIDATION_RULES["analysis_mart"]["expected_schema"],
    **{
        column: CURATED_VALIDATION_RULES["onpage_signals"]["expected_schema"][column]
        for column in ONPAGE_FEATURES_EXTRA_COLUMNS
    },
}
ONPAGE_FEATURES_BOUNDED_COLUMNS = {
    **FEATURE_VALIDATION_RULES["analysis_mart"]["bounded_columns"],
    "onpage_score": (0, 100),
    # Slices 11-14: meta block counts and sizes
    "description_length": (0, None),
    "title_length": (0, None),
    "external_links_count": (0, None),
    "internal_links_count": (0, None),
    "images_count": (0, None),
    "images_size": (0, None),
    "scripts_count": (0, None),
    "scripts_size": (0, None),
    "stylesheets_count": (0, None),
    "stylesheets_size": (0, None),
    "render_blocking_scripts_count": (0, None),
    "render_blocking_stylesheets_count": (0, None),
    "inbound_links_count": (0, None),
    "duplicate_meta_tags_count": (0, None),
    # Slice 12: consistency scores (0-1 ratios)
    "description_to_content_consistency": (0, 1),
    "title_to_content_consistency": (0, 1),
    "meta_keywords_to_content_consistency": (0, 1),
    # Slice 13: htag counts
    "h1_count": (0, None),
    "h2_count": (0, None),
    "h3_count": (0, None),
    # Slice 13: readability and content metrics
    "plain_text_word_count": (0, None),
    "plain_text_rate": (0, 1),
    # Slice 14: page timing
    "time_to_first_byte_ms": (0, None),
    "largest_contentful_paint_ms": (0, None),
    "cumulative_layout_shift": (0, None),
    "connection_time_ms": (0, None),
    "time_to_secure_connection_ms": (0, None),
    "request_sent_time_ms": (0, None),
    "download_time_ms": (0, None),
    "duration_time_ms": (0, None),
    "fetch_end_ms": (0, None),
    "dom_complete_ms": (0, None),
    "time_to_interactive_ms": (0, None),
    "first_input_delay_ms": (0, None),
    # Slice 14: resource/cache/DOM/size
    "total_transfer_size": (0, None),
    "micromarkup_items_count": (0, None),
    "micromarkup_errors_count": (0, None),
    "micromarkup_warnings_count": (0, None),
    "cache_control_ttl": (0, None),
    "resource_errors_count": (0, None),
    "resource_warnings_count": (0, None),
    "click_depth": (0, None),
    "encoded_size": (0, None),
    "total_dom_size": (0, None),
}
FEATURE_REQUIRED_COLUMNS["onpage_features"] = ONPAGE_FEATURES_REQUIRED_COLUMNS
FEATURE_VALIDATION_RULES["onpage_features"] = {
    "expected_schema": ONPAGE_FEATURES_EXPECTED_SCHEMA,
    "unique_columns": FEATURE_VALIDATION_RULES["analysis_mart"]["unique_columns"],
    "non_null_columns": FEATURE_VALIDATION_RULES["analysis_mart"]["non_null_columns"],
    "bounded_columns": ONPAGE_FEATURES_BOUNDED_COLUMNS,
}


def build_site_scale(frame: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
    """Build one standardized-mean site-scale value per run and hostname."""

    lazy_frame = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    page_medians = (
        lazy_frame.group_by(["run_id", "domain", "canonical_url_hash"])
        .agg(
            [
                pl.col(column).cast(pl.Float64).median().alias(column)
                for column in SITE_SCALE_COLUMNS
            ]
        )
    )
    domain_medians = page_medians.group_by(["run_id", "domain"]).agg(
        [pl.col(column).median().alias(column) for column in SITE_SCALE_COLUMNS]
    )
    logged = domain_medians.with_columns(
        [
            (pl.col(column) + 1.0).log().alias(f"__log_{column}")
            for column in SITE_SCALE_COLUMNS
        ]
    )
    z_scores = logged.with_columns(
        [
            pl.when(pl.col(column).is_null())
            .then(None)
            .when(
                pl.col(f"__log_{column}").std(ddof=1).over("run_id").is_null()
                | (pl.col(f"__log_{column}").std(ddof=1).over("run_id") == 0.0)
            )
            .then(0.0)
            .otherwise(
                (
                    pl.col(f"__log_{column}")
                    - pl.col(f"__log_{column}").mean().over("run_id")
                )
                / pl.col(f"__log_{column}").std(ddof=1).over("run_id")
            )
            .alias(f"__z_{column}")
            for column in SITE_SCALE_COLUMNS
        ]
    )
    complete = pl.all_horizontal(
        [pl.col(column).is_not_null() for column in SITE_SCALE_COLUMNS]
    )
    return z_scores.with_columns(
        pl.when(complete)
        .then(pl.mean_horizontal([pl.col(f"__z_{column}") for column in SITE_SCALE_COLUMNS]))
        .otherwise(None)
        .cast(pl.Float64)
        .alias("site_scale")
    ).select(["run_id", "domain", "site_scale"])


def build_analysis_panel_keyword_serp(
    keyword_serp: pl.LazyFrame,
    page_features: pl.LazyFrame,
    domain_features: pl.LazyFrame,
) -> pl.LazyFrame:
    """Keep only URL keys with scored pages and a usable domain control."""

    join_keys = ["run_id", "target_keyword_id", "canonical_url_hash", "url"]
    scored_urls = page_features.select(join_keys).unique(join_keys)
    scaled_domains = (
        domain_features.select(["run_id", "domain", "site_scale"])
        .filter(pl.col("site_scale").is_not_null())
        .unique(["run_id", "domain"])
    )
    return (
        keyword_serp.join(scored_urls, on=join_keys, how="inner")
        .with_columns(
            pl.col("url").str.extract(r"^https?://([^/]+)", 1).alias("__domain")
        )
        .join(
            scaled_domains,
            left_on=["run_id", "__domain"],
            right_on=["run_id", "domain"],
            how="inner",
        )
        .drop(["__domain", "site_scale"])
    )


def build_feature_lazyframes(
    curated_frames: Mapping[str, pl.LazyFrame],
) -> dict[str, pl.LazyFrame]:
    keywords = curated_frames["keywords"]
    serp_items = curated_frames["serp_items"]
    pages = curated_frames["pages"]
    passages = curated_frames["passages"]
    similarity_scores = curated_frames["similarity_scores"]
    backlinks = curated_frames["backlinks"]
    onpage_signals = curated_frames["onpage_signals"]
    entities = curated_frames["entities"]
    onpage_required_columns = CURATED_VALIDATION_RULES["onpage_signals"]["non_null_columns"]
    onpage_signals = align_lazyframe_schema(
        onpage_signals,
        {
            column: dtype
            for column, dtype in CURATED_VALIDATION_RULES["onpage_signals"]["expected_schema"].items()
            if column not in onpage_required_columns
        },
    )

    keyword_serp = (
        keywords.join(
            serp_items,
            on=["run_id", "target_keyword_id", "target_keyword"],
            how="inner",
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "keyword_order",
                "source_response_id",
                "serp_item_id",
                "canonical_url_hash",
                "url",
                "serp_rank",
                "title",
                "description",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "serp_rank", "serp_item_id"])
    )

    page_features = (
        pages.join(
            similarity_scores,
            on=["run_id", "target_keyword_id", "canonical_url_hash", "url"],
            how="inner",
        )
        .with_columns(
            pl.col("text").str.len_chars().alias("page_text_length"),
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "page_id",
                "response_id",
                "canonical_url_hash",
                "url",
                "title",
                "page_text_length",
                "bge_raw_score",
                "bge_normalized_score",
                "gemini_doc_retrieval_raw_score",
                "gemini_doc_retrieval_normalized_score",
                "gemini_semantic_similarity_raw_score",
                "gemini_semantic_similarity_normalized_score",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "canonical_url_hash", "page_id"])
    )

    passage_features = (
        passages.with_columns(
            pl.col("text").str.len_chars().alias("passage_text_length"),
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "page_id",
                "response_id",
                "passage_id",
                "canonical_url_hash",
                "url",
                "source",
                "word_count",
                "passage_text_length",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "passage_id"])
    )

    serp_domains = serp_items.with_columns(
        pl.col("url").str.extract(r"^https?://([^/]+)", 1).alias("domain"),
    )
    domain_site_scale = build_site_scale(
        serp_domains.select(
            ["run_id", "domain", "canonical_url_hash", "url", "target_keyword_id"]
        ).join(
            onpage_signals.select(
                ["run_id", "target_keyword_id", "canonical_url_hash", "url", *SITE_SCALE_COLUMNS]
            ),
            on=["run_id", "target_keyword_id", "canonical_url_hash", "url"],
            how="left",
        )
    )
    domain_features = (
        serp_domains
        .group_by(["run_id", "target_keyword_id", "target_keyword", "domain"])
        .agg(
            [
                pl.len().alias("serp_item_count"),
                pl.min("serp_rank").alias("best_serp_rank"),
                pl.max("serp_rank").alias("worst_serp_rank"),
            ]
        )
        .with_columns(
            pl.struct(
                ["run_id", "target_keyword_id", "target_keyword", "domain"]
            )
            .map_elements(
                lambda row: stable_id(
                    row["run_id"],
                    row["target_keyword_id"],
                    row["domain"],
                ),
                return_dtype=pl.Utf8,
            )
            .alias("domain_feature_id"),
        )
        .join(
            domain_site_scale,
            on=["run_id", "domain"],
            how="left",
        )
        .with_columns(
            pl.lit(FEATURE_SCHEMA_VERSION).alias("schema_version"),
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "domain_feature_id",
                "domain",
                "serp_item_count",
                "best_serp_rank",
                "worst_serp_rank",
                "site_scale",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "domain"])
    )
    analysis_keyword_serp = build_analysis_panel_keyword_serp(
        keyword_serp,
        page_features,
        domain_features,
    )

    analysis_base = build_analysis_lazyframe(
        {
            "keyword_serp": analysis_keyword_serp,
            "page_features": page_features,
            "backlinks": backlinks,
            "onpage_signals": onpage_signals,
            "domain_features": domain_features,
        }
    )
    backlinks_analysis = (
        analysis_base.join(
            backlinks.select(
                [
                    "run_id",
                    "target_keyword_id",
                    "canonical_url_hash",
                    "url",
                    *BACKLINKS_ANALYSIS_EXTRA_COLUMNS,
                ]
            ),
            on=["run_id", "target_keyword_id", "canonical_url_hash", "url"],
            how="left",
        )
        .with_columns(pl.lit(FEATURE_SCHEMA_VERSION).alias("schema_version"))
        .sort(["target_keyword_id", "serp_rank", "canonical_url_hash"])
    )
    onpage_features = (
        analysis_base.join(
            onpage_signals.select(
                [
                    "run_id",
                    "target_keyword_id",
                    "canonical_url_hash",
                    "url",
                    *ONPAGE_FEATURES_EXTRA_COLUMNS,
                ]
            ),
            on=["run_id", "target_keyword_id", "canonical_url_hash", "url"],
            how="left",
        )
        .with_columns(pl.lit(FEATURE_SCHEMA_VERSION).alias("schema_version"))
        .sort(["target_keyword_id", "serp_rank", "canonical_url_hash"])
    )
    entity_signals = build_entity_signals_lazyframe(
        entities,
        curated_frames["textrazor_page_metrics_curated"],
        serp_items,
    )

    return {
        "keyword_serp": analysis_keyword_serp,
        "page_features": page_features,
        "passage_features": passage_features,
        "domain_features": domain_features,
        "backlinks_analysis": backlinks_analysis,
        "onpage_features": onpage_features,
        "textrazor_page_metrics": curated_frames["textrazor_page_metrics_curated"],
        "entity_signals": entity_signals,
    }


def build_entity_signals_lazyframe(
    entities: pl.LazyFrame,
    textrazor_page_metrics: pl.LazyFrame,
    serp_items: pl.LazyFrame,
) -> pl.LazyFrame:
    """Build one entity-presence row per usable SERP page.

    Candidate entities expand only across keywords where they were observed;
    pages with a usable TextRazor response but no matching entity become the
    explicit absence rows needed for page-level rank analysis.
    """

    entity_keys = [
        "run_id",
        "target_keyword_id",
        "target_keyword",
        "canonical_url_hash",
        "url",
        "entity_id",
    ]
    occurrences = entities.group_by(entity_keys).agg(
        [
            pl.len().alias("entity_mention_count"),
            pl.col("confidence").mean().alias("entity_confidence_mean"),
            pl.col("relevance").mean().alias("entity_relevance_mean"),
            pl.col("matched_text").unique().sort().alias("matched_texts"),
        ]
    )
    entity_types = (
        entities.explode("types")
        .rename({"types": "entity_type"})
        .select([*entity_keys, "entity_type"])
        .filter(pl.col("entity_type").is_not_null())
        .group_by(entity_keys)
        .agg(pl.col("entity_type").unique().sort().alias("entity_types"))
    )
    candidate_keywords = occurrences.select(
        ["run_id", "target_keyword_id", "target_keyword", "entity_id"]
    ).unique()
    usable_pages = textrazor_page_metrics.select(
        ["run_id", "target_keyword_id", "target_keyword", "canonical_url_hash", "url"]
    ).join(
        serp_items.select(
            ["run_id", "target_keyword_id", "canonical_url_hash", "url", "serp_rank"]
        ),
        on=["run_id", "target_keyword_id", "canonical_url_hash", "url"],
        how="inner",
    )
    return (
        candidate_keywords.join(
            usable_pages,
            on=["run_id", "target_keyword_id", "target_keyword"],
            how="inner",
        )
        .join(occurrences, on=entity_keys, how="left")
        .join(entity_types, on=entity_keys, how="left")
        .with_columns(
            [
                pl.col("entity_mention_count").fill_null(0).cast(pl.Int64),
                pl.when(pl.col("entity_mention_count").is_null())
                .then(pl.lit(0))
                .otherwise(pl.lit(1))
                .cast(pl.Int64)
                .alias("entity_present"),
                pl.col("matched_texts")
                .fill_null(pl.lit([], dtype=pl.List(pl.Utf8)))
                .alias("matched_texts"),
                pl.col("entity_types")
                .fill_null(pl.lit([], dtype=pl.List(pl.Utf8)))
                .alias("entity_types"),
                pl.lit(FEATURE_SCHEMA_VERSION).alias("schema_version"),
            ]
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "canonical_url_hash",
                "url",
                "serp_rank",
                "entity_id",
                "matched_texts",
                "entity_types",
                "entity_present",
                "entity_mention_count",
                "entity_confidence_mean",
                "entity_relevance_mean",
                "schema_version",
            ]
        )
        .sort(["entity_id", "target_keyword_id", "serp_rank", "url"])
    )


REQUIRED_FEATURE_MARTS_FOR_ANALYSIS = (
    "keyword_serp",
    "page_features",
    "passage_features",
    "domain_features",
    "backlinks_analysis",
    "onpage_features",
    "entity_signals",
)


def ensure_feature_marts_for_analysis(run_dir: Path) -> None:
    """Rebuild derived marts when partitions are missing or schema-stale."""

    run_json_path = Path(run_dir) / "run.json"
    if run_json_path.exists():
        run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
        if isinstance(run_payload.get("combined_analysis"), Mapping):
            return

    parquet_dir = Path(run_dir) / "parquet"
    feature_marts_stale = any(
        not _dataset_matches_schema(parquet_dir / name, FEATURE_SCHEMA_VERSION)
        for name in REQUIRED_FEATURE_MARTS_FOR_ANALYSIS
    )
    if not feature_marts_stale:
        return
    if not run_json_path.exists():
        return
    build_feature_marts(Path(run_dir))


def _dataset_matches_schema(dataset_dir: Path, expected_version: str) -> bool:
    files = sorted(dataset_dir.glob("part-*.parquet"))
    if not files:
        return False
    try:
        schema = pq.read_schema(files[0])
        if "schema_version" not in schema.names:
            return False
        values = pq.read_table(files[0], columns=["schema_version"])["schema_version"].unique().to_pylist()
    except (OSError, ValueError, KeyError):
        return False
    return values == [expected_version]


def build_feature_marts(run_dir: Path) -> dict[str, object]:
    """Materialize feature marts from stored curated tables."""

    run_dir = Path(run_dir)
    run_json_path = run_dir / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    catalog: dict[str, object] = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)

    blocklist = DomainBlocklist.load()
    curated_frames = {
        name: (
            scan_curated_table(run_dir, name)
            if name == "keywords"
            else filter_blocklisted_domain_rows(
                scan_curated_table(run_dir, name), blocklist=blocklist
            )
        )
        for name in (
            "keywords",
            "serp_items",
            "pages",
            "passages",
            "similarity_scores",
            "backlinks",
            "onpage_signals",
            "entities",
            "textrazor_page_metrics_curated",
        )
    }
    feature_frames = build_feature_lazyframes(curated_frames)

    for name, frame in feature_frames.items():
        validation = FEATURE_VALIDATION_RULES[name]
        frame = validate_frame_contract(
            frame,
            required_columns=FEATURE_REQUIRED_COLUMNS[name],
            expected_schema=validation.get("expected_schema"),
            unique_columns=validation.get("unique_columns", ()),
            non_null_columns=validation.get("non_null_columns", ()),
            bounded_columns=validation.get("bounded_columns"),
        )
        dataset_catalog[name] = write_feature_dataset(
            run_dir,
            name=name,
            frame=frame,
        )

    run_payload["catalog"] = catalog
    run_json_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalog


def build_analysis_mart(run_dir: Path) -> dict[str, object]:
    """Materialize the analysis mart from feature marts."""

    run_dir = Path(run_dir)
    run_json_path = run_dir / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    catalog: dict[str, object] = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)

    feature_frames = {
        name: scan_curated_table(run_dir, name)
        for name in ("keyword_serp", "page_features", "passage_features", "domain_features")
    }
    if (run_dir / "parquet" / "onpage_signals").exists():
        feature_frames["onpage_signals"] = scan_curated_table(run_dir, "onpage_signals")
    analysis_frame = build_analysis_lazyframe(feature_frames)
    analysis_frame = validate_frame_contract(
        analysis_frame,
        required_columns=ANALYSIS_REQUIRED_COLUMNS,
        expected_schema=FEATURE_VALIDATION_RULES["analysis_mart"]["expected_schema"],
        unique_columns=FEATURE_VALIDATION_RULES["analysis_mart"]["unique_columns"],
        non_null_columns=FEATURE_VALIDATION_RULES["analysis_mart"]["non_null_columns"],
        bounded_columns=FEATURE_VALIDATION_RULES["analysis_mart"]["bounded_columns"],
    )
    dataset_catalog["analysis_mart"] = write_feature_dataset(
        run_dir,
        name="analysis_mart",
        frame=analysis_frame,
    )

    run_payload["catalog"] = catalog
    run_json_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalog


def write_feature_dataset(
    run_dir: Path,
    *,
    name: str,
    frame: pl.LazyFrame,
) -> dict[str, object]:
    dataset_dir = run_dir / "parquet" / name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for part_path in dataset_dir.glob("part-*.parquet"):
        part_path.unlink()
    file_path = dataset_dir / "part-0.parquet"
    validation = FEATURE_VALIDATION_RULES[name]
    try:
        frame.sink_parquet(file_path, compression="zstd", statistics=True)
        validate_materialized_frame_contract(
            pl.from_arrow(pq.read_table(file_path)),
            unique_columns=validation.get("unique_columns", ()),
            non_null_columns=validation.get("non_null_columns", ()),
            bounded_columns=validation.get("bounded_columns"),
        )
    except ValueError as error:
        raise ValueError(f"{name} validation failed: {error}") from error
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "row_count": pq.ParquetFile(file_path).metadata.num_rows,
        "files": [file_path.relative_to(run_dir).as_posix()],
        "file_checksums": {
            file_path.relative_to(run_dir).as_posix(): file_sha256(file_path)
        },
    }


def stable_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
