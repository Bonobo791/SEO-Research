from __future__ import annotations

import json

import polars as pl
import pytest

from seo_rank.stats.spec import load_analysis_spec
from seo_rank.stats.textrazor_explainability import (
    RANKING_IMPORTANCE_GROUP_ORDER,
    ranking_importance_factor_columns,
    summarize_ranking_relative_importance,
)


def _ranking_importance_panel_frame() -> pl.DataFrame:
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
                    "bge_raw_score": signal,
                    "bge_normalized_score": signal,
                    "gemini_doc_retrieval_raw_score": signal - 0.1,
                    "gemini_doc_retrieval_normalized_score": signal - 0.1,
                    "gemini_semantic_similarity_raw_score": signal - 0.2,
                    "gemini_semantic_similarity_normalized_score": signal - 0.2,
                    "textrazor_entity_confidence_score": signal + 0.5,
                    "textrazor_entity_relevance_score": signal + 0.4,
                    "textrazor_topic_score": signal + 0.3,
                    "textrazor_entailment_score": signal + 0.05,
                    "textrazor_relation_count": int(serp_rank + 1),
                    "textrazor_property_count": int(serp_rank),
                    "backlinks_count": 40 + keyword_index + serp_rank,
                    "dofollow_backlinks_count": 30 + keyword_index + serp_rank,
                    "onpage_score": 60.0 + signal * 10.0,
                    "plain_text_word_count": 500.0 + serp_rank * 10.0 + keyword_index,
                    "plain_text_rate": 0.02 + serp_rank * 0.001,
                    "flesch_kincaid_readability_index": 50.0 + signal,
                    "title_to_content_consistency": 0.2 + serp_rank * 0.05,
                    "largest_contentful_paint_ms": 2000.0 - serp_rank * 100.0,
                    "cumulative_layout_shift": 0.05 + serp_rank * 0.01,
                    "title_too_long": serp_rank == 1,
                    "is_https": serp_rank != 2,
                    "canonical": serp_rank != 1,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def test_ranking_importance_factor_columns_maps_registry_groups() -> None:
    spec = load_analysis_spec()
    groups = ranking_importance_factor_columns(spec)

    assert tuple(groups) == RANKING_IMPORTANCE_GROUP_ORDER
    assert "bge_normalized_score" in groups["similarity"]
    assert "textrazor_entity_confidence_score" in groups["textrazor"]
    assert "backlinks_count" in groups["backlinks"]
    assert "onpage_score" in groups["content"]
    assert "time_to_first_byte_ms" in groups["technical"]
    assert "title_too_long" in groups["technical"]


def test_summarize_ranking_relative_importance_computes_group_and_metric_rows() -> None:
    panel = _ranking_importance_panel_frame()
    spec = load_analysis_spec()
    summary = summarize_ranking_relative_importance(
        panel,
        spec=spec,
        cv_folds=3,
        bootstraps=30,
        random_state=0,
    )

    assert summary["status"] == "computed"
    assert summary["row_count"] == panel.height
    assert summary["keyword_count"] == 10
    assert summary["cv_folds"] == 3
    assert summary["bootstraps"] == 30
    assert len(summary["groups"]) == len(RANKING_IMPORTANCE_GROUP_ORDER)

    shapley_total = sum(group["shapley_share"] for group in summary["groups"])
    assert 0.99 <= shapley_total <= 1.01

    computed_partials = [
        group["full_model_partial_r2"]
        for group in summary["groups"]
        if group["full_model_partial_r2"] is not None
    ]
    assert computed_partials
    assert all(partial >= 0 for partial in computed_partials)

    similarity = summary["groups"][0]
    assert similarity["factor"] == "similarity"
    oos_deltas = [
        group["out_of_sample_delta_r2"]
        for group in summary["groups"]
        if group["out_of_sample_delta_r2"] is not None
    ]
    assert oos_deltas
    assert len(similarity["metrics"]) >= 3
    metric_partials = [
        metric["full_model_partial_r2"]
        for group in summary["groups"]
        for metric in group["metrics"]
        if metric["full_model_partial_r2"] is not None
    ]
    assert metric_partials
    assert all(partial >= 0 for partial in metric_partials)

    ci_groups = [
        group["clustered_ci"]
        for group in summary["groups"]
        if isinstance(group.get("clustered_ci"), dict)
        and group["clustered_ci"].get("point") is not None
    ]
    assert ci_groups
    assert all(
        ci["lower"] <= ci["point"] <= ci["upper"]
        for ci in ci_groups
    )
    json.dumps(summary)


def test_partial_r_squared_uses_standard_formula() -> None:
    from seo_rank.stats.textrazor_explainability import _partial_r_squared

    assert _partial_r_squared(0.8, 0.5) == (0.8 - 0.5) / (1.0 - 0.5)
    assert _partial_r_squared(0.5, 0.8) == (0.5 - 0.8) / (1.0 - 0.8)
    assert _partial_r_squared(0.9, 1.0) is None


