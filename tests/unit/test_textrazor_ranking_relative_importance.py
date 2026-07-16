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
                    "referring_domains_count": 120 + (keyword_index * 3) + serp_rank**2,
                    "deprecated_html_tags": (keyword_index + serp_rank) % 3 == 0,
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                    "time_to_first_byte_ms": 100 + serp_rank,
                    "site_scale": (keyword_index * 0.1) + ((serp_rank % 2) * 0.03),
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
    assert "bge_normalized_score" in groups["relevance"]
    assert "textrazor_entity_confidence_score" in groups["relevance"]
    assert "backlinks_count" in groups["authority"]
    assert "onpage_score" in groups["content"]
    assert groups["metadata_presentation"][:2] == ("title_length", "description_length")
    assert "time_to_first_byte_ms" not in groups["performance"]
    assert "title_too_long" not in groups["content"]


def test_ranking_importance_factor_columns_can_skip_backlinks() -> None:
    groups = ranking_importance_factor_columns(
        load_analysis_spec(),
        include_backlinks=False,
    )

    assert groups["authority"] == ()


def test_ranking_importance_factor_columns_uses_seo_concept_groups() -> None:
    groups = ranking_importance_factor_columns(load_analysis_spec())

    assert RANKING_IMPORTANCE_GROUP_ORDER == (
        "relevance",
        "content",
        "authority",
        "technical",
        "performance",
        "resources",
        "metadata_presentation",
    )
    assert groups["relevance"] == (
        "bge_normalized_score",
        "gemini_doc_retrieval_normalized_score",
        "gemini_semantic_similarity_normalized_score",
        "textrazor_entity_confidence_score",
        "textrazor_entity_relevance_score",
        "textrazor_topic_score",
        "textrazor_category_score",
        "textrazor_classifier_score",
        "textrazor_entailment_score",
        "textrazor_entailment_prior",
        "textrazor_entailment_context",
    )
    assert groups["content"] == (
        "textrazor_word_count",
        "textrazor_grammar_count",
        "textrazor_sense_count",
        "textrazor_spelling_count",
        "textrazor_relation_count",
        "textrazor_property_count",
        "textrazor_noun_phrase_count",
        "onpage_score",
        "plain_text_word_count",
        "plain_text_rate",
        "flesch_kincaid_readability_index",
        "coleman_liau_readability_index",
        "smog_readability_index",
        "dale_chall_readability_index",
        "description_to_content_consistency",
        "title_to_content_consistency",
        "meta_keywords_to_content_consistency",
        "h1_count",
        "h2_count",
        "h3_count",
        "high_content_rate",
        "high_character_count",
        "duplicate_meta_tags_count",
        "duplicate_content",
        "lorem_ipsum",
    )
    assert groups["authority"] == (
        "backlinks_count",
        "referring_domains_count",
        "dofollow_backlinks_count",
    )
    assert groups["technical"] == (
        "is_redirect",
        "follow",
        "inbound_links_count",
        "click_depth",
        "seo_friendly_url",
        "has_valid_structured_data",
        "has_micromarkup",
        "has_micromarkup_errors",
        "flash",
        "frame",
    )
    assert groups["performance"] == (
        "connection_time_ms",
        "time_to_secure_connection_ms",
        "request_sent_time_ms",
        "download_time_ms",
        "duration_time_ms",
        "fetch_end_ms",
        "dom_complete_ms",
        "time_to_interactive_ms",
        "cache_control_cachable",
        "cache_control_ttl",
    )
    assert groups["resources"] == (
        "images_count",
        "images_size",
        "scripts_count",
        "stylesheets_count",
        "encoded_size",
        "small_page_size",
        "resource_warnings_count",
    )
    assert groups["metadata_presentation"] == (
        "title_length",
        "description_length",
        "has_og_tags",
        "has_twitter_tags",
        "no_favicon",
        "no_image_title",
    )
    assigned = [column for columns in groups.values() for column in columns]
    assert len(assigned) == len(set(assigned))


