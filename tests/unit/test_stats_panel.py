import json
import logging
from pathlib import Path
from types import MappingProxyType

import polars as pl
import pytest

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.panel import load_analysis_panel, prepare_analysis_panel, prepare_rank_depth_panel
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec


def _analysis_mart_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 10):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        for serp_rank in range(1, 3):
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
                    "bge_raw_score": 0.9 - (keyword_index * 0.01),
                    "bge_normalized_score": 0.9 - (keyword_index * 0.01),
                    "gemini_doc_retrieval_raw_score": 0.8,
                    "gemini_doc_retrieval_normalized_score": 0.8,
                    "gemini_semantic_similarity_raw_score": 0.7,
                    "gemini_semantic_similarity_normalized_score": 0.7,
                    "schema_version": "analysis_mart.v1",
                }
            )

    rows.append(
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-10",
            "target_keyword": "keyword 10",
            "keyword_order": 10,
            "source_response_id": "resp-10",
            "serp_item_id": "serp-10-1",
            "page_id": "page-10-1",
            "response_id": "page-resp-10-1",
            "canonical_url_hash": "url-10-1",
            "url": "https://example.com/10/1",
            "serp_rank": 1,
            "title": "title-10-1",
            "description": "description-10-1",
            "page_text_length": 101,
            "bge_raw_score": None,
            "bge_normalized_score": None,
            "gemini_doc_retrieval_raw_score": 0.8,
            "gemini_doc_retrieval_normalized_score": 0.8,
            "gemini_semantic_similarity_raw_score": 0.7,
            "gemini_semantic_similarity_normalized_score": 0.7,
            "schema_version": "analysis_mart.v1",
        }
    )
    rows.append(
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-10",
            "target_keyword": "keyword 10",
            "keyword_order": 10,
            "source_response_id": "resp-10",
            "serp_item_id": "serp-10-2",
            "page_id": "page-10-2",
            "response_id": "page-resp-10-2",
            "canonical_url_hash": "url-10-2",
            "url": "https://example.com/10/2",
            "serp_rank": 2,
            "title": "title-10-2",
            "description": "description-10-2",
            "page_text_length": 102,
            "bge_raw_score": 0.81,
            "bge_normalized_score": 0.81,
            "gemini_doc_retrieval_raw_score": 0.0,
            "gemini_doc_retrieval_normalized_score": 0.0,
            "gemini_semantic_similarity_raw_score": 0.7,
            "gemini_semantic_similarity_normalized_score": 0.7,
            "schema_version": "analysis_mart.v1",
        }
    )
    return pl.DataFrame(rows)


def _zero_serp_variance_frame() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": "serp-1-1",
                "page_id": "page-1-1",
                "response_id": "page-resp-1-1",
                "canonical_url_hash": "url-1-1",
                "url": "https://example.com/1/1",
                "serp_rank": 1,
                "title": "title-1-1",
                "description": "description-1-1",
                "page_text_length": 100,
                "bge_raw_score": 0.5,
                "bge_normalized_score": 0.5,
                "gemini_doc_retrieval_raw_score": 0.8,
                "gemini_doc_retrieval_normalized_score": 0.8,
                "gemini_semantic_similarity_raw_score": 0.7,
                "gemini_semantic_similarity_normalized_score": 0.7,
                "schema_version": "analysis_mart.v1",
            },
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": "serp-1-2",
                "page_id": "page-1-2",
                "response_id": "page-resp-1-2",
                "canonical_url_hash": "url-1-2",
                "url": "https://example.com/1/2",
                "serp_rank": 1,
                "title": "title-1-2",
                "description": "description-1-2",
                "page_text_length": 101,
                "bge_raw_score": 0.6,
                "bge_normalized_score": 0.6,
                "gemini_doc_retrieval_raw_score": 0.8,
                "gemini_doc_retrieval_normalized_score": 0.8,
                "gemini_semantic_similarity_raw_score": 0.7,
                "gemini_semantic_similarity_normalized_score": 0.7,
                "schema_version": "analysis_mart.v1",
            },
        ]
    )


def _analysis_spec_with_primary_rank_depth(depth_key: str) -> AnalysisSpec:
    spec = load_analysis_spec()
    data = dict(spec.data)
    rank_depths = dict(data["rank_depths"])
    rank_depths["primary"] = depth_key
    data["rank_depths"] = rank_depths
    return AnalysisSpec(
        path=spec.path,
        source_path=spec.source_path,
        data=MappingProxyType(data),
        _signal_families=spec.signal_families,
    )


