import json
from pathlib import Path

import polars as pl
import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.features import build_feature_marts
from seo_rank.data.normalize import normalize_run


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

    normalize_run(output_dir)
    catalog = build_feature_marts(output_dir)

    assert catalog["datasets"]["keyword_serp"]["row_count"] == 25
    assert catalog["datasets"]["page_features"]["row_count"] == 25
    assert catalog["datasets"]["passage_features"]["row_count"] == 74
    assert catalog["datasets"]["domain_features"]["row_count"] == 25

    keyword_serp = ds.dataset(
        output_dir / "parquet" / "keyword_serp",
        format="parquet",
    ).to_table().to_pylist()
    domain_features = ds.dataset(
        output_dir / "parquet" / "domain_features",
        format="parquet",
    ).to_table().to_pylist()

    assert any(row["serp_rank"] == 1 for row in keyword_serp)
    assert any(row["domain"] == "example.com" for row in domain_features)

    run_json = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["catalog"]["datasets"]["keyword_serp"]["row_count"] == 25
    assert run_json["catalog"]["datasets"]["domain_features"]["row_count"] == 25


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
        }

    def fake_validate_required_columns(frame, *, required_columns):
        calls.append(("validate", tuple(required_columns)))
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
        "seo_rank.data.features.validate_required_columns",
        fake_validate_required_columns,
        raising=False,
    )
    monkeypatch.setattr("seo_rank.data.features.write_feature_dataset", fake_write_feature_dataset)

    build_feature_marts(run_dir)

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
                "canonical_url_hash",
                "url",
                "serp_rank",
                "title",
                "description",
                "schema_version",
            ),
        ),
        ("write", "keyword_serp"),
        (
            "validate",
            (
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "page_id",
                "response_id",
                "canonical_url_hash",
                "url",
                "title",
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
        ("write", "page_features"),
        (
            "validate",
            (
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "page_id",
                "response_id",
                "passage_id",
                "canonical_url_hash",
                "url",
                "source",
                "word_count",
                "passage_text_length",
                "schema_version",
            ),
        ),
        ("write", "passage_features"),
        (
            "validate",
            (
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "domain_feature_id",
                "domain",
                "serp_item_count",
                "best_serp_rank",
                "worst_serp_rank",
                "schema_version",
            ),
        ),
        ("write", "domain_features"),
    ]