def test_summarize_ranking_relative_importance_computes_group_and_metric_rows() -> None:
    panel = _ranking_importance_panel_frame()
    spec = load_analysis_spec()
    summary = summarize_ranking_relative_importance(
        panel,
        spec=spec,
        include_individual_signals=True,
        cv_folds=3,
        cv_repeats=2,
        bootstraps=5,
        shapley_permutations=4,
        random_state=0,
    )

    assert summary["status"] == "computed"
    assert summary["row_count"] == panel.height
    assert summary["keyword_count"] == 10
    assert summary["cv_folds"] == 3
    assert summary["cv_repeats"] == 2
    assert summary["bootstraps"] == 5
    assert len(summary["groups"]) == len(RANKING_IMPORTANCE_GROUP_ORDER)

    shapley_total = sum(
        group["shapley_share"]
        for group in summary["groups"]
        if group["shapley_share"] is not None
    )
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
    assert "out_of_sample_full_r2" in similarity
    assert "out_of_sample_reduced_r2" in similarity
    assert "out_of_sample_delta_r2" in similarity
    oos_ready = [
        group
        for group in summary["groups"]
        if group["out_of_sample_full_r2"] is not None
        and group["out_of_sample_reduced_r2"] is not None
        and group["out_of_sample_delta_r2"] is not None
    ]
    assert oos_ready
    for group in oos_ready:
        assert group["out_of_sample_delta_r2"] == pytest.approx(
            group["out_of_sample_full_r2"] - group["out_of_sample_reduced_r2"]
        )

    assert len(similarity["metrics"]) >= 1
    assert similarity["repeat_mean_ndcg_delta"] is not None
    assert similarity["repeat_sd_ndcg_delta"] is not None
    metric_partials = [
        metric["full_model_partial_r2"]
        for group in summary["groups"]
        for metric in group["metrics"]
        if metric["full_model_partial_r2"] is not None
    ]
    assert metric_partials
    assert all(partial >= 0 for partial in metric_partials)
    json.dumps(summary)


def test_relative_importance_measures_each_signal_with_group_parity(monkeypatch) -> None:
    import seo_rank.stats.textrazor_explainability as module

    def shapley(_model_data, factor_columns, **_kwargs):
        return {
            "values": {name: 0.1 for name in factor_columns},
            "mcse": {},
            "convergence_difference": {},
            "successful_contributions": {},
        }

    def oos(_panel, factor_columns, **_kwargs):
        return {
            "groups": {
                name: {
                    "full_r2": 0.8,
                    "reduced_r2": 0.6,
                    "delta_r2": 0.2,
                    "ndcg_delta": 0.1,
                }
                for name in factor_columns
            },
            "predictor_fold_inclusion_rates": {
                column: 1.0
                for columns in factor_columns.values()
                for column in columns
            },
        }

    def bootstrap(result, **_kwargs):
        return {
            name: {
                "delta_r2": {"point": 0.2, "lower": 0.1, "upper": 0.3},
                "ndcg_delta": {"point": 0.1, "lower": 0.0, "upper": 0.2},
            }
            for name in result["groups"]
        }

    monkeypatch.setattr(module, "_permutation_shapley_statistics", shapley)
    monkeypatch.setattr(module, "_compute_grouped_oof_importance", oos)
    monkeypatch.setattr(module, "_domain_holdout_oof_importance", oos)
    monkeypatch.setattr(module, "_bootstrap_oos_delta_ci", bootstrap)

    group_only = module.summarize_ranking_relative_importance(
        _ranking_importance_panel_frame(),
        spec=load_analysis_spec(),
        cv_folds=3,
        cv_repeats=2,
        bootstraps=3,
        shapley_permutations=4,
        domain_cv_repeats=2,
        random_state=0,
    )
    assert group_only["individual_signals_included"] is False
    assert all(not group["metrics"] for group in group_only["groups"])

    summary = module.summarize_ranking_relative_importance(
        _ranking_importance_panel_frame(),
        spec=load_analysis_spec(),
        include_individual_signals=True,
        cv_folds=3,
        cv_repeats=2,
        bootstraps=3,
        shapley_permutations=4,
        domain_cv_repeats=2,
        random_state=0,
    )
    assert summary["individual_signals_included"] is True

    signal = next(
        metric
        for group in summary["groups"]
        if group["factor"] == "relevance"
        for metric in group["metrics"]
        if metric["column"] == "bge_normalized_score"
    )

    assert signal["shapley_share"] is not None
    assert signal["out_of_sample_delta_r2"] is not None
    assert signal["out_of_sample_delta_r2_ci"]["point"] == pytest.approx(
        signal["out_of_sample_delta_r2"]
    )
    assert signal["out_of_sample_ndcg_delta"] is not None
    assert signal["domain_holdout_delta_r2"] == pytest.approx(0.2)
    assert signal["evidence_status"] in {
        "Portable",
        "Keyword-supported",
        "Dataset-specific",
        "Uncertain",
        "Redundant/no value",
    }
    assert signal["ndcg_evidence_status"] in {
        "Keyword-supported",
        "Uncertain",
        "Redundant/no value",
    }


def test_signal_evidence_statuses_use_metric_specific_tested_flags(
    monkeypatch, caplog
) -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    monkeypatch.setattr(module, "_fit_importance_r_squared", lambda *_args, **_kwargs: 0.6)
    caplog.set_level(__import__("logging").DEBUG, logger=module.__name__)

    rows = module._metric_relative_importance_rows(
        pd.DataFrame(),
        group="similarity",
        group_columns=("signal",),
        selected_columns=("signal",),
        keyword_count=2,
        control_columns=(),
        full_r2=0.8,
        shapley_values={"signal": 0.2},
        shapley_total=0.2,
        oos_result={
            "groups": {"signal": {"delta_r2": 0.2, "ndcg_delta": None}},
            "predictor_fold_inclusion_rates": {"signal": 1.0},
        },
        oos_bootstrap={
            "signal": {
                "delta_r2": {"lower": 0.1, "upper": 0.3},
                "ndcg_delta": {"lower": None, "upper": None},
            }
        },
        domain_holdout={"groups": {"signal": {"delta_r2": 0.1}}},
        domain_bootstrap={
            "signal": {"delta_r2": {"lower": 0.05, "upper": 0.15}}
        },
    )

    assert rows[0]["evidence_status"] == "Portable"
    assert rows[0]["ndcg_evidence_status"] == "Not tested"
    assert "signal=signal r2_tested=True ndcg_tested=False" in caplog.text


