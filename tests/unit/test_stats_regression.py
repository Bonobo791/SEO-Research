import json
from pathlib import Path

import polars as pl

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.regression import (
    summarize_backend_regression,
    summarize_regression_backends,
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


def test_summarize_backend_regression_supports_single_keyword_with_hc3_inference() -> None:
    summary = summarize_backend_regression(
        _single_keyword_regression_frame(),
        backend="bge",
    )

    assert summary["keyword_count"] == 1
    assert summary["row_count"] == 10
    assert summary["feature_model"]["covariance"]["type"] == "HC3"
    assert summary["feature_model"]["covariance"]["clusters"] == []
    assert summary["baseline_model"]["formula"] == "outcome ~ np.log(page_text_length + 1)"
    assert "C(target_keyword_id)" not in summary["feature_model"]["formula"]
    assert summary["feature_model"]["clustered_standard_error"] > 0


def test_summarize_backend_regression_uses_keyword_clustered_inference() -> None:
    summary = summarize_backend_regression(_regression_analysis_mart_frame(), backend="bge")

    assert summary["backend"] == "bge"
    assert summary["row_count"] == 40
    assert summary["keyword_count"] == 10
    assert summary["score_column"] == "bge_normalized_score"
    assert summary["feature_model"]["covariance"]["type"] == "cluster"
    assert summary["feature_model"]["covariance"]["clusters"] == ["target_keyword_id"]
    assert summary["feature_model"]["coefficient"] > 0
    assert summary["feature_model"]["clustered_standard_error"] > 0
    assert summary["feature_model"]["clustered_confidence_interval"][0] < summary["feature_model"]["coefficient"]
    assert summary["feature_model"]["clustered_confidence_interval"][1] > summary["feature_model"]["coefficient"]
    assert "naive_standard_error" not in summary["feature_model"]
    assert summary["descriptive_fit_delta"]["adjusted_r_squared"] >= 0
    assert summary["effect_size"]["similarity_sd"] > 0
    assert summary["effect_size"]["approximate_delta_rank_per_1sd"] < 0
    assert (
        summary["effect_size"]["formula"]
        == "median_rank * (exp(-(coefficient * similarity_sd)) - 1)"
    )
    assert summary["sensitivity"]["two_way_cluster"]["status"] == "computed"
    assert summary["sensitivity"]["two_way_cluster"]["clusters"] == [
        "target_keyword_id",
        "canonical_url_hash",
    ]


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


def test_summarize_backend_regression_excludes_rows_with_incomplete_covariates() -> None:
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

    assert summary["row_count"] == 40
    assert "status" not in summary


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

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _regression_analysis_mart_frame().lazy(),
    )

    result = run_phase5_stats(run_dir)

    summary = (run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8")
    diagnostics = json.loads(
        (run_dir / "stats" / "stats_diagnostics.json").read_text(encoding="utf-8")
    )
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert result.hard_fail is False
    assert '"regression"' in summary
    assert '"clustered_standard_error"' in summary
    assert '"two_way_cluster"' in summary
    assert '"naive_standard_error"' not in summary
    assert diagnostics["analysis_spec_version"]
    assert diagnostics["backends"]["bge"]["backend"] == "bge"
    assert "## Regression" in report
