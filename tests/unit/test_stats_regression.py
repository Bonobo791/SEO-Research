import json
import logging
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import polars as pl
import pytest

from seo_rank.stats.artifacts import run_phase5_stats
import seo_rank.stats.regression as regression_module
from seo_rank.stats.regression import (
    summarize_backend_regression,
    summarize_regression_backends,
    summarize_regression_for_score_column,
)


def _regression_analysis_mart_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 5):
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
                    "canonical_url_hash": f"shared-url-{serp_rank}",
                    "url": f"https://example.com/{serp_rank}",
                    "serp_rank": serp_rank,
                    "title": f"title-{keyword_index}-{serp_rank}",
                    "description": f"description-{keyword_index}-{serp_rank}",
                    "page_text_length": 300 + (keyword_index * 9) + ((serp_rank % 2) * 5),
                    "referring_domains_count": 300 + (keyword_index * 9) + ((serp_rank % 2) * 5),
                    "deprecated_html_tags": (keyword_index + serp_rank) % 3 == 0,
                    "time_to_first_byte_ms": 100 + (keyword_index * 7) + serp_rank,
                    "site_scale": (keyword_index * 0.1) + (serp_rank * 0.01),
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                    "bge_raw_score": 1.1 - (serp_rank * 0.22) + keyword_offset,
                    "bge_normalized_score": 1.1 - (serp_rank * 0.22) + keyword_offset,
                    "gemini_doc_retrieval_raw_score": 0.9 - (serp_rank * 0.16) + keyword_offset,
                    "gemini_doc_retrieval_normalized_score": 0.9
                    - (serp_rank * 0.16)
                    + keyword_offset,
                    "gemini_semantic_similarity_raw_score": 0.7
                    - (serp_rank * 0.09)
                    + keyword_offset,
                    "gemini_semantic_similarity_normalized_score": 0.7
                    - (serp_rank * 0.09)
                    + keyword_offset,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def _single_keyword_regression_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for serp_rank in range(1, 11):
        rows.append(
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "technical seo",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": f"serp-1-{serp_rank}",
                "page_id": f"page-1-{serp_rank}",
                "response_id": f"page-resp-1-{serp_rank}",
                "canonical_url_hash": f"url-1-{serp_rank}",
                "url": f"https://example.com/{serp_rank}",
                "serp_rank": serp_rank,
                "title": f"title-1-{serp_rank}",
                "description": f"description-1-{serp_rank}",
                "page_text_length": 200 + serp_rank,
                "referring_domains_count": 200 + serp_rank,
                "deprecated_html_tags": False,
                "time_to_first_byte_ms": 100 + serp_rank,
                "site_scale": serp_rank * 0.1,
                "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                "bge_raw_score": 1.0 - (serp_rank * 0.05),
                "bge_normalized_score": 1.0 - (serp_rank * 0.05),
                "gemini_doc_retrieval_raw_score": 0.9 - (serp_rank * 0.04),
                "gemini_doc_retrieval_normalized_score": 0.9 - (serp_rank * 0.04),
                "gemini_semantic_similarity_raw_score": 0.8 - (serp_rank * 0.03),
                "gemini_semantic_similarity_normalized_score": 0.8 - (serp_rank * 0.03),
                "schema_version": "analysis_mart.v1",
            }
        )
    return pl.DataFrame(rows)