def _analysis_mart_frame_with_depth(max_rank: int) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for serp_rank in range(1, max_rank + 1):
        rows.append(
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": f"serp-1-{serp_rank}",
                "page_id": f"page-1-{serp_rank}",
                "response_id": f"page-resp-1-{serp_rank}",
                "canonical_url_hash": f"url-1-{serp_rank}",
                "url": f"https://example.com/1/{serp_rank}",
                "serp_rank": serp_rank,
                "title": f"title-1-{serp_rank}",
                "description": f"description-1-{serp_rank}",
                "page_text_length": 100 + serp_rank,
                "bge_raw_score": 1.0 - serp_rank * 0.01,
                "bge_normalized_score": 1.0 - serp_rank * 0.01,
                "gemini_doc_retrieval_raw_score": 0.8,
                "gemini_doc_retrieval_normalized_score": 0.8,
                "gemini_semantic_similarity_raw_score": 0.7,
                "gemini_semantic_similarity_normalized_score": 0.7,
                "schema_version": "analysis_mart.v1",
            }
        )
    return pl.DataFrame(rows)


def test_load_analysis_panel_filters_top20_and_evaluates_guardrails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _analysis_mart_frame().lazy(),
    )

    result = load_analysis_panel(run_dir)

    assert result.hard_fail is False
    assert result.primary_backend == "bge"
    assert result.analysis_mart.height == 20
    assert result.panel.height == 19
    assert result.panel.filter(pl.col("bge_normalized_score").is_null()).height == 0
    assert result.guardrails == [
        {
            "name": "serp_rank_variance_within_keyword",
            "status": "pass",
            "value": 0.25,
            "threshold": 0,
        },
        {
            "name": "similarity_variance_within_keyword",
            "status": "warn",
            "value": {
                "bge": 0.0,
                "gemini_doc_retrieval": 0.0,
                "gemini_semantic_similarity": 0.0,
            },
            "threshold": 0,
        },
    ]
    assert result.limitations == {
        "observational_only": "Associations are observational, not causal.",
        "top_20_truncation": "Associations are limited to observed top-20 SERP rows per keyword.",
        "no_causal_claims": "Do not interpret coefficients as causal ranking factors.",
        "measurement_error_conservative": "Similarity scores are model outputs and may attenuate effects.",
    }


def test_prepare_analysis_panel_uses_spec_primary_rank_depth_limit(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    spec = _analysis_spec_with_primary_rank_depth("top_10")
    analysis_mart = _analysis_mart_frame_with_depth(15)

    result = prepare_analysis_panel(run_dir, analysis_mart, spec=spec)

    assert result.analysis_mart.height == 10
    assert result.analysis_mart.select(pl.col("serp_rank").max()).item() == 10
    assert result.panel.height == 10


def test_load_analysis_panel_logs_panel_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _analysis_mart_frame().lazy(),
    )
    caplog.set_level(logging.INFO, logger="seo_rank.stats.panel")

    load_analysis_panel(run_dir)

    messages = [record.getMessage() for record in caplog.records]
    assert any("loading analysis panel" in message for message in messages)
    assert any("loaded analysis panel" in message and "mart_rows=20" in message for message in messages)
    assert any("prepared analysis panel" in message for message in messages)


def test_prepare_rank_depth_panel_logs_depth_shape(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = load_analysis_spec()
    frame = _analysis_mart_frame()
    caplog.set_level(logging.INFO, logger="seo_rank.stats.panel")

    prepare_rank_depth_panel(frame, depth_key="top_10", spec=spec)

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "prepared rank_depth_panel depth=top_10 max_rank=10" in message for message in messages
    )


def test_load_analysis_panel_hard_fails_when_serp_rank_has_no_variance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _zero_serp_variance_frame().lazy(),
    )

    result = load_analysis_panel(run_dir)

    assert result.hard_fail is True
    assert result.guardrails[0] == {
        "name": "serp_rank_variance_within_keyword",
        "status": "fail",
        "value": 0.0,
        "threshold": 0,
    }


def test_run_phase5_stats_writes_full_artifacts_when_guardrails_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _analysis_mart_frame().lazy(),
    )

    result = run_phase5_stats(run_dir)

    summary_path = run_dir / "stats" / "stats_summary.json"
    report_path = run_dir / "stats" / "stats_report.md"
    diagnostics_path = run_dir / "stats" / "stats_diagnostics.json"

    assert summary_path.exists()
    assert report_path.exists()
    assert diagnostics_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert result.hard_fail is False
    assert "regression" in summary
    assert "spearman" in summary
    assert "## Rank depth: top_20" in report
    assert "Confirmatory inference skipped" not in report


def test_run_phase5_stats_writes_minimal_report_on_hard_fail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _zero_serp_variance_frame().lazy(),
    )

    result = run_phase5_stats(run_dir)

    summary_path = run_dir / "stats" / "stats_summary.json"
    report_path = run_dir / "stats" / "stats_report.md"

    assert summary_path.exists()
    assert report_path.exists()
    assert not (run_dir / "stats" / "stats_diagnostics.json").exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert result.hard_fail is True
    assert "regression" not in summary
    assert "spearman" not in summary
    assert "rank_depths" in summary
    assert summary["rank_depths"]["top_20"]["hard_fail"] is True
    report = report_path.read_text(encoding="utf-8")
    assert "## Rank depth: top_20" in report
    assert "Confirmatory inference skipped" in report
