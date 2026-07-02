import logging
from pathlib import Path

import polars as pl
import pytest

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.bh import adjust_p_values
from seo_rank.stats.spearman import summarize_backend_spearman


def _passing_analysis_mart_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        for serp_rank in range(1, 4):
            score = float(4 - serp_rank)
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
                    "page_text_length": 100 + serp_rank,
                    "bge_raw_score": score,
                    "bge_normalized_score": score,
                    "gemini_doc_retrieval_raw_score": score - 0.1,
                    "gemini_doc_retrieval_normalized_score": score - 0.1,
                    "gemini_semantic_similarity_raw_score": score - 0.2,
                    "gemini_semantic_similarity_normalized_score": score - 0.2,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def _secondary_backend_only_keyword_frame() -> pl.DataFrame:
    frame = _passing_analysis_mart_frame()
    extra_rows = [
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-11",
            "target_keyword": "keyword 11",
            "keyword_order": 11,
            "source_response_id": "resp-11",
            "serp_item_id": "serp-11-1",
            "page_id": "page-11-1",
            "response_id": "page-resp-11-1",
            "canonical_url_hash": "url-11-1",
            "url": "https://example.com/11/1",
            "serp_rank": 1,
            "title": "title-11-1",
            "description": "description-11-1",
            "page_text_length": 101,
            "bge_raw_score": None,
            "bge_normalized_score": None,
            "gemini_doc_retrieval_raw_score": 0.8,
            "gemini_doc_retrieval_normalized_score": 0.8,
            "gemini_semantic_similarity_raw_score": 0.7,
            "gemini_semantic_similarity_normalized_score": 0.7,
            "schema_version": "analysis_mart.v1",
        },
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-11",
            "target_keyword": "keyword 11",
            "keyword_order": 11,
            "source_response_id": "resp-11",
            "serp_item_id": "serp-11-2",
            "page_id": "page-11-2",
            "response_id": "page-resp-11-2",
            "canonical_url_hash": "url-11-2",
            "url": "https://example.com/11/2",
            "serp_rank": 2,
            "title": "title-11-2",
            "description": "description-11-2",
            "page_text_length": 102,
            "bge_raw_score": None,
            "bge_normalized_score": None,
            "gemini_doc_retrieval_raw_score": 0.7,
            "gemini_doc_retrieval_normalized_score": 0.7,
            "gemini_semantic_similarity_raw_score": 0.6,
            "gemini_semantic_similarity_normalized_score": 0.6,
            "schema_version": "analysis_mart.v1",
        },
    ]
    return pl.concat([frame, pl.DataFrame(extra_rows)], how="vertical_relaxed")


def _underpowered_analysis_mart_frame() -> pl.DataFrame:
    frame = _passing_analysis_mart_frame()
    return frame.filter(pl.col("target_keyword_id") != "kw-10")


def test_adjust_p_values_applies_benjamini_hochberg_ordering() -> None:
    adjusted = adjust_p_values([0.01, 0.04, 0.03, 0.002])

    assert adjusted == [0.02, 0.04, 0.04, 0.008]


def test_summarize_backend_spearman_applies_bh_for_sufficient_keywords() -> None:
    summary = summarize_backend_spearman(_passing_analysis_mart_frame(), backend="bge")

    assert summary["backend"] == "bge"
    assert summary["keyword_count"] == 10
    assert summary["median_rho"] == -1.0
    assert summary["rho_iqr"] == 0.0
    assert summary["fraction_same_sign"] == 1.0
    assert summary["bh_q_values"] == [0.0] * 10
    assert "bh_skipped_reason" not in summary


def test_summarize_backend_spearman_skips_bh_when_underpowered() -> None:
    summary = summarize_backend_spearman(_underpowered_analysis_mart_frame(), backend="bge")

    assert summary["backend"] == "bge"
    assert summary["keyword_count"] == 9
    assert summary["bh_skipped_reason"] == "underpowered"
    assert "bh_q_values" not in summary
    assert summary["keyword_tests"][0]["p_value"] == 0.0


def test_summarize_backend_spearman_logs_summary_and_bh_skip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="seo_rank.stats.spearman")

    summarize_backend_spearman(_passing_analysis_mart_frame(), backend="bge")
    summarize_backend_spearman(_underpowered_analysis_mart_frame(), backend="bge")

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "backend=bge" in message and "keyword_count=10" in message and "bh=applied" in message
        for message in messages
    )
    assert any(
        "backend=bge" in message and "keyword_count=9" in message and "bh=skipped" in message
        for message in messages
    )


def test_summarize_backend_spearman_uses_backend_specific_non_null_rows() -> None:
    frame = _secondary_backend_only_keyword_frame()

    bge_summary = summarize_backend_spearman(frame, backend="bge")
    gemini_summary = summarize_backend_spearman(frame, backend="gemini_doc_retrieval")

    assert bge_summary["keyword_count"] == 10
    assert gemini_summary["keyword_count"] == 11
    assert any(test["target_keyword_id"] == "kw-11" for test in gemini_summary["keyword_tests"])
    assert all(test["target_keyword_id"] != "kw-11" for test in bge_summary["keyword_tests"])


def test_run_phase5_stats_includes_spearman_summary_on_passing_panels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _secondary_backend_only_keyword_frame().lazy(),
    )

    result = run_phase5_stats(run_dir)

    assert result.hard_fail is False
    summary_path = run_dir / "stats" / "stats_summary.json"
    summary = summary_path.read_text(encoding="utf-8")

    assert '"spearman"' in summary
    assert '"bh_q_values"' in summary
    assert '"keyword_count": 11' in summary
