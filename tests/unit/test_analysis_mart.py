import json
from pathlib import Path

import polars as pl
import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.features import build_analysis_mart, build_feature_marts
from seo_rank.data.normalize import normalize_run


def test_build_analysis_mart_materializes_one_row_per_serp_url(
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
    build_feature_marts(output_dir)
    catalog = build_analysis_mart(output_dir)

    assert catalog["datasets"]["analysis_mart"]["row_count"] == 1

    analysis_mart = ds.dataset(
        output_dir / "parquet" / "analysis_mart",
        format="parquet",
    ).to_table().to_pylist()

    assert len(analysis_mart) == 1
    assert all(row["serp_rank"] == 1 for row in analysis_mart)
    assert any(row["target_keyword"] == "technical seo" for row in analysis_mart)
    assert any(row["page_text_length"] > 0 for row in analysis_mart)

    run_json = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["catalog"]["datasets"]["analysis_mart"]["row_count"] == 1


def test_build_analysis_mart_validates_the_analysis_frame_before_sinking(
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

    def fake_build_analysis_lazyframe(feature_frames):
        return pl.DataFrame([{"run_id": "run-1"}]).lazy()

    def fake_validate_frame_contract(frame, **kwargs):
        calls.append(("validate", tuple(kwargs["required_columns"])))
        return frame

    def fake_write_feature_dataset(run_dir: Path, *, name: str, frame: pl.LazyFrame):
        calls.append(("write", name))
        return {
            "schema_version": "analysis_mart.v1",
            "row_count": 1,
            "files": [f"parquet/{name}/part-0.parquet"],
            "file_checksums": {f"parquet/{name}/part-0.parquet": "abc123"},
        }

    monkeypatch.setattr("seo_rank.data.features.build_analysis_lazyframe", fake_build_analysis_lazyframe)
    monkeypatch.setattr(
        "seo_rank.data.features.validate_frame_contract",
        fake_validate_frame_contract,
        raising=False,
    )
    monkeypatch.setattr("seo_rank.data.features.write_feature_dataset", fake_write_feature_dataset)
    monkeypatch.setattr(
        "seo_rank.data.features.scan_curated_table",
        lambda run_dir, table_name: pl.DataFrame([{"run_id": "run-1"}]).lazy(),
    )

    build_analysis_mart(run_dir)

    assert calls == [
        (
            "validate",
            (
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "keyword_order",
                "source_response_id",
                "serp_item_id",
                "page_id",
                "response_id",
                "canonical_url_hash",
                "url",
                "serp_rank",
                "title",
                "description",
                "page_text_length",
                "bge_raw_score",
                "bge_normalized_score",
                "gemini_doc_retrieval_raw_score",
                "gemini_doc_retrieval_normalized_score",
                "gemini_semantic_similarity_raw_score",
                "gemini_semantic_similarity_normalized_score",
                "schema_version",
            ),
        ),
        ("write", "analysis_mart"),
    ]


def test_build_analysis_mart_keeps_serp_rows_without_matching_page_features(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "run-1", "catalog": {}}),
        encoding="utf-8",
    )

    keyword_serp = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": "serp-1",
                "canonical_url_hash": "url-1",
                "url": "https://example.com/1",
                "serp_rank": 1,
                "title": "one",
                "description": "desc",
                "schema_version": "feature_marts.v1",
            },
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "keyword_order": 1,
                "source_response_id": "resp-1",
                "serp_item_id": "serp-2",
                "canonical_url_hash": "url-2",
                "url": "https://example.com/2",
                "serp_rank": 2,
                "title": "two",
                "description": "desc",
                "schema_version": "feature_marts.v1",
            },
        ]
    )
    page_features = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "keyword 1",
                "page_id": "page-1",
                "response_id": "page-resp-1",
                "canonical_url_hash": "url-1",
                "url": "https://example.com/1",
                "title": "one",
                "page_text_length": 120,
                "bge_raw_score": 0.8,
                "bge_normalized_score": 0.9,
                "gemini_doc_retrieval_raw_score": 0.7,
                "gemini_doc_retrieval_normalized_score": 0.85,
                "gemini_semantic_similarity_raw_score": 0.6,
                "gemini_semantic_similarity_normalized_score": 0.8,
                "schema_version": "feature_marts.v1",
            }
        ],
        schema_overrides={"page_text_length": pl.UInt32},
    )

    def fake_scan_curated_table(run_dir: Path, table_name: str) -> pl.LazyFrame:
        del run_dir
        frames = {
            "keyword_serp": keyword_serp.lazy(),
            "page_features": page_features.lazy(),
            "passage_features": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
            "domain_features": pl.DataFrame([{"run_id": "run-1"}]).lazy(),
        }
        return frames[table_name]

    monkeypatch.setattr("seo_rank.data.features.scan_curated_table", fake_scan_curated_table)

    catalog = build_analysis_mart(run_dir)

    assert catalog["datasets"]["analysis_mart"]["row_count"] == 2

    analysis_mart = ds.dataset(
        run_dir / "parquet" / "analysis_mart",
        format="parquet",
    ).to_table().to_pylist()

    assert len(analysis_mart) == 2
    assert sum(row["page_id"] is None for row in analysis_mart) == 1