def test_relative_importance_uses_permutation_shapley(monkeypatch) -> None:
    import seo_rank.stats.textrazor_explainability as module

    panel = _ranking_importance_panel_frame()
    monkeypatch.setattr(
        module,
        "_build_coalition_r_squared_cache",
        lambda *args, **kwargs: pytest.fail("exact coalition Shapley must not run"),
        raising=False,
    )

    summary = summarize_ranking_relative_importance(
        panel,
        spec=load_analysis_spec(),
        cv_folds=3,
        cv_repeats=1,
        bootstraps=1,
        shapley_permutations=3,
    )

    assert summary["shapley_method"] == "permutation"
    assert summary["shapley_permutations"] == 3


def test_prepare_importance_context_imputes_and_demeans_without_complete_case_drop() -> None:
    import seo_rank.stats.textrazor_explainability as module

    panel = _ranking_importance_panel_frame().with_columns(
        pl.when(pl.col("serp_rank") == 1)
        .then(None)
        .otherwise(pl.col("onpage_score"))
        .alias("onpage_score")
    )
    spec = load_analysis_spec()
    groups = ranking_importance_factor_columns(spec)

    prepared = module._prepare_ranking_importance_context(panel, groups)

    assert prepared is not None
    assert prepared["row_count"] == panel.height
    assert prepared["model_data"]["outcome_fe"].notna().all()
    assert prepared["model_data"]["onpage_score"].notna().all()
    assert prepared["model_data"].attrs["within_keyword_fe"] is True
    assert "bge_normalized_score" in prepared["candidate_columns"]
    assert "textrazor_entity_confidence_score" in prepared["candidate_columns"]


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
        cv_repeats=1,
        bootstraps=2,
        shapley_permutations=4,
        random_state=0,
    )

    assert summary["status"] == "computed"
    assert "full_model_r_squared" in summary
    assert "full_model_adjusted_r_squared" not in summary
    assert 0.0 <= summary["full_model_r_squared"] <= 1.0


def test_summarize_ranking_relative_importance_skips_excessively_missing_columns() -> None:
    """Sparse predictors are excluded from explanatory RI; source data remains intact."""

    panel = _ranking_importance_panel_frame()
    # Inject a sparse content column that would wipe complete-case if kept.
    sparse = [None] * (panel.height - 1) + [0.5]
    panel = panel.with_columns(pl.Series("meta_keywords_to_content_consistency", sparse))
    spec = load_analysis_spec()
    groups = ranking_importance_factor_columns(spec)
    assert "meta_keywords_to_content_consistency" in groups["content"]

    summary = summarize_ranking_relative_importance(
        panel,
        spec=spec,
        cv_folds=3,
        cv_repeats=1,
        bootstraps=2,
        shapley_permutations=4,
        random_state=0,
        min_complete_rows=20,
    )

    assert summary["status"] == "computed"
    assert summary["row_count"] >= 20
    excluded = {entry["column"] for entry in summary["excluded_predictors"]}
    assert "meta_keywords_to_content_consistency" in excluded
    assert next(
        entry["reason"]
        for entry in summary["excluded_predictors"]
        if entry["column"] == "meta_keywords_to_content_consistency"
    ) == "excessive_missingness"
    assert "meta_keywords_to_content_consistency" not in summary["predictor_columns"]
    assert {
        "bge_normalized_score",
        "gemini_doc_retrieval_normalized_score",
    } & set(summary["predictor_columns"])


def test_balanced_group_folds_are_nearly_equal() -> None:
    import seo_rank.stats.textrazor_explainability as module

    groups = [f"k{i}" for i in range(24) for _ in range(2)]
    rng = module.np.random.default_rng(0)
    splits = module._balanced_group_folds(groups, n_splits=5, rng=rng)
    assert len(splits) == 5
    test_sizes = []
    for _, test_idx in splits:
        keywords = {groups[i] for i in test_idx}
        test_sizes.append(len(keywords))
    assert sorted(test_sizes) == [4, 5, 5, 5, 5]


