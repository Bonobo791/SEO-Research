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
from seo_rank.data.features import ONPAGE_FEATURES_REQUIRED_COLUMNS
from seo_rank.data.features import build_feature_marts, write_feature_dataset
from seo_rank.data.normalize import normalize_run
from seo_rank.dataforseo import BACKLINKS_QUERY_SUMMARY
from seo_rank.dataforseo import fixture_backlinks_response
from seo_rank.dataforseo import fixture_onpage_instant_pages_response

LEGACY_ONPAGE_META_COLUMNS = (
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
)


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

    run_json = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["catalog"]["datasets"]["keyword_serp"]["row_count"] == 1
    assert run_json["catalog"]["datasets"]["domain_features"]["row_count"] == 1
    assert run_json["catalog"]["datasets"]["backlinks_analysis"]["row_count"] == 1
    assert run_json["catalog"]["datasets"]["onpage_features"]["row_count"] == 1


def test_build_feature_marts_onpage_features_null_when_partition_missing(
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

    assert catalog["datasets"]["onpage_features"]["row_count"] == 1
    onpage_features = ds.dataset(
        output_dir / "parquet" / "onpage_features",
        format="parquet",
    ).to_table().to_pylist()
    row = onpage_features[0]
    assert row["serp_rank"] == 1
    assert row["onpage_score"] is None
    assert row["onpage_signal_id"] is None
    assert row["has_valid_structured_data"] is None


def test_build_feature_marts_legacy_onpage_signals_backfills_missing_meta_columns(
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

    assert catalog["datasets"]["onpage_features"]["row_count"] == 1
    onpage_features = ds.dataset(
        output_dir / "parquet" / "onpage_features",
        format="parquet",
    ).to_table().to_pylist()
    row = onpage_features[0]
    assert row["onpage_score"] == 85.5
    assert row["title_length"] is None
    assert row["follow"] is None
    assert row["description_to_content_consistency"] is None


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

    def fake_write_feature_dataset(run_dir: Path, *, name: str, frame: pl.LazyFrame):
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

    assert captured["path"] == run_dir / "parquet" / "keyword_serp" / "part-0.parquet"
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