def _constant_similarity_keyword_regression_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 4):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.02
        for serp_rank in range(1, 5):
            similarity = 0.8 if keyword_index == 3 else 1.2 - (serp_rank * 0.1) + keyword_offset
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
                    "page_text_length": 220 + (keyword_index * 3) + serp_rank,
                    "referring_domains_count": 220 + (keyword_index * 3) + serp_rank,
                    "deprecated_html_tags": False,
                    "time_to_first_byte_ms": 100 + (keyword_index * 7) + serp_rank,
                    "site_scale": (keyword_index * 0.1) + (serp_rank * 0.01),
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                    "bge_raw_score": similarity,
                    "bge_normalized_score": similarity,
                    "gemini_doc_retrieval_raw_score": similarity * 0.8,
                    "gemini_doc_retrieval_normalized_score": similarity * 0.8,
                    "gemini_semantic_similarity_raw_score": similarity * 0.6,
                    "gemini_semantic_similarity_normalized_score": similarity * 0.6,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def test_parameter_standard_error_clamps_negative_covariance_without_warning() -> None:
    result = SimpleNamespace(
        model=SimpleNamespace(exog_names=["signal"]),
        params=np.array([1.0]),
        cov_params=lambda: np.array([[-1.0]]),
        df_resid=10,
        use_t=True,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        standard_error = regression_module._parameter_standard_error(result, "signal")

    assert caught == []
    assert standard_error == 0.0
    assert regression_module._parameter_confidence_interval(result, "signal") == [1.0, 1.0]


def test_summarize_regression_for_boolean_onpage_predictor_uses_numeric_encoding() -> None:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 6):
        for serp_rank in range(1, 4):
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "serp_rank": serp_rank,
                    "page_text_length": 200 + serp_rank,
                    "referring_domains_count": 200 + serp_rank,
                    "deprecated_html_tags": False,
                    "time_to_first_byte_ms": 100 + serp_rank,
                    "site_scale": serp_rank * 0.1,
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                    "title_too_long": serp_rank == 1,
                }
            )
    frame = pl.DataFrame(rows)

    summary = summarize_regression_for_score_column(
        frame,
        label="onpage_technical_checks",
        score_column="title_too_long",
    )

    assert summary["status"] == "computed"
    assert summary["score_column"] == "title_too_long"
    assert "title_too_long" in summary["feature_model"]["formula"]
    assert "[T.True]" not in summary["feature_model"]["formula"]


def test_summarize_backend_regression_supports_single_keyword_with_hc3_inference() -> None:
    summary = summarize_backend_regression(
        _single_keyword_regression_frame(),
        backend="bge",
    )

    assert summary["keyword_count"] == 1
    assert summary["row_count"] == 10
    assert summary["feature_model"]["covariance"]["type"] == "HC3"
    assert summary["feature_model"]["covariance"]["clusters"] == []
    assert summary["baseline_model"]["formula"] == (
        "outcome ~ site_scale"
    )
    assert "C(target_keyword_id)" not in summary["feature_model"]["formula"]
    assert summary["feature_model"]["formula"] == (
        "outcome ~ bge_normalized_score + site_scale"
    )
    assert summary["feature_model"]["clustered_standard_error"] > 0


def test_summarize_backend_regression_uses_keyword_clustered_inference() -> None:
    summary = summarize_backend_regression(_regression_analysis_mart_frame(), backend="bge")

    assert summary["backend"] == "bge"
    assert summary["row_count"] == 40
    assert summary["keyword_count"] == 10
    assert summary["score_column"] == "bge_normalized_score"
    assert summary["feature_model"]["covariance"]["type"] == "cluster"
    assert summary["feature_model"]["covariance"]["clusters"] == ["target_keyword_id"]
    assert (
        summary["baseline_model"]["formula"]
        == "outcome ~ site_scale + C(target_keyword_id)"
    )
    assert (
        summary["feature_model"]["formula"]
        == "outcome ~ bge_normalized_score + site_scale + C(target_keyword_id)"
    )
    assert summary["feature_model"]["coefficient"] > 0
    assert summary["feature_model"]["clustered_standard_error"] > 0
    assert summary["feature_model"]["clustered_confidence_interval"][0] < summary["feature_model"][
        "coefficient"
    ]
    assert summary["feature_model"]["clustered_confidence_interval"][1] > summary["feature_model"][
        "coefficient"
    ]
    assert "naive_standard_error" not in summary["feature_model"]
    assert summary["descriptive_fit_delta"]["adjusted_r_squared"] >= 0
    assert summary["effect_size"]["similarity_sd"] > 0
    assert summary["effect_size"]["approximate_delta_rank_per_1sd"] < 0
    assert (
        summary["effect_size"]["formula"]
        == "median_rank * (exp(-(coefficient * similarity_sd)) - 1)"
    )
    assert "bge_normalized_score" in summary["feature_model"]["formula"]
    assert summary["sensitivity"]["two_way_cluster"]["status"] == "computed"
    assert summary["sensitivity"]["two_way_cluster"]["clusters"] == [
        "target_keyword_id",
        "canonical_url_hash",
    ]
    assert summary["sensitivity"]["two_way_cluster"]["coefficient"] != 0


