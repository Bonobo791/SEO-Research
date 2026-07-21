import json
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from seo_rank.cli import main
from seo_rank.cli import RAW_RESPONSE_SCHEMA
from seo_rank.cli import build_raw_response_record
from seo_rank.data.features import BACKLINKS_ANALYSIS_REQUIRED_COLUMNS
from seo_rank.data.features import FEATURE_VALIDATION_RULES
from seo_rank.data.features import ONPAGE_FEATURES_BOUNDED_COLUMNS
from seo_rank.data.features import ONPAGE_FEATURES_EXTRA_COLUMNS
from seo_rank.data.features import ONPAGE_FEATURES_REQUIRED_COLUMNS
from seo_rank.data.features import (
    build_analysis_panel_keyword_serp,
    build_feature_marts,
    write_feature_dataset,
)
from seo_rank.data.normalize import CURATED_VALIDATION_RULES
from seo_rank.data.normalize import normalize_run
from seo_rank.data.validate import with_serp_depth_bounds
from seo_rank.dataforseo import BACKLINKS_QUERY_SUMMARY
from seo_rank.dataforseo import fixture_backlinks_response
from seo_rank.dataforseo import fixture_onpage_instant_pages_response
from seo_rank import domain_blocklist

LEGACY_ONPAGE_META_COLUMNS = (
    # Slice 12: meta block metrics
    "description_length",
    "title_length",
    "external_links_count",
    "internal_links_count",
    "images_count",
    "images_size",
    "scripts_count",
    "scripts_size",
    "stylesheets_count",
    "stylesheets_size",
    "render_blocking_scripts_count",
    "render_blocking_stylesheets_count",
    "follow",
    "inbound_links_count",
    "duplicate_meta_tags_count",
    "description_to_content_consistency",
    "title_to_content_consistency",
    "meta_keywords_to_content_consistency",
    # Slice 13: htag counts, social tags, readability
    "h1_count",
    "h2_count",
    "h3_count",
    "has_og_tags",
    "has_twitter_tags",
    "plain_text_word_count",
    "plain_text_rate",
    "flesch_kincaid_readability_index",
    "coleman_liau_readability_index",
    "smog_readability_index",
    "dale_chall_readability_index",
    # Slice 14: resource/cache/DOM/size
    "cache_control_cachable",
    "cache_control_ttl",
    "resource_errors_count",
    "resource_warnings_count",
    "broken_links",
    "broken_resources",
    "duplicate_content",
    "duplicate_description",
    "duplicate_title",
    "click_depth",
    "encoded_size",
    "total_dom_size",
    # Slice 15: page_timing expansion
    "connection_time_ms",
    "time_to_secure_connection_ms",
    "request_sent_time_ms",
    "download_time_ms",
    "duration_time_ms",
    "fetch_end_ms",
    "dom_complete_ms",
    "time_to_interactive_ms",
    "first_input_delay_ms",
)


def test_feature_rank_bounds_follow_the_requested_serp_depth() -> None:
    bounds = with_serp_depth_bounds(
        FEATURE_VALIDATION_RULES["analysis_mart"]["bounded_columns"],
        depth=50,
    )

    assert bounds["serp_rank"] == (1, 50)
    assert bounds["bge_rank"] == (1, 50)
    assert bounds["gemini_doc_retrieval_rank"] == (1, 50)
    assert bounds["gemini_semantic_similarity_rank"] == (1, 50)


def test_materialization_drops_blocklisted_domain_rows_and_replaces_stale_parts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--depth",
                "1",
                "--output-dir",
                str(output_dir),
                "--dry-run",
            ]
        )
        == 0
    )

    blocklist_path = tmp_path / "blocklist.txt"
    blocklist_path.write_text("example.com\n", encoding="utf-8")
    monkeypatch.setattr(domain_blocklist, "_resolve_default_path", lambda: blocklist_path)

    stale_feature_part = output_dir / "parquet" / "keyword_serp" / "part-stale.parquet"
    stale_feature_part.write_bytes(
        (output_dir / "parquet" / "keyword_serp" / "part-0.parquet").read_bytes()
    )
    build_feature_marts(output_dir)

    assert not stale_feature_part.exists()
    for name in (
        "keyword_serp",
        "page_features",
        "passage_features",
        "domain_features",
        "backlinks_analysis",
        "onpage_features",
        "textrazor_page_metrics",
    ):
        assert ds.dataset(output_dir / "parquet" / name, format="parquet").count_rows() == 0

    stale_curated_part = output_dir / "parquet" / "serp_items" / "part-stale.parquet"
    stale_curated_part.write_bytes(
        (output_dir / "parquet" / "serp_items" / "part-0.parquet").read_bytes()
    )
    normalize_run(output_dir)

    assert not stale_curated_part.exists()
    assert ds.dataset(output_dir / "parquet" / "keywords", format="parquet").count_rows() > 0
    for name in (
        "serp_items",
        "pages",
        "page_html",
        "page_content_fields",
        "passages",
        "backlinks",
        "onpage_signals",
        "entities",
        "textrazor_page_metrics_curated",
        "similarity_scores",
    ):
        assert ds.dataset(output_dir / "parquet" / name, format="parquet").count_rows() == 0


