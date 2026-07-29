from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from seo_rank.cli import emit_keyword_analysis


def _analysis_mart_frame() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": "serp-1-1",
                "page_id": "page-1-1",
                "response_id": "page-resp-1-1",
                "canonical_url_hash": "url-1-1",
                "url": "https://example.com/1/1",
                "serp_rank": 1,
                "title": "title-1-1",
                "description": "description-1-1",
                "page_text_length": 123,
                "referring_domains_count": 123,
                "bge_raw_score": 0.9,
                "bge_normalized_score": 0.9,
                "bge_rank": 1,
                "bge_pct": 0.0,
                "bge_z": None,
                "gemini_doc_retrieval_raw_score": 0.8,
                "gemini_doc_retrieval_normalized_score": 0.8,
                "gemini_doc_retrieval_rank": 1,
                "gemini_doc_retrieval_pct": 0.0,
                "gemini_doc_retrieval_z": None,
                "gemini_semantic_similarity_raw_score": 0.7,
                "gemini_semantic_similarity_normalized_score": 0.7,
                "gemini_semantic_similarity_rank": 1,
                "gemini_semantic_similarity_pct": 0.0,
                "gemini_semantic_similarity_z": None,
                "schema_version": "analysis_mart.v2",
            }
        ]
    )


def _textrazor_page_metrics_frame() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "response_id": "page-resp-1-1",
                "canonical_url_hash": "url-1-1",
                "url": "https://example.com/1/1",
                "page_metrics_row_id": "metrics-1",
                "textrazor_entity_confidence_score": 4.0,
                "textrazor_entity_relevance_score": 3.5,
                "textrazor_topic_score": 3.0,
                "textrazor_category_score": 2.5,
                "textrazor_classifier_score": 2.0,
                "textrazor_entailment_score": 1.5,
                "textrazor_entailment_prior": 1.0,
                "textrazor_entailment_context": 0.5,
                "textrazor_word_count": 20,
                "textrazor_sense_score": 0.91,
                "textrazor_spelling_suggestion_count": 0,
                "textrazor_relation_count": 4,
                "textrazor_property_count": 3,
                "textrazor_noun_phrase_count": 2,
                "schema_version": "curated.v1",
            }
        ]
    )


def test_emit_keyword_analysis_merges_textrazor_metrics_next_to_similarity_columns(
    tmp_path: Path,
    capsys,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "textrazor_page_metrics").mkdir(parents=True)

    _analysis_mart_frame().write_parquet(run_dir / "parquet" / "analysis_mart" / "part-0.parquet")
    _textrazor_page_metrics_frame().write_parquet(
        run_dir / "parquet" / "textrazor_page_metrics" / "part-0.parquet"
    )

    emit_keyword_analysis(run_dir, "keyword 1")

    payload = json.loads(capsys.readouterr().out)
    row = payload[0]
    key_order = list(row)

    assert row["bge_normalized_score"] == 0.9
    assert row["textrazor_topic_score"] == 3.0
    assert row["page_metrics_row_id"] == "metrics-1"
    assert key_order.index("bge_normalized_score") < key_order.index("textrazor_topic_score")
    assert key_order.index("gemini_semantic_similarity_normalized_score") < key_order.index(
        "textrazor_relation_count"
    )


def test_emit_keyword_analysis_includes_rank_columns(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    _analysis_mart_frame().write_parquet(run_dir / "parquet" / "analysis_mart" / "part-0.parquet")

    emit_keyword_analysis(run_dir, "keyword 1")

    row = json.loads(capsys.readouterr().out)[0]
    assert row["bge_rank"] == 1
    assert row["bge_pct"] == 0.0
    assert row["bge_z"] is None