def test_summarize_backend_regression_reports_raw_model_coefficient() -> None:
    fit = regression_module.fit_backend_regression(_regression_analysis_mart_frame(), backend="bge")
    assert fit is not None

    summary = summarize_backend_regression(_regression_analysis_mart_frame(), backend="bge")
    raw_coefficient = regression_module._parameter_value(fit.clustered_result, fit.score_column)

    assert summary["feature_model"]["coefficient"] == pytest.approx(raw_coefficient)


def test_summarize_backend_regression_keeps_zero_variance_keyword_in_raw_model() -> None:
    summary = summarize_backend_regression(
        _constant_similarity_keyword_regression_frame(),
        backend="bge",
    )

    assert summary["row_count"] == 12
    assert summary["keyword_count"] == 3
    assert summary["feature_model"]["formula"] == (
        "outcome ~ bge_normalized_score + site_scale + C(target_keyword_id)"
    )


def test_fit_backend_regression_skips_when_design_matrix_is_column_rank_deficient() -> None:
    # Constructed so that np.linalg.matrix_rank(exog) == 6 (df_resid == 1, so the
    # naive `df_resid <= 0` guard passes) while exog has 7 raw columns == nobs (7).
    # statsmodels' cluster-robust covariance correction divides by
    # (nobs - k_params) using the *raw* column count, not the rank, so this shape
    # previously reached get_robustcov_results() and raised ZeroDivisionError.
    model_data = pd.DataFrame(
        {
            "outcome": [1.0, 2.0, 1.5, 3.0, 2.5, 4.0, 4.2],
            "bge_normalized_score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.6],
            "page_text_length": [100, 200, 300, 400, 500, 600, 600],
            "referring_domains_count": [100, 200, 300, 400, 500, 600, 600],
            "deprecated_html_tags": [False, False, False, False, False, False, False],
            "time_to_first_byte_ms": [100, 200, 300, 400, 500, 600, 600],
            "site_scale": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "meta_keywords_to_content_consistency": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "target_keyword_id": ["k0", "k1", "k2", "k3", "k4", "k4", "k4"],
            "serp_rank": [1, 1, 1, 1, 1, 2, 3],
        }
    )

    fit = regression_module._fit_backend_regression_from_model_data(
        model_data,
        label="bge",
        score_column="bge_normalized_score",
    )

    assert fit is None


def test_summarize_backend_regression_skips_when_backend_has_no_usable_rows() -> None:
    frame = _regression_analysis_mart_frame().with_columns(
        pl.lit(None, dtype=pl.Float64).alias("gemini_doc_retrieval_normalized_score")
    )

    summary = summarize_backend_regression(frame, backend="gemini_doc_retrieval")

    assert summary["backend"] == "gemini_doc_retrieval"
    assert summary["status"] == "skipped"
    assert summary["skipped_reason"] == "no_usable_rows"
    assert summary["row_count"] == 0
    assert "feature_model" not in summary


