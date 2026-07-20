from __future__ import annotations

import json

import numpy as np
import polars as pl
import pytest

import seo_rank.stats.textrazor_explainability as textrazor_module

from seo_rank.stats.textrazor_explainability import (
    CURATED_RANKING_SCORE_COLUMNS,
    SIMILARITY_RANKING_METRICS,
    TEXTRAZOR_RANKING_METRICS,
    fit_multivariate_ranking_model,
    summarize_ranking_explainability,
    summarize_similarity_ranking_explainability,
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
                    "referring_domains_count": 120 + (keyword_index * 3) + serp_rank,
                    "deprecated_html_tags": (keyword_index + serp_rank) % 3 == 0,
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                    "time_to_first_byte_ms": 100 + serp_rank,
                    "site_scale": (keyword_index * 0.1) + (serp_rank * 0.01),
                    "authority_proxy": ((keyword_index * 5 + serp_rank * 13) % 11) * 0.01,
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


def test_fit_multivariate_ranking_model_skips_when_design_matrix_is_column_rank_deficient() -> None:
    # Mirrors the regression.py rank-deficiency case: df_resid (rank-based) is
    # positive, but nobs == raw exog column count, which previously reached
    # get_robustcov_results(cov_type="cluster") and raised ZeroDivisionError.
    panel = pl.DataFrame(
        {
            "target_keyword_id": ["k0", "k1", "k2", "k3", "k4", "k4", "k4"],
            "serp_rank": [1, 1, 1, 1, 1, 2, 3],
            "page_text_length": [100, 200, 300, 400, 500, 600, 600],
            "referring_domains_count": [100, 200, 300, 400, 500, 600, 600],
            "deprecated_html_tags": [False, False, True, False, True, False, True],
            "site_scale": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "authority_proxy": [0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
            "meta_keywords_to_content_consistency": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "bge_normalized_score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.6],
        }
    )

    fit = fit_multivariate_ranking_model(panel, score_columns=["bge_normalized_score"])

    assert fit is None or fit.get("status") == "skipped"


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
    assert "meta_keywords_to_content_consistency" not in multivariate["feature_model"]["formula"]
    assert "site_scale" in multivariate["feature_model"]["formula"]
    assert (
        multivariate["descriptive_fit_delta"]["adjusted_r_squared"] >= 0
    )

    json.dumps(summary)


def test_summarize_similarity_ranking_explainability_computes_univariate_and_multivariate() -> None:
    panel = _textrazor_panel_frame()
    summary = summarize_similarity_ranking_explainability(
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )

    assert summary["run_id"] == "run-1"
    assert summary["rank_depth"] == "top_20"
    assert len(summary["univariate"]) == len(SIMILARITY_RANKING_METRICS)

    computed = [entry for entry in summary["univariate"] if entry["status"] == "computed"]
    assert len(computed) == len(SIMILARITY_RANKING_METRICS)
    assert any(
        entry["descriptive_fit_delta"]["adjusted_r_squared"] > 0 for entry in computed
    )

    multivariate = summary["multivariate"]
    assert multivariate["status"] == "computed"
    assert multivariate["row_count"] == panel.height
    assert multivariate["keyword_count"] == 10
    assert len(multivariate["score_columns"]) == len(SIMILARITY_RANKING_METRICS)


def test_summarize_ranking_explainability_includes_similarity_and_textrazor() -> None:
    panel = _textrazor_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )

    assert summary["run_id"] == "run-1"
    assert summary["rank_depth"] == "top_20"
    assert len(summary["similarity"]["univariate"]) == len(SIMILARITY_RANKING_METRICS)
    assert len(summary["textrazor"]["univariate"]) == len(TEXTRAZOR_RANKING_METRICS)
    assert summary["similarity"]["multivariate"]["status"] == "computed"
    assert summary["textrazor"]["multivariate"]["status"] == "computed"

    combined = summary["multivariate"]
    assert combined["status"] == "computed"
    similarity_columns = {column for _, column in SIMILARITY_RANKING_METRICS}
    textrazor_columns = {column for _, column in TEXTRAZOR_RANKING_METRICS}
    assert similarity_columns.issubset(set(combined["score_columns"]))
    assert textrazor_columns.issubset(set(combined["score_columns"]))
    assert len(combined["score_columns"]) == len(SIMILARITY_RANKING_METRICS) + len(
        TEXTRAZOR_RANKING_METRICS
    )
    json.dumps(summary)


def test_summarize_ranking_explainability_includes_curated_multivariate() -> None:
    panel = _textrazor_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )

    curated = summary["multivariate_curated"]
    assert curated["status"] == "computed"
    assert curated["score_columns"] == list(CURATED_RANKING_SCORE_COLUMNS)
    assert curated["label"] == "relation_property_relevance_gemini_semantic"
    coefficients = curated["feature_model"]["coefficients"]
    assert set(coefficients) == set(CURATED_RANKING_SCORE_COLUMNS)


def test_summarize_ranking_explainability_combined_multivariate_renders() -> None:
    from analysis.textrazor_ranking_r2 import _render_multivariate_section

    panel = _textrazor_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )

    rendered = _render_multivariate_section(
        summary["multivariate"],
        title="Combined model (similarity + TextRazor metrics)",
    )
    assert "unavailable" not in rendered
    assert "skipped" not in rendered
    assert "baseline adjusted R²:" in rendered
    assert "bge_normalized_score" in rendered
    assert "textrazor_entity_confidence_score" in rendered


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


def test_fit_multivariate_ranking_model_skips_when_ols_svd_does_not_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomModel:
        def fit(self, *_args, **_kwargs):
            raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(textrazor_module.smf, "ols", lambda *_a, **_k: _BoomModel())

    fit = fit_multivariate_ranking_model(
        _textrazor_panel_frame(),
        score_columns=["textrazor_entity_confidence_score"],
    )

    assert fit is None or fit.get("status") == "skipped"
