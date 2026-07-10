from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from seo_rank.data.features import ONPAGE_FEATURES_EXPECTED_SCHEMA, ONPAGE_FEATURES_EXTRA_COLUMNS
from seo_rank.stats.artifacts import _format_regression_lines
from seo_rank.stats.artifacts import build_family_source_frames
from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.spec import load_analysis_spec


def _combined_analysis_mart_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 4):
            signal = float(4 - serp_rank) + keyword_offset
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
                    "page_text_length": 120 + (keyword_index * 3) + serp_rank,
                    "referring_domains_count": 120 + (keyword_index * 3) + serp_rank,
                    "deprecated_html_tags": (keyword_index + serp_rank) % 3 == 0,
                    "meta_keywords_to_content_consistency": 0.5,
                    "site_scale": (keyword_index * 0.1) + (serp_rank * 0.01),
                    "bge_raw_score": signal,
                    "bge_normalized_score": signal,
                    "gemini_doc_retrieval_raw_score": signal - 0.1,
                    "gemini_doc_retrieval_normalized_score": signal - 0.1,
                    "gemini_semantic_similarity_raw_score": signal - 0.2,
                    "gemini_semantic_similarity_normalized_score": signal - 0.2,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def _combined_textrazor_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 4):
            signal = float(4 - serp_rank) + keyword_offset
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": f"page-resp-{keyword_index}-{serp_rank}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "url": f"https://example.com/{keyword_index}/{serp_rank}",
                    "page_metrics_row_id": f"metrics-{keyword_index}-{serp_rank}",
                    "textrazor_entity_confidence_score": signal + 0.5,
                    "textrazor_entity_relevance_score": signal + 0.4,
                    "textrazor_topic_score": signal + 0.3,
                    "textrazor_category_score": signal + 0.2,
                    "textrazor_classifier_score": signal + 0.1,
                    "textrazor_entailment_score": signal + 0.05,
                    "textrazor_entailment_prior": signal - 0.05,
                    "textrazor_entailment_context": signal - 0.1,
                    "textrazor_word_count": 20 + serp_rank,
                    "textrazor_grammar_count": 2 + serp_rank,
                    "textrazor_sense_count": 1 + serp_rank,
                    "textrazor_spelling_count": 1,
                    "textrazor_relation_count": None,
                    "textrazor_property_count": None,
                    "textrazor_noun_phrase_count": None,
                    "schema_version": "curated.v1",
                }
            )
    return pl.DataFrame(rows)


def test_format_regression_lines_handles_control_error_summary() -> None:
    regression = {
        "backends": {
            "onpage_core_web_vitals": {
                "backend": "onpage_core_web_vitals",
                "score_column": "onpage_core_web_vitals_score",
                "status": "error",
                "error_note": "required control data is incomplete; model not fit",
                "invalid_controls": [
                    {"column": "time_to_first_byte_ms", "reason": "missing_values"}
                ],
            }
        }
    }

    lines = _format_regression_lines(regression)

    assert lines == [
        "- onpage_core_web_vitals: status=error, "
        "error_note=required control data is incomplete; model not fit, "
        "invalid_controls=[{'column': 'time_to_first_byte_ms', "
        "'reason': 'missing_values'}]"
    ]


