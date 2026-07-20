import json
import logging
from pathlib import Path
from types import MappingProxyType

import polars as pl
import pytest

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.panel import (
    _restore_analysis_controls,
    load_analysis_panel,
    prepare_analysis_panel,
    prepare_rank_depth_panel,
)
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec


def _analysis_mart_frame() -> pl.DataFrame:
    """Build a synthetic analysis mart containing ranked keyword results and domain controls.
    
    Returns:
    	pl.DataFrame: An in-memory analysis mart with model scores, SERP metadata, and domain control columns.
    """
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
                    "referring_domains_count": 100 + serp_rank,
                    "deprecated_html_tags": serp_rank % 2 == 0,
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
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
            "referring_domains_count": 101,
            "deprecated_html_tags": False,
            "meta_keywords_to_content_consistency": 0.1,
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
            "referring_domains_count": 102,
            "deprecated_html_tags": False,
            "meta_keywords_to_content_consistency": 0.2,
            "bge_raw_score": 0.81,
            "bge_normalized_score": 0.81,
            "gemini_doc_retrieval_raw_score": 0.0,
            "gemini_doc_retrieval_normalized_score": 0.0,
            "gemini_semantic_similarity_raw_score": 0.7,
            "gemini_semantic_similarity_normalized_score": 0.7,
            "schema_version": "analysis_mart.v1",
        }
    )
    return pl.DataFrame(rows).with_columns(
        pl.lit(0.5).alias("site_scale"),
        pl.lit(0.25).alias("authority_proxy"),
    )


def _zero_serp_variance_frame() -> pl.DataFrame:
    """Create a synthetic analysis mart with no SERP-rank variance within a keyword.
    
    Returns:
    	pl.DataFrame: Two rows for one keyword sharing the same SERP rank, with varying score values and domain controls.
    """
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
                "referring_domains_count": 100,
                "deprecated_html_tags": False,
                "meta_keywords_to_content_consistency": 0.1,
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
                "referring_domains_count": 101,
                "deprecated_html_tags": False,
                "meta_keywords_to_content_consistency": 0.2,
                "bge_raw_score": 0.6,
                "bge_normalized_score": 0.6,
                "gemini_doc_retrieval_raw_score": 0.8,
                "gemini_doc_retrieval_normalized_score": 0.8,
                "gemini_semantic_similarity_raw_score": 0.7,
                "gemini_semantic_similarity_normalized_score": 0.7,
                "schema_version": "analysis_mart.v1",
            },
        ]
    ).with_columns(
        pl.lit(0.5).alias("site_scale"),
        pl.lit(0.25).alias("authority_proxy"),
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
    """Create a synthetic analysis mart with rows spanning the requested SERP rank depth.
    
    Parameters:
    	max_rank (int): Maximum SERP rank to include.
    
    Returns:
    	pl.DataFrame: Analysis mart rows with synthetic ranking metrics and domain controls.
    """
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
                "referring_domains_count": 100 + serp_rank,
                "deprecated_html_tags": serp_rank % 2 == 0,
                "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                "bge_raw_score": 1.0 - serp_rank * 0.01,
                "bge_normalized_score": 1.0 - serp_rank * 0.01,
                "gemini_doc_retrieval_raw_score": 0.8,
                "gemini_doc_retrieval_normalized_score": 0.8,
                "gemini_semantic_similarity_raw_score": 0.7,
                "gemini_semantic_similarity_normalized_score": 0.7,
                "schema_version": "analysis_mart.v1",
            }
        )
    return pl.DataFrame(rows).with_columns(
        pl.lit(0.5).alias("site_scale"),
        pl.lit(0.25).alias("authority_proxy"),
    )



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



