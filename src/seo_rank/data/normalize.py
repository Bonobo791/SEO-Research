"""Normalize stored raw responses into curated Parquet tables."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import polars as pl
import pyarrow as pa

from seo_rank.data.scans import scan_raw_responses
from seo_rank.data.validate import (
    validate_frame_contract,
    validate_materialized_frame_contract,
)
from seo_rank.dataforseo import (
    BACKLINKS_QUERY_DOFOLLOW,
    BACKLINKS_QUERY_SUMMARY,
    DATAFORSEO_RESPONSE_SCHEMAS,
    DEFAULT_KEYWORD_LIMIT,
    backlinks_response_is_successful_empty,
    decode_content_parsing_items,
    extract_response_url,
    extract_onpage_instant_pages_item,
    normalize_keyword_expansion,
    normalize_serp_results,
    onpage_instant_pages_response_is_usable,
    parsed_page_text,
    parsed_page_text_details,
    validate_dataforseo_response,
)

BACKLINKS_LEGACY_ENDPOINT = "backlinks"
BACKLINKS_SUMMARY_ENDPOINT = "backlinks_summary"
BACKLINKS_DOFOLLOW_ENDPOINT = "backlinks_dofollow_summary"
BACKLINKS_RAW_ENDPOINTS = frozenset(
    {
        BACKLINKS_LEGACY_ENDPOINT,
        BACKLINKS_SUMMARY_ENDPOINT,
        BACKLINKS_DOFOLLOW_ENDPOINT,
    }
)
BACKLINKS_DISTRIBUTION_JSON_COLUMNS = {
    "referring_links_types": "referring_links_types_json",
    "referring_links_tld": "referring_links_tld_json",
    "referring_links_platform_types": "referring_links_platform_types_json",
    "referring_links_semantic_locations": "referring_links_semantic_locations_json",
    "referring_links_attributes": "referring_links_attributes_json",
    "referring_links_countries": "referring_links_countries_json",
}
ONPAGE_INSTANT_PAGES_ENDPOINT = "onpage_instant_pages"
ONPAGE_CURATED_CHECK_FIELDS = (
    "title_too_long",
    "title_too_short",
    "no_title",
    "no_description",
    "no_h1_tag",
    "canonical",
    "is_https",
    "has_render_blocking_resources",
    "duplicate_meta_tags",
    "has_meta_title",
    "irrelevant_description",
    "low_readability_rate",
)
from seo_rank.text import normalize_page_text
from seo_rank.textrazor import TEXTRAZOR_ENDPOINTS, normalize_entities, normalize_page_metrics

CURATED_SCHEMA_VERSION = "curated.v1"

CURATED_SCHEMAS = {
    "keywords": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("source_seed", pa.string()),
            ("source_response_id", pa.string()),
            ("keyword_order", pa.int64()),
            ("schema_version", pa.string()),
        ]
    ),
    "serp_items": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("serp_item_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("serp_rank", pa.int64()),
            ("title", pa.string()),
            ("description", pa.string()),
            ("schema_version", pa.string()),
        ]
    ),
    "pages": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("page_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("title", pa.string()),
            ("text", pa.string()),
            ("schema_version", pa.string()),
        ]
    ),
    "page_html": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("page_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("raw_html", pa.string()),
            ("schema_version", pa.string()),
        ]
    ),
    "page_content_fields": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("page_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("field_row_id", pa.string()),
            ("field_path", pa.string()),
            ("field_name", pa.string()),
            ("value_type", pa.string()),
            ("text", pa.string()),
            ("structured_value", pa.string()),
            ("ordinal", pa.int64()),
            ("schema_version", pa.string()),
        ]
    ),
    "passages": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("page_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("passage_id", pa.string()),
            ("source", pa.string()),
            ("text", pa.string()),
            ("word_count", pa.int64()),
            ("schema_version", pa.string()),
        ]
    ),
    "entities": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("entity_row_id", pa.string()),
            ("entity_id", pa.string()),
            ("matched_text", pa.string()),
            ("confidence", pa.float64()),
            ("relevance", pa.float64()),
            ("types", pa.list_(pa.string())),
            ("schema_version", pa.string()),
        ]
    ),
    "textrazor_page_metrics_curated": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("page_metrics_row_id", pa.string()),
            ("textrazor_entity_confidence_score", pa.float64()),
            ("textrazor_entity_relevance_score", pa.float64()),
            ("textrazor_topic_score", pa.float64()),
            ("textrazor_category_score", pa.float64()),
            ("textrazor_classifier_score", pa.float64()),
            ("textrazor_entailment_score", pa.float64()),
            ("textrazor_entailment_prior", pa.float64()),
            ("textrazor_entailment_context", pa.float64()),
            ("textrazor_word_count", pa.int64()),
            ("textrazor_grammar_count", pa.int64()),
            ("textrazor_sense_count", pa.int64()),
            ("textrazor_spelling_count", pa.int64()),
            ("textrazor_relation_count", pa.int64()),
            ("textrazor_property_count", pa.int64()),
            ("textrazor_noun_phrase_count", pa.int64()),
            ("textrazor_entities_present", pa.bool_()),
            ("textrazor_topics_present", pa.bool_()),
            ("textrazor_categories_present", pa.bool_()),
            ("textrazor_entailments_present", pa.bool_()),
            ("textrazor_words_present", pa.bool_()),
            ("textrazor_relations_present", pa.bool_()),
            ("textrazor_properties_present", pa.bool_()),
            ("textrazor_noun_phrases_present", pa.bool_()),
            ("textrazor_page_metrics_complete", pa.bool_()),
            ("schema_version", pa.string()),
        ]
    ),
    "similarity_scores": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("score_row_id", pa.string()),
            ("bge_raw_score", pa.float64()),
            ("bge_normalized_score", pa.float64()),
            ("gemini_doc_retrieval_raw_score", pa.float64()),
            ("gemini_doc_retrieval_normalized_score", pa.float64()),
            ("gemini_semantic_similarity_raw_score", pa.float64()),
            ("gemini_semantic_similarity_normalized_score", pa.float64()),
            ("schema_version", pa.string()),
        ]
    ),
    "backlinks": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("summary_response_id", pa.string()),
            ("dofollow_summary_response_id", pa.string()),
            ("backlink_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("backlinks_count", pa.int64()),
            ("referring_domains_count", pa.int64()),
            ("dofollow_backlinks_count", pa.int64()),
            ("dofollow_referring_domains_count", pa.int64()),
            ("rank", pa.int64()),
            ("backlinks_spam_score", pa.int64()),
            ("target_spam_score", pa.int64()),
            ("new_backlinks", pa.int64()),
            ("lost_backlinks", pa.int64()),
            ("new_referring_domains", pa.int64()),
            ("lost_referring_domains", pa.int64()),
            ("referring_pages", pa.int64()),
            ("referring_main_domains", pa.int64()),
            ("referring_ips", pa.int64()),
            ("referring_subnets", pa.int64()),
            ("broken_backlinks", pa.int64()),
            ("broken_pages", pa.int64()),
            ("referring_domains_nofollow", pa.int64()),
            ("crawled_pages", pa.int64()),
            ("internal_links_count", pa.int64()),
            ("external_links_count", pa.int64()),
            ("first_seen", pa.string()),
            ("lost_date", pa.string()),
            ("referring_links_types_json", pa.string()),
            ("referring_links_tld_json", pa.string()),
            ("referring_links_platform_types_json", pa.string()),
            ("referring_links_semantic_locations_json", pa.string()),
            ("referring_links_attributes_json", pa.string()),
            ("referring_links_countries_json", pa.string()),
            ("backlinks_metrics_complete", pa.bool_()),
            ("schema_version", pa.string()),
        ]
    ),
    "onpage_signals": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("onpage_signal_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("onpage_score", pa.float64()),
            ("title_too_long", pa.bool_()),
            ("title_too_short", pa.bool_()),
            ("no_title", pa.bool_()),
            ("no_description", pa.bool_()),
            ("no_h1_tag", pa.bool_()),
            ("canonical", pa.bool_()),
            ("is_https", pa.bool_()),
            ("has_render_blocking_resources", pa.bool_()),
            ("duplicate_meta_tags", pa.bool_()),
            ("has_meta_title", pa.bool_()),
            ("irrelevant_description", pa.bool_()),
            ("low_readability_rate", pa.bool_()),
            ("plain_text_word_count", pa.float64()),
            ("plain_text_rate", pa.float64()),
            ("flesch_kincaid_readability_index", pa.float64()),
            ("coleman_liau_readability_index", pa.float64()),
            ("smog_readability_index", pa.float64()),
            ("dale_chall_readability_index", pa.float64()),
            ("time_to_first_byte_ms", pa.int64()),
            ("largest_contentful_paint_ms", pa.float64()),
            ("cumulative_layout_shift", pa.float64()),
            ("total_transfer_size", pa.int64()),
            ("micromarkup_items_count", pa.int64()),
            ("micromarkup_errors_count", pa.int64()),
            ("micromarkup_warnings_count", pa.int64()),
            ("has_valid_structured_data", pa.bool_()),
            ("schema_version", pa.string()),
        ]
    ),
}

CURATED_VALIDATION_RULES = {
    "keywords": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "source_seed": pl.Utf8,
            "source_response_id": pl.Utf8,
            "keyword_order": pl.Int64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("target_keyword_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "source_seed",
            "source_response_id",
            "keyword_order",
            "schema_version",
        ),
    },
    "serp_items": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
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
            "response_id",
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
    "pages": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "page_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "title": pl.Utf8,
            "text": pl.Utf8,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("page_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "title",
            "text",
            "schema_version",
        ),
    },
    "page_html": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "page_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "raw_html": pl.Utf8,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("page_id", "response_id"),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "raw_html",
            "schema_version",
        ),
    },
    "page_content_fields": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "page_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "field_row_id": pl.Utf8,
            "field_path": pl.Utf8,
            "field_name": pl.Utf8,
            "value_type": pl.Utf8,
            "text": pl.Utf8,
            "structured_value": pl.Utf8,
            "ordinal": pl.Int64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("field_row_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "field_row_id",
            "field_path",
            "field_name",
            "value_type",
            "text",
            "structured_value",
            "ordinal",
            "schema_version",
        ),
        "bounded_columns": {"ordinal": (0, None)},
    },
    "passages": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "page_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "passage_id": pl.Utf8,
            "source": pl.Utf8,
            "text": pl.Utf8,
            "word_count": pl.Int64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("passage_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "passage_id",
            "source",
            "text",
            "word_count",
            "schema_version",
        ),
        "bounded_columns": {"word_count": (1, None)},
    },
    "entities": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "entity_row_id": pl.Utf8,
            "entity_id": pl.Utf8,
            "matched_text": pl.Utf8,
            "confidence": pl.Float64,
            "relevance": pl.Float64,
            "types": pl.List(pl.Utf8),
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("entity_row_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "canonical_url_hash",
            "url",
            "entity_row_id",
            "entity_id",
            "matched_text",
            "confidence",
            "relevance",
            "types",
            "schema_version",
        ),
        "bounded_columns": {"confidence": (0, None), "relevance": (0, 1)},
    },
    "textrazor_page_metrics_curated": {
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
    "similarity_scores": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "score_row_id": pl.Utf8,
            "bge_raw_score": pl.Float64,
            "bge_normalized_score": pl.Float64,
            "gemini_doc_retrieval_raw_score": pl.Float64,
            "gemini_doc_retrieval_normalized_score": pl.Float64,
            "gemini_semantic_similarity_raw_score": pl.Float64,
            "gemini_semantic_similarity_normalized_score": pl.Float64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("score_row_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "canonical_url_hash",
            "url",
            "score_row_id",
            "bge_raw_score",
            "bge_normalized_score",
            "gemini_doc_retrieval_raw_score",
            "gemini_doc_retrieval_normalized_score",
            "gemini_semantic_similarity_raw_score",
            "gemini_semantic_similarity_normalized_score",
            "schema_version",
        ),
        "bounded_columns": {
            "bge_normalized_score": (0, 1),
            "gemini_doc_retrieval_normalized_score": (0, 1),
            "gemini_semantic_similarity_normalized_score": (0, 1),
        },
    },
    "backlinks": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "summary_response_id": pl.Utf8,
            "dofollow_summary_response_id": pl.Utf8,
            "backlink_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "backlinks_count": pl.Int64,
            "referring_domains_count": pl.Int64,
            "dofollow_backlinks_count": pl.Int64,
            "dofollow_referring_domains_count": pl.Int64,
            "rank": pl.Int64,
            "backlinks_spam_score": pl.Int64,
            "target_spam_score": pl.Int64,
            "new_backlinks": pl.Int64,
            "lost_backlinks": pl.Int64,
            "new_referring_domains": pl.Int64,
            "lost_referring_domains": pl.Int64,
            "referring_pages": pl.Int64,
            "referring_main_domains": pl.Int64,
            "referring_ips": pl.Int64,
            "referring_subnets": pl.Int64,
            "broken_backlinks": pl.Int64,
            "broken_pages": pl.Int64,
            "referring_domains_nofollow": pl.Int64,
            "crawled_pages": pl.Int64,
            "internal_links_count": pl.Int64,
            "external_links_count": pl.Int64,
            "first_seen": pl.Utf8,
            "lost_date": pl.Utf8,
            "referring_links_types_json": pl.Utf8,
            "referring_links_tld_json": pl.Utf8,
            "referring_links_platform_types_json": pl.Utf8,
            "referring_links_semantic_locations_json": pl.Utf8,
            "referring_links_attributes_json": pl.Utf8,
            "referring_links_countries_json": pl.Utf8,
            "backlinks_metrics_complete": pl.Boolean,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("backlink_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "summary_response_id",
            "backlink_id",
            "canonical_url_hash",
            "url",
            "backlinks_count",
            "backlinks_metrics_complete",
            "schema_version",
        ),
    },
    "onpage_signals": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "onpage_signal_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "onpage_score": pl.Float64,
            "title_too_long": pl.Boolean,
            "title_too_short": pl.Boolean,
            "no_title": pl.Boolean,
            "no_description": pl.Boolean,
            "no_h1_tag": pl.Boolean,
            "canonical": pl.Boolean,
            "is_https": pl.Boolean,
            "has_render_blocking_resources": pl.Boolean,
            "duplicate_meta_tags": pl.Boolean,
            "has_meta_title": pl.Boolean,
            "irrelevant_description": pl.Boolean,
            "low_readability_rate": pl.Boolean,
            "plain_text_word_count": pl.Float64,
            "plain_text_rate": pl.Float64,
            "flesch_kincaid_readability_index": pl.Float64,
            "coleman_liau_readability_index": pl.Float64,
            "smog_readability_index": pl.Float64,
            "dale_chall_readability_index": pl.Float64,
            "time_to_first_byte_ms": pl.Int64,
            "largest_contentful_paint_ms": pl.Float64,
            "cumulative_layout_shift": pl.Float64,
            "total_transfer_size": pl.Int64,
            "micromarkup_items_count": pl.Int64,
            "micromarkup_errors_count": pl.Int64,
            "micromarkup_warnings_count": pl.Int64,
            "has_valid_structured_data": pl.Boolean,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("onpage_signal_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "onpage_signal_id",
            "canonical_url_hash",
            "url",
            "onpage_score",
            "schema_version",
        ),
    },
}

CURATED_PAGE_AND_PASSAGE_SCHEMA = {
    **CURATED_VALIDATION_RULES["pages"]["expected_schema"],
    "passage_id": pl.Utf8,
    "source": pl.Utf8,
    "word_count": pl.Int64,
}


def normalize_run(run_dir: Path) -> dict[str, object]:
    """Materialize curated tables from stored raw responses."""

    run_dir = Path(run_dir)
    run_json_path = run_dir / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    run_id = str(run_payload["run_id"])
    config = run_payload["config"]
    assert isinstance(config, Mapping)
    seed = str(config["seed"])
    depth = int(config["depth"])
    keyword_limit = int(config.get("keyword_limit", DEFAULT_KEYWORD_LIMIT))
    page_similarity_scores = _load_run_page_similarity_scores(run_payload)

    catalog: dict[str, object] = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)

    raw_responses = scan_raw_responses(run_dir)
    raw_responses = raw_responses.unique(
        subset=["response_id"],
        keep="first",
        maintain_order=True,
    )
    validate_raw_response_bodies(raw_responses)
    curated_lazyframes = build_curated_lazyframes_from_raw_responses(
        raw_responses,
        run_id=run_id,
        seed=seed,
        depth=depth,
        keyword_limit=keyword_limit,
        page_similarity_scores=page_similarity_scores,
    )
    for name, frame in curated_lazyframes.items():
        dataset_catalog[name] = write_curated_lazyframe_dataset(
            run_dir,
            name=name,
            frame=frame,
            schema=CURATED_SCHEMAS[name],
        )

    run_payload["catalog"] = catalog
    run_json_path.write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return catalog


def validate_raw_response_bodies(raw_responses: pl.LazyFrame) -> None:
    """Fail fast on any stored raw response schema drift before curated writes."""

    for record in raw_responses.select(
        ["endpoint", "request_metadata_json", "response_body_bytes"]
    ).collect(
        engine="streaming"
    ).to_dicts():
        endpoint = str(record["endpoint"])
        metadata_raw = record.get("request_metadata_json")
        metadata: dict[str, object] = {}
        if metadata_raw is not None:
            metadata = json.loads(str(metadata_raw))
        variant = (
            _backlinks_record_variant(endpoint, metadata)
            if endpoint in BACKLINKS_RAW_ENDPOINTS
            else None
        )
        validate_endpoint = _backlinks_validation_endpoint(endpoint, variant=variant)
        if validate_endpoint not in DATAFORSEO_RESPONSE_SCHEMAS:
            continue
        if _backlinks_record_skips_summary_schema_validation(record, endpoint=endpoint):
            continue
        _validated_response_body(record, endpoint=validate_endpoint)


def load_raw_response_rows(run_dir: Path) -> list[dict[str, object]]:
    rows = scan_raw_responses(run_dir).collect().to_dicts()
    rows.sort(
        key=lambda row: (
            str(row["endpoint"]),
            str(row.get("target_keyword") or ""),
            str(row["response_id"]),
        )
    )
    return rows


def build_curated_lazyframes(
    datasets: Mapping[str, list[dict[str, object]]],
) -> dict[str, pl.LazyFrame]:
    lazyframes: dict[str, pl.LazyFrame] = {}
    for name, rows in datasets.items():
        frame = pl.DataFrame(rows).lazy()
        if rows:
            frame = validate_frame_contract(
                frame,
                required_columns=rows[0].keys(),
            )
        lazyframes[name] = frame
    return lazyframes


def build_curated_lazyframes_from_raw_responses(
    raw_responses: pl.LazyFrame,
    *,
    run_id: str,
    seed: str,
    depth: int,
    keyword_limit: int,
    page_similarity_scores: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> dict[str, pl.LazyFrame]:
    keyword_responses = raw_responses.filter(
        pl.col("endpoint") == "keyword_expansion"
    ).select(["response_id", "response_body_bytes"])
    serp_responses = raw_responses.filter(pl.col("endpoint") == "serp").select(
        ["run_id", "response_id", "target_keyword", "response_body_bytes"]
    )
    backlink_responses = raw_responses.filter(
        pl.col("endpoint").is_in(sorted(BACKLINKS_RAW_ENDPOINTS))
    ).select(
        [
            "run_id",
            "response_id",
            "target_keyword",
            "endpoint",
            "request_metadata_json",
            "response_body_bytes",
        ]
    )
    page_responses = raw_responses.filter(pl.col("endpoint") == "page_text").select(
        ["run_id", "response_id", "target_keyword", "response_body_bytes"]
    )
    entity_responses = raw_responses.filter(
        pl.col("endpoint") == TEXTRAZOR_ENDPOINTS["entities"].raw_response_endpoint
    ).select(["run_id", "response_id", "target_keyword", "response_body_bytes"])
    onpage_responses = raw_responses.filter(
        pl.col("endpoint") == ONPAGE_INSTANT_PAGES_ENDPOINT
    ).select(
        [
            "run_id",
            "response_id",
            "target_keyword",
            "timestamp",
            "request_metadata_json",
            "response_body_bytes",
        ]
    )

    keywords = keyword_responses.map_batches(
        lambda frame: build_keywords_frame(
            frame,
            run_id=run_id,
            seed=seed,
            keyword_limit=keyword_limit,
        ),
        schema=CURATED_VALIDATION_RULES["keywords"]["expected_schema"],
    )
    serp_items = serp_responses.map_batches(
        lambda frame: build_serp_items_frame(frame, run_id=run_id, depth=depth),
        schema=CURATED_VALIDATION_RULES["serp_items"]["expected_schema"],
    )
    backlinks = backlink_responses.map_batches(
        lambda frame: build_backlinks_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["backlinks"]["expected_schema"],
    )
    onpage_signals = onpage_responses.map_batches(
        lambda frame: build_onpage_signals_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["onpage_signals"]["expected_schema"],
    )
    pages_and_passages = page_responses.map_batches(
        lambda frame: build_pages_and_passages_frame(frame, run_id=run_id),
        schema=CURATED_PAGE_AND_PASSAGE_SCHEMA,
    )
    page_content_fields = page_responses.map_batches(
        lambda frame: build_page_content_fields_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["page_content_fields"]["expected_schema"],
    )
    page_html = page_responses.map_batches(
        lambda frame: build_page_html_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["page_html"]["expected_schema"],
    )
    pages = pages_and_passages.filter(pl.col("passage_id").is_null()).select(
        [
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "title",
            "text",
            "schema_version",
        ]
    )
    passages = pages_and_passages.select(
        [
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "passage_id",
            "source",
            "text",
            "word_count",
            "schema_version",
        ]
    ).filter(pl.col("passage_id").is_not_null())
    page_content_field_rows = page_content_fields
    entities = entity_responses.map_batches(
        lambda frame: build_entities_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["entities"]["expected_schema"],
    )
    textrazor_page_metrics = entity_responses.map_batches(
        lambda frame: build_textrazor_page_metrics_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["textrazor_page_metrics_curated"]["expected_schema"],
    )
    similarity_scores = pages.group_by("target_keyword").map_groups(
        lambda frame: build_similarity_scores_frame(
            frame,
            run_id=run_id,
            page_similarity_scores=page_similarity_scores.get(
                str(frame.get_column("target_keyword")[0]),
                {},
            ),
        ),
        schema=CURATED_VALIDATION_RULES["similarity_scores"]["expected_schema"],
    )

    return {
        "keywords": keywords,
        "serp_items": serp_items,
        "backlinks": backlinks,
        "onpage_signals": onpage_signals,
        "pages": pages,
        "page_html": page_html,
        "page_content_fields": page_content_field_rows,
        "passages": passages,
        "entities": entities,
        "textrazor_page_metrics_curated": textrazor_page_metrics,
        "similarity_scores": similarity_scores,
    }


def build_keywords_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
    seed: str,
    keyword_limit: int = DEFAULT_KEYWORD_LIMIT,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        body = _validated_response_body(record, endpoint="keyword_expansion")
        for order, keyword in enumerate(
            normalize_keyword_expansion(body, seed=seed, limit=keyword_limit),
            start=1,
        ):
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": stable_id(keyword),
                    "target_keyword": keyword,
                    "source_seed": seed,
                    "source_response_id": response_id,
                    "keyword_order": order,
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
    if not rows:
        return pl.DataFrame(
            schema=CURATED_VALIDATION_RULES["keywords"]["expected_schema"]
        )
    return pl.DataFrame(rows, schema=CURATED_VALIDATION_RULES["keywords"]["expected_schema"])


def build_serp_items_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
    depth: int,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        body = _validated_response_body(record, endpoint="serp")
        target_keyword_id = stable_id(target_keyword)
        for result in normalize_serp_results(
            body,
            keyword=target_keyword,
            depth=depth,
        ):
            url = str(result["url"])
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": response_id,
                    "serp_item_id": stable_id(run_id, target_keyword, url, result["rank"]),
                    "canonical_url_hash": stable_id(url),
                    "url": url,
                    "serp_rank": int(result["rank"]),
                    "title": str(result["title"]),
                    "description": str(result["description"]),
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
        )
    return pl.DataFrame(rows)


def build_backlinks_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    grouped: dict[tuple[str, str], dict[str, object]] = {}

    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        endpoint = str(record["endpoint"])
        metadata = json.loads(str(record["request_metadata_json"]))
        variant = _backlinks_record_variant(endpoint, metadata)
        body = _backlinks_response_body(record, endpoint=endpoint, variant=variant)
        url = _backlinks_url_from_record(metadata, body)
        if url is None:
            continue
        group_key = (target_keyword, url)
        entry = grouped.setdefault(
            group_key,
            {
                "target_keyword": target_keyword,
                "url": url,
                "summary": None,
                "dofollow": None,
            },
        )
        payload = {
            "response_id": response_id,
            "body": body,
        }
        if variant == BACKLINKS_QUERY_DOFOLLOW:
            entry["dofollow"] = payload
        else:
            entry["summary"] = payload

    rows: list[dict[str, object]] = []
    for (target_keyword, url), entry in grouped.items():
        summary = entry.get("summary")
        dofollow = entry.get("dofollow")
        if not isinstance(summary, Mapping):
            continue
        target_keyword_id = stable_id(target_keyword)
        summary_body = summary["body"]
        assert isinstance(summary_body, Mapping)
        summary_result = _backlinks_result_or_successful_empty(
            summary_body,
            variant=BACKLINKS_QUERY_SUMMARY,
        )
        summary_response_id = str(summary["response_id"])
        dofollow_response_id: str | None = None
        dofollow_backlinks_count: int | None = None
        dofollow_referring_domains_count: int | None = None
        if isinstance(dofollow, Mapping):
            dofollow_body = dofollow["body"]
            assert isinstance(dofollow_body, Mapping)
            dofollow_result = _backlinks_result_or_successful_empty(
                dofollow_body,
                variant=BACKLINKS_QUERY_DOFOLLOW,
            )
            dofollow_response_id = str(dofollow["response_id"])
            dofollow_backlinks_count = _required_backlink_metric(
                dofollow_result,
                "backlinks",
            )
            dofollow_referring_domains_count = _optional_backlink_metric(
                dofollow_result,
                "referring_domains",
            )
        row = _summary_backlinks_row(
            run_id=run_id,
            target_keyword=target_keyword,
            target_keyword_id=target_keyword_id,
            url=url,
            summary_response_id=summary_response_id,
            dofollow_summary_response_id=dofollow_response_id,
            summary_result=summary_result,
            dofollow_backlinks_count=dofollow_backlinks_count,
            dofollow_referring_domains_count=dofollow_referring_domains_count,
            backlinks_metrics_complete=dofollow_response_id is not None
            and not _is_legacy_backlinks_live_result(summary_result),
        )
        rows.append(row)

    if not rows:
        return pl.DataFrame(schema=CURATED_VALIDATION_RULES["backlinks"]["expected_schema"])
    return pl.DataFrame(rows, schema=CURATED_VALIDATION_RULES["backlinks"]["expected_schema"])


def build_onpage_signals_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    records = sorted(
        frame.to_dicts(),
        key=_onpage_raw_record_recency_key,
        reverse=True,
    )
    seen_keys: set[tuple[str, str]] = set()
    rows: list[dict[str, object]] = []
    for record in records:
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        if not onpage_instant_pages_response_is_usable(body):
            continue
        metadata = json.loads(str(record.get("request_metadata_json", "{}")))
        url = _onpage_url_from_record(metadata, body)
        if url is None:
            continue
        target_keyword = str(record["target_keyword"])
        group_key = (target_keyword, url)
        if group_key in seen_keys:
            continue
        item = extract_onpage_instant_pages_item(body)
        if item is None:
            continue
        seen_keys.add(group_key)
        rows.append(
            _onpage_signals_row(
                run_id=run_id,
                target_keyword=target_keyword,
                response_id=str(record["response_id"]),
                url=url,
                item=item,
            )
        )

    if not rows:
        return pl.DataFrame(
            schema=CURATED_VALIDATION_RULES["onpage_signals"]["expected_schema"]
        )
    return pl.DataFrame(rows, schema=CURATED_VALIDATION_RULES["onpage_signals"]["expected_schema"])


def build_pages_and_passages_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    seen_page_ids: set[str] = set()
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        target_keyword_id = stable_id(target_keyword)
        body = _validated_response_body(record, endpoint="page_text")
        page = parsed_page_text_details(body)
        url = str(page.get("url", ""))
        title = str(page.get("title", ""))
        text = str(page.get("text", "")).strip()
        raw_html = str(page.get("raw_html", "")).strip()
        if not url or (not text and not raw_html):
            continue
        canonical_url_hash = stable_id(url)
        page_id = stable_id(run_id, target_keyword, url)
        if page_id in seen_page_ids:
            continue
        seen_page_ids.add(page_id)
        rows.append(
            {
                "run_id": run_id,
                "target_keyword_id": target_keyword_id,
                "target_keyword": target_keyword,
                "response_id": response_id,
                "page_id": page_id,
                "canonical_url_hash": canonical_url_hash,
                "url": url,
                "title": title,
                "text": text,
                "passage_id": None,
                "source": None,
                "word_count": None,
                "schema_version": CURATED_SCHEMA_VERSION,
            }
        )
        if text:
            for passage in normalize_page_text({"url": url, "text": text}):
                rows.append(
                    {
                        "run_id": run_id,
                        "target_keyword_id": target_keyword_id,
                        "target_keyword": target_keyword,
                        "response_id": response_id,
                        "page_id": page_id,
                        "canonical_url_hash": canonical_url_hash,
                        "url": url,
                        "passage_id": stable_id(page_id, passage["passage_id"]),
                        "source": passage["source"],
                        "text": passage["text"],
                        "word_count": int(passage["word_count"]),
                        "schema_version": CURATED_SCHEMA_VERSION,
                    }
                )
    if not rows:
        return pl.DataFrame(schema=CURATED_PAGE_AND_PASSAGE_SCHEMA)
    return pl.DataFrame(rows, schema=CURATED_PAGE_AND_PASSAGE_SCHEMA)


def build_page_content_fields_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        target_keyword_id = stable_id(target_keyword)
        body = _validated_response_body(record, endpoint="page_text")
        page = parsed_page_text(body)
        url = str(page.get("url", "")).strip()
        if not url:
            continue
        canonical_url_hash = stable_id(url)
        page_id = stable_id(run_id, target_keyword, url)
        field_records, _ = decode_content_parsing_items(body)
        for field_record in field_records:
            field_path = str(field_record["field_path"])
            ordinal = int(field_record["ordinal"])
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": response_id,
                    "page_id": page_id,
                    "canonical_url_hash": canonical_url_hash,
                    "url": url,
                    "field_row_id": stable_id(
                        page_id,
                        response_id,
                        field_path,
                        ordinal,
                    ),
                    "field_path": field_path,
                    "field_name": str(field_record["field_name"]),
                    "value_type": str(field_record["value_type"]),
                    "text": str(field_record["text"]),
                    "structured_value": (
                        None
                        if field_record["structured_value"] is None
                        else str(field_record["structured_value"])
                    ),
                    "ordinal": ordinal,
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
    if not rows:
        return pl.DataFrame(
            schema=CURATED_VALIDATION_RULES["page_content_fields"]["expected_schema"]
        )
    return pl.DataFrame(rows)


def build_page_html_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        target_keyword_id = stable_id(target_keyword)
        body = _validated_response_body(record, endpoint="page_text")
        page = parsed_page_text_details(body)
        url = str(page.get("url", "")).strip()
        raw_html = str(page.get("raw_html", "")).strip()
        if not url or not raw_html:
            continue
        canonical_url_hash = stable_id(url)
        page_id = stable_id(run_id, target_keyword, url)
        rows.append(
            {
                "run_id": run_id,
                "target_keyword_id": target_keyword_id,
                "target_keyword": target_keyword,
                "response_id": response_id,
                "page_id": page_id,
                "canonical_url_hash": canonical_url_hash,
                "url": url,
                "raw_html": raw_html,
                "schema_version": CURATED_SCHEMA_VERSION,
            }
        )
    if not rows:
        return pl.DataFrame(schema=CURATED_VALIDATION_RULES["page_html"]["expected_schema"])
    return pl.DataFrame(rows)


def build_entities_frame(frame: pl.DataFrame, *, run_id: str) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    seen_entity_row_ids: set[str] = set()
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        target_keyword_id = stable_id(target_keyword)
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        url = str(body.get("url", ""))
        canonical_url_hash = stable_id(url)
        for entity in normalize_entities(body, url=url):
            entity_row_id = stable_id(
                run_id,
                target_keyword,
                url,
                entity["entity_id"],
                entity["matched_text"],
            )
            if entity_row_id in seen_entity_row_ids:
                continue
            seen_entity_row_ids.add(entity_row_id)
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": response_id,
                    "canonical_url_hash": canonical_url_hash,
                    "url": url,
                    "entity_row_id": entity_row_id,
                    "entity_id": entity["entity_id"],
                    "matched_text": entity["matched_text"],
                    "confidence": float(entity["confidence"]),
                    "relevance": float(entity["relevance"]),
                    "types": list(entity["types"]),
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
    if not rows:
        return pl.DataFrame(
            schema=CURATED_VALIDATION_RULES["entities"]["expected_schema"]
        )
    return pl.DataFrame(rows)


def build_textrazor_page_metrics_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        target_keyword_id = stable_id(target_keyword)
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        url = str(body.get("url", "")).strip()
        if not url:
            continue
        metrics = normalize_page_metrics(body, url=url)
        rows.append(
            {
                "run_id": run_id,
                "target_keyword_id": target_keyword_id,
                "target_keyword": target_keyword,
                "response_id": response_id,
                "canonical_url_hash": stable_id(url),
                "url": url,
                "page_metrics_row_id": stable_id(run_id, target_keyword, url),
                **metrics,
                "schema_version": CURATED_SCHEMA_VERSION,
            }
        )
    if not rows:
        return pl.DataFrame(
            schema=CURATED_VALIDATION_RULES["textrazor_page_metrics_curated"]["expected_schema"]
        )
    return pl.DataFrame(
        rows,
        schema=CURATED_VALIDATION_RULES["textrazor_page_metrics_curated"]["expected_schema"],
    )


def build_similarity_scores_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
    page_similarity_scores: Mapping[str, Mapping[str, object]] | None = None,
) -> pl.DataFrame:
    rows = frame.to_dicts()
    if not rows:
        return pl.DataFrame(
            schema=CURATED_VALIDATION_RULES["similarity_scores"]["expected_schema"]
        )
    if page_similarity_scores is None:
        raise ValueError("page_similarity_scores are required to normalize similarity scores")
    target_keyword = str(rows[0]["target_keyword"])
    target_keyword_id = stable_id(target_keyword)
    similarity_rows: list[dict[str, object]] = []
    for row in rows:
        url = str(row["url"])
        page_score = page_similarity_scores.get(url)
        if page_score is None:
            raise ValueError(f"page similarity score missing for normalized url {url!r}")
        similarity_rows.append(
            {
                "run_id": run_id,
                "target_keyword_id": target_keyword_id,
                "target_keyword": target_keyword,
                "response_id": str(row["response_id"]),
                "canonical_url_hash": str(row["canonical_url_hash"]),
                "url": url,
                "score_row_id": stable_id(run_id, target_keyword, url),
                "bge_raw_score": float(page_score["bge"]["raw_score"]),
                "bge_normalized_score": float(page_score["bge"]["normalized_score"]),
                "gemini_doc_retrieval_raw_score": float(
                    page_score["gemini_doc_retrieval"]["raw_score"]
                ),
                "gemini_doc_retrieval_normalized_score": float(
                    page_score["gemini_doc_retrieval"]["normalized_score"]
                ),
                "gemini_semantic_similarity_raw_score": float(
                    page_score["gemini_semantic_similarity"]["raw_score"]
                ),
                "gemini_semantic_similarity_normalized_score": float(
                    page_score["gemini_semantic_similarity"]["normalized_score"]
                ),
                "schema_version": CURATED_SCHEMA_VERSION,
            }
        )
    return pl.DataFrame(similarity_rows)


def _load_run_page_similarity_scores(
    run_payload: Mapping[str, object],
) -> dict[str, dict[str, dict[str, object]]]:
    page_similarity = run_payload.get("page_similarity")
    if page_similarity is None:
        raise ValueError("run.json is missing page_similarity")
    if not isinstance(page_similarity, list):
        raise ValueError("run.json page_similarity must be a list")

    scores_by_keyword: dict[str, dict[str, dict[str, object]]] = {}
    for score in page_similarity:
        if not isinstance(score, Mapping):
            continue
        target_keyword = str(score["target_keyword"])
        url = str(score["url"])
        page_score = score["page_similarity"]
        if not isinstance(page_score, Mapping):
            raise ValueError("run.json page_similarity entries must contain scores")
        scores_by_keyword.setdefault(target_keyword, {})[url] = dict(page_score)
    return scores_by_keyword


def _backlinks_validation_endpoint(
    endpoint: str,
    *,
    variant: str | None = None,
) -> str:
    if endpoint == BACKLINKS_DOFOLLOW_ENDPOINT or variant == BACKLINKS_QUERY_DOFOLLOW:
        return BACKLINKS_DOFOLLOW_ENDPOINT
    if endpoint in {BACKLINKS_LEGACY_ENDPOINT, BACKLINKS_SUMMARY_ENDPOINT}:
        return BACKLINKS_SUMMARY_ENDPOINT
    return endpoint


def _backlinks_record_variant(endpoint: str, metadata: Mapping[str, object]) -> str:
    variant = metadata.get("variant")
    if isinstance(variant, str) and variant.strip():
        return variant.strip()
    backlinks_query = metadata.get("backlinks_query")
    if isinstance(backlinks_query, str) and backlinks_query.strip():
        return backlinks_query.strip()
    if endpoint == BACKLINKS_DOFOLLOW_ENDPOINT:
        return BACKLINKS_QUERY_DOFOLLOW
    return BACKLINKS_QUERY_SUMMARY


def _backlinks_record_is_legacy_live_shape(record: Mapping[str, object]) -> bool:
    try:
        raw_body = record["response_body_bytes"]
        body_bytes = (
            raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode()
        )
        body = json.loads(body_bytes)
        if not isinstance(body, Mapping):
            return False
        result = _single_backlinks_result(body)
    except (ValueError, json.JSONDecodeError, TypeError, KeyError):
        return False
    return _is_legacy_backlinks_live_result(result)


def _backlinks_record_skips_summary_schema_validation(
    record: Mapping[str, object],
    *,
    endpoint: str,
) -> bool:
    if endpoint == BACKLINKS_LEGACY_ENDPOINT and not _backlinks_summary_has_aggregates(
        record
    ):
        return True
    return endpoint in BACKLINKS_RAW_ENDPOINTS and _backlinks_record_is_legacy_live_shape(
        record
    )


def _backlinks_summary_has_aggregates(record: Mapping[str, object]) -> bool:
    try:
        raw_body = record["response_body_bytes"]
        body_bytes = (
            raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode()
        )
        body = json.loads(body_bytes)
        if not isinstance(body, Mapping):
            return False
        result = _single_backlinks_result(body)
    except (ValueError, json.JSONDecodeError, TypeError, KeyError):
        return False
    return "backlinks" in result and "referring_domains" in result


def _is_legacy_backlinks_live_result(result: Mapping[str, object]) -> bool:
    return "backlinks" not in result and (
        "total_count" in result or "items_count" in result
    )


def _legacy_backlinks_count(result: Mapping[str, object]) -> int:
    for key in ("total_count", "items_count"):
        if key in result:
            value = result[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"legacy backlinks aggregate field {key!r} must be numeric"
                )
            return int(value)
    raise ValueError("legacy backlinks response is missing total_count/items_count")


def _backlinks_url_from_record(
    metadata: Mapping[str, object],
    body: Mapping[str, object],
) -> str | None:
    url = metadata.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    response_url = extract_response_url(body)
    if isinstance(response_url, str) and response_url.strip():
        return response_url.strip()
    return None


def _onpage_url_from_record(
    metadata: Mapping[str, object],
    body: Mapping[str, object],
) -> str | None:
    return _backlinks_url_from_record(metadata, body)


def _onpage_raw_record_recency_key(record: Mapping[str, object]) -> tuple[str, str]:
    timestamp = record.get("timestamp")
    normalized_timestamp = str(timestamp) if timestamp is not None else ""
    return (normalized_timestamp, str(record.get("response_id", "")))


def _optional_mapping_bool(mapping: object, key: str) -> bool | None:
    if not isinstance(mapping, Mapping):
        return None
    value = mapping.get(key)
    return value if isinstance(value, bool) else None


def _optional_mapping_number(mapping: object, key: str) -> float | None:
    if not isinstance(mapping, Mapping):
        return None
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _optional_mapping_int(mapping: object, key: str) -> int | None:
    number = _optional_mapping_number(mapping, key)
    if number is None:
        return None
    return int(number)


def _derive_has_valid_structured_data(item: Mapping[str, object]) -> bool | None:
    has_micromarkup = item.get("has_micromarkup")
    has_errors = item.get("has_micromarkup_errors")
    if has_micromarkup is None and has_errors is None:
        return None
    if has_micromarkup is True:
        return has_errors is False
    if has_micromarkup is False:
        return False
    return None


def _micromarkup_summary_counts(
    item: Mapping[str, object],
) -> tuple[int | None, int | None, int | None]:
    micromarkup = item.get("micromarkup")
    if not isinstance(micromarkup, Mapping):
        return None, None, None
    return (
        _optional_mapping_int(micromarkup, "items_count"),
        _optional_mapping_int(micromarkup, "errors_count"),
        _optional_mapping_int(micromarkup, "warnings_count"),
    )


def _onpage_signals_row(
    *,
    run_id: str,
    target_keyword: str,
    response_id: str,
    url: str,
    item: Mapping[str, object],
) -> dict[str, object]:
    target_keyword_id = stable_id(target_keyword)
    checks = item.get("checks")
    content = item.get("content")
    page_timing = item.get("page_timing")
    score = item.get("onpage_score")
    assert isinstance(score, (int, float))
    cumulative_layout_shift = _optional_mapping_number(
        page_timing,
        "cumulative_layout_shift",
    )
    if cumulative_layout_shift is None:
        cumulative_layout_shift = _optional_mapping_number(item, "cumulative_layout_shift")
    items_count, errors_count, warnings_count = _micromarkup_summary_counts(item)
    row: dict[str, object] = {
        "run_id": run_id,
        "target_keyword_id": target_keyword_id,
        "target_keyword": target_keyword,
        "response_id": response_id,
        "onpage_signal_id": stable_id(run_id, target_keyword, url),
        "canonical_url_hash": stable_id(url),
        "url": url,
        "onpage_score": float(score),
        "plain_text_word_count": _optional_mapping_number(content, "plain_text_word_count"),
        "plain_text_rate": _optional_mapping_number(content, "plain_text_rate"),
        "flesch_kincaid_readability_index": _optional_mapping_number(
            content,
            "flesch_kincaid_readability_index",
        ),
        "coleman_liau_readability_index": _optional_mapping_number(
            content,
            "coleman_liau_readability_index",
        ),
        "smog_readability_index": _optional_mapping_number(content, "smog_readability_index"),
        "dale_chall_readability_index": _optional_mapping_number(
            content,
            "dale_chall_readability_index",
        ),
        "time_to_first_byte_ms": _optional_mapping_int(page_timing, "waiting_time"),
        "largest_contentful_paint_ms": _optional_mapping_number(
            page_timing,
            "largest_contentful_paint",
        ),
        "cumulative_layout_shift": cumulative_layout_shift,
        "total_transfer_size": _optional_mapping_int(item, "total_transfer_size"),
        "micromarkup_items_count": items_count,
        "micromarkup_errors_count": errors_count,
        "micromarkup_warnings_count": warnings_count,
        "has_valid_structured_data": _derive_has_valid_structured_data(item),
        "schema_version": CURATED_SCHEMA_VERSION,
    }
    for field in ONPAGE_CURATED_CHECK_FIELDS:
        row[field] = _optional_mapping_bool(checks, field)
    return row


def _single_backlinks_result(body: Mapping[str, object]) -> Mapping[str, object]:
    tasks = body.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("backlinks response is missing tasks")
    task = tasks[0]
    if not isinstance(task, Mapping):
        raise ValueError("backlinks response task must be an object")
    results = task.get("result", [])
    if not isinstance(results, list) or not results:
        raise ValueError("backlinks response is missing result aggregates")
    result = results[0]
    if not isinstance(result, Mapping):
        raise ValueError("backlinks response result must be an object")
    return result


def _empty_backlinks_result_for_variant(variant: str) -> dict[str, int]:
    if variant == BACKLINKS_QUERY_DOFOLLOW:
        return {"backlinks": 0}
    return {
        "backlinks": 0,
        "referring_domains": 0,
    }


def _backlinks_result_or_successful_empty(
    body: Mapping[str, object],
    *,
    variant: str,
) -> Mapping[str, object]:
    if backlinks_response_is_successful_empty(body):
        return _empty_backlinks_result_for_variant(variant)
    return _single_backlinks_result(body)


def _summary_backlinks_row(
    *,
    run_id: str,
    target_keyword: str,
    target_keyword_id: str,
    url: str,
    summary_response_id: str,
    dofollow_summary_response_id: str | None,
    summary_result: Mapping[str, object],
    dofollow_backlinks_count: int | None,
    dofollow_referring_domains_count: int | None,
    backlinks_metrics_complete: bool,
) -> dict[str, object]:
    info = summary_result.get("info")
    target_spam_score = None
    if isinstance(info, Mapping):
        target_spam_score = _optional_backlink_metric(info, "target_spam_score")

    if _is_legacy_backlinks_live_result(summary_result):
        return {
            "run_id": run_id,
            "target_keyword_id": target_keyword_id,
            "target_keyword": target_keyword,
            "response_id": summary_response_id,
            "summary_response_id": summary_response_id,
            "dofollow_summary_response_id": dofollow_summary_response_id,
            "backlink_id": stable_id(run_id, target_keyword, url),
            "canonical_url_hash": stable_id(url),
            "url": url,
            "backlinks_count": _legacy_backlinks_count(summary_result),
            "referring_domains_count": None,
            "dofollow_backlinks_count": None,
            "dofollow_referring_domains_count": None,
            "rank": None,
            "backlinks_spam_score": None,
            "target_spam_score": target_spam_score,
            "new_backlinks": None,
            "lost_backlinks": None,
            "new_referring_domains": None,
            "lost_referring_domains": None,
            "referring_pages": None,
            "referring_main_domains": None,
            "referring_ips": None,
            "referring_subnets": None,
            "broken_backlinks": None,
            "broken_pages": None,
            "referring_domains_nofollow": None,
            "crawled_pages": None,
            "internal_links_count": None,
            "external_links_count": None,
            "first_seen": None,
            "lost_date": None,
            "referring_links_types_json": None,
            "referring_links_tld_json": None,
            "referring_links_platform_types_json": None,
            "referring_links_semantic_locations_json": None,
            "referring_links_attributes_json": None,
            "referring_links_countries_json": None,
            "backlinks_metrics_complete": False,
            "schema_version": CURATED_SCHEMA_VERSION,
        }

    row: dict[str, object] = {
        "run_id": run_id,
        "target_keyword_id": target_keyword_id,
        "target_keyword": target_keyword,
        "response_id": summary_response_id,
        "summary_response_id": summary_response_id,
        "dofollow_summary_response_id": dofollow_summary_response_id,
        "backlink_id": stable_id(run_id, target_keyword, url),
        "canonical_url_hash": stable_id(url),
        "url": url,
        "backlinks_count": _required_backlink_metric(summary_result, "backlinks"),
        "referring_domains_count": _required_backlink_metric(
            summary_result,
            "referring_domains",
        ),
        "dofollow_backlinks_count": dofollow_backlinks_count,
        "dofollow_referring_domains_count": dofollow_referring_domains_count,
        "rank": _optional_backlink_metric(summary_result, "rank"),
        "backlinks_spam_score": _optional_backlink_metric(
            summary_result,
            "backlinks_spam_score",
        ),
        "target_spam_score": target_spam_score,
        "new_backlinks": _optional_backlink_metric(summary_result, "new_backlinks"),
        "lost_backlinks": _optional_backlink_metric(summary_result, "lost_backlinks"),
        "new_referring_domains": _optional_backlink_metric(
            summary_result,
            "new_referring_domains",
        ),
        "lost_referring_domains": _optional_backlink_metric(
            summary_result,
            "lost_referring_domains",
        ),
        "referring_pages": _optional_backlink_metric(summary_result, "referring_pages"),
        "referring_main_domains": _optional_backlink_metric(
            summary_result,
            "referring_main_domains",
        ),
        "referring_ips": _optional_backlink_metric(summary_result, "referring_ips"),
        "referring_subnets": _optional_backlink_metric(
            summary_result,
            "referring_subnets",
        ),
        "broken_backlinks": _optional_backlink_metric(summary_result, "broken_backlinks"),
        "broken_pages": _optional_backlink_metric(summary_result, "broken_pages"),
        "referring_domains_nofollow": _optional_backlink_metric(
            summary_result,
            "referring_domains_nofollow",
        ),
        "crawled_pages": _optional_backlink_metric(summary_result, "crawled_pages"),
        "internal_links_count": _optional_backlink_metric(
            summary_result,
            "internal_links_count",
        ),
        "external_links_count": _optional_backlink_metric(
            summary_result,
            "external_links_count",
        ),
        "first_seen": _optional_backlink_text(summary_result, "first_seen"),
        "lost_date": _optional_backlink_text(summary_result, "lost_date"),
        "backlinks_metrics_complete": backlinks_metrics_complete,
        "schema_version": CURATED_SCHEMA_VERSION,
    }
    for source_key, target_key in BACKLINKS_DISTRIBUTION_JSON_COLUMNS.items():
        row[target_key] = _serialize_backlinks_distribution(
            summary_result.get(source_key),
        )
    return row


def _serialize_backlinks_distribution(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("backlinks distribution field must be an object")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _optional_backlink_text(result: Mapping[str, object], key: str) -> str | None:
    value = result.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)

def _required_backlink_metric(item: Mapping[str, object], key: str) -> int:
    if key not in item:
        raise ValueError(f"backlinks aggregate is missing required field {key!r}")
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"backlinks aggregate field {key!r} must be numeric, got {type(value).__name__}"
        )
    return int(value)


def _optional_backlink_metric(item: Mapping[str, object], key: str) -> int | None:
    if key not in item:
        return None
    value = item.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"backlinks aggregate field {key!r} must be numeric, got {type(value).__name__}"
        )
    return int(value)


def _validated_response_body(
    record: Mapping[str, object],
    *,
    endpoint: str,
) -> dict[str, object]:
    body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
    validate_dataforseo_response(endpoint, body)
    return body


def _backlinks_response_body(
    record: Mapping[str, object],
    *,
    endpoint: str,
    variant: str,
) -> dict[str, object]:
    if _backlinks_record_skips_summary_schema_validation(record, endpoint=endpoint):
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("backlinks response body must be an object")
        return body
    validation_endpoint = _backlinks_validation_endpoint(endpoint, variant=variant)
    return _validated_response_body(record, endpoint=validation_endpoint)


def write_curated_lazyframe_dataset(
    run_dir: Path,
    *,
    name: str,
    frame: pl.LazyFrame,
    schema: pa.Schema,
) -> dict[str, object]:
    validation = CURATED_VALIDATION_RULES[name]
    try:
        frame = validate_frame_contract(
            frame,
            required_columns=schema.names,
            expected_schema=validation.get("expected_schema"),
            unique_columns=validation.get("unique_columns", ()),
            non_null_columns=validation.get("non_null_columns", ()),
            bounded_columns=validation.get("bounded_columns"),
        )
        materialized_frame = frame.collect(engine="streaming")
        validate_materialized_frame_contract(
            materialized_frame,
            unique_columns=validation.get("unique_columns", ()),
            non_null_columns=validation.get("non_null_columns", ()),
            bounded_columns=validation.get("bounded_columns"),
        )
    except ValueError as error:
        raise ValueError(f"{name} validation failed: {error}") from error
    rows = materialized_frame.to_dicts()
    return write_curated_dataset(run_dir, name=name, rows=rows, schema=schema)


def write_curated_dataset(
    run_dir: Path,
    *,
    name: str,
    rows: list[dict[str, object]],
    schema: pa.Schema,
) -> dict[str, object]:
    dataset_dir = run_dir / "parquet" / name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    file_path = dataset_dir / "part-0.parquet"
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("target_keyword_id") or ""),
            str(row.get("canonical_url_hash") or ""),
            str(row.get("serp_rank") or row.get("keyword_order") or ""),
            str(row.get("response_id") or row.get("source_response_id") or ""),
            str(row.get("page_id") or ""),
            str(row.get("field_path") or ""),
            str(row.get("ordinal")) if row.get("ordinal") is not None else "",
        ),
    )
    pl.from_arrow(pa.Table.from_pylist(sorted_rows, schema=schema)).lazy().sink_parquet(
        file_path,
        compression="zstd",
        statistics=True,
    )
    return {
        "schema_version": CURATED_SCHEMA_VERSION,
        "row_count": len(rows),
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
