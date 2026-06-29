import json
from pathlib import Path

import polars as pl
import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.normalize import build_similarity_scores_frame, normalize_run


def test_normalize_run_materializes_curated_tables_from_raw_responses(
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

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["keywords"]["row_count"] == 25
    assert catalog["datasets"]["serp_items"]["row_count"] == 25
    assert catalog["datasets"]["pages"]["row_count"] == 25
    assert catalog["datasets"]["passages"]["row_count"] == 74
    assert catalog["datasets"]["entities"]["row_count"] == 50
    assert catalog["datasets"]["similarity_scores"]["row_count"] == 25

    keywords_dir = output_dir / "parquet" / "keywords"
    pages_dir = output_dir / "parquet" / "pages"
    passages_dir = output_dir / "parquet" / "passages"
    similarity_scores_dir = output_dir / "parquet" / "similarity_scores"
    assert keywords_dir.exists()
    assert pages_dir.exists()
    assert passages_dir.exists()
    assert similarity_scores_dir.exists()

    keywords = ds.dataset(keywords_dir, format="parquet").to_table().to_pylist()
    pages = ds.dataset(pages_dir, format="parquet").to_table().to_pylist()
    passages = ds.dataset(passages_dir, format="parquet").to_table().to_pylist()
    scores = ds.dataset(similarity_scores_dir, format="parquet").to_table().to_pylist()

    assert any(row["target_keyword"] == "technical seo" for row in keywords)
    assert any(row["target_keyword_id"] for row in keywords)
    assert any(row["url"] == "https://example.com/technical-seo/1" for row in pages)
    assert any(row["response_id"] for row in pages)
    assert any(row["passage_id"].endswith("#p1") for row in passages)
    assert any(row["bge_raw_score"] == 0.98 for row in scores)

    run_json = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["catalog"]["datasets"]["keywords"]["row_count"] == 25
    assert run_json["catalog"]["datasets"]["similarity_scores"]["row_count"] == 25


def test_normalize_run_does_not_load_raw_rows_eagerly(
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

    def fail_if_called(*args, **kwargs):  # noqa: ANN001, ANN002
        raise AssertionError("normalize_run should not eagerly load raw rows")

    monkeypatch.setattr("seo_rank.data.normalize.load_raw_response_rows", fail_if_called)

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["keywords"]["row_count"] == 25


def test_build_similarity_scores_frame_handles_empty_group() -> None:
    frame = pl.DataFrame(
        {
            "run_id": [],
            "target_keyword_id": [],
            "target_keyword": [],
            "response_id": [],
            "canonical_url_hash": [],
            "url": [],
            "title": [],
            "text": [],
        }
    )

    result = build_similarity_scores_frame(frame, run_id="run-1")

    assert result.is_empty()
