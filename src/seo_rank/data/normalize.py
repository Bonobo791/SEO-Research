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
    DATAFORSEO_RESPONSE_SCHEMAS,
    DEFAULT_KEYWORD_LIMIT,
    decode_content_parsing_items,
    normalize_keyword_expansion,
    normalize_serp_results,
    parsed_page_text,
    parsed_page_text_details,
    validate_dataforseo_response,
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
            "schema_version",
        ),
        "bounded_columns": {
            "textrazor_entity_confidence_score": (0, None),
            "textrazor_entity_relevance_score": (0, 1),
            "textrazor_topic_score": (0, 1),
            "textrazor_category_score": (0, 1),
            "textrazor_classifier_score": (0, 1),
            "textrazor_entailment_score": (0, 1),
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

    for record in raw_responses.select(["endpoint", "response_body_bytes"]).collect(
        engine="streaming"
    ).to_dicts():
        validate_endpoint = str(record["endpoint"])
        if validate_endpoint not in DATAFORSEO_RESPONSE_SCHEMAS:
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
    page_responses = raw_responses.filter(pl.col("endpoint") == "page_text").select(
        ["run_id", "response_id", "target_keyword", "response_body_bytes"]
    )
    entity_responses = raw_responses.filter(
        pl.col("endpoint") == TEXTRAZOR_ENDPOINTS["entities"].raw_response_endpoint
    ).select(["run_id", "response_id", "target_keyword", "response_body_bytes"])

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
    return pl.DataFrame(rows)


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


def _validated_response_body(
    record: Mapping[str, object],
    *,
    endpoint: str,
) -> dict[str, object]:
    body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
    validate_dataforseo_response(endpoint, body)
    return body


def write_curated_lazyframe_dataset(
    run_dir: Path,
    *,
    name: str,
    frame: pl.LazyFrame,
    schema: pa.Schema,
) -> dict[str, object]:
    validation = CURATED_VALIDATION_RULES[name]
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