def test_summarize_ranking_relative_importance_reports_ordinary_r_squared() -> None:
    panel = _ranking_importance_panel_frame()
    spec = load_analysis_spec()
    summary = summarize_ranking_relative_importance(
        panel,
        spec=spec,
        cv_folds=3,
        bootstraps=10,
        random_state=0,
    )

    assert summary["status"] == "computed"
    assert "full_model_r_squared" in summary
    assert "full_model_adjusted_r_squared" not in summary
    assert 0.0 <= summary["full_model_r_squared"] <= 1.0


def test_summarize_ranking_relative_importance_skips_sparse_columns_not_parquet() -> None:
    """Sparse predictors are dropped only for RI complete-case; dense groups still fit."""

    panel = _ranking_importance_panel_frame()
    # Inject a sparse content column that would wipe complete-case if kept.
    sparse = [None] * (panel.height - 1) + [0.5]
    panel = panel.with_columns(pl.Series("meta_keywords_to_content_consistency", sparse))
    # Also add a dense technical column that should survive.
    if "time_to_first_byte_ms" not in panel.columns:
        panel = panel.with_columns(
            (pl.col("serp_rank") * 10 + 100).alias("time_to_first_byte_ms")
        )

    # Ensure the sparse column is requested via registry (content group).
    spec = load_analysis_spec()
    groups = ranking_importance_factor_columns(spec)
    assert "meta_keywords_to_content_consistency" in groups["content"]

    summary = summarize_ranking_relative_importance(
        panel,
        spec=spec,
        cv_folds=3,
        bootstraps=10,
        random_state=0,
        min_complete_rows=20,
    )

    assert summary["status"] == "computed"
    assert summary["row_count"] >= 20
    excluded = {entry["column"] for entry in summary["excluded_predictors"]}
    assert "meta_keywords_to_content_consistency" in excluded
    assert all(entry["reason"] == "sparse_complete_case" for entry in summary["excluded_predictors"])
    assert "meta_keywords_to_content_consistency" not in summary["predictor_columns"]
    # Dense similarity predictors remain.
    assert "bge_normalized_score" in summary["predictor_columns"]


def test_keyword_grouped_cv_stores_delta_r2_not_partial_r2(monkeypatch) -> None:
    """OOS column must be R²_full - R²_reduced, not the partial-R² transform."""

    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    calls: list[tuple[str, ...]] = []

    def fake_eval(train, test, score_columns, *, control_columns):
        key = tuple(score_columns)
        calls.append(key)
        # Full model includes "a"; reduced without group drops "a".
        if "a" in score_columns:
            return 0.8
        return 0.5

    monkeypatch.setattr(module, "_eval_oos_r_squared", fake_eval)

    model_data = pd.DataFrame(
        {
            "target_keyword_id": ["k1", "k1", "k2", "k2", "k3", "k3", "k4", "k4"],
            "serp_rank": [1, 2, 1, 2, 1, 2, 1, 2],
            "a": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
            "b": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
            "site_scale": [0.1] * 8,
        }
    )
    factor_columns = {
        "similarity": ("a",),
        "textrazor": ("b",),
        "backlinks": (),
        "technical": (),
        "content": (),
    }
    rng = module.np.random.default_rng(0)
    deltas = module._keyword_grouped_cv_delta_r2(
        model_data,
        factor_columns,
        selected_columns=("a", "b"),
        control_columns=("site_scale",),
        cv_folds=2,
        rng=rng,
    )

    # partial R² would be (0.8-0.5)/(1-0.5)=0.6; delta R² is 0.3
    assert deltas["similarity"] == pytest.approx(0.3)


def test_parse_args_rejects_nonpositive_resampling_counts(monkeypatch) -> None:
    from analysis.textrazor_ranking_r2 import _parse_args

    monkeypatch.setattr(
        "sys.argv",
        ["textrazor_ranking_r2.py", "--run", "runs/example", "--cv-folds", "0"],
    )
    with pytest.raises(SystemExit):
        _parse_args()

    monkeypatch.setattr(
        "sys.argv",
        ["textrazor_ranking_r2.py", "--run", "runs/example", "--cv-folds", "1"],
    )
    with pytest.raises(SystemExit):
        _parse_args()

    monkeypatch.setattr(
        "sys.argv",
        ["textrazor_ranking_r2.py", "--run", "runs/example", "--bootstraps", "0"],
    )
    with pytest.raises(SystemExit):
        _parse_args()

    monkeypatch.setattr(
        "sys.argv",
        ["textrazor_ranking_r2.py", "--run", "runs/example", "--bootstraps", "-3"],
    )
    with pytest.raises(SystemExit):
        _parse_args()


def test_parse_args_accepts_positive_resampling_counts(monkeypatch) -> None:
    from analysis.textrazor_ranking_r2 import _parse_args

    monkeypatch.setattr(
        "sys.argv",
        [
            "textrazor_ranking_r2.py",
            "--run",
            "runs/example",
            "--cv-folds",
            "2",
            "--bootstraps",
            "1",
            "--no-show",
        ],
    )
    args = _parse_args()
    assert args.cv_folds == 2
    assert args.bootstraps == 1
