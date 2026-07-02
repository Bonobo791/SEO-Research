import json
from pathlib import Path

import polars as pl

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.panel import load_analysis_panel


def _analysis_mart_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 10):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        for serp_rank in range(1, 3):
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "keyword_order": keyword_index,
                    "source_response_id": f"resp-{keyword_index}",
                    "serp_item_id": f"serp-{keyword_index}-{serp_rank}",
                    "page_id": f"page-{keyword_index}-{serp_rank}",
                    "response_id": f"page-resp-{keyword_index}-{serp_rank}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "url": f"https://example.com/{keyword_index}/{serp_rank}",
                    "serp_rank": serp_rank,
                    "title": f"title-{keyword_index}-{serp_rank}",
                    "description": f"description-{keyword_index}-{serp_rank}",
                    "page_text_length": 100 + serp_rank,
                    "bge_raw_score": 0.9 - (keyword_index * 0.01),
                    "bge_normalized_score": 0.9 - (keyword_index * 0.01),
                    "gemini_doc_retrieval_raw_score": 0.8,
                    "gemini_doc_retrieval_normalized_score": 0.8,
                    "gemini_semantic_similarity_raw_score": 0.7,
                    "gemini_semantic_similarity_normalized_score": 0.7,
                    "schema_version": "analysis_mart.v1",
                }
            )

    rows.append(
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-10",
            "target_keyword": "keyword 10",
            "keyword_order": 10,
            "source_response_id": "resp-10",
            "serp_item_id": "serp-10-1",
            "page_id": "page-10-1",
            "response_id": "page-resp-10-1",
            "canonical_url_hash": "url-10-1",
            "url": "https://example.com/10/1",
            "serp_rank": 1,
            "title": "title-10-1",
            "description": "description-10-1",
            "page_text_length": 101,
            "bge_raw_score": None,
            "bge_normalized_score": None,
            "gemini_doc_retrieval_raw_score": 0.8,
            "gemini_doc_retrieval_normalized_score": 0.8,
            "gemini_semantic_similarity_raw_score": 0.7,
            "gemini_semantic_similarity_normalized_score": 0.7,
            "schema_version": "analysis_mart.v1",
        }
    )
    rows.append(
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-10",
            "target_keyword": "keyword 10",
            "keyword_order": 10,
            "source_response_id": "resp-10",
            "serp_item_id": "serp-10-2",
            "page_id": "page-10-2",
            "response_id": "page-resp-10-2",
            "canonical_url_hash": "url-10-2",
            "url": "https://example.com/10/2",
            "serp_rank": 2,
            "title": "title-10-2",
            "description": "description-10-2",
            "page_text_length": 102,
            "bge_raw_score": 0.81,
            "bge_normalized_score": 0.81,
            "gemini_doc_retrieval_raw_score": 0.0,
            "gemini_doc_retrieval_normalized_score": 0.0,
            "gemini_semantic_similarity_raw_score": 0.7,
            "gemini_semantic_similarity_normalized_score": 0.7,
            "schema_version": "analysis_mart.v1",
        }
    )
    return pl.DataFrame(rows)


def test_load_analysis_panel_filters_top20_and_evaluates_guardrails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _analysis_mart_frame().lazy(),
    )

    result = load_analysis_panel(run_dir)

    assert result.hard_fail is True
    assert result.primary_backend == "bge"
    assert result.analysis_mart.height == 20
    assert result.panel.height == 19
    assert result.panel.filter(pl.col("bge_normalized_score").is_null()).height == 0
    assert result.guardrails == [
        {
            "name": "keywords_with_complete_primary_backend_scores",
            "status": "fail",
            "value": 9,
            "threshold": 10,
        },
        {
            "name": "non_null_score_rate_per_backend",
            "status": "pass",
            "value": {
                "bge": 0.95,
                "gemini_doc_retrieval": 1.0,
                "gemini_semantic_similarity": 1.0,
            },
            "threshold": 0.9,
        },
        {
            "name": "serp_rank_variance_within_keyword",
            "status": "pass",
            "value": 0.25,
            "threshold": 0,
        },
        {
            "name": "similarity_variance_within_keyword",
            "status": "warn",
            "value": {
                "bge": 0.0,
                "gemini_doc_retrieval": 0.0,
                "gemini_semantic_similarity": 0.0,
            },
            "threshold": 0,
        },
    ]
    assert result.limitations == {
        "observational_only": "Associations are observational, not causal.",
        "top_20_truncation": "Associations are limited to observed top-20 SERP rows per keyword.",
        "no_causal_claims": "Do not interpret coefficients as causal ranking factors.",
        "measurement_error_conservative": "Similarity scores are model outputs and may attenuate effects.",
    }


def test_run_phase5_stats_writes_guardrail_summary_and_minimal_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _analysis_mart_frame().lazy(),
    )

    result = run_phase5_stats(run_dir)

    summary_path = run_dir / "stats" / "stats_summary.json"
    report_path = run_dir / "stats" / "stats_report.md"

    assert summary_path.exists()
    assert report_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["hard_fail"] is True
    assert summary["guardrails"][0]["name"] == "keywords_with_complete_primary_backend_scores"
    assert summary["limitations"]["no_causal_claims"].startswith("Do not interpret")
    assert "Confirmatory inference skipped" in report_path.read_text(encoding="utf-8")
