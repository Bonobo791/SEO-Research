from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from seo_rank.stats.artifacts import build_rank_depth_bundles, run_phase5_stats
from seo_rank.stats.plackett_luce import summarize_backend_plackett_luce
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.regression import summarize_regression_rank_depths
from seo_rank.stats.spearman import summarize_spearman_rank_depths
from seo_rank.stats.spec import load_analysis_spec


def _sample_panel() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 3):
        for serp_rank in range(1, 21):
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "serp_rank": serp_rank,
                    "serp_item_id": f"serp-{keyword_index}-{serp_rank}",
                }
            )
    return pl.DataFrame(rows)


def _depth_divergent_panel(*, keyword_count: int = 12) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, keyword_count + 1):
        keyword_id = f"kw-{keyword_index}"
        for serp_rank in range(1, 21):
            if serp_rank <= 5:
                similarity = float(6 - serp_rank)
            else:
                similarity = 0.0
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": keyword_id,
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
                    "page_text_length": 200 + serp_rank,
                    "referring_domains_count": 200 + serp_rank,
                    "deprecated_html_tags": serp_rank % 2 == 0,
                    "meta_keywords_to_content_consistency": 0.1 + (serp_rank * 0.05),
                    "bge_normalized_score": similarity,
                    "gemini_doc_retrieval_normalized_score": similarity * 0.8,
                    "gemini_semantic_similarity_normalized_score": similarity * 0.6,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def test_load_analysis_spec_includes_rank_depths() -> None:
    analysis_spec = load_analysis_spec()

    assert analysis_spec.primary_rank_depth == "top_20"
    assert analysis_spec.confirmatory_rank_depths == ("top_20", "top_10", "top_5", "top_3")
    assert analysis_spec.rank_depth_limit("top_10") == 10
    assert analysis_spec.limitation_key_for_rank_depth("top_5") == "top_5_truncation"


def test_filter_panel_by_max_rank_keeps_rows_up_to_limit() -> None:
    panel = _sample_panel()

    top_10 = filter_panel_by_max_rank(panel, max_rank=10)

    assert top_10.height == 20
    assert top_10.get_column("serp_rank").max() == 10
    assert top_10.filter(pl.col("serp_rank") > 10).is_empty()


def test_filter_panel_by_max_rank_logs_row_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="seo_rank.stats.rank_depth")

    filter_panel_by_max_rank(_sample_panel(), max_rank=10)

    messages = [record.getMessage() for record in caplog.records]
    assert any("filter_panel_by_max_rank max_rank=10" in message and "rows=40 -> 20" in message for message in messages)


def test_summarize_spearman_rank_depths_differs_by_depth() -> None:
    spec = load_analysis_spec()
    panel = _depth_divergent_panel()

    summary = summarize_spearman_rank_depths(
        panel,
        spec.backend_order,
        depth_order=spec.confirmatory_rank_depths,
        spec=spec,
    )

    top_20 = summary["depths"]["top_20"]["backends"]["bge"]["median_rho"]
    top_5 = summary["depths"]["top_5"]["backends"]["bge"]["median_rho"]
    assert top_20 != top_5


def test_summarize_regression_rank_depths_emits_all_depths() -> None:
    spec = load_analysis_spec()
    panel = _depth_divergent_panel()

    summary = summarize_regression_rank_depths(
        panel,
        spec.backend_order,
        depth_order=spec.confirmatory_rank_depths,
        spec=spec,
    )

    assert summary["depth_order"] == ["top_20", "top_10", "top_5", "top_3"]
    assert "feature_model" in summary["depths"]["top_3"]["backends"]["bge"]


def test_summarize_backend_plackett_luce_top_5_choice_set_is_bounded() -> None:
    panel = _depth_divergent_panel(keyword_count=12)
    summary = summarize_backend_plackett_luce(
        filter_panel_by_max_rank(panel, max_rank=5),
        backend="bge",
    )

    assert summary["status"] in {"computed", "unstable"}
    assert summary["choice_set_size_summary"]["max"] <= 5


def test_build_rank_depth_bundles_has_monotonic_row_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    from seo_rank.stats import panel as panel_module

    monkeypatch.setattr(
        panel_module,
        "scan_curated_table",
        lambda path, table_name: _depth_divergent_panel().lazy(),
    )

    from seo_rank.stats.panel import load_analysis_panel

    result = load_analysis_panel(run_dir)
    spec = load_analysis_spec()
    bundles, diagnostics = build_rank_depth_bundles(result, spec=spec)

    row_counts = [int(bundles[depth]["analysis_mart_rows"]) for depth in spec.confirmatory_rank_depths]
    assert row_counts == sorted(row_counts, reverse=True)
    assert diagnostics["top_20"]["regression"]["backends"]["bge"]["backend"] == "bge"


def test_run_phase5_stats_emits_rank_depth_summary_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: _depth_divergent_panel().lazy(),
    )

    run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert set(summary["rank_depths"]) == {"top_20", "top_10", "top_5", "top_3"}
    assert set(summary["actionable_association_by_rank_depth"]) == {
        "top_20",
        "top_10",
        "top_5",
        "top_3",
    }
    for depth_key in ("top_20", "top_10", "top_5", "top_3"):
        assert f"## Rank depth: {depth_key}" in report

    messages = [record.getMessage() for record in caplog.records]
    assert any("running phase5 stats" in message for message in messages)
    assert any("phase5 stats complete" in message for message in messages)
    assert any("building rank_depth bundles" in message for message in messages)
    assert any("wrote stats artifacts" in message for message in messages)
