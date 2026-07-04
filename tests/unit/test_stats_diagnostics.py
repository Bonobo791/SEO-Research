from pathlib import Path
import json
import logging
import warnings

import polars as pl
import pytest

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats import diagnostics as diagnostics_module
from seo_rank.stats.diagnostics import summarize_backend_diagnostics
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.spec import load_analysis_spec


def _diagnostics_analysis_mart_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 5):
            score = 1.2 - (serp_rank * 0.18) + keyword_offset
            if keyword_index == 1 and serp_rank == 1:
                score = 8.0
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
                    "bge_raw_score": score,
                    "bge_normalized_score": score,
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


def _small_diagnostics_frame() -> pl.DataFrame:
    frame = _diagnostics_analysis_mart_frame()
    return frame.filter(pl.col("keyword_order") <= 4)


def _empty_backend_frame() -> pl.DataFrame:
    return _diagnostics_analysis_mart_frame().with_columns(
        pl.lit(None, dtype=pl.Float64).alias("bge_normalized_score")
    )


def _multivariate_panel_frame(*, collinear: bool) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 7):
        target_keyword_id = f"kw-{keyword_index}"
        keyword_offset = keyword_index * 0.05
        for serp_rank in range(1, 5):
            if collinear:
                page_text_length = 100 + (keyword_index * 10) + (serp_rank * 2)
                bge_score = float(page_text_length)
                doc_score = float(page_text_length)
                semantic_score = float(page_text_length)
            else:
                keyword_factor = keyword_index - 3.5
                rank_factor = serp_rank - 2.5
                page_text_length = 100 + (keyword_factor**2) + (rank_factor**2)
                bge_score = keyword_factor
                doc_score = rank_factor
                semantic_score = keyword_factor * rank_factor
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": f"keyword {keyword_index}",
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
                    "bge_normalized_score": bge_score,
                    "gemini_doc_retrieval_normalized_score": doc_score,
                    "gemini_semantic_similarity_normalized_score": semantic_score,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def test_summarize_backend_diagnostics_reports_reset_bp_and_influence_metrics() -> None:
    summary = summarize_backend_diagnostics(_diagnostics_analysis_mart_frame(), backend="bge")

    assert summary["backend"] == "bge"
    assert summary["reset"]["status"] == "computed"
    assert summary["breusch_pagan"]["status"] == "computed"
    assert summary["breusch_pagan"]["recommended_se_type"] == "HC3"
    assert summary["influence"]["cook_d_threshold"] == pytest.approx(4 / summary["row_count"])
    assert summary["influence"]["influential_count"] >= 1


def test_summarize_backend_diagnostics_marks_small_sample_shapiro_as_informational() -> None:
    summary = summarize_backend_diagnostics(_small_diagnostics_frame(), backend="bge")

    assert summary["shapiro"]["status"] == "informational"
    assert summary["shapiro"]["p_value"] is not None


def test_summarize_backend_diagnostics_handles_top_3_without_runtime_warnings() -> None:
    spec = load_analysis_spec()
    top_3_frame = filter_panel_by_max_rank(
        _diagnostics_analysis_mart_frame(),
        max_rank=spec.rank_depth_limit("top_3"),
    )

    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        summary = summarize_backend_diagnostics(top_3_frame, backend="bge")

    assert captured_warnings == []
    assert summary["status"] == "computed"
    assert summary["reset"]["status"] == "computed"
    assert summary["influence"]["influential_count"] > 0


def test_summarize_backend_diagnostics_skips_reset_when_df_resid_is_too_small() -> None:
    spec = load_analysis_spec()
    run_frame = pl.read_parquet(
        Path(__file__).resolve().parents[2]
        / "runs"
        / "seo-company-columbus-e26107bade78"
        / "parquet"
        / "analysis_mart"
        / "part-0.parquet"
    )
    top_5_frame = filter_panel_by_max_rank(
        run_frame,
        max_rank=spec.rank_depth_limit("top_5"),
    )

    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        summary = summarize_backend_diagnostics(top_5_frame, backend="bge")

    assert captured_warnings == []
    assert summary["status"] == "computed"
    assert summary["reset"]["status"] == "skipped"
    assert summary["reset"]["skipped_reason"] == "insufficient_df_resid"


def test_run_phase5_stats_writes_stats_diagnostics_json_and_report_section(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _diagnostics_analysis_mart_frame().lazy(),
    )

    result = run_phase5_stats(run_dir)

    diagnostics_path = run_dir / "stats" / "stats_diagnostics.json"
    report_path = run_dir / "stats" / "stats_report.md"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert result.hard_fail is False
    assert diagnostics_path.exists()
    assert diagnostics["analysis_spec_version"]
    assert diagnostics["backends"]["bge"]["backend"] == "bge"
    assert "## Diagnostics" in report


def test_summarize_multivariate_sensitivity_keeps_all_backends_when_vif_is_below_threshold() -> None:
    spec = load_analysis_spec()

    summary = diagnostics_module.summarize_multivariate_sensitivity(
        _multivariate_panel_frame(collinear=False),
        vif_threshold=spec.multivariate_vif_threshold,
        backend_drop_order=spec.backend_drop_order,
    )

    assert summary["status"] == "computed"
    assert summary["kept_backends"] == [
        "bge",
        "gemini_doc_retrieval",
        "gemini_semantic_similarity",
    ]
    assert summary["drop_log"] == []
    assert summary["vif_table"]
    assert any(row["term"] == "bge_normalized_score" for row in summary["vif_table"])


def test_summarize_multivariate_sensitivity_drops_backends_in_configured_order() -> None:
    spec = load_analysis_spec()

    summary = diagnostics_module.summarize_multivariate_sensitivity(
        _multivariate_panel_frame(collinear=True),
        vif_threshold=spec.multivariate_vif_threshold,
        backend_drop_order=spec.backend_drop_order,
    )

    assert summary["status"] == "unresolved"
    assert summary["drop_log"][0]["dropped_backend"] == "gemini_semantic_similarity"
    assert summary["drop_log"][1]["dropped_backend"] == "gemini_doc_retrieval"
    assert summary["drop_log"][-1]["kept_backends"] == ["bge"]
    assert summary["kept_backends"] == ["bge"]


def test_run_phase5_stats_writes_multivariate_sensitivity_block_and_report_section(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _multivariate_panel_frame(collinear=True).lazy(),
    )

    run_phase5_stats(run_dir)

    diagnostics = json.loads(
        (run_dir / "stats" / "stats_diagnostics.json").read_text(encoding="utf-8")
    )
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert diagnostics["rank_depths"]["top_20"]["multivariate_sensitivity"]["status"] in {
        "computed",
        "unresolved",
    }
    assert "### Robustness" in report


def test_summarize_backend_diagnostics_skips_when_backend_has_no_usable_rows() -> None:
    summary = summarize_backend_diagnostics(_empty_backend_frame(), backend="bge")

    assert summary["status"] == "skipped"
    assert summary["skipped_reason"] == "no_usable_rows"


def test_summarize_backend_diagnostics_logs_fit_and_skip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="seo_rank.stats.diagnostics")

    summarize_backend_diagnostics(_diagnostics_analysis_mart_frame(), backend="bge")
    summarize_backend_diagnostics(_empty_backend_frame(), backend="bge")

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "backend=bge" in message and "status=computed" in message and "influential_count=" in message
        for message in messages
    )
    assert any(
        "backend=bge" in message and "status=skipped" in message and "skipped_reason=no_usable_rows" in message
        for message in messages
    )