def test_build_analysis_panel_keyword_serp_keeps_only_scored_urls_with_complete_controls() -> None:
    keyword_serp = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "canonical_url_hash": f"url-{index}",
                "url": url,
            }
            for index, url in enumerate(
                (
                    "https://complete.example/1",
                    "https://complete.example/2",
                    "https://incomplete.example/1",
                ),
                start=1,
            )
        ]
    ).lazy()
    page_features = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "canonical_url_hash": f"url-{index}",
                "url": url,
            }
            for index, url in (
                (1, "https://complete.example/1"),
                (3, "https://incomplete.example/1"),
            )
        ]
    ).lazy()
    domain_features = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "domain": "complete.example",
                "site_scale": 1.25,
                "authority_proxy": 0.25,
            },
            {
                "run_id": "run-1",
                "domain": "incomplete.example",
                "site_scale": None,
                "authority_proxy": 0.25,
            },
        ],
        schema_overrides={"site_scale": pl.Float64, "authority_proxy": pl.Float64},
    ).lazy()

    result = build_analysis_panel_keyword_serp(
        keyword_serp,
        page_features,
        domain_features,
    ).collect()

    assert result["url"].to_list() == ["https://complete.example/1"]


def test_build_feature_marts_materializes_lazy_joins_from_curated_tables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--depth",
            "1",
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )

    assert exit_code == 0

    summary_dir = output_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    target_url = "https://example.com/technical-seo/1"
    summary_record = build_raw_response_record(
        output_dir.name,
        endpoint="backlinks_summary",
        provider="dataforseo",
        response=fixture_backlinks_response(target_url),
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": target_url,
            "variant": BACKLINKS_QUERY_SUMMARY,
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([summary_record], schema=RAW_RESPONSE_SCHEMA),
        summary_dir / "part-0.parquet",
    )

    onpage_dir = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
    )
    onpage_dir.mkdir(parents=True, exist_ok=True)
    onpage_record = build_raw_response_record(
        output_dir.name,
        endpoint="onpage_instant_pages",
        provider="dataforseo",
        response=fixture_onpage_instant_pages_response(target_url),
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": target_url,
        },
        recorded_at="2026-07-05T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([onpage_record], schema=RAW_RESPONSE_SCHEMA),
        onpage_dir / "part-0.parquet",
    )

    normalize_run(output_dir)
    catalog = build_feature_marts(output_dir)

    assert catalog["datasets"]["keyword_serp"]["row_count"] == 1
    assert catalog["datasets"]["page_features"]["row_count"] == 1
    assert catalog["datasets"]["passage_features"]["row_count"] == 2
    assert catalog["datasets"]["domain_features"]["row_count"] == 1
    assert catalog["datasets"]["backlinks_analysis"]["row_count"] == 1
    assert catalog["datasets"]["onpage_features"]["row_count"] == 1

    keyword_serp = ds.dataset(
        output_dir / "parquet" / "keyword_serp",
        format="parquet",
    ).to_table().to_pylist()
    backlinks_analysis = ds.dataset(
        output_dir / "parquet" / "backlinks_analysis",
        format="parquet",
    ).to_table().to_pylist()
    onpage_features = ds.dataset(
        output_dir / "parquet" / "onpage_features",
        format="parquet",
    ).to_table().to_pylist()
    domain_features = ds.dataset(
        output_dir / "parquet" / "domain_features",
        format="parquet",
    ).to_table().to_pylist()

    assert any(row["serp_rank"] == 1 for row in keyword_serp)
    assert any(row["domain"] == "example.com" for row in domain_features)
    assert any(row["backlinks_count"] == 42 for row in backlinks_analysis)
    assert any(row["referring_links_types_json"] is not None for row in backlinks_analysis)
    assert any(row["onpage_score"] == 85.5 for row in onpage_features)
    assert any(row["is_https"] is True for row in onpage_features)
    assert any(row["time_to_first_byte_ms"] == 120 for row in onpage_features)
    assert any(row["has_valid_structured_data"] is True for row in onpage_features)
    assert any(row["description_length"] == 128 for row in onpage_features)
    assert any(row["title_length"] == 49 for row in onpage_features)
    assert any(row["internal_links_count"] == 98 for row in onpage_features)
    assert any(row["external_links_count"] == 7 for row in onpage_features)
    assert any(row["h1_count"] == 1 for row in onpage_features)
    assert any(row["h2_count"] == 1 for row in onpage_features)
    assert any(row["h3_count"] == 0 for row in onpage_features)
    assert any(row["has_og_tags"] is True for row in onpage_features)
    assert any(row["has_twitter_tags"] is True for row in onpage_features)
    assert any(row["cache_control_cachable"] is False for row in onpage_features)
    assert any(row["cache_control_ttl"] == 3600 for row in onpage_features)
    assert any(row["click_depth"] == 2 for row in onpage_features)
    assert any(row["encoded_size"] == 25_070 for row in onpage_features)
    assert any(row["total_dom_size"] == 5_632_490 for row in onpage_features)
    assert any(row["resource_errors_count"] == 0 for row in onpage_features)
    assert any(row["resource_warnings_count"] == 1 for row in onpage_features)
    assert any(row["description_to_content_consistency"] == pytest.approx(0.4737, abs=0.001) for row in onpage_features)
    assert any(row["title_to_content_consistency"] == pytest.approx(0.7143, abs=0.001) for row in onpage_features)
    assert any(row["connection_time_ms"] == 50 for row in onpage_features)
    assert any(row["time_to_secure_connection_ms"] == 80 for row in onpage_features)
    assert any(row["request_sent_time_ms"] == 10 for row in onpage_features)
    assert any(row["download_time_ms"] == 200 for row in onpage_features)
    assert any(row["duration_time_ms"] == 350 for row in onpage_features)
    assert any(row["fetch_end_ms"] == 150 for row in onpage_features)
    assert any(row["dom_complete_ms"] == 400 for row in onpage_features)
    assert any(row["time_to_interactive_ms"] == 500 for row in onpage_features)
    assert any(row["first_input_delay_ms"] == pytest.approx(12.5) for row in onpage_features)

    run_json = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["catalog"]["datasets"]["keyword_serp"]["row_count"] == 1
    assert run_json["catalog"]["datasets"]["domain_features"]["row_count"] == 1
    assert run_json["catalog"]["datasets"]["backlinks_analysis"]["row_count"] == 1
    assert run_json["catalog"]["datasets"]["onpage_features"]["row_count"] == 1