def test_summarize_backend_regression_logs_fit_and_skip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="seo_rank.stats.regression")

    summarize_backend_regression(_regression_analysis_mart_frame(), backend="bge")
    frame = _regression_analysis_mart_frame().with_columns(
        pl.lit(None, dtype=pl.Float64).alias("gemini_doc_retrieval_normalized_score")
    )
    summarize_backend_regression(frame, backend="gemini_doc_retrieval")

    messages = [record.getMessage() for record in caplog.records]
    assert any("backend=bge" in message and "status=computed" in message for message in messages)
    assert any(
        "backend=gemini_doc_retrieval" in message and "skipped_reason=no_usable_rows" in message
        for message in messages
    )


def test_summarize_backend_regression_reports_incomplete_control_data() -> None:
    frame = _regression_analysis_mart_frame()
    frame = pl.concat(
        [
            frame,
            pl.DataFrame(
                [
                    {
                        "run_id": "run-1",
                        "target_keyword_id": "kw-1",
                        "target_keyword": "keyword 1",
                        "keyword_order": 1,
                        "source_response_id": "resp-1",
                        "serp_item_id": "serp-extra",
                        "page_id": None,
                        "response_id": None,
                        "canonical_url_hash": "url-extra",
                        "url": "https://example.com/extra",
                        "serp_rank": 5,
                        "title": "extra",
                        "description": "extra",
                        "page_text_length": None,
                            "referring_domains_count": None,
                            "deprecated_html_tags": None,
                            "time_to_first_byte_ms": None,
                            "site_scale": None,
                            "meta_keywords_to_content_consistency": None,
                        "bge_raw_score": 0.5,
                        "bge_normalized_score": 0.5,
                        "gemini_doc_retrieval_raw_score": None,
                        "gemini_doc_retrieval_normalized_score": None,
                        "gemini_semantic_similarity_raw_score": None,
                        "gemini_semantic_similarity_normalized_score": None,
                        "schema_version": "analysis_mart.v1",
                    }
                ]
            ),
        ],
        how="vertical_relaxed",
    )

    summary = summarize_backend_regression(frame, backend="bge")

    assert summary["status"] == "error"
    assert summary["invalid_controls"] == [
        {"column": "site_scale", "reason": "missing_values"},
    ]


def test_summarize_regression_backends_skips_empty_backend_without_aborting_others() -> None:
    frame = _regression_analysis_mart_frame().with_columns(
        pl.lit(None, dtype=pl.Float64).alias("gemini_doc_retrieval_normalized_score")
    )

    summary = summarize_regression_backends(
        frame,
        ["bge", "gemini_doc_retrieval", "gemini_semantic_similarity"],
    )

    assert summary["backends"]["bge"]["row_count"] == 40
    assert summary["backends"]["gemini_doc_retrieval"]["status"] == "skipped"
    assert summary["backends"]["gemini_semantic_similarity"]["row_count"] == 40


def test_run_phase5_stats_writes_regression_for_single_keyword_panel(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _single_keyword_regression_frame().lazy(),
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    assert result.hard_fail is False
    assert summary["regression"]["backends"]["bge"]["keyword_count"] == 1
    assert summary["regression"]["backends"]["bge"]["feature_model"]["covariance"]["type"] == "HC3"


def test_run_phase5_stats_writes_regression_summary_for_passing_panels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    frame = _regression_analysis_mart_frame().with_row_index("_row").with_columns(
        pl.when(pl.col("_row") == 0)
        .then(None)
        .otherwise(pl.col("meta_keywords_to_content_consistency"))
        .alias("meta_keywords_to_content_consistency"),
    ).drop("_row")

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: frame.lazy(),
    )

    result = run_phase5_stats(run_dir)

    summary = (run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8")
    diagnostics = json.loads(
        (run_dir / "stats" / "stats_diagnostics.json").read_text(encoding="utf-8")
    )
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert result.hard_fail is False
    assert '"regression"' in summary
    assert '"rank_depths"' in summary
    assert '"clustered_standard_error"' in summary
    assert '"two_way_cluster"' in summary
    assert '"naive_standard_error"' not in summary
    assert diagnostics["analysis_spec_version"]
    assert diagnostics["backends"]["bge"]["backend"] == "bge"
    assert diagnostics["rank_depths"]["top_20"]["regression"]["backends"]["bge"]["backend"] == "bge"
    assert "## Rank depth: top_20" in report
    assert "### Regression" in report


def test_run_phase5_stats_sets_actionable_association_on_passing_panels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _regression_analysis_mart_frame().lazy(),
    )

    run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))

    assert summary["actionable_association"] is True
    assert summary["actionable_association_by_rank_depth"]["top_20"] is True