def test_prepare_oos_importance_frame_keeps_baseline_controls() -> None:
    import seo_rank.stats.textrazor_explainability as module

    panel = pl.DataFrame(
        {
            "target_keyword_id": ["k1", "k1", "k2", "k2"],
            "serp_rank": [1, 2, 1, 2],
            "bge_normalized_score": [0.9, 0.1, 0.8, 0.2],
            "site_scale": [1.0, 1.1, 1.2, 1.3],
        }
    )
    frame = module._prepare_oos_importance_frame(
        panel,
        {"similarity": ("bge_normalized_score",)},
    )

    assert frame is not None
    assert frame.attrs["predictor_columns"] == (
        "bge_normalized_score",
        "site_scale",
    )


def test_extract_domain_returns_registrable_domain() -> None:
    import seo_rank.stats.textrazor_explainability as module

    assert module._extract_domain("https://news.blog.example.co.uk/page") == "example.co.uk"


def test_ridge_tuning_preprocesses_each_inner_fold(monkeypatch) -> None:
    import numpy as np
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    train = pd.DataFrame(
        {
            "row_id": list(range(6)),
            "feature": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    test = pd.DataFrame({"row_id": [6, 7], "feature": [6.0, 7.0]})
    groups = np.array(["a", "a", "b", "b", "c", "c"])
    calls: list[int] = []
    original = module._preprocess_fold_matrices

    def track_preprocess(inner_train, inner_test, columns):
        calls.append(len(inner_train))
        return original(inner_train, inner_test, columns)

    monkeypatch.setattr(module, "_preprocess_fold_matrices", track_preprocess)
    predictions = module._fit_ridge_predict(
        train,
        np.arange(6, dtype=float),
        test,
        ("feature",),
        groups,
    )

    assert predictions is not None
    assert any(size < len(train) for size in calls)
    assert len(train) in calls


def test_compute_grouped_oof_reports_full_reduced_and_delta() -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 13):
        for serp_rank in range(1, 5):
            signal = float(4 - serp_rank) + keyword_index * 0.01
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "serp_rank": serp_rank,
                    "outcome": -__import__("numpy").log(float(serp_rank)),
                    "url": f"https://example{keyword_index % 3}.com/{serp_rank}",
                    "bge_normalized_score": signal,
                    "textrazor_entity_relevance_score": signal * 0.5,
                    "backlinks_count": 10 + serp_rank,
                    "time_to_first_byte_ms": 100 + serp_rank,
                    "onpage_score": 50 + signal,
                }
            )
    frame = pd.DataFrame(rows)
    frame["domain"] = frame["url"].map(module._extract_domain)
    frame.attrs["predictor_columns"] = (
        "bge_normalized_score",
        "textrazor_entity_relevance_score",
        "backlinks_count",
        "time_to_first_byte_ms",
        "onpage_score",
    )
    factor_columns = {
        "similarity": ("bge_normalized_score",),
        "textrazor": ("textrazor_entity_relevance_score",),
        "backlinks": ("backlinks_count",),
        "metadata_lengths": (),
        "performance": ("time_to_first_byte_ms",),
        "crawl_architecture": (),
        "structured_markup": (),
        "document_structure": (),
        "quality_flags": (),
        "resource_footprint": (),
        "presentation_metadata": (),
        "delivery_configuration": (),
        "legacy_embedding": (),
        "content": ("onpage_score",),
    }
    result = module._compute_grouped_oof_importance(
        frame,
        factor_columns,
        cv_folds=3,
        cv_repeats=2,
        random_state=0,
    )
    assert result is not None
    assert result["full_r2"] is not None
    similarity = result["groups"]["similarity"]
    assert similarity["full_r2"] is not None
    assert similarity["reduced_r2"] is not None
    assert similarity["delta_r2"] == pytest.approx(
        similarity["full_r2"] - similarity["reduced_r2"]
    )
    assert len(result["repeat_results"]) == 2
    assert similarity["repeat_mean_delta_r2"] is not None
    assert similarity["repeat_sd_delta_r2"] is not None
    assert similarity["repeat_min_delta_r2"] <= similarity["repeat_max_delta_r2"]


def test_evidence_status_distinguishes_portability_and_missing_predictors() -> None:
    import seo_rank.stats.textrazor_explainability as module

    assert module._evidence_status((0.1, 0.2), 0.1, domain_ci=(0.1, 0.2), keyword_delta=0.1, tested=True) == "Portable"
    assert module._evidence_status((0.1, 0.2), -0.01, keyword_delta=0.1, tested=True) == "Dataset-specific"
    assert module._evidence_status((-0.1, 0.2), 0.5, keyword_delta=0.1, tested=True) == "Uncertain"
    assert module._evidence_status((-0.1, 0.2), 0.5, keyword_delta=-0.1, tested=True) == "Redundant/no value"
    assert module._evidence_status((0.1, 0.2), None, tested=True) == "Uncertain"
    assert module._evidence_status(None, None, tested=False) == "Not tested"