def _combined_backlinks_analysis_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for row in _combined_analysis_mart_frame().to_dicts():
        keyword_index = int(str(row["target_keyword_id"]).split("-")[-1])
        serp_rank = int(row["serp_rank"])
        rows.append(
            {
                **row,
                "backlink_id": f"backlink-{keyword_index}-{serp_rank}",
                "summary_response_id": f"backlinks-summary-{keyword_index}-{serp_rank}",
                "dofollow_summary_response_id": f"backlinks-dofollow-{keyword_index}-{serp_rank}",
                "backlinks_count": 42 + keyword_index + serp_rank,
                "referring_domains_count": 12 + keyword_index,
                "deprecated_html_tags": keyword_index % 2 == 0,
                "dofollow_backlinks_count": 35 + keyword_index,
                "dofollow_referring_domains_count": 10 + keyword_index,
                "rank": 400 + serp_rank,
                "backlinks_spam_score": 1 + serp_rank,
                "target_spam_score": 6,
                "new_backlinks": 2 + serp_rank,
                "lost_backlinks": 1,
                "new_referring_domains": 3,
                "lost_referring_domains": 1,
                "referring_pages": 20 + serp_rank,
                "referring_main_domains": 15 + serp_rank,
                "referring_ips": 5 + serp_rank,
                "referring_subnets": 4 + serp_rank,
                "broken_backlinks": 0,
                "broken_pages": 0,
                "referring_domains_nofollow": 8 + serp_rank,
                "crawled_pages": 100 + serp_rank,
                "internal_links_count": 200 + serp_rank,
                "external_links_count": 300 + serp_rank,
                "first_seen": "2026-07-01",
                "lost_date": None,
                "referring_links_types_json": "{\"nofollow\":1}",
                "referring_links_tld_json": "{\"com\":1}",
                "referring_links_platform_types_json": "{\"cms\":1}",
                "referring_links_semantic_locations_json": "{\"content\":1}",
                "referring_links_attributes_json": "{\"rel\":1}",
                "referring_links_countries_json": "{\"us\":1}",
                "backlinks_metrics_complete": True,
                "schema_version": "feature_marts.v1",
            }
        )
    return pl.DataFrame(rows)


def _onpage_column_default(
    column: str,
    *,
    keyword_index: int,
    serp_rank: int,
    signal: float,
) -> object:
    dtype = ONPAGE_FEATURES_EXPECTED_SCHEMA[column]
    if dtype == pl.Boolean:
        return (keyword_index + serp_rank) % 2 == 0
    if dtype == pl.Int64:
        return serp_rank + keyword_index
    if dtype == pl.Float64:
        if column in {
            "description_to_content_consistency",
            "title_to_content_consistency",
            "meta_keywords_to_content_consistency",
            "plain_text_rate",
            "cumulative_layout_shift",
        }:
            return 0.1 + serp_rank * 0.05
        return float(signal)
    if dtype == pl.Utf8:
        return f"{column}-{keyword_index}-{serp_rank}"
    raise TypeError(f"unsupported onpage_features dtype for {column}: {dtype}")


def _combined_onpage_features_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for row in _combined_analysis_mart_frame().to_dicts():
        keyword_index = int(str(row["target_keyword_id"]).split("-")[-1])
        serp_rank = int(row["serp_rank"])
        signal = float(4 - serp_rank) + keyword_index * 0.01
        row = {
                **row,
                "onpage_signal_id": f"onpage-{keyword_index}-{serp_rank}",
                "onpage_score": 60.0 + signal * 10.0,
                "title_too_long": serp_rank == 1,
                "title_too_short": serp_rank == 2,
                "no_title": keyword_index % 3 == 0,
                "no_description": keyword_index % 4 == 0,
                "no_h1_tag": serp_rank == 3,
                "canonical": serp_rank != 1,
                "is_https": serp_rank != 2,
                "has_render_blocking_resources": serp_rank == 1,
                "duplicate_meta_tags": keyword_index % 5 == 0,
                "has_meta_title": serp_rank != 2,
                "irrelevant_description": keyword_index % 6 == 0,
                "low_readability_rate": serp_rank == 2,
                "plain_text_word_count": 500.0 + serp_rank * 10.0 + keyword_index,
                "plain_text_rate": 0.02 + serp_rank * 0.001,
                "flesch_kincaid_readability_index": 50.0 + signal,
                "coleman_liau_readability_index": 10.0 + signal,
                "smog_readability_index": 8.0 + signal,
                "dale_chall_readability_index": 7.0 + signal,
                "time_to_first_byte_ms": 100 + serp_rank * 10 + keyword_index,
                "largest_contentful_paint_ms": 2000.0 - serp_rank * 100.0,
                "cumulative_layout_shift": 0.05 + serp_rank * 0.01,
                "total_transfer_size": 100_000 + serp_rank * 1000 + keyword_index,
                "micromarkup_items_count": 2 + serp_rank,
                "micromarkup_errors_count": serp_rank - 1,
                "micromarkup_warnings_count": keyword_index % 3,
                "has_valid_structured_data": serp_rank != 3,
                "schema_version": "feature_marts.v1",
            }
        for column in ONPAGE_FEATURES_EXTRA_COLUMNS:
            if column not in row:
                row[column] = _onpage_column_default(
                    column,
                    keyword_index=keyword_index,
                    serp_rank=serp_rank,
                    signal=signal,
                )
        rows.append(row)
    return pl.DataFrame(rows)