def test_load_analysis_panel_restores_authority_proxy_from_domain_features(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "domain_features").mkdir(parents=True)

    analysis_mart = (
        _analysis_mart_frame()
        .drop("authority_proxy")
        .with_columns(pl.lit(0.5).alias("site_scale"))
    )
    domain_features = pl.DataFrame(
        {
            "run_id": ["run-1"],
            "domain": ["example.com"],
            "site_scale": [0.5],
            "authority_proxy": [0.42],
            "schema_version": ["domain_features.v1"],
        }
    )

    def _scan(path, table_name):
        if table_name == "analysis_mart":
            return analysis_mart.lazy()
        if table_name == "domain_features":
            return domain_features.lazy()
        raise AssertionError(f"unexpected table {table_name}")

    monkeypatch.setattr("seo_rank.stats.panel.scan_curated_table", _scan)

    result = load_analysis_panel(run_dir)

    assert "authority_proxy" in result.analysis_mart.columns
    assert result.analysis_mart["authority_proxy"].null_count() == 0
    assert result.analysis_mart["authority_proxy"].unique().to_list() == [0.42]


def test_load_analysis_panel_does_not_null_fill_missing_domain_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    analysis_mart = _analysis_mart_frame().drop(["site_scale", "authority_proxy"])

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: analysis_mart.lazy(),
    )

    result = load_analysis_panel(run_dir)

    assert "authority_proxy" not in result.analysis_mart.columns
    assert "site_scale" not in result.analysis_mart.columns
    assert result.analysis_mart.height == analysis_mart.height


def test_restore_analysis_controls_leaves_domain_controls_absent_when_missing() -> None:
    source = pl.DataFrame(
        {
            "run_id": ["run-1"],
            "target_keyword_id": ["kw-1"],
            "canonical_url_hash": ["url-1"],
            "url": ["https://example.com/1"],
            "deprecated_html_tags": [False],
        }
    )
    analysis_mart = pl.DataFrame(
        {
            "run_id": ["run-1"],
            "target_keyword_id": ["kw-1"],
            "canonical_url_hash": ["url-1"],
            "url": ["https://example.com/1"],
            "time_to_first_byte_ms": [100],
        }
    )

    restored = _restore_analysis_controls(source, analysis_mart)

    assert "authority_proxy" not in restored.columns
    assert "site_scale" not in restored.columns
    assert "time_to_first_byte_ms" in restored.columns
    assert restored["time_to_first_byte_ms"].to_list() == [100]


def test_restore_analysis_controls_joins_domain_controls_from_analysis_mart() -> None:
    source = pl.DataFrame(
        {
            "run_id": ["run-1"],
            "target_keyword_id": ["kw-1"],
            "canonical_url_hash": ["url-1"],
            "url": ["https://example.com/1"],
        }
    )
    analysis_mart = pl.DataFrame(
        {
            "run_id": ["run-1"],
            "target_keyword_id": ["kw-1"],
            "canonical_url_hash": ["url-1"],
            "url": ["https://example.com/1"],
            "site_scale": [0.5],
            "authority_proxy": [0.42],
        }
    )

    restored = _restore_analysis_controls(source, analysis_mart)

    assert restored["authority_proxy"].to_list() == [0.42]
    assert restored["site_scale"].to_list() == [0.5]


def test_prepare_analysis_panel_keeps_rows_with_null_required_controls(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    analysis_mart = _analysis_mart_frame().with_columns(
        pl.lit(0.5).alias("site_scale"),
        pl.when(pl.col("canonical_url_hash") == "url-1-1")
        .then(None)
        .otherwise(pl.lit(0.25))
        .alias("authority_proxy"),
    )

    result = prepare_analysis_panel(run_dir, analysis_mart)

    # complete_case applies at model fit, not panel prepare — Spearman/guardrails
    # keep the full prepared panel including null-control rows.
    assert result.analysis_mart.height == analysis_mart.height
    assert result.panel.height == analysis_mart.filter(
        pl.col("bge_normalized_score").is_not_null()
    ).height
    assert result.panel.filter(pl.col("authority_proxy").is_null()).height == 1
    assert "url-1-1" in result.panel["canonical_url_hash"].to_list()


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
