from __future__ import annotations

import logging
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from seo_rank.stats.artifacts import _format_plackett_luce_lines, run_phase5_stats
import seo_rank.stats.plackett_luce as plackett_luce_module
from seo_rank.stats.plackett_luce import (
    fit_backend_plackett_luce,
    summarize_backend_plackett_luce,
    summarize_plackett_luce_backends,
)
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
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []

    for keyword_index in range(1, keyword_count + 1):
        keyword_id = f"kw-{keyword_index}"
        keyword = f"keyword {keyword_index}"
        frame_rows: list[dict[str, object]] = []
        for serp_rank in range(1, items_per_keyword + 1):
            similarity = float(rng.normal(loc=0.0, scale=1.0))
            page_text_length = int(rng.integers(120, 420))
            utility = (similarity_beta * similarity) + (
                length_beta * float(np.log(page_text_length + 1.0))
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
                    "page_text_length": page_text_length,
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


def test_summarize_backend_plackett_luce_fits_rank_ordered_logit_with_clustered_se() -> None:
    summary = summarize_backend_plackett_luce(_sample_plackett_luce_panel(), backend="bge")

    assert summary["backend"] == "bge"
    assert summary["status"] == "computed"
    assert summary["keyword_count"] == 12
    assert summary["row_count"] == 60
    assert summary["choice_set_size_summary"]["min"] == 5
    assert summary["choice_set_size_summary"]["max"] == 5
    assert summary["main_model"]["formula"] == "rank_ordered_logit ~ similarity + log(page_text_length + 1)"
    assert summary["main_model"]["log_odds_per_1sd"] > 0
    assert summary["main_model"]["log_odds_per_1sd_standard_error"] > 0
    assert summary["main_model"]["log_odds_per_1sd_confidence_interval"][0] < summary["main_model"][
        "log_odds_per_1sd"
    ]
    assert summary["main_model"]["log_odds_per_1sd_confidence_interval"][1] > summary["main_model"][
        "log_odds_per_1sd"
    ]
    assert summary["main_model"]["odds_ratio_per_1sd"] > 1
    assert summary["convergence_confirmed"] is True
    assert "coefficient" not in summary["main_model"]
    assert "diagnostics" not in summary


def test_summarize_backend_plackett_luce_diagnostics_reports_optimizer_and_iia_refits() -> None:
    diagnostics = plackett_luce_module.summarize_backend_plackett_luce_diagnostics(
        _sample_plackett_luce_panel(),
        backend="bge",
    )

    assert diagnostics["backend"] == "bge"
    assert diagnostics["status"] == "computed"
    assert diagnostics["optimizer"]["converged"] is True
    assert diagnostics["optimizer"]["gradient_norm"] < 1e-4
    assert diagnostics["duplicate_serp_rank_keyword_count"] == 0
    assert diagnostics["hessian_condition_number"] > 0
    assert diagnostics["convergence_confirmed"] is True
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

    assert diagnostics["backends"]["bge"]["iia_sensitivity"]["leave_one_out_top_rank"]["status"] == "computed"


def test_summarize_backend_plackett_luce_uses_backend_specific_non_null_rows() -> None:
    summary = summarize_backend_plackett_luce(_partial_plackett_luce_panel(), backend="bge")

    assert summary["status"] in {"computed", "unstable"}
    assert summary["row_count"] == 12
    assert summary["keyword_count"] == 3
    assert summary["choice_set_size_summary"]["min"] == 4
    assert summary["choice_set_size_summary"]["per_keyword"][0]["choice_set_size"] == 4
    assert "diagnostics" not in summary


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
        optimizer_options={"maxiter": 0},
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
    )
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
    assert summary["status"] == "computed"
    assert summary["convergence_confirmed"] is True
    assert summary["main_model"]["convergence_confirmed"] is True


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
    assert any("backend=bge" in message and "status=computed" in message for message in messages)
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
    ]["leave_one_out_top_rank"]["status"] == "computed"
    assert "## Rank depth: top_20" in report
    assert "## Rank depth: top_3" in report
    assert "### Plackett-Luce" in report
    assert "convergence_confirmed=" in report
    assert "leave_one_out_top_rank_status=computed" in report
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