def _single_keyword_analysis_mart_frame() -> pl.DataFrame:
    return _combined_analysis_mart_frame().filter(pl.col("target_keyword_id") == "kw-1")


def test_run_phase5_stats_emits_combined_family_tree_and_keeps_similarity_compatibility(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "backlinks_analysis").mkdir(parents=True)
    (run_dir / "parquet" / "onpage_features").mkdir(parents=True)
    (run_dir / "parquet" / "textrazor_page_metrics").mkdir(parents=True)

    _combined_analysis_mart_frame().write_parquet(
        run_dir / "parquet" / "analysis_mart" / "part-0.parquet"
    )
    _combined_backlinks_analysis_frame().write_parquet(
        run_dir / "parquet" / "backlinks_analysis" / "part-0.parquet"
    )
    _combined_onpage_features_frame().write_parquet(
        run_dir / "parquet" / "onpage_features" / "part-0.parquet"
    )
    _combined_textrazor_frame().write_parquet(
        run_dir / "parquet" / "textrazor_page_metrics" / "part-0.parquet"
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    diagnostics = json.loads(
        (run_dir / "stats" / "stats_diagnostics.json").read_text(encoding="utf-8")
    )
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")
    spec = load_analysis_spec()

    assert result.hard_fail is False
    assert summary["metadata"]["signal_family_order"] == list(spec.signal_family_keys)
    assert summary["spearman"]["backends"]["bge"]["backend"] == "bge"
    assert summary["regression"]["backends"]["bge"]["backend"] == "bge"
    assert summary["plackett_luce"]["backends"]["bge"]["backend"] == "bge"
    assert list(summary["rank_depths"]["top_20"]["families"]) == list(spec.signal_family_keys)
    assert summary["rank_depths"]["top_20"]["families"]["backlinks_counts"]["kind"] == "backlinks_metric"

    topic_family = summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]
    sparse_family = summary["rank_depths"]["top_20"]["families"][
        "textrazor_relation_property_noun_phrase"
    ]
    backlinks_family = summary["rank_depths"]["top_20"]["families"]["backlinks_counts"]
    onpage_quality_family = summary["rank_depths"]["top_20"]["families"]["onpage_content_quality"]
    onpage_cwv_family = summary["rank_depths"]["top_20"]["families"]["onpage_core_web_vitals"]

    assert topic_family["spearman"]["signals"]["textrazor_topic_score"]["status"] == "computed"
    assert topic_family["regression"]["signals"]["textrazor_topic_score"]["status"] == "computed"
    assert topic_family["diagnostics"]["signals"]["textrazor_topic_score"]["status"] == "computed"
    assert topic_family["plackett_luce"]["signals"]["textrazor_topic_score"]["status"] in {
        "computed",
        "unstable",
    }
    assert sparse_family["spearman"]["status"] == "skipped"
    assert sparse_family["regression"]["status"] == "skipped"
    assert sparse_family["diagnostics"]["status"] == "skipped"
    assert sparse_family["plackett_luce"]["status"] == "skipped"
    assert backlinks_family["spearman"]["signals"]["backlinks_count"]["status"] == "computed"
    assert backlinks_family["regression"]["signals"]["backlinks_count"]["status"] == "computed"
    assert backlinks_family["diagnostics"]["signals"]["backlinks_count"]["status"] == "computed"
    assert backlinks_family["plackett_luce"]["signals"]["backlinks_count"]["status"] in {
        "computed",
        "unstable",
    }
    assert onpage_quality_family["spearman"]["signals"]["onpage_score"]["status"] == "computed"
    assert onpage_quality_family["regression"]["signals"]["onpage_score"]["status"] == "computed"
    assert onpage_cwv_family["spearman"]["signals"]["time_to_first_byte_ms"]["status"] == "computed"
    onpage_technical_family = summary["rank_depths"]["top_20"]["families"]["onpage_technical_checks"]
    assert onpage_technical_family["regression"]["signals"]["title_too_long"]["status"] == "computed"
    assert onpage_quality_family["plackett_luce"]["signals"]["onpage_score"]["status"] in {
        "computed",
        "unstable",
    }
    assert onpage_cwv_family["plackett_luce"]["signals"]["time_to_first_byte_ms"]["status"] in {
        "computed",
        "unstable",
    }
    assert onpage_technical_family["plackett_luce"]["signals"]["title_too_long"]["status"] in {
        "computed",
        "unstable",
        "skipped",
    }

    assert diagnostics["metadata"]["signal_family_order"] == list(spec.signal_family_keys)
    assert diagnostics["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["diagnostics"][
        "signals"
    ]["textrazor_topic_score"]["status"] == "computed"
    assert diagnostics["rank_depths"]["top_20"]["families"]["backlinks_counts"]["diagnostics"][
        "signals"
    ]["backlinks_count"]["status"] == "computed"
    assert "### Families" in report
    assert "#### Family: textrazor_topic_score" in report
    assert "#### Family: textrazor_relation_property_noun_phrase" in report
    assert "#### Family: backlinks_counts" in report
    assert "#### Family: onpage_content_quality" in report
    assert "#### Family: onpage_core_web_vitals" in report
    assert "#### Family: onpage_technical_checks" in report


