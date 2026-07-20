from __future__ import annotations

import logging
import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest

from seo_rank.stats.artifacts import _format_plackett_luce_lines, run_phase5_stats
import seo_rank.stats.plackett_luce as plackett_luce_module
from seo_rank.stats.plackett_luce import (
    fit_backend_plackett_luce,
    fit_plackett_luce_for_score_column,
    summarize_backend_plackett_luce,
    summarize_plackett_luce_backends,
    summarize_plackett_luce_family,
)
from seo_rank.stats.spec import load_analysis_spec
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.spec import load_analysis_spec


def _sample_plackett_luce_panel(
    *,
    keyword_count: int = 12,
    items_per_keyword: int = 5,
    similarity_beta: float = 1.4,
    length_beta: float = -0.25,
    seed: int = 17,
) -> pl.DataFrame:
    """Generate synthetic Plackett–Luce panel data for testing.
    
    Parameters:
    	keyword_count (int): Number of target keywords to generate.
    	items_per_keyword (int): Number of SERP items generated for each keyword.
    	similarity_beta (float): Utility weight for item similarity.
    	length_beta (float): Utility weight for the logarithm of referring-domain count.
    	seed (int): Seed for deterministic random generation.
    
    Returns:
    	pl.DataFrame: Synthetic panel data with observed SERP rankings and model features.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []

    for keyword_index in range(1, keyword_count + 1):
        keyword_id = f"kw-{keyword_index}"
        keyword = f"keyword {keyword_index}"
        frame_rows: list[dict[str, object]] = []
        for serp_rank in range(1, items_per_keyword + 1):
            similarity = float(rng.uniform(0.0, 1.0))
            referring_domains_count = int(rng.integers(120, 420))
            utility = (similarity_beta * similarity) + (
                length_beta * float(np.log(referring_domains_count + 1.0))
            )
            frame_rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": keyword_id,
                    "target_keyword": keyword,
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
                    "referring_domains_count": referring_domains_count,
                    "deprecated_html_tags": (keyword_index + serp_rank) % 3 == 0,
                    "time_to_first_byte_ms": 100 + (keyword_index * 7) + serp_rank,
                    "site_scale": (keyword_index * 0.1) + (serp_rank * 0.01),
                    "authority_proxy": ((keyword_index * 5 + serp_rank * 13) % 11) * 0.01,
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                    "bge_raw_score": similarity,
                    "bge_normalized_score": similarity,
                    "gemini_doc_retrieval_raw_score": similarity * 0.8,
                    "gemini_doc_retrieval_normalized_score": similarity * 0.8,
                    "gemini_semantic_similarity_raw_score": similarity * 0.6,
                    "gemini_semantic_similarity_normalized_score": similarity * 0.6,
                    "utility": utility,
                    "schema_version": "analysis_mart.v1",
                }
            )

        remaining = frame_rows.copy()
        ordered_rows: list[dict[str, object]] = []
        while remaining:
            weights = np.array([np.exp(float(row["utility"])) for row in remaining], dtype=float)
            weights = weights / weights.sum()
            sampled_index = int(rng.choice(len(remaining), p=weights))
            ordered_rows.append(remaining.pop(sampled_index))

        for observed_rank, row in enumerate(ordered_rows, start=1):
            row = dict(row)
            row["serp_rank"] = observed_rank
            row.pop("utility", None)
            rows.append(row)

    return pl.DataFrame(rows)


def _partial_plackett_luce_panel() -> pl.DataFrame:
    frame = _sample_plackett_luce_panel(keyword_count=4, items_per_keyword=4)
    return frame.with_columns(
        pl.when((pl.col("target_keyword_id") == "kw-2") & (pl.col("serp_rank") == 4))
        .then(None)
        .otherwise(pl.col("bge_normalized_score"))
        .alias("bge_normalized_score")
    )


def _duplicate_rank_plackett_luce_panel() -> pl.DataFrame:
    frame = _sample_plackett_luce_panel(keyword_count=3, items_per_keyword=4)
    return frame.with_columns(
        pl.when((pl.col("target_keyword_id") == "kw-1") & (pl.col("serp_rank") == 4))
        .then(3)
        .otherwise(pl.col("serp_rank"))
        .alias("serp_rank")
    )


def _too_small_plackett_luce_panel() -> pl.DataFrame:
    return _sample_plackett_luce_panel(keyword_count=1, items_per_keyword=1)


def test_stats_package_exports_plackett_luce_module_surface() -> None:
    import seo_rank.stats as stats

    assert stats.plackett_luce.__name__ == "seo_rank.stats.plackett_luce"


def test_summarize_plackett_luce_family_reuses_single_frame_prep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_spec = load_analysis_spec()
    family = analysis_spec.signal_families.family("gemini_doc_retrieval")
    frame = _sample_plackett_luce_panel()
    prep_calls = 0
    original = plackett_luce_module._prepare_plackett_luce_frame

    def counting_prep(*args, **kwargs):
        nonlocal prep_calls
        prep_calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(plackett_luce_module, "_prepare_plackett_luce_frame", counting_prep)

    summary = summarize_plackett_luce_family(
        {"analysis_mart": frame},
        family=family,
    )

    assert prep_calls == 1
    assert summary["status"] in {"computed", "unstable"}
    assert len(summary["signals"]) == len(family.signal_columns)


def test_summarize_plackett_luce_family_skips_constant_boolean_signal_without_optimizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_spec = load_analysis_spec()
    family = analysis_spec.signal_families.family("onpage_technical_checks")
    frame = _sample_plackett_luce_panel().with_columns(
        pl.lit(True).alias("is_redirect"),
    )
    optimize_calls = 0
    original = plackett_luce_module._maximize_log_likelihood

    def counting_optimize(*args, **kwargs):
        nonlocal optimize_calls
        optimize_calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(plackett_luce_module, "_maximize_log_likelihood", counting_optimize)

    summary = summarize_plackett_luce_family(
        {"onpage_features": frame},
        family=family,
    )

    constant_summary = summary["signals"]["is_redirect"]
    assert constant_summary["status"] == "skipped"
    assert constant_summary["skipped_reason"] == "insufficient_signal_variance"
    assert optimize_calls < len(family.signal_columns)


def test_onpage_metric_families_enable_family_plackett_luce() -> None:
    analysis_spec = load_analysis_spec()
    from seo_rank.stats.families import plackett_luce_enabled_for_family

    for family_key in (
        "onpage_content_quality",
        "onpage_core_web_vitals",
        "onpage_technical_checks",
    ):
        family = analysis_spec.signal_families.family(family_key)
        assert family.kind == "onpage_metric"
        assert plackett_luce_enabled_for_family(family) is True


def test_summarize_backend_plackett_luce_fits_rank_ordered_logit_with_clustered_se() -> None:
    summary = summarize_backend_plackett_luce(_sample_plackett_luce_panel(), backend="bge")

    assert summary["backend"] == "bge"
    assert summary["status"] in {"computed", "unstable"}
    assert summary["keyword_count"] == 12
    assert summary["row_count"] == 60
    assert summary["choice_set_size_summary"]["min"] == 5
    assert summary["choice_set_size_summary"]["max"] == 5
    assert summary["main_model"]["formula"] == (
        "rank_ordered_logit ~ log(bge_normalized_score + 1) + site_scale + authority_proxy"
    )
    assert summary["main_model"]["omitted_controls"] == []
    assert summary["main_model"]["log_odds_per_1sd"] > 0
    assert summary["main_model"]["log_odds_per_1sd_standard_error"] > 0
    assert summary["main_model"]["log_odds_per_1sd_confidence_interval"][0] < summary["main_model"][
        "log_odds_per_1sd"
    ]
    assert summary["main_model"]["log_odds_per_1sd_confidence_interval"][1] > summary["main_model"][
        "log_odds_per_1sd"
    ]
    assert summary["main_model"]["odds_ratio_per_1sd"] > 1
    assert summary["convergence_confirmed"] is (summary["status"] == "computed")
    assert "coefficient" not in summary["main_model"]
    assert "diagnostics" not in summary


def test_plackett_luce_ignores_meta_keyword_control() -> None:
    panel = _sample_plackett_luce_panel().with_columns(
        pl.lit(False).alias("deprecated_html_tags"),
    )

    fit = fit_backend_plackett_luce(panel, backend="bge")
    summary = summarize_backend_plackett_luce(panel, backend="bge")

    assert fit is not None
    assert fit.params.shape == (3,)
    assert fit.information.shape == (3, 3)
    assert summary["main_model"]["formula"] == "rank_ordered_logit ~ log(bge_normalized_score + 1) + site_scale + authority_proxy"
    assert summary["main_model"]["omitted_controls"] == []


def test_plackett_luce_ignores_constant_meta_keyword_control() -> None:
    panel = _sample_plackett_luce_panel().with_columns(
        pl.lit(0.5).alias("meta_keywords_to_content_consistency"),
    )

    fit = fit_backend_plackett_luce(panel, backend="bge")
    summary = summarize_backend_plackett_luce(panel, backend="bge")

    assert fit is not None
    assert fit.params.shape == (3,)
    assert summary["main_model"]["formula"] == (
        "rank_ordered_logit ~ log(bge_normalized_score + 1) + site_scale + authority_proxy"
    )
    assert summary["main_model"]["omitted_controls"] == []


def test_plackett_luce_omits_constant_control_but_keeps_latency_control() -> None:
    panel = _sample_plackett_luce_panel().with_columns(
        pl.lit(200).alias("referring_domains_count"),
        pl.lit(False).alias("deprecated_html_tags"),
        pl.lit(0.5).alias("meta_keywords_to_content_consistency"),
        pl.lit(0.5).alias("site_scale"),
    )

    fit = fit_backend_plackett_luce(panel, backend="bge")
    summary = summarize_backend_plackett_luce(panel, backend="bge")

    assert fit is not None
    assert fit.params.shape == (2,)
    assert fit.information.shape == (2, 2)
    assert summary["main_model"]["formula"] == "rank_ordered_logit ~ log(bge_normalized_score + 1) + authority_proxy"
    assert summary["main_model"]["omitted_controls"] == [
        {"column": "site_scale", "reason": "constant"},
    ]


def test_plackett_luce_recomputes_omitted_controls_for_subset_refits() -> None:
    panel = _sample_plackett_luce_panel().with_columns(
        (pl.col("serp_rank") == 1).alias("site_scale"),
    )
    fit = fit_backend_plackett_luce(panel, backend="bge")

    assert fit is not None
    subset_fit = plackett_luce_module._fit_subset(
        fit,
        lambda frame: frame[frame["serp_rank"] > 1],
    )

    assert fit.omitted_controls == ()
    assert subset_fit is not None
    assert subset_fit.omitted_controls == (
        {"column": "site_scale", "reason": "constant"},
    )


def test_plackett_luce_logs_score_and_controls_in_feature_matrix() -> None:
    frame = pd.DataFrame(
        {
            "bge_normalized_score": [2.0, 3.0],
            "site_scale": [1.0, 2.0],
        }
    )

    features = plackett_luce_module._feature_matrix(
        frame,
        "bge_normalized_score",
        ("site_scale",),
    )

    np.testing.assert_allclose(
        features,
        np.array([[np.log(3.0), 1.0], [np.log(4.0), 2.0]]),
    )


def test_plackett_luce_handles_signed_signal_without_nonfinite_features() -> None:
    panel = _sample_plackett_luce_panel().with_columns(
        pl.Series("signed_signal", np.linspace(-5.0, 5.0, 60)),
    )

    fit = fit_plackett_luce_for_score_column(
        panel,
        label="signed_signal",
        score_column="signed_signal",
    )

    assert fit is not None
    assert np.isfinite(fit.params).all()
    assert np.isfinite(fit.information).all()
    assert "signed_log1p(signed_signal)" in plackett_luce_module._fitted_formula(
        "signed_signal",
        fit.fitted_control_columns,
        signed=True,
    )


def test_summarize_backend_plackett_luce_diagnostics_reports_optimizer_and_iia_refits() -> None:
    diagnostics = plackett_luce_module.summarize_backend_plackett_luce_diagnostics(
        _sample_plackett_luce_panel(),
        backend="bge",
    )

    assert diagnostics["backend"] == "bge"
    assert diagnostics["status"] in {"computed", "unstable"}
    assert diagnostics["optimizer"]["converged"] is True
    assert diagnostics["optimizer"]["gradient_norm"] < 1e-4
    assert diagnostics["duplicate_serp_rank_keyword_count"] == 0
    assert diagnostics["hessian_condition_number"] > 0
    assert diagnostics["convergence_confirmed"] is (diagnostics["status"] == "computed")
    assert "iia_sensitivity" not in diagnostics


def test_summarize_plackett_luce_diagnostics_includes_leave_one_out_when_requested() -> None:
    diagnostics = plackett_luce_module.summarize_plackett_luce_diagnostics_backends_from_fits(
        _sample_plackett_luce_panel(),
        ["bge"],
        fits={
            "bge": fit_backend_plackett_luce(_sample_plackett_luce_panel(), backend="bge"),
        },
        include_iia_sensitivity=True,
    )

    assert diagnostics["backends"]["bge"]["iia_sensitivity"]["leave_one_out_top_rank"]["status"] in {
        "computed",
        "unstable",
    }


def test_summarize_backend_plackett_luce_uses_backend_specific_non_null_rows() -> None:
    summary = summarize_backend_plackett_luce(_partial_plackett_luce_panel(), backend="bge")

    assert summary["status"] in {"computed", "unstable"}
    assert summary["row_count"] == 15
    assert summary["keyword_count"] == 4
    assert summary["choice_set_size_summary"]["min"] == 3
    assert summary["choice_set_size_summary"]["per_keyword"][0]["choice_set_size"] == 4
    assert "diagnostics" not in summary


def test_summarize_backend_plackett_luce_ignores_sparse_meta_keyword_control() -> None:
    frame = _sample_plackett_luce_panel().with_columns(
        pl.when(pl.col("serp_rank") == 1)
        .then(None)
        .otherwise(pl.col("meta_keywords_to_content_consistency"))
        .alias("meta_keywords_to_content_consistency")
    )

    summary = summarize_backend_plackett_luce(frame, backend="bge")

    assert summary["status"] in {"computed", "unstable"}
    assert summary["row_count"] == frame.height
    assert summary["main_model"]["omitted_controls"] == []


def test_summarize_backend_plackett_luce_skips_duplicate_rank_keyword() -> None:
    summary = summarize_backend_plackett_luce(_duplicate_rank_plackett_luce_panel(), backend="bge")
    diagnostics = plackett_luce_module.summarize_backend_plackett_luce_diagnostics(
        _duplicate_rank_plackett_luce_panel(),
        backend="bge",
    )

    assert summary["status"] in {"computed", "unstable"}
    assert summary["row_count"] == 8
    assert summary["keyword_count"] == 2
    assert summary["choice_set_size_summary"]["min"] == 4
    assert diagnostics["duplicate_serp_rank_keyword_count"] == 1


def test_fit_backend_plackett_luce_reports_optimizer_non_convergence() -> None:
    fit = fit_backend_plackett_luce(
        _sample_plackett_luce_panel(keyword_count=2, items_per_keyword=4),
        backend="bge",
        optimizer_options={"maxiter": 1},
    )

    assert fit is not None
    assert fit.optimizer.converged is False
    assert fit.optimizer.gradient_norm >= 0

    summary = plackett_luce_module._summarize_fit(fit)
    assert summary["convergence_confirmed"] is False
    assert summary["main_model"]["status"] == "unstable"
    assert "log_odds_per_1sd" in summary["main_model"]
    assert "odds_ratio_per_1sd" in summary["main_model"]


def test_fit_backend_plackett_luce_treats_precision_loss_with_tiny_gradient_as_converged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = load_analysis_spec()
    run_frame = pl.read_parquet(
        Path(__file__).resolve().parents[2]
        / "runs"
        / "seo-company-columbus-e26107bade78"
        / "parquet"
        / "analysis_mart"
        / "part-0.parquet"
        ).with_row_index("_row").with_columns(
            (pl.col("_row") % 3 == 0).alias("site_scale"),
            pl.lit(0.5).alias("authority_proxy"),
            pl.lit(0.5).alias("meta_keywords_to_content_consistency"),
            pl.lit(250).alias("time_to_first_byte_ms"),
        ).drop("_row")
    top_10_frame = filter_panel_by_max_rank(
        run_frame,
        max_rank=spec.rank_depth_limit("top_10"),
    )

    with caplog.at_level(logging.WARNING, logger="seo_rank.stats.plackett_luce"):
        fit = fit_backend_plackett_luce(top_10_frame, backend="bge")

    assert fit is not None
    assert fit.optimizer.converged is True
    assert fit.optimizer.gradient_norm < 1.1e-6
    assert not any("optimizer did not converge" in record.getMessage() for record in caplog.records)
    summary = plackett_luce_module._summarize_backend_plackett_luce_result(
        top_10_frame,
        backend="bge",
        fit=fit,
        include_diagnostics=True,
    )
    assert summary["status"] in {"computed", "unstable"}
    assert summary["convergence_confirmed"] is (summary["status"] == "computed")
    assert summary["main_model"]["convergence_confirmed"] is (summary["status"] == "computed")


def test_summarize_backend_plackett_luce_marks_unstable_fit_as_unstable() -> None:
    unstable_summary = plackett_luce_module._summarize_backend_plackett_luce_result(
        _sample_plackett_luce_panel(keyword_count=2, items_per_keyword=4),
        backend="bge",
        fit=fit_backend_plackett_luce(
            _sample_plackett_luce_panel(keyword_count=2, items_per_keyword=4),
            backend="bge",
            optimizer_options={"maxiter": 0},
        ),
        include_diagnostics=True,
    )

    assert unstable_summary["status"] == "unstable"
    assert unstable_summary["main_model"]["status"] == "unstable"


def test_summarize_backend_plackett_luce_skips_too_small_choice_sets() -> None:
    summary = summarize_backend_plackett_luce(_too_small_plackett_luce_panel(), backend="bge")

    assert summary["status"] == "skipped"
    assert summary["skipped_reason"] == "insufficient_choice_set"


def test_summarize_backend_plackett_luce_logs_fit_and_skip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="seo_rank.stats.plackett_luce")

    summarize_backend_plackett_luce(_sample_plackett_luce_panel(), backend="bge")
    summarize_backend_plackett_luce(_too_small_plackett_luce_panel(), backend="bge")

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "backend=bge" in message and "status=" in message and "status=skipped" not in message
        for message in messages
    )
    assert any(
        "backend=bge" in message and "skipped_reason=insufficient_choice_set" in message
        for message in messages
    )


def test_format_plackett_luce_lines_surfaces_leave_one_out_iia_status() -> None:
    plackett_luce = {
        "backends": {
            "bge": {
                "status": "computed",
                "main_model": {"odds_ratio_per_1sd": 1.5},
            }
        }
    }
    diagnostics = {
        "backends": {
            "bge": {
                "convergence_confirmed": True,
                "hessian_condition_number": 12.3,
                "iia_sensitivity": {
                    "leave_one_out_top_rank": {"status": "computed"},
                },
            }
        }
    }

    lines = _format_plackett_luce_lines(plackett_luce, diagnostics)

    assert len(lines) == 1
    assert "leave_one_out_top_rank_status=computed" in lines[0]


def test_format_plackett_luce_lines_shows_n_a_without_iia_diagnostics() -> None:
    plackett_luce = {
        "backends": {
            "bge": {
                "status": "computed",
                "main_model": {"odds_ratio_per_1sd": 1.5},
            }
        }
    }
    diagnostics = {
        "backends": {
            "bge": {
                "convergence_confirmed": True,
                "hessian_condition_number": 12.3,
            }
        }
    }

    lines = _format_plackett_luce_lines(plackett_luce, diagnostics)

    assert len(lines) == 1
    assert "leave_one_out_top_rank_status=n/a" in lines[0]


def test_run_phase5_stats_writes_plackett_luce_sections(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _sample_plackett_luce_panel().lazy(),
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    diagnostics = json.loads(
        (run_dir / "stats" / "stats_diagnostics.json").read_text(encoding="utf-8")
    )
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert result.hard_fail is False
    assert "rank_depths" in summary
    assert summary["rank_depths"]["top_20"]["plackett_luce"] is not None
    assert "plackett_luce" in diagnostics
    assert diagnostics["rank_depths"]["top_20"]["plackett_luce"]["backends"]["bge"][
        "iia_sensitivity"
    ]["leave_one_out_top_rank"]["status"] in {"computed", "unstable"}
    assert "## Rank depth: top_20" in report
    assert "## Rank depth: top_3" in report
    assert "### Plackett-Luce" in report
    assert "convergence_confirmed=" in report
    assert "leave_one_out_top_rank_status=" in report
    assert "Plackett-Luce top-10 sensitivity" not in report


def test_run_phase5_stats_fits_plackett_luce_once_per_backend(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _sample_plackett_luce_panel().lazy(),
    )

    call_count = 0
    original_fit = plackett_luce_module.fit_plackett_luce_backends

    def wrapped_fit(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_fit(*args, **kwargs)

    monkeypatch.setattr(
        "seo_rank.stats.artifacts.fit_plackett_luce_backends",
        wrapped_fit,
    )

    run_phase5_stats(run_dir)

    assert call_count == 4


def test_plackett_luce_drops_null_control_rows_instead_of_control_error() -> None:
    frame = _sample_plackett_luce_panel().with_columns(
        pl.when(pl.col("serp_rank") == 1)
        .then(None)
        .otherwise(pl.lit(250))
        .alias("site_scale"),
    )
    expected_rows = frame.filter(pl.col("site_scale").is_not_null()).height

    summary = summarize_backend_plackett_luce(frame, backend="bge")

    assert summary["status"] in {"computed", "unstable"}
    assert summary["row_count"] == expected_rows
    assert "invalid_controls" not in summary


def test_plackett_luce_reports_control_error_when_required_control_column_missing() -> None:
    frame = _sample_plackett_luce_panel().drop("authority_proxy")

    summary = summarize_backend_plackett_luce(frame, backend="bge")

    assert summary["status"] == "error"
    assert summary["error_note"] == "required control data is incomplete; model not fit"
    assert summary["invalid_controls"] == [
        {"column": "authority_proxy", "reason": "missing_column"}
    ]


def test_plackett_luce_keeps_signal_null_filter_local_to_that_backend() -> None:
    frame = _sample_plackett_luce_panel().with_columns(
        pl.lit(0.5).alias("site_scale"),
        pl.when(pl.col("serp_rank") == 1)
        .then(None)
        .otherwise(pl.col("bge_normalized_score"))
        .alias("bge_normalized_score"),
    )

    summary = summarize_backend_plackett_luce(frame, backend="bge")

    assert summary["status"] in {"computed", "unstable"}
    assert summary["row_count"] == frame.height - 12


def test_condition_number_returns_inf_when_svd_does_not_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args, **_kwargs):
        raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(plackett_luce_module.np.linalg, "svd", boom)

    assert plackett_luce_module._condition_number(np.eye(2)) == float("inf")


def test_fit_plackett_luce_returns_skipped_fit_when_pinv_svd_does_not_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args, **_kwargs):
        raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(plackett_luce_module.np.linalg, "pinv", boom)

    fit = fit_plackett_luce_for_score_column(
        _sample_plackett_luce_panel(keyword_count=4, items_per_keyword=4),
        label="bge",
        score_column="bge_normalized_score",
    )

    assert isinstance(fit, plackett_luce_module.SkippedModelFit)
    assert fit.reason == "svd_did_not_converge"


def test_summarize_backend_plackett_luce_skips_when_pinv_svd_does_not_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args, **_kwargs):
        raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(plackett_luce_module.np.linalg, "pinv", boom)

    summary = summarize_backend_plackett_luce(
        _sample_plackett_luce_panel(keyword_count=4, items_per_keyword=4),
        backend="bge",
    )

    assert summary["status"] == "skipped"
    assert summary["skipped_reason"] == "svd_did_not_converge"