def test_evidence_status_uses_domain_ci_taxonomy() -> None:
    import seo_rank.stats.textrazor_explainability as module

    assert module._evidence_status((0.1, 0.2), 0.1, domain_ci=(0.1, 0.2), keyword_delta=0.1, tested=True) == "Portable"
    assert module._evidence_status((0.1, 0.2), 0.1, domain_ci=(-0.1, 0.2), keyword_delta=0.1, tested=True) == "Keyword-supported"
    assert module._evidence_status((0.1, 0.2), -0.2, domain_ci=(-0.2, -0.1), keyword_delta=0.1, tested=True) == "Harmful to portability"
    assert module._evidence_status((0.1, 0.2), -0.01, keyword_delta=0.1, tested=True) == "Dataset-specific"
    assert module._evidence_status((0.1, 0.2), 0.1, domain_ci=(0.0, 0.2), keyword_delta=0.1, tested=True) == "Keyword-supported"


def test_ndcg_status_is_not_tested_without_ndcg_delta() -> None:
    import seo_rank.stats.textrazor_explainability as module

    assert module._ndcg_evidence_status(
        keyword_ci=None,
        keyword_delta=None,
        tested=False,
    ) == "Not tested"


def test_effective_oos_columns_exclude_zero_inclusion_predictors() -> None:
    import seo_rank.stats.textrazor_explainability as module

    assert module._effective_oos_columns(
        ("signal_a", "signal_b"),
        {"signal_a": 0.0, "signal_b": 0.5},
    ) == ("signal_b",)


def test_relative_importance_marks_zero_predictor_groups_untested_and_reports_uncertainty() -> None:
    panel = _ranking_importance_panel_frame()
    summary = summarize_ranking_relative_importance(
        panel,
        spec=load_analysis_spec(),
        cv_folds=3,
        cv_repeats=1,
        bootstraps=2,
        shapley_permutations=4,
        random_state=0,
    )

    performance = next(group for group in summary["groups"] if group["factor"] == "performance")
    assert performance["in_sample_predictor_count"] == 0
    assert performance["full_model_partial_r2"] is None
    assert performance["shapley_share"] is None
    assert performance["evidence_status"] == "Not tested"

    assert summary["shapley_mcse"] is not None
    assert summary["shapley_convergence_difference"] is not None


def test_domain_coverage_reports_failures_folds_and_repeat_deltas() -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    frame = pd.DataFrame(
        {
            "target_keyword_id": ["k1", "k1", "k2", "k2", "k3", "k3", "k4", "k4", "k5", "k5"],
            "serp_rank": [1, 2] * 5,
            "outcome": [0.0, -1.0] * 5,
            "url": [
                "https://a.example1.com/1", "https://a.example1.com/2",
                "https://b.example2.com/1", "https://b.example2.com/2",
                "https://c.example3.com/1", "https://c.example3.com/2",
                "https://d.example4.com/1", "https://d.example4.com/2",
                "not-a-url", "not-a-url",
            ],
                "signal": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
                "noise": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
        }
    )
    frame["domain"] = frame["url"].map(module._extract_domain)
    frame.attrs["predictor_columns"] = ("signal", "noise")
    factors = {group: () for group in module.RANKING_IMPORTANCE_GROUP_ORDER}
    factors["similarity"] = ("signal",)
    factors["textrazor"] = ("noise",)

    result = module._domain_holdout_oof_importance(
        frame,
        factors,
        random_state=0,
        cv_repeats=2,
    )

    assert result is not None
    assert result["domain_rows"] == 8
    assert result["domain_count"] == 4
    assert result["groups"]["similarity"]["row_count"] <= result["domain_rows"]
    assert result["groups"]["similarity"]["group_count"] <= result["domain_count"]
    assert result["domain_rows_with_extraction_failure"] == 2
    assert result["domains_per_fold"] == [1, 1, 1, 1]
    assert len(result["repeat_results"]) == 2
    assert result["groups"]["similarity"]["repeat_mean_delta_r2"] is not None


def test_oos_delta_ci_bootstraps_out_of_sample_delta(monkeypatch) -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    def fail_if_refit(*args, **kwargs):
        raise AssertionError("bootstrap must use fixed OOF predictions")

    monkeypatch.setattr(module, "_compute_grouped_oof_importance", fail_if_refit)
    oof = pd.DataFrame(
        {
            "target_keyword_id": ["k1", "k1", "k2", "k2", "k3", "k3"],
            "serp_rank": [1, 2, 1, 2, 1, 2],
            "outcome": [0.0, -1.0, 0.0, -1.0, 0.0, -1.0],
            "full_prediction": [0.0, -1.0, 0.0, -1.0, 0.0, -1.0],
            "reduced_prediction": [-1.0, 0.0, -1.0, 0.0, -1.0, 0.0],
        }
    )
    oof_result = {
        "groups": {
            group: {"oof_predictions": oof}
            for group in module.RANKING_IMPORTANCE_GROUP_ORDER
        }
    }
    intervals = module._bootstrap_oos_delta_ci(
        oof_result,
        bootstraps=4,
        random_state=0,
    )
    r2_ci = intervals["similarity"]["delta_r2"]
    ndcg_ci = intervals["similarity"]["ndcg_delta"]
    assert r2_ci["point"] is not None
    assert r2_ci["lower"] <= r2_ci["point"] <= r2_ci["upper"]
    assert ndcg_ci["point"] is not None
    assert ndcg_ci["lower"] <= ndcg_ci["point"] <= ndcg_ci["upper"]