def test_build_feature_marts_excludes_urls_when_onpage_partition_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--depth",
            "1",
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )

    assert exit_code == 0

    normalize_run(output_dir)
    catalog = build_feature_marts(output_dir)

    assert catalog["datasets"]["keyword_serp"]["row_count"] == 0
    assert catalog["datasets"]["onpage_features"]["row_count"] == 0
    onpage_features = ds.dataset(
        output_dir / "parquet" / "onpage_features",
        format="parquet",
    ).to_table().to_pylist()
    assert onpage_features == []


def test_build_feature_marts_excludes_legacy_onpage_rows_missing_scale_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--depth",
            "1",
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )
    assert exit_code == 0

    onpage_dir = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
    )
    onpage_dir.mkdir(parents=True, exist_ok=True)
    target_url = "https://example.com/technical-seo/1"
    onpage_record = build_raw_response_record(
        output_dir.name,
        endpoint="onpage_instant_pages",
        provider="dataforseo",
        response=fixture_onpage_instant_pages_response(target_url),
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": target_url,
        },
        recorded_at="2026-07-05T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([onpage_record], schema=RAW_RESPONSE_SCHEMA),
        onpage_dir / "part-0.parquet",
    )

    normalize_run(output_dir)

    onpage_signals_path = output_dir / "parquet" / "onpage_signals" / "part-0.parquet"
    legacy_table = pq.read_table(onpage_signals_path)
    legacy_columns = [
        name for name in legacy_table.column_names if name not in LEGACY_ONPAGE_META_COLUMNS
    ]
    pq.write_table(legacy_table.select(legacy_columns), onpage_signals_path)

    catalog = build_feature_marts(output_dir)

    assert catalog["datasets"]["keyword_serp"]["row_count"] == 0
    assert catalog["datasets"]["onpage_features"]["row_count"] == 0