def test_run_phase5_stats_rebuilds_onpage_features_for_legacy_run_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text('{"catalog": {"datasets": {}}}', encoding="utf-8")
    parquet_dir = run_dir / "parquet"
    for name in (
        "keyword_serp",
        "page_features",
        "passage_features",
        "domain_features",
        "backlinks_analysis",
    ):
        (parquet_dir / name).mkdir(parents=True)
        pl.DataFrame([{"run_id": "run-1"}]).write_parquet(parquet_dir / name / "part-0.parquet")

    (parquet_dir / "analysis_mart").mkdir(parents=True)
    (parquet_dir / "backlinks_analysis").mkdir(parents=True, exist_ok=True)
    (parquet_dir / "textrazor_page_metrics").mkdir(parents=True)
    _combined_analysis_mart_frame().write_parquet(parquet_dir / "analysis_mart" / "part-0.parquet")
    _combined_backlinks_analysis_frame().write_parquet(
        parquet_dir / "backlinks_analysis" / "part-0.parquet"
    )
    _combined_textrazor_frame().write_parquet(
        parquet_dir / "textrazor_page_metrics" / "part-0.parquet"
    )

    build_calls: list[Path] = []

    def materialize_onpage_features(path: Path) -> dict[str, object]:
        build_calls.append(path)
        onpage_dir = path / "parquet" / "onpage_features"
        onpage_dir.mkdir(parents=True, exist_ok=True)
        _combined_onpage_features_frame().write_parquet(onpage_dir / "part-0.parquet")
        return {"datasets": {}}

    monkeypatch.setattr(
        "seo_rank.data.features.build_feature_marts",
        materialize_onpage_features,
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    onpage_quality = summary["rank_depths"]["top_20"]["families"]["onpage_content_quality"]

    assert build_calls == [run_dir]
    assert result.hard_fail is False
    assert onpage_quality["spearman"]["signals"]["onpage_score"]["status"] == "computed"
    assert onpage_quality["regression"]["signals"]["onpage_score"]["status"] == "computed"


def test_build_family_source_frames_loads_onpage_features_when_present(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "onpage_features").mkdir(parents=True)
    analysis_mart = _combined_analysis_mart_frame()
    onpage_features = _combined_onpage_features_frame()
    analysis_mart.write_parquet(run_dir / "parquet" / "analysis_mart" / "part-0.parquet")
    onpage_features.write_parquet(run_dir / "parquet" / "onpage_features" / "part-0.parquet")

    spec = load_analysis_spec()
    source_frames = build_family_source_frames(
        run_dir,
        analysis_mart=analysis_mart,
        spec=spec,
    )

    assert not source_frames["onpage_features"].is_empty()
    assert source_frames["onpage_features"].height == onpage_features.height
    assert "onpage_score" in source_frames["onpage_features"].columns


def test_build_family_source_frames_restores_missing_controls_from_analysis_mart(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "backlinks_analysis").mkdir(parents=True)
    analysis_mart = _combined_analysis_mart_frame()
    legacy_backlinks = _combined_backlinks_analysis_frame().drop("deprecated_html_tags")
    legacy_backlinks.write_parquet(
        run_dir / "parquet" / "backlinks_analysis" / "part-0.parquet"
    )

    source_frames = build_family_source_frames(
        run_dir,
        analysis_mart=analysis_mart,
        spec=load_analysis_spec(),
    )

    restored = source_frames["backlinks_analysis"]
    assert "deprecated_html_tags" in restored.columns
    assert restored.get_column("deprecated_html_tags").to_list() == analysis_mart.get_column(
        "deprecated_html_tags"
    ).to_list()


def test_build_family_source_frames_restores_latency_control_from_analysis_mart(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "onpage_features").mkdir(parents=True)
    analysis_mart = _combined_analysis_mart_frame().with_columns(
        (pl.arange(0, pl.len()) + 100).cast(pl.Int64).alias("time_to_first_byte_ms")
    )
    legacy_onpage = _combined_onpage_features_frame().drop("time_to_first_byte_ms")
    legacy_onpage.write_parquet(run_dir / "parquet" / "onpage_features" / "part-0.parquet")

    source_frames = build_family_source_frames(
        run_dir,
        analysis_mart=analysis_mart,
        spec=load_analysis_spec(),
    )

    restored = source_frames["onpage_features"]
    assert restored.get_column("time_to_first_byte_ms").to_list() == analysis_mart.get_column(
        "time_to_first_byte_ms"
    ).to_list()


def test_run_phase5_stats_marks_textrazor_family_blocks_skipped_on_hard_fail(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "backlinks_analysis").mkdir(parents=True)
    (run_dir / "parquet" / "onpage_features").mkdir(parents=True)
    (run_dir / "parquet" / "textrazor_page_metrics").mkdir(parents=True)

    hard_fail_frame = _combined_analysis_mart_frame().with_columns(
        pl.lit(1, dtype=pl.Int64).alias("serp_rank")
    )
    hard_fail_frame.write_parquet(run_dir / "parquet" / "analysis_mart" / "part-0.parquet")
    _combined_backlinks_analysis_frame().write_parquet(
        run_dir / "parquet" / "backlinks_analysis" / "part-0.parquet"
    )
    _combined_onpage_features_frame().write_parquet(
        run_dir / "parquet" / "onpage_features" / "part-0.parquet"
    )
    _combined_textrazor_frame().write_parquet(
        run_dir / "parquet" / "textrazor_page_metrics" / "part-0.parquet"
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert result.hard_fail is True
    assert summary["hard_fail"] is True
    assert summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["spearman"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["regression"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["diagnostics"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["plackett_luce"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["backlinks_counts"]["spearman"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["backlinks_counts"]["regression"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["backlinks_counts"]["diagnostics"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["backlinks_counts"]["plackett_luce"][
        "status"
    ] == "skipped"
    for onpage_family_key in (
        "onpage_content_quality",
        "onpage_core_web_vitals",
        "onpage_technical_checks",
    ):
        onpage_family = summary["rank_depths"]["top_20"]["families"][onpage_family_key]
        assert onpage_family["spearman"]["status"] == "skipped"
        assert onpage_family["regression"]["status"] == "skipped"
        assert onpage_family["diagnostics"]["status"] == "skipped"
        assert onpage_family["plackett_luce"]["status"] == "skipped"
    assert "Confirmatory inference skipped because hard-fail guardrails did not pass." in report
    assert "#### Family: textrazor_topic_score" in report
    assert "#### Family: backlinks_counts" in report
    assert "#### Family: onpage_content_quality" in report
    assert "#### Family: onpage_core_web_vitals" in report
    assert "#### Family: onpage_technical_checks" in report


def test_run_phase5_stats_marks_single_keyword_runs_as_underpowered(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    _single_keyword_analysis_mart_frame().write_parquet(
        run_dir / "parquet" / "analysis_mart" / "part-0.parquet"
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert result.hard_fail is False
    assert summary["rank_depths"]["top_20"]["keyword_count"] == 1
    assert summary["rank_depths"]["top_20"]["inference_mode"] == "underpowered"
    assert (
        summary["rank_depths"]["top_20"]["spearman"]["backends"]["bge"]["inference_mode"]
        == "underpowered"
    )
    assert (
        summary["rank_depths"]["top_20"]["regression"]["backends"]["bge"]["inference_mode"]
        == "underpowered"
    )
    assert "inference_mode=underpowered" in report
    assert "confirmatory inference may proceed" not in report