def test_grouped_oof_ndcg_delta_uses_reduced_model_coverage(monkeypatch) -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    rows = []
    for keyword_index, keyword in enumerate(("k1", "k2", "k3")):
        for serp_rank in (1, 2):
            rows.append(
                {
                    "target_keyword_id": keyword,
                    "serp_rank": serp_rank,
                    "outcome": -float(serp_rank),
                    "signal": float(3 - serp_rank),
                    "reduced": float(serp_rank) if keyword == "k3" else 0.0,
                }
            )
    frame = pd.DataFrame(rows)
    frame.attrs["predictor_columns"] = ("signal", "reduced")
    factor_columns = {
        "similarity": ("signal",),
        "textrazor": (),
        "backlinks": (),
        "metadata_lengths": (),
        "performance": (),
        "crawl_architecture": (),
        "structured_markup": (),
        "document_structure": (),
        "quality_flags": (),
        "resource_footprint": (),
        "presentation_metadata": (),
        "delivery_configuration": (),
        "legacy_embedding": (),
        "content": (),
    }
    monkeypatch.setattr(
        module,
        "_keyword_ndcg",
        lambda scored_frame, predictions: float(len(scored_frame)),
    )

    result = module._compute_grouped_oof_importance(
        frame,
        factor_columns,
        cv_folds=3,
        cv_repeats=1,
        random_state=0,
    )

    assert result is not None
    similarity = result["groups"]["similarity"]
    assert similarity["ndcg_full"] == 6.0
    assert similarity["ndcg_reduced"] is None
    assert similarity["ndcg_delta"] is None


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


def test_parse_args_defaults_to_precise_group_analysis(monkeypatch) -> None:
    from analysis.textrazor_ranking_r2 import _parse_args

    monkeypatch.setattr(
        "sys.argv", ["textrazor_ranking_r2.py", "--run", "runs/example"]
    )
    defaults = _parse_args()
    assert (
        defaults.cv_folds,
        defaults.cv_repeats,
        defaults.bootstraps,
        defaults.shapley_permutations,
        defaults.domain_cv_repeats,
    ) == (5, 10, 500, 2000, 10)
    assert defaults.individual_signals is False

    monkeypatch.setattr(
        "sys.argv",
        [
            "textrazor_ranking_r2.py",
            "--run",
            "runs/example",
            "--individual-signals",
            "--shapley-permutations",
            "7",
        ],
    )
    overridden = _parse_args()
    assert overridden.individual_signals is True
    assert overridden.shapley_permutations == 7
    assert overridden.bootstraps == 500

    monkeypatch.setattr(
        "sys.argv",
        ["textrazor_ranking_r2.py", "--run", "runs/example", "--exhaustive"],
    )
    with pytest.raises(SystemExit):
        _parse_args()


def test_relative_importance_renderer_separates_explanatory_and_oos_tables() -> None:
    from analysis.textrazor_ranking_r2 import _render_relative_importance_table

    rendered = _render_relative_importance_table(
        {
            "status": "computed",
            "row_count": 10,
            "keyword_count": 2,
            "shapley_permutations": 3,
            "predictor_columns": ["bge_normalized_score"],
            "excluded_predictors": [],
            "warnings": [],
            "groups": [
                {
                    "factor": "legacy_embedding",
                    "in_sample_predictor_count": 0,
                    "in_sample_predictor_columns": [],
                    "in_sample_rows": None,
                    "in_sample_keywords": None,
                    "out_of_sample_full_r2": None,
                    "out_of_sample_reduced_r2": None,
                    "out_of_sample_delta_r2": None,
                    "out_of_sample_delta_r2_ci": None,
                    "out_of_sample_ndcg_delta": None,
                    "domain_holdout_delta_r2": None,
                    "domain_holdout_delta_r2_ci": None,
                    "oos_predictor_columns": [],
                    "oos_predictor_count": 0,
                    "repeat_mean_ndcg_delta": 0.12,
                    "repeat_sd_ndcg_delta": 0.03,
                    "repeat_min_ndcg_delta": 0.08,
                    "repeat_max_ndcg_delta": 0.16,
                    "domain_rows": None,
                    "domain_count": None,
                    "evidence_status": "Not tested",
                }
            ],
        }
    )

    assert "A. Within-keyword fixed-effects explanation" in rendered
    assert "B. Keyword-held-out predictive importance" in rendered
    assert "C. Domain-held-out portability" in rendered
    assert "Shapley raw ΔR² MCSE" in rendered
    assert "repeat ΔNDCG mean/sd/range" in rendered
    assert "fold inclusion rates" in rendered
    assert "0.1200 / 0.0300 / [0.0800, 0.1600]" in rendered
    assert "n/a — not included" in rendered
    assert "domain ΔR²" not in rendered.split("B. Keyword-held-out predictive importance", 1)[1].split("C. Domain-held-out portability", 1)[0]