def test_onpage_features_bounded_columns_cover_all_numeric_non_key_columns() -> None:
    """Drift guard: every non-boolean, non-key numeric column must have bounds."""
    key_columns = {
        "run_id", "target_keyword_id", "target_keyword", "response_id",
        "canonical_url_hash", "url", "schema_version", "onpage_signal_id",
    }
    unbounded_whitelist = {
        # Readability indices have no natural non-negative bound
        "flesch_kincaid_readability_index",
        "coleman_liau_readability_index",
        "smog_readability_index",
        "dale_chall_readability_index",
    }
    for column in ONPAGE_FEATURES_EXTRA_COLUMNS:
        if column in key_columns or column in unbounded_whitelist:
            continue
        dtype = CURATED_VALIDATION_RULES["onpage_signals"]["expected_schema"].get(column)
        if dtype is None:
            continue
        if dtype == pl.Boolean:
            continue
        assert column in ONPAGE_FEATURES_BOUNDED_COLUMNS, (
            f"Numeric column {column!r} missing from ONPAGE_FEATURES_BOUNDED_COLUMNS; "
            "add a (lower, upper) bound to prevent silent data drift"
        )


def test_build_feature_marts_validates_each_feature_frame_before_sinking(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "run-1", "catalog": {}}),
        encoding="utf-8",
    )

    calls: list[tuple[str, object]] = []

    def fake_scan_curated_table(run_dir: Path, table_name: str) -> pl.LazyFrame:
        return pl.DataFrame([{"run_id": "run-1"}]).lazy()

    def fake_build_feature_lazyframes(curated_frames):
        return {
            "keyword_serp": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
            "page_features": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
            "passage_features": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
            "domain_features": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
            "backlinks_analysis": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
            "onpage_features": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
            "textrazor_page_metrics": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
        }

    def fake_validate_frame_contract(frame, **kwargs):
        calls.append(("validate", tuple(kwargs["required_columns"])))
        return frame

    def fake_write_feature_dataset(run_dir: Path, *, name: str, frame: pl.LazyFrame, **kwargs):
        calls.append(("write", name))
        return {
            "schema_version": "feature_marts.v1",
            "row_count": 1,
            "files": [f"parquet/{name}/part-0.parquet"],
            "file_checksums": {f"parquet/{name}/part-0.parquet": "abc123"},
        }

    monkeypatch.setattr("seo_rank.data.features.scan_curated_table", fake_scan_curated_table)
    monkeypatch.setattr("seo_rank.data.features.build_feature_lazyframes", fake_build_feature_lazyframes)
    monkeypatch.setattr(
        "seo_rank.data.features.validate_frame_contract",
        fake_validate_frame_contract,
        raising=False,
    )
    monkeypatch.setattr("seo_rank.data.features.write_feature_dataset", fake_write_feature_dataset)

    build_feature_marts(run_dir)

    assert ("validate", BACKLINKS_ANALYSIS_REQUIRED_COLUMNS) in calls
    assert ("validate", ONPAGE_FEATURES_REQUIRED_COLUMNS) in calls
    assert ("write", "backlinks_analysis") in calls
    assert ("write", "onpage_features") in calls
    assert calls.index(("write", "backlinks_analysis")) > calls.index(("write", "domain_features"))
    assert calls.index(("write", "onpage_features")) > calls.index(("write", "backlinks_analysis"))
    assert calls.index(("write", "textrazor_page_metrics")) > calls.index(("write", "onpage_features"))


def test_write_feature_dataset_uses_lazy_sink_parquet_with_statistics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run-1"
    frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "technical seo",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": "serp-1",
                "canonical_url_hash": "hash-1",
                "url": "https://example.com",
                "serp_rank": 1,
                "title": "Example",
                "description": "Example result",
                "schema_version": "keyword_serp.v1",
            }
        ]
    ).lazy()
    captured: dict[str, object] = {}
    rows = frame.collect().to_dicts()

    def fake_sink_parquet(self, path, **kwargs):  # noqa: ANN001, ANN003
        captured["path"] = path
        captured["kwargs"] = kwargs
        pq.write_table(pa.Table.from_pylist(rows), path)

    def fail_collect(*args, **kwargs):  # noqa: ANN001, ANN003
        raise AssertionError("write_feature_dataset should not collect before sink")

    monkeypatch.setattr(pl.LazyFrame, "sink_parquet", fake_sink_parquet)
    monkeypatch.setattr(pl.LazyFrame, "collect", fail_collect)

    catalog = write_feature_dataset(
        run_dir,
        name="keyword_serp",
        frame=frame,
    )

    assert captured["path"] == run_dir / "parquet" / "keyword_serp" / "part-0.parquet.tmp"
    assert captured["kwargs"] == {"compression": "zstd", "statistics": True}
    assert catalog["row_count"] == 1


