from __future__ import annotations

import json

import polars as pl

from seo_rank.stats.textrazor_explainability import (
    TEXTRAZOR_RANKING_METRICS,
    summarize_textrazor_ranking_explainability,
)


def _textrazor_panel_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 5):
            signal = float(4 - serp_rank) + keyword_offset
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
                    "page_text_length": 120 + (keyword_index * 3) + serp_rank,
                    "bge_raw_score": signal,
                    "bge_normalized_score": signal,
                    "gemini_doc_retrieval_raw_score": signal - 0.1,
                    "gemini_doc_retrieval_normalized_score": signal - 0.1,
                    "gemini_semantic_similarity_raw_score": signal - 0.2,
                    "gemini_semantic_similarity_normalized_score": signal - 0.2,
                    "textrazor_entity_confidence_score": signal + 0.5,
                    "textrazor_entity_relevance_score": signal + 0.4,
                    "textrazor_entailment_score": signal + 0.05,
                    "textrazor_relation_count": int(serp_rank + 1),
                    "textrazor_property_count": int(serp_rank),
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def test_summarize_textrazor_ranking_explainability_computes_univariate_and_multivariate() -> None:
    panel = _textrazor_panel_frame()
    summary = summarize_textrazor_ranking_explainability(
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )

    assert summary["run_id"] == "run-1"
    assert summary["rank_depth"] == "top_20"
    assert summary["estimand"]["outcome"] == "-log(serp_rank)"
    assert len(summary["univariate"]) == len(TEXTRAZOR_RANKING_METRICS)

    computed = [entry for entry in summary["univariate"] if entry["status"] == "computed"]
    assert len(computed) == len(TEXTRAZOR_RANKING_METRICS)
    assert any(
        entry["descriptive_fit_delta"]["adjusted_r_squared"] > 0 for entry in computed
    )
    assert all(
        entry["feature_model"]["adjusted_r_squared"]
        >= entry["baseline_model"]["adjusted_r_squared"]
        for entry in computed
    )

    multivariate = summary["multivariate"]
    assert multivariate["status"] == "computed"
    assert multivariate["row_count"] == panel.height
    assert multivariate["keyword_count"] == 10
    assert (
        multivariate["descriptive_fit_delta"]["adjusted_r_squared"] >= 0
    )

    json.dumps(summary)


def test_summarize_textrazor_ranking_explainability_reports_metric_coverage() -> None:
    panel = _textrazor_panel_frame()
    summary = summarize_textrazor_ranking_explainability(
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )

    coverage = summary["panel"]["metric_coverage"]
    assert coverage["textrazor_entity_confidence_score"]["non_null"] == panel.height
    assert coverage["textrazor_relation_count"]["non_null"] == panel.height