def test_bootstrap_ci_point_matches_ensemble_delta() -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    frame = pd.DataFrame(
        {
            "target_keyword_id": ["k1", "k1", "k2", "k2"],
            "serp_rank": [1, 2, 1, 2],
            "outcome": [0.0, -1.0, 0.0, -1.0],
            "full_prediction": [0.0, -1.0, 0.0, -1.0],
            "reduced_prediction": [-1.0, 0.0, -1.0, 0.0],
        }
    )
    oof_result = {
        "groups": {
            "similarity": {
                "delta_r2": 0.25,
                "oof_predictions": frame,
            }
        },
        "repeat_results": [
            {"groups": {"similarity": {"oof_predictions": frame}}},
            {"groups": {"similarity": {"oof_predictions": frame}}},
        ],
    }
    intervals = module._bootstrap_oos_delta_ci(
        oof_result,
        bootstraps=5,
        random_state=0,
    )

    assert intervals["similarity"]["delta_r2"]["point"] == pytest.approx(0.25)


def test_domain_holdout_does_not_emit_ndcg() -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    frame = pd.DataFrame(
        {
            "target_keyword_id": [f"k{i}" for i in range(1, 6) for _ in (1, 2)],
            "serp_rank": [1, 2] * 5,
            "outcome": [0.0, -1.0] * 5,
            "url": [f"https://example{i}.com/x" for i in range(1, 6) for _ in (1, 2)],
            "signal": [1.0, 0.0] * 5,
        }
    )
    frame["domain"] = frame["url"].map(module._extract_domain)
    frame.attrs["predictor_columns"] = ("signal",)
    factors = {group: () for group in module.RANKING_IMPORTANCE_GROUP_ORDER}
    factors["similarity"] = ("signal",)

    result = module._domain_holdout_oof_importance(
        frame, factors, random_state=0, cv_repeats=1
    )

    assert result is not None
    assert "ndcg_delta" not in result["groups"]["similarity"]


def test_importance_join_rejects_duplicate_source_keys() -> None:
    import seo_rank.stats.textrazor_explainability as module

    keys = {"run_id": ["r1"], "target_keyword_id": ["k1"], "canonical_url_hash": ["u1"]}
    source_frames = {
        name: __import__("polars").DataFrame(keys)
        for name in ("analysis_mart", "backlinks_analysis", "onpage_features")
    }
    source_frames["textrazor_page_metrics"] = __import__("polars").DataFrame(
        {
            "run_id": ["r1", "r1"],
            "target_keyword_id": ["k1", "k1"],
            "canonical_url_hash": ["u1", "u1"],
            "metric": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="duplicate.*textrazor_page_metrics"):
        module._merge_ranking_importance_frames(
            source_frames, {"textrazor": ("metric",)}
        )


def test_importance_join_preserves_duplicate_canonical_urls_by_serp_item() -> None:
    import seo_rank.stats.textrazor_explainability as module

    pl = __import__("polars")
    base = {
        "run_id": ["r1", "r1"],
        "target_keyword_id": ["k1", "k1"],
        "canonical_url_hash": ["u1", "u1"],
        "serp_item_id": ["s1", "s2"],
    }
    source_frames = {
        "analysis_mart": pl.DataFrame(base),
        "backlinks_analysis": pl.DataFrame(
            {**base, "backlinks_count": [10, 20]}
        ),
        "onpage_features": pl.DataFrame(base),
        "textrazor_page_metrics": pl.DataFrame(
            {
                "run_id": ["r1"],
                "target_keyword_id": ["k1"],
                "canonical_url_hash": ["u1"],
                "metric": [0.5],
            }
        ),
    }

    merged = module._merge_ranking_importance_frames(
        source_frames,
        {"backlinks": ("backlinks_count",), "textrazor": ("metric",)},
    )

    assert merged.height == 2
    assert merged.get_column("backlinks_count").to_list() == [10, 20]
    assert merged.get_column("metric").to_list() == [0.5, 0.5]


def test_fold_preprocessing_rejects_sparse_and_unbalanced_predictors() -> None:
    import numpy as np
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    train = pd.DataFrame(
        {
            "sparse": [1.0, None, None, None, None, None, None, None, None, None],
            "binary": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0],
            "usable": np.arange(10, dtype=float),
        }
    )
    test = train.iloc[:2].copy()
    prepared = module._preprocess_fold_matrices(train, test, ("sparse", "binary", "usable"))

    assert prepared is not None
    assert prepared[2] == ["usable"]