def test_run_phase5_stats_fits_regression_once_per_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _regression_analysis_mart_frame().lazy(),
    )

    call_count = 0
    original_fit = regression_module.fit_backend_regression

    def wrapped_fit(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_fit(*args, **kwargs)

    monkeypatch.setattr("seo_rank.stats.regression.fit_backend_regression", wrapped_fit)
    monkeypatch.setattr("seo_rank.stats.diagnostics.fit_backend_regression", wrapped_fit)

    run_phase5_stats(run_dir)

    assert call_count == 12


def test_regression_reports_control_error_instead_of_omitting_null_control() -> None:
    frame = _regression_analysis_mart_frame().with_columns(
        pl.when(pl.col("serp_rank") == 1)
        .then(None)
        .otherwise(pl.lit(0.5))
        .alias("site_scale"),
    )

    summary = summarize_backend_regression(frame, backend="bge")

    assert summary["status"] == "error"
    assert summary["error_note"] == "required control data is incomplete; model not fit"
    assert summary["invalid_controls"] == [
        {"column": "site_scale", "reason": "missing_values"}
    ]
    assert "omitted_controls" not in summary


def test_regression_filters_null_signal_rows_without_mutating_other_model_inputs() -> None:
    frame = _regression_analysis_mart_frame().with_columns(
        pl.lit(250).alias("time_to_first_byte_ms"),
        pl.when(pl.col("serp_rank") == 1)
        .then(None)
        .otherwise(pl.col("bge_normalized_score"))
        .alias("bge_normalized_score"),
    )

    summary = summarize_backend_regression(frame, backend="bge")

    assert summary["status"] == "computed"
    assert summary["row_count"] == frame.height - 10
    assert "site_scale" in summary["feature_model"]["formula"]


def test_summarize_score_column_preserves_control_error_status() -> None:
    frame = _regression_analysis_mart_frame().with_columns(
        pl.when(pl.col("serp_rank") == 1)
        .then(None)
        .otherwise(pl.lit(250))
        .alias("site_scale"),
    )

    summary = summarize_regression_for_score_column(
        frame,
        label="onpage_core_web_vitals",
        score_column="bge_normalized_score",
    )

    assert summary["status"] == "error"
    assert summary["error_note"] == "required control data is incomplete; model not fit"


def test_fit_backend_regression_returns_skipped_fit_when_ols_svd_does_not_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomModel:
        def fit(self, *_args, **_kwargs):
            raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(regression_module.smf, "ols", lambda *_a, **_k: _BoomModel())

    model_data = _regression_analysis_mart_frame().to_pandas()
    fit = regression_module._fit_backend_regression_from_model_data(
        model_data,
        label="bge",
        score_column="bge_normalized_score",
    )

    assert isinstance(fit, regression_module.SkippedModelFit)
    assert fit.reason == "svd_did_not_converge"


def test_summarize_backend_regression_skips_when_ols_svd_does_not_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomModel:
        def fit(self, *_args, **_kwargs):
            raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(regression_module.smf, "ols", lambda *_a, **_k: _BoomModel())

    summary = summarize_backend_regression(
        _regression_analysis_mart_frame(),
        backend="bge",
    )

    assert summary["status"] == "skipped"
    assert summary["skipped_reason"] == "svd_did_not_converge"
