import json
from pathlib import Path

import polars as pl
import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.features import build_analysis_mart, build_feature_marts
from seo_rank.data.normalize import normalize_run
from tests.fixtures.onpage_pipeline import write_onpage_instant_pages_raw_row


def test_build_analysis_mart_materializes_one_row_per_complete_url(
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

    write_onpage_instant_pages_raw_row(
        output_dir,
        target_keyword="technical seo",
        url="https://example.com/technical-seo/1",
    )
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

    def fake_write_feature_dataset(run_dir: Path, *, name: str, frame: pl.LazyFrame, **kwargs):
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
                "bge_rank",
                "bge_pct",
                "bge_z",
                "gemini_doc_retrieval_raw_score",
                "gemini_doc_retrieval_normalized_score",
                "gemini_doc_retrieval_rank",
                "gemini_doc_retrieval_pct",
                "gemini_doc_retrieval_z",
                "gemini_semantic_similarity_raw_score",
                "gemini_semantic_similarity_normalized_score",
                "gemini_semantic_similarity_rank",
                "gemini_semantic_similarity_pct",
                "gemini_semantic_similarity_z",
                    "deprecated_html_tags",
                    "meta_keywords_to_content_consistency",
                    "time_to_first_byte_ms",
                    "site_scale",
                    "schema_version",
            ),
        ),
        ("write", "analysis_mart"),
    ]