def test_domain_preprocessing_uses_keyword_groups_for_variation() -> None:
    import pandas as pd
    import seo_rank.stats.textrazor_explainability as module

    train = pd.DataFrame(
        {
            "domain_signal": [1.0, 1.0, 2.0, 2.0],
        }
    )
    train.attrs["oos_train_groups"] = ["domain-a", "domain-a", "domain-b", "domain-b"]
    train.attrs["oos_variation_groups"] = ["keyword-a", "keyword-b", "keyword-a", "keyword-b"]

    prepared = module._preprocess_fold_matrices(train, train.copy(), ("domain_signal",))

    assert prepared is not None
    assert prepared[2] == ["domain_signal"]


def test_min_complete_rows_skips_small_eligible_sample() -> None:
    summary = summarize_ranking_relative_importance(
        _ranking_importance_panel_frame(),
        spec=load_analysis_spec(),
        min_complete_rows=1000,
    )

    assert summary["status"] == "skipped"
    assert summary["skipped_reason"] == "below_min_complete_rows"
    assert summary["min_complete_rows"] == 1000


def test_evidence_status_rejects_entirely_negative_keyword_ci() -> None:
    import seo_rank.stats.textrazor_explainability as module

    assert module._evidence_status(
        (-0.4, -0.1),
        0.2,
        domain_ci=(0.1, 0.2),
        keyword_delta=0.2,
        tested=True,
    ) == "Redundant/no value"


def test_shapley_reports_successful_contribution_counts(monkeypatch) -> None:
    import seo_rank.stats.textrazor_explainability as module

    model_data = __import__("pandas").DataFrame({"outcome_fe": [0.0, 1.0]})
    factor_columns = {group: () for group in module.RANKING_IMPORTANCE_GROUP_ORDER}
    factor_columns["similarity"] = ("signal",)

    monkeypatch.setattr(
        module,
        "_fit_importance_r_squared",
        lambda _data, columns, **_kwargs: 0.0 if not columns else 0.5,
    )
    result = module._permutation_shapley_statistics(
        model_data,
        factor_columns,
        selected_columns=("signal",),
        keyword_count=1,
        control_columns=(),
        permutations=3,
        random_state=0,
    )

    assert result["successful_contributions"]["similarity"] == 3
    assert result["values"]["similarity"] == pytest.approx(0.5)


def test_shapley_logs_progress(monkeypatch, caplog) -> None:
    import logging
    import seo_rank.stats.textrazor_explainability as module

    model_data = __import__("pandas").DataFrame({"outcome_fe": [0.0, 1.0]})
    monkeypatch.setattr(
        module,
        "_fit_importance_r_squared",
        lambda _data, columns, **_kwargs: 0.0 if not columns else 0.5,
    )
    caplog.set_level(logging.INFO, logger=module.__name__)

    module._permutation_shapley_statistics(
        model_data,
        {"signal": ("signal",)},
        selected_columns=("signal",),
        keyword_count=1,
        control_columns=(),
        permutations=10,
        random_state=0,
        progress_label="signal Shapley",
    )

    assert "signal Shapley progress 10/10" in caplog.text


def test_renderer_reports_keyword_ndcg_ci_and_omits_domain_ndcg() -> None:
    from analysis.textrazor_ranking_r2 import _render_relative_importance_table

    rendered = _render_relative_importance_table(
        {
            "status": "computed",
            "row_count": 1,
            "keyword_count": 1,
            "shapley_permutations": 3,
            "predictor_columns": [],
            "excluded_predictors": [],
            "warnings": [],
            "groups": [
                {
                    "factor": "similarity",
                    "in_sample_predictor_count": 0,
                    "in_sample_predictor_columns": [],
                    "out_of_sample_ndcg_delta": 0.1,
                    "out_of_sample_ndcg_delta_ci": {"lower": 0.0, "upper": 0.2},
                    "domain_holdout_delta_r2": 0.1,
                    "domain_holdout_delta_r2_ci": {"lower": 0.0, "upper": 0.2},
                    "domain_rows": 1,
                    "domain_count": 1,
                    "evidence_status": "Keyword-supported",
                    "ndcg_evidence_status": "Keyword-supported",
                    "metrics": [
                        {
                            "column": "bge_normalized_score",
                            "full_model_partial_r2": 0.2,
                            "shapley_share": 0.1,
                            "out_of_sample_delta_r2": 0.05,
                            "out_of_sample_delta_r2_ci": {"lower": 0.0, "upper": 0.1},
                            "out_of_sample_ndcg_delta": 0.02,
                            "out_of_sample_ndcg_delta_ci": {"lower": 0.0, "upper": 0.04},
                            "domain_holdout_delta_r2": 0.03,
                            "evidence_status": "Keyword-supported",
                        }
                    ],
                }
            ],
        }
    )

    assert "ΔNDCG CI" in rendered
    assert "NDCG status" in rendered
    assert "signal bge_normalized_score" in rendered
    domain_section = rendered.split("C. Domain-held-out portability", 1)[1]
    assert "ΔNDCG" not in domain_section
