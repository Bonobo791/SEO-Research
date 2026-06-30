import json
from pathlib import Path

import polars as pl
import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.normalize import (
    CURATED_SCHEMAS,
    CURATED_VALIDATION_RULES,
    build_entities_frame,
    build_similarity_scores_frame,
    build_pages_and_passages_frame,
    normalize_run,
    write_curated_dataset,
)


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
    assert len({row["passage_id"] for row in passages}) == len(passages)
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


def test_build_pages_and_passages_frame_parses_nested_page_content() -> None:
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": (
                    b'{"tasks":[{"data":{"url":"https://example.com/page"},"result":['
                    b'{"items":[{"page_content":{"main_topic":[{"primary_content":['
                    b'{"text":"Technical SEO intro paragraph with enough words."},'
                    b'{"text":"Site structure matters for crawlability and indexation."}'
                    b']}]},"header":{"primary_content":[{"text":"Header text."}]}}]}]}]}'
                ),
            }
        ]
    )

    result = build_pages_and_passages_frame(frame, run_id="run-1")
    rows = result.to_dicts()

    assert any(row["url"] == "https://example.com/page" for row in rows if row.get("passage_id") is None)
    assert any(
        "Technical SEO intro paragraph" in row["text"]
        for row in rows
        if row.get("passage_id") is not None
    )


def test_build_pages_and_passages_frame_keeps_passage_ids_unique_across_keywords() -> None:
    response_bytes = (
        b'{"tasks":[{"data":{"url":"https://example.com/page"},"result":['
        b'{"items":[{"page_content":{"main_topic":[{"primary_content":['
        b'{"text":"Technical SEO intro paragraph with enough words."},'
        b'{"text":"Site structure matters for crawlability and indexation."}'
        b']}]} }]}]}]}'
    )
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": response_bytes,
            },
            {
                "response_id": "resp-2",
                "target_keyword": "technical seo agencies",
                "response_body_bytes": response_bytes,
            },
        ]
    )

    rows = build_pages_and_passages_frame(frame, run_id="run-1").to_dicts()
    passage_ids = [row["passage_id"] for row in rows if row.get("passage_id") is not None]

    assert len(passage_ids) == len(set(passage_ids))


def test_build_entities_frame_returns_typed_empty_frame_when_no_entities() -> None:
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": (
                    b'{"response":{"entities":[]}}'
                ),
            }
        ]
    )

    result = build_entities_frame(frame, run_id="run-1")

    assert result.schema == CURATED_VALIDATION_RULES["entities"]["expected_schema"]
    assert result.is_empty()


def test_write_curated_dataset_uses_lazy_sink_parquet_with_statistics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    captured: dict[str, object] = {}

    def fake_sink_parquet(self, path, **kwargs):  # noqa: ANN001, ANN003
        captured["path"] = Path(path)
        captured["kwargs"] = kwargs
        captured["rows"] = self.collect(engine="streaming").to_dicts()
        Path(path).write_bytes(b"curated-parquet")

    monkeypatch.setattr(pl.LazyFrame, "sink_parquet", fake_sink_parquet)

    catalog = write_curated_dataset(
        run_dir,
        name="keywords",
        rows=[
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-2",
                "target_keyword": "zeta",
                "source_seed": "technical seo",
                "source_response_id": "resp-2",
                "keyword_order": 2,
                "schema_version": "curated.v1",
            },
            {
                "run_id": "run-1",
                "target_keyword_id": "kw-1",
                "target_keyword": "alpha",
                "source_seed": "technical seo",
                "source_response_id": "resp-1",
                "keyword_order": 1,
                "schema_version": "curated.v1",
            },
        ],
        schema=CURATED_SCHEMAS["keywords"],
    )

    assert captured["path"] == run_dir / "parquet" / "keywords" / "part-0.parquet"
    assert captured["kwargs"] == {"compression": "zstd", "statistics": True}
    assert [row["target_keyword_id"] for row in captured["rows"]] == ["kw-1", "kw-2"]
    assert catalog["row_count"] == 2
