from pathlib import Path
import json

import polars as pl
import pytest

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.diagnostics import summarize_backend_diagnostics


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


def test_summarize_backend_diagnostics_skips_when_backend_has_no_usable_rows() -> None:
    summary = summarize_backend_diagnostics(_empty_backend_frame(), backend="bge")

    assert summary["status"] == "skipped"
    assert summary["skipped_reason"] == "no_usable_rows"