def test_write_feature_dataset_allows_textrazor_entailment_scores_above_one(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-1"
    frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "technical seo",
                "response_id": "page-resp-1",
                "canonical_url_hash": "hash-1",
                "url": "https://example.com",
                "page_metrics_row_id": "metrics-1",
                "textrazor_entity_confidence_score": 7.5,
                "textrazor_entity_relevance_score": 0.92,
                "textrazor_topic_score": 0.66,
                "textrazor_category_score": 0.83,
                "textrazor_classifier_score": 0.74,
                "textrazor_entailment_score": 7.317,
                "textrazor_entailment_prior": 1.0,
                "textrazor_entailment_context": 1.0,
                "textrazor_word_count": 2,
                "textrazor_grammar_count": 1,
                "textrazor_sense_count": 1,
                "textrazor_spelling_count": 1,
                "textrazor_relation_count": 2,
                "textrazor_property_count": 1,
                "textrazor_noun_phrase_count": 3,
                "textrazor_entities_present": True,
                "textrazor_topics_present": True,
                "textrazor_categories_present": True,
                "textrazor_entailments_present": True,
                "textrazor_words_present": True,
                "textrazor_relations_present": True,
                "textrazor_properties_present": True,
                "textrazor_noun_phrases_present": True,
                "textrazor_page_metrics_complete": True,
                "schema_version": "feature_marts.v1",
            }
        ]
    ).lazy()

    catalog = write_feature_dataset(
        run_dir,
        name="textrazor_page_metrics",
        frame=frame,
    )

    assert catalog["row_count"] == 1


def test_write_feature_dataset_includes_dataset_name_on_validation_failure(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-1"
    frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "technical seo",
                "response_id": "page-resp-1",
                "canonical_url_hash": "hash-1",
                "url": "https://example.com",
                "page_metrics_row_id": "metrics-1",
                "textrazor_entity_confidence_score": 7.5,
                "textrazor_entity_relevance_score": 0.92,
                "textrazor_topic_score": 2.0,
                "textrazor_category_score": 0.83,
                "textrazor_classifier_score": 0.74,
                "textrazor_entailment_score": 0.61,
                "textrazor_entailment_prior": 0.34,
                "textrazor_entailment_context": 0.27,
                "textrazor_word_count": 2,
                "textrazor_grammar_count": 1,
                "textrazor_sense_count": 1,
                "textrazor_spelling_count": 1,
                "textrazor_relation_count": 2,
                "textrazor_property_count": 1,
                "textrazor_noun_phrase_count": 3,
                "textrazor_entities_present": True,
                "textrazor_topics_present": True,
                "textrazor_categories_present": True,
                "textrazor_entailments_present": True,
                "textrazor_words_present": True,
                "textrazor_relations_present": True,
                "textrazor_properties_present": True,
                "textrazor_noun_phrases_present": True,
                "textrazor_page_metrics_complete": True,
                "schema_version": "feature_marts.v1",
            }
        ]
    ).lazy()

    with pytest.raises(
        ValueError,
        match="textrazor_page_metrics validation failed: Column textrazor_topic_score is above maximum 1",
    ):
        write_feature_dataset(
            run_dir,
            name="textrazor_page_metrics",
            frame=frame,
        )



def test_write_feature_dataset_keeps_prior_parts_when_sink_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run-1"
    frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "technical seo",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": "serp-1",
                "canonical_url_hash": "hash-1",
                "url": "https://example.com",
                "serp_rank": 1,
                "title": "Example",
                "description": "Example result",
                "schema_version": "keyword_serp.v1",
            }
        ]
    ).lazy()
    write_feature_dataset(run_dir, name="keyword_serp", frame=frame)
    prior = (run_dir / "parquet" / "keyword_serp" / "part-0.parquet").read_bytes()

    def boom(self, path, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError("sink failed")

    monkeypatch.setattr(pl.LazyFrame, "sink_parquet", boom)

    try:
        write_feature_dataset(run_dir, name="keyword_serp", frame=frame)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected sink failure")

    part = run_dir / "parquet" / "keyword_serp" / "part-0.parquet"
    assert part.exists()
    assert part.read_bytes() == prior
    assert not (run_dir / "parquet" / "keyword_serp" / "part-0.parquet.tmp").exists()
