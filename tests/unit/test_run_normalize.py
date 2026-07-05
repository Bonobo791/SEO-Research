import hashlib
import json
import shutil
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from seo_rank.cli import build_raw_response_record
from seo_rank.cli import main
from seo_rank.cli import RAW_RESPONSE_SCHEMA
from seo_rank.dataforseo import (
    BACKLINKS_QUERY_DOFOLLOW,
    BACKLINKS_QUERY_SUMMARY,
    DataForSeoParseError,
    fixture_backlinks_response,
    fixture_keyword_expansion_response,
    fixture_serp_response,
)
from seo_rank.data.normalize import (
    CURATED_SCHEMAS,
    CURATED_VALIDATION_RULES,
    build_entities_frame,
    build_page_html_frame,
    build_page_content_fields_frame,
    build_similarity_scores_frame,
    build_pages_and_passages_frame,
    build_textrazor_page_metrics_frame,
    normalize_run,
    stable_id,
    write_curated_dataset,
    write_curated_lazyframe_dataset,
)
from seo_rank.textrazor import fixture_page_metrics_response

ROOT = Path(__file__).resolve().parents[2]


def _page_similarity_entry(
    *,
    target_keyword: str,
    url: str,
    bge: float = 0.9,
    gemini_doc_retrieval: float = 0.9,
    gemini_semantic_similarity: float = 0.9,
) -> dict[str, object]:
    return {
        "target_keyword": target_keyword,
        "url": url,
        "page_similarity": {
            "bge": {"raw_score": bge, "normalized_score": bge},
            "gemini_doc_retrieval": {
                "raw_score": gemini_doc_retrieval,
                "normalized_score": gemini_doc_retrieval,
            },
            "gemini_semantic_similarity": {
                "raw_score": gemini_semantic_similarity,
                "normalized_score": gemini_semantic_similarity,
            },
        },
    }


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

    assert catalog["datasets"]["keywords"]["row_count"] == 1
    assert catalog["datasets"]["serp_items"]["row_count"] == 1
    assert catalog["datasets"]["pages"]["row_count"] == 1
    assert catalog["datasets"]["passages"]["row_count"] == 2
    assert catalog["datasets"]["entities"]["row_count"] == 2
    assert catalog["datasets"]["similarity_scores"]["row_count"] == 1

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
    assert run_json["catalog"]["datasets"]["keywords"]["row_count"] == 1
    assert run_json["catalog"]["datasets"]["similarity_scores"]["row_count"] == 1


def test_normalize_run_materializes_backlinks_table_from_summary_only_with_null_dofollow(
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

    summary_dir = (
        output_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    )
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

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["backlinks"]["row_count"] == 1
    backlinks = ds.dataset(output_dir / "parquet" / "backlinks", format="parquet").to_table().to_pylist()
    assert backlinks[0]["backlinks_count"] == 42
    assert backlinks[0]["referring_domains_count"] == 12
    assert backlinks[0]["dofollow_backlinks_count"] is None
    assert backlinks[0]["backlinks_metrics_complete"] is False
    assert backlinks[0]["referring_links_types_json"] is not None


def test_normalize_run_materializes_backlinks_table_from_summary_and_dofollow_responses(
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

    summary_dir = (
        output_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    )
    dofollow_dir = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_dofollow_summary"
    )
    summary_dir.mkdir(parents=True, exist_ok=True)
    dofollow_dir.mkdir(parents=True, exist_ok=True)
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
    dofollow_record = build_raw_response_record(
        output_dir.name,
        endpoint="backlinks_dofollow_summary",
        provider="dataforseo",
        response=fixture_backlinks_response(target_url, dofollow_only=True),
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": target_url,
            "variant": BACKLINKS_QUERY_DOFOLLOW,
        },
        recorded_at="2026-07-02T12:00:01+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([summary_record], schema=RAW_RESPONSE_SCHEMA),
        summary_dir / "part-0.parquet",
    )
    pq.write_table(
        pa.Table.from_pylist([dofollow_record], schema=RAW_RESPONSE_SCHEMA),
        dofollow_dir / "part-0.parquet",
    )

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["backlinks"]["row_count"] == 1
    backlinks = ds.dataset(output_dir / "parquet" / "backlinks", format="parquet").to_table().to_pylist()
    assert backlinks[0]["backlinks_count"] == 42
    assert backlinks[0]["referring_domains_count"] == 12
    assert backlinks[0]["dofollow_backlinks_count"] == 35
    assert backlinks[0]["dofollow_referring_domains_count"] == 10
    assert backlinks[0]["backlinks_metrics_complete"] is True
    assert backlinks[0]["rank"] == 412
    assert backlinks[0]["target_spam_score"] == 6


def test_normalize_run_materializes_backlinks_table_from_legacy_backlinks_partition(
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

    legacy_dir = output_dir / "parquet" / "raw_responses" / "endpoint=backlinks"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    target_url = "https://example.com/technical-seo/1"
    legacy_record = build_raw_response_record(
        output_dir.name,
        endpoint="backlinks",
        provider="dataforseo",
        response=fixture_backlinks_response(target_url),
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": target_url,
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([legacy_record], schema=RAW_RESPONSE_SCHEMA),
        legacy_dir / "part-0.parquet",
    )

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["backlinks"]["row_count"] == 1
    backlinks = ds.dataset(output_dir / "parquet" / "backlinks", format="parquet").to_table().to_pylist()
    assert backlinks[0]["backlinks_count"] == 42
    assert backlinks[0]["dofollow_backlinks_count"] is None
    assert backlinks[0]["backlinks_metrics_complete"] is False


def test_normalize_run_rejects_backlinks_summary_missing_required_aggregates(
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

    summary_dir = (
        output_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    )
    summary_dir.mkdir(parents=True, exist_ok=True)
    backlinks_response = {
        "status_code": 20000,
        "provider": "dataforseo",
        "endpoint": "backlinks/summary/live",
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "https://example.com/technical-seo/1",
                        "backlinks": 42,
                    }
                ],
            }
        ],
    }
    backlinks_record = build_raw_response_record(
        output_dir.name,
        endpoint="backlinks_summary",
        provider="dataforseo",
        response=backlinks_response,
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": "https://example.com/technical-seo/1",
            "variant": BACKLINKS_QUERY_SUMMARY,
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([backlinks_record], schema=RAW_RESPONSE_SCHEMA),
        summary_dir / "part-0.parquet",
    )

    with pytest.raises(DataForSeoParseError):
        normalize_run(output_dir)


def test_normalize_run_materializes_backlinks_table_from_legacy_live_shape_in_summary_partition(
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

    summary_dir = (
        output_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    )
    summary_dir.mkdir(parents=True, exist_ok=True)
    target_url = "https://example.com/technical-seo/1"
    legacy_live_response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "path": ["v3", "backlinks", "backlinks", "live"],
                "result": [
                    {
                        "target": target_url,
                        "total_count": 42,
                        "items_count": 0,
                        "items": None,
                    }
                ],
            }
        ],
    }
    backlinks_record = build_raw_response_record(
        output_dir.name,
        endpoint="backlinks_summary",
        provider="dataforseo",
        response=legacy_live_response,
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": target_url,
            "variant": BACKLINKS_QUERY_SUMMARY,
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([backlinks_record], schema=RAW_RESPONSE_SCHEMA),
        summary_dir / "part-0.parquet",
    )

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["backlinks"]["row_count"] == 1
    backlinks = (
        ds.dataset(output_dir / "parquet" / "backlinks", format="parquet")
        .to_table()
        .to_pylist()
    )
    assert backlinks[0]["backlinks_count"] == 42
    assert backlinks[0]["referring_domains_count"] is None
    assert backlinks[0]["backlinks_metrics_complete"] is False


def test_normalize_run_materializes_backlinks_table_with_zero_backlinks(
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

    summary_dir = (
        output_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    )
    summary_dir.mkdir(parents=True, exist_ok=True)
    backlinks_response = {
        "status_code": 20000,
        "provider": "dataforseo",
        "endpoint": "backlinks/summary/live",
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "https://example.com/technical-seo/1",
                        "backlinks": 0,
                        "referring_domains": 0,
                    }
                ],
            }
        ],
    }
    backlinks_record = build_raw_response_record(
        output_dir.name,
        endpoint="backlinks_summary",
        provider="dataforseo",
        response=backlinks_response,
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": "https://example.com/technical-seo/1",
            "variant": BACKLINKS_QUERY_SUMMARY,
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist([backlinks_record], schema=RAW_RESPONSE_SCHEMA),
        summary_dir / "part-0.parquet",
    )

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["backlinks"]["row_count"] == 1
    backlinks = ds.dataset(output_dir / "parquet" / "backlinks", format="parquet").to_table().to_pylist()
    assert backlinks[0]["backlinks_count"] == 0
    assert backlinks[0]["referring_domains_count"] == 0
    assert backlinks[0]["dofollow_backlinks_count"] is None


def test_dry_run_materializes_textrazor_topic_and_page_metrics(
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

    metrics_path = output_dir / "parquet" / "textrazor_page_metrics_curated" / "part-0.parquet"
    assert metrics_path.exists(), "dry-run should materialize textrazor_page_metrics_curated"

    metrics = pl.read_parquet(metrics_path)
    assert metrics.height >= 1
    assert metrics["textrazor_topics_present"].all()
    assert metrics["textrazor_topic_score"].null_count() == 0
    assert metrics["textrazor_page_metrics_complete"].all()


def test_write_curated_lazyframe_dataset_allows_textrazor_entailment_scores_above_one(
    tmp_path: Path,
) -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["entailments"][0]["score"] = 7.317
    response["response"]["entailments"][0]["priorScore"] = 1.0
    response["response"]["entailments"][0]["contextScore"] = 1.0

    frame = build_textrazor_page_metrics_frame(
        pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "response_id": "page-resp-1",
                    "target_keyword": "Technical SEO",
                    "response_body_bytes": json.dumps(response).encode("utf-8"),
                }
            ]
        ),
        run_id="run-1",
    ).lazy()

    catalog = write_curated_lazyframe_dataset(
        tmp_path,
        name="textrazor_page_metrics_curated",
        frame=frame,
        schema=CURATED_SCHEMAS["textrazor_page_metrics_curated"],
    )

    assert catalog["row_count"] == 1


def test_write_curated_lazyframe_dataset_includes_dataset_name_on_validation_failure(
    tmp_path: Path,
) -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )

    frame = build_textrazor_page_metrics_frame(
        pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "response_id": "page-resp-1",
                    "target_keyword": "Technical SEO",
                    "response_body_bytes": json.dumps(response).encode("utf-8"),
                }
            ]
        ),
        run_id="run-1",
    ).with_columns(pl.lit(2.0).alias("textrazor_topic_score")).lazy()

    with pytest.raises(
        ValueError,
        match="textrazor_page_metrics_curated validation failed: Column textrazor_topic_score is above maximum 1",
    ):
        write_curated_lazyframe_dataset(
            tmp_path,
            name="textrazor_page_metrics_curated",
            frame=frame,
            schema=CURATED_SCHEMAS["textrazor_page_metrics_curated"],
        )


def test_normalize_run_preserves_run_json_page_similarity_scores(
    tmp_path: Path,
) -> None:
    source_run_dir = ROOT / "runs" / "northwest-houston-realtor-b0a0813b1789"
    run_dir = tmp_path / "northwest-houston-realtor-b0a0813b1789"
    shutil.copytree(source_run_dir, run_dir)

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    report_row = run_payload["page_similarity"][0]
    report_url = report_row["url"]
    report_score = report_row["page_similarity"]["bge"]["normalized_score"]

    normalize_run(run_dir)

    similarity_scores = ds.dataset(
        run_dir / "parquet" / "similarity_scores",
        format="parquet",
    ).to_table().to_pylist()
    parquet_row = next(row for row in similarity_scores if row["url"] == report_url)

    assert parquet_row["bge_normalized_score"] == report_score


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

    assert catalog["datasets"]["keywords"]["row_count"] == 1


def test_normalize_run_stores_raw_html_when_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

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

    page_text_dir = output_dir / "parquet" / "raw_responses" / "endpoint=page_text"

    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/product"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/product",
                                "status_code": 200,
                                "page_content": {
                                    "ratings": [
                                        {
                                            "rating_value": 4,
                                            "max_rating_value": 5,
                                            "rating_count": 12,
                                            "relative_rating": 0.8,
                                        }
                                    ],
                                    "offers": [
                                        {
                                            "price": 129,
                                            "price_currency": "USD",
                                        }
                                    ],
                                    "comments": [
                                        {
                                            "rating": {
                                                "rating_value": 5,
                                                "max_rating_value": 5,
                                                "relative_rating": 1.0,
                                            }
                                        }
                                    ],
                                },
                                "raw_html": "<html><body><main>Raw HTML body</main></body></html>",
                            }
                        ]
                    }
                ],
            }
        ]
    }

    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "page-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(page_text_dir / "part-structured-only.parquet")

    run_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    run_payload.setdefault("page_similarity", []).append(
        _page_similarity_entry(
            target_keyword="technical seo",
            url="https://example.com/product",
            bge=0.9,
            gemini_doc_retrieval=0.9,
            gemini_semantic_similarity=0.9,
        )
    )
    (output_dir / "run.json").write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["page_content_fields"]["row_count"] > 0
    assert catalog["datasets"]["page_html"]["row_count"] > 0

    page_content_fields_dir = output_dir / "parquet" / "page_content_fields"
    page_html_dir = output_dir / "parquet" / "page_html"
    page_rows = ds.dataset(output_dir / "parquet" / "pages", format="parquet").to_table().to_pylist()
    field_rows = ds.dataset(page_content_fields_dir, format="parquet").to_table().to_pylist()
    html_rows = ds.dataset(page_html_dir, format="parquet").to_table().to_pylist()

    structured_field = next(
        row
        for row in field_rows
        if row["response_id"] == "page-resp-1" and row["field_name"] == "status_code"
    )
    html_row = next(row for row in html_rows if row["response_id"] == "page-resp-1")

    assert structured_field["field_path"] == "tasks[0].result[0].items[0].status_code"
    assert structured_field["structured_value"] == "200"
    assert structured_field["text"] == ""
    assert structured_field["field_row_id"] == stable_id(
        structured_field["page_id"],
        structured_field["response_id"],
        structured_field["field_path"],
        structured_field["ordinal"],
    )
    assert html_row["page_id"] == structured_field["page_id"]
    assert html_row["raw_html"] == "<html><body><main>Raw HTML body</main></body></html>"
    assert any(
        row["page_id"] == structured_field["page_id"] and row["text"] == ""
        for row in page_rows
    )


def test_normalize_run_deduplicates_repeated_page_text_raw_responses(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "artifacts"
    raw_responses_root = output_dir / "parquet" / "raw_responses"
    keyword_responses_dir = raw_responses_root / "endpoint=keyword_expansion"
    serp_responses_dir = raw_responses_root / "endpoint=serp"
    page_text_responses_dir = raw_responses_root / "endpoint=page_text"
    keyword_responses_dir.mkdir(parents=True)
    serp_responses_dir.mkdir(parents=True)
    page_text_responses_dir.mkdir(parents=True)

    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/product"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/product",
                                "status_code": 200,
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {"text": "Header intro with enough words."}
                                        ]
                                    },
                                    "ratings": [
                                        {
                                            "rating_value": 4,
                                            "max_rating_value": 5,
                                            "rating_count": 12,
                                            "relative_rating": 0.8,
                                        }
                                    ],
                                    "offers": [
                                        {
                                            "price": 129,
                                            "price_currency": "USD",
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }
    response_body_bytes = json.dumps(response_body).encode("utf-8")
    response_sha256 = hashlib.sha256(response_body_bytes).hexdigest()
    response_id = "page-text-duplicate-1"

    raw_rows = [
        {
            "run_id": "artifacts",
            "response_id": "keyword-expansion-1",
            "endpoint": "keyword_expansion",
            "provider": "dataforseo",
            "target_keyword": "",
            "task_id": "keyword-task-1",
            "timestamp": "2026-07-02T00:00:00+00:00",
            "request_metadata_json": json.dumps(
                {"seed": "technical seo"},
                sort_keys=True,
            ),
            "content_type": "application/json",
            "status": 200,
            "response_body_bytes": json.dumps(
                fixture_keyword_expansion_response("technical seo"),
                sort_keys=True,
            ).encode("utf-8"),
            "sha256": hashlib.sha256(
                json.dumps(
                    fixture_keyword_expansion_response("technical seo"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            "schema_version": "raw_responses.v1",
        },
        {
            "run_id": "artifacts",
            "response_id": "serp-1",
            "endpoint": "serp",
            "provider": "dataforseo",
            "target_keyword": "technical seo",
            "task_id": "serp-task-1",
            "timestamp": "2026-07-02T00:00:00+00:00",
            "request_metadata_json": json.dumps(
                {"target_keyword": "technical seo"},
                sort_keys=True,
            ),
            "content_type": "application/json",
            "status": 200,
            "response_body_bytes": json.dumps(
                fixture_serp_response("technical seo"),
                sort_keys=True,
            ).encode("utf-8"),
            "sha256": hashlib.sha256(
                json.dumps(
                    fixture_serp_response("technical seo"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            "schema_version": "raw_responses.v1",
        },
        {
            "run_id": "artifacts",
            "response_id": response_id,
            "endpoint": "page_text",
            "provider": "dataforseo",
            "target_keyword": "technical seo",
            "task_id": "page-task-1",
            "timestamp": "2026-07-02T00:00:00+00:00",
            "request_metadata_json": json.dumps(
                {
                    "target_keyword": "technical seo",
                    "url": "https://example.com/product",
                },
                sort_keys=True,
            ),
            "content_type": "application/json",
            "status": 200,
            "response_body_bytes": response_body_bytes,
            "sha256": response_sha256,
            "schema_version": "raw_responses.v1",
        },
        {
            "run_id": "artifacts",
            "response_id": response_id,
            "endpoint": "page_text",
            "provider": "dataforseo",
            "target_keyword": "technical seo",
            "task_id": "page-task-1",
            "timestamp": "2026-07-02T00:00:00+00:00",
            "request_metadata_json": json.dumps(
                {
                    "target_keyword": "technical seo",
                    "url": "https://example.com/product",
                },
                sort_keys=True,
            ),
            "content_type": "application/json",
            "status": 200,
            "response_body_bytes": response_body_bytes,
            "sha256": response_sha256,
            "schema_version": "raw_responses.v1",
        },
    ]
    pl.DataFrame([raw_rows[0]]).write_parquet(keyword_responses_dir / "part-0.parquet")
    pl.DataFrame([raw_rows[1]]).write_parquet(serp_responses_dir / "part-0.parquet")
    pl.DataFrame(raw_rows[2:]).write_parquet(page_text_responses_dir / "part-0.parquet")

    run_payload = {
        "run_id": "artifacts",
        "config": {
            "seed": "technical seo",
            "depth": 1,
            "dry_run": True,
        },
        "catalog": {},
        "page_similarity": [
            {
                "target_keyword": "technical seo",
                "url": "https://example.com/product",
                "page_similarity": {
                    "bge": {"raw_score": 0.9, "normalized_score": 0.9},
                    "gemini_doc_retrieval": {
                        "raw_score": 0.9,
                        "normalized_score": 0.9,
                    },
                    "gemini_semantic_similarity": {
                        "raw_score": 0.9,
                        "normalized_score": 0.9,
                    },
                },
            }
        ],
    }
    (output_dir / "run.json").write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    catalog = normalize_run(output_dir)

    field_rows = ds.dataset(
        output_dir / "parquet" / "page_content_fields",
        format="parquet",
    ).to_table().to_pylist()

    assert catalog["datasets"]["page_content_fields"]["row_count"] == len(field_rows)
    assert len(field_rows) > 0
    assert len({row["field_row_id"] for row in field_rows}) == len(field_rows)
    assert catalog["datasets"]["page_html"]["row_count"] == 0


def test_normalize_run_deduplicates_repeated_page_text_urls(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "artifacts"
    raw_responses_dir = output_dir / "parquet" / "raw_responses"
    (raw_responses_dir / "endpoint=keyword_expansion").mkdir(parents=True)
    (raw_responses_dir / "endpoint=serp").mkdir(parents=True)
    (raw_responses_dir / "endpoint=page_text").mkdir(parents=True)

    run_payload = {
        "run_id": "artifacts",
        "config": {
            "seed": "technical seo",
            "depth": 1,
            "dry_run": True,
        },
        "catalog": {},
        "page_similarity": [
            _page_similarity_entry(
                target_keyword="technical seo",
                url="https://example.com/page",
                bge=0.9,
                gemini_doc_retrieval=0.9,
                gemini_semantic_similarity=0.9,
            )
        ],
    }
    (output_dir / "run.json").write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    keyword_response_body = fixture_keyword_expansion_response("technical seo")
    serp_response_body = {
        "tasks": [
            {
                "keyword": "technical seo",
                "result": [
                    {
                        "items": [
                            {
                                "type": "organic",
                                "rank_group": 1,
                                "url": "https://example.com/page",
                                "title": "Example Page",
                                "description": "First duplicate result.",
                            },
                            {
                                "type": "organic",
                                "rank_group": 2,
                                "url": "https://example.com/page",
                                "title": "Example Page",
                                "description": "Second duplicate result.",
                            },
                        ]
                    }
                ],
            }
        ]
    }
    page_text_response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "url": "https://example.com/page",
                        "title": "Example Page",
                        "text": """
                            Technical SEO helps crawlers discover pages.

                            Internal links and index controls make findings actionable.
                        """,
                        "raw_html": "<html><body><main>Example Page</main></body></html>",
                    }
                ],
            }
        ]
    }

    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "kw-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(keyword_response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=keyword_expansion" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "serp-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(serp_response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=serp" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "page-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(page_text_response_body).encode("utf-8"),
            },
            {
                "run_id": "artifacts",
                "response_id": "page-resp-2",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(page_text_response_body).encode("utf-8"),
            },
        ]
    ).write_parquet(raw_responses_dir / "endpoint=page_text" / "part-0.parquet")

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["pages"]["row_count"] == 1
    assert catalog["datasets"]["passages"]["row_count"] == 2
    assert catalog["datasets"]["similarity_scores"]["row_count"] == 1

    pages = ds.dataset(output_dir / "parquet" / "pages", format="parquet").to_table().to_pylist()
    passages = ds.dataset(output_dir / "parquet" / "passages", format="parquet").to_table().to_pylist()

    assert len(pages) == 1
    assert len(passages) == 2
    assert {row["page_id"] for row in passages} == {pages[0]["page_id"]}


def test_build_page_content_fields_frame_decodes_structured_fields() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/page",
                                "status_code": 200,
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {"text": "Header intro with enough words."}
                                        ]
                                    },
                                    "main_topic": [
                                        {
                                            "primary_content": [
                                                {
                                                    "text": (
                                                        "Technical SEO intro paragraph "
                                                        "with enough words."
                                                    )
                                                }
                                            ],
                                            "secondary_content": [
                                                {
                                                    "text": (
                                                        "Secondary supporting section "
                                                        "with enough words."
                                                    )
                                                }
                                            ],
                                        }
                                    ],
                                },
                                "page_as_markdown": (
                                    "# Technical SEO\n\n"
                                    "Markdown fallback should not be used here."
                                ),
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_page_content_fields_frame(frame, run_id="run-1")
    rows = result.to_dicts()

    assert result.schema == CURATED_VALIDATION_RULES["page_content_fields"][
        "expected_schema"
    ]
    assert len(rows) >= 4
    assert any(
        row["field_path"] == "tasks[0].result[0].items[0].status_code" for row in rows
    )
    assert any(
        row["field_path"]
        == "tasks[0].result[0].items[0].page_content.header.primary_content[0].text"
        for row in rows
    )
    assert any(row["field_name"] == "page_as_markdown" for row in rows)
    assert any(
        row["text"] == "Technical SEO intro paragraph with enough words."
        for row in rows
    )


def test_build_pages_and_passages_frame_preserves_aggregate_text_with_field_decode() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/page",
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {"text": "Header intro with enough words."}
                                        ]
                                    },
                                    "main_topic": [
                                        {
                                            "primary_content": [
                                                {
                                                    "text": (
                                                        "Technical SEO intro paragraph "
                                                        "with enough words."
                                                    )
                                                }
                                            ]
                                        }
                                    ],
                                },
                                "page_as_markdown": "# Example Page\n\nMarkdown fallback.",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-aggregate-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_pages_and_passages_frame(frame, run_id="run-1")
    rows = result.to_dicts()
    page_rows = [row for row in rows if row.get("passage_id") is None]

    assert len(page_rows) == 1
    assert page_rows[0]["text"] == (
        "Header intro with enough words.\n\n"
        "Technical SEO intro paragraph with enough words."
    )
    assert page_rows[0]["url"] == "https://example.com/page"
    assert any(
        row["text"] == "Header intro with enough words."
        for row in rows
        if row.get("passage_id") is not None
    )


def test_build_page_content_fields_frame_keeps_structured_fields_without_aggregate_text() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/empty"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/empty",
                                "status_code": 200,
                                "page_content": {},
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-empty",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_page_content_fields_frame(frame, run_id="run-1")

    rows = result.to_dicts()

    assert len(rows) > 0
    assert any(row["field_name"] == "status_code" for row in rows)


def test_build_page_content_fields_frame_keeps_structured_fields_without_page_text() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/product"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/product",
                                "status_code": 200,
                                "page_content": {
                                    "ratings": [
                                        {
                                            "name": None,
                                            "rating_value": 4,
                                            "max_rating_value": 5,
                                            "rating_count": 12,
                                            "relative_rating": 0.8,
                                        }
                                    ],
                                    "offers": [
                                        {
                                            "name": "SEO Audit",
                                            "price": 129,
                                            "price_currency": "USD",
                                            "price_valid_until": (
                                                "2026-08-01 00:00:00 +00:00"
                                            ),
                                        }
                                    ],
                                    "comments": [
                                        {
                                            "rating": {
                                                "name": None,
                                                "rating_value": 5,
                                                "max_rating_value": 5,
                                                "rating_count": None,
                                                "relative_rating": 1.0,
                                            },
                                            "title": "Helpful",
                                            "publish_date": "2026-06-30",
                                            "author": "Jordan",
                                            "primary_content": [
                                                {"text": "Great write-up."}
                                            ],
                                        }
                                    ],
                                    "contacts": {
                                        "telephones": ["+1-555-0100"],
                                        "emails": ["info@example.com"],
                                    },
                                },
                                "raw_html": "<html><body><main>Raw HTML</main></body></html>",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-structured-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_page_content_fields_frame(frame, run_id="run-1")
    rows = result.to_dicts()

    assert len(rows) > 0
    assert any(
        row["field_path"]
        == "tasks[0].result[0].items[0].page_content.ratings[0].rating_value"
        for row in rows
    )
    assert any(
        row["field_path"]
        == "tasks[0].result[0].items[0].page_content.offers[0].price"
        for row in rows
    )
    assert any(
        row["field_path"]
        == "tasks[0].result[0].items[0].page_content.comments[0].primary_content[0].text"
        for row in rows
    )
    assert any(
        row["field_path"]
        == "tasks[0].result[0].items[0].page_content.contacts.telephones[0]"
        for row in rows
    )


def test_build_page_html_frame_persists_raw_html_without_page_text() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/empty"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/empty",
                                "raw_html": "<html><body><main>Raw HTML</main></body></html>",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-html-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_page_html_frame(frame, run_id="run-1")
    rows = result.to_dicts()

    assert result.schema == CURATED_VALIDATION_RULES["page_html"]["expected_schema"]
    assert len(rows) == 1
    assert rows[0]["raw_html"] == "<html><body><main>Raw HTML</main></body></html>"
    assert rows[0]["url"] == "https://example.com/empty"


def test_build_page_html_frame_does_not_cross_pair_url_and_html_across_items() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/first"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/first",
                            },
                            {
                                "url": "https://example.com/second",
                                "raw_html": "<html><body>Second item HTML</body></html>",
                            },
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-html-2",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_page_html_frame(frame, run_id="run-1")

    assert result.is_empty()


def test_normalize_run_materializes_page_content_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    raw_responses_dir = output_dir / "parquet" / "raw_responses"
    (raw_responses_dir / "endpoint=keyword_expansion").mkdir(parents=True)
    (raw_responses_dir / "endpoint=serp").mkdir(parents=True)
    (raw_responses_dir / "endpoint=page_text").mkdir(parents=True)
    (raw_responses_dir / "endpoint=entities").mkdir(parents=True)
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    keyword_response_body = {
        "tasks": [
            {
                "result": [
                    {"keyword": "technical seo"},
                    {"keyword": "technical seo audit"},
                ]
            }
        ]
    }
    serp_response_body = {
        "tasks": [
            {
                "keyword": "technical seo",
                "result": [
                    {
                        "items": [
                            {
                                "type": "organic",
                                "rank_group": 1,
                                "url": "https://example.com/page",
                                "title": "Technical SEO Page",
                                "description": "Fixture organic result for technical seo.",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/page",
                                "status_code": 200,
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {"text": "Header intro with enough words."}
                                        ]
                                    },
                                    "main_topic": [
                                        {
                                            "primary_content": [
                                                {
                                                    "text": (
                                                        "Technical SEO intro paragraph "
                                                        "with enough words."
                                                    )
                                                }
                                            ]
                                        }
                                    ],
                                },
                                "raw_html": "<html><body><main>Raw HTML body</main></body></html>",
                                "page_as_markdown": (
                                    "# Technical SEO\n\n"
                                    "Markdown fallback should be captured."
                                ),
                            }
                        ]
                    }
                ],
            }
        ]
    }
    entity_response_body = {
        "response": {
            "entities": [
                {
                    "entityId": "technical-seo",
                    "matchedText": "Technical SEO",
                    "confidenceScore": 7.5,
                    "relevanceScore": 0.92,
                    "type": ["Topic", "SEO"],
                }
            ]
        }
    }
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "kw-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(keyword_response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=keyword_expansion" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "serp-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(serp_response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=serp" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "page-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=page_text" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "entity-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(entity_response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=entities" / "part-0.parquet")

    (output_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "artifacts",
                "config": {"seed": "technical seo", "depth": 1},
                    "page_similarity": [
                        _page_similarity_entry(
                            target_keyword="technical seo",
                            url="https://example.com/page",
                            bge=0.9,
                            gemini_doc_retrieval=0.9,
                            gemini_semantic_similarity=0.9,
                        )
                    ],
                "catalog": {"datasets": {}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["page_content_fields"]["row_count"] > 0
    assert catalog["datasets"]["page_html"]["row_count"] > 0
    page_content_fields_dir = output_dir / "parquet" / "page_content_fields"
    page_html_dir = output_dir / "parquet" / "page_html"
    assert page_content_fields_dir.exists()
    assert page_html_dir.exists()

    rows = ds.dataset(page_content_fields_dir, format="parquet").to_table().to_pylist()
    html_rows = ds.dataset(page_html_dir, format="parquet").to_table().to_pylist()
    assert any(row["field_name"] == "page_content" for row in rows)
    assert any(row["field_name"] == "status_code" for row in rows)
    assert any(row["field_name"] == "page_as_markdown" for row in rows)
    assert any(row["raw_html"] == "<html><body><main>Raw HTML body</main></body></html>" for row in html_rows)


def test_normalize_run_materializes_structured_fields_and_html_from_stored_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    raw_responses_dir = output_dir / "parquet" / "raw_responses"
    (raw_responses_dir / "endpoint=keyword_expansion").mkdir(parents=True)
    (raw_responses_dir / "endpoint=serp").mkdir(parents=True)
    (raw_responses_dir / "endpoint=page_text").mkdir(parents=True)
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    keyword_response_body = {
        "tasks": [
            {
                "result": [
                    {"keyword": "technical seo"},
                ]
            }
        ]
    }
    serp_response_body = {
        "tasks": [
            {
                "keyword": "technical seo",
                "result": [
                    {
                        "items": [
                            {
                                "type": "organic",
                                "rank_group": 1,
                                "url": "https://example.com/product",
                                "title": "Technical SEO Product",
                                "description": "Fixture organic result.",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/product"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/product",
                                "status_code": 200,
                                "page_content": {
                                    "ratings": [
                                        {
                                            "name": None,
                                            "rating_value": 4,
                                            "max_rating_value": 5,
                                            "rating_count": 12,
                                            "relative_rating": 0.8,
                                        }
                                    ],
                                    "offers": [
                                        {
                                            "price": 129,
                                        }
                                    ],
                                    "comments": [
                                        {
                                            "rating": {
                                                "name": None,
                                                "rating_value": 5,
                                                "max_rating_value": 5,
                                                "rating_count": None,
                                                "relative_rating": 1.0,
                                            },
                                        }
                                    ],
                                },
                                "raw_html": "<html><body><main>Raw HTML body</main></body></html>",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "kw-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(keyword_response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=keyword_expansion" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "serp-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(serp_response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=serp" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "page-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=page_text" / "part-0.parquet")

    (output_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "artifacts",
                "config": {"seed": "technical seo", "depth": 1},
                "page_similarity": [
                    _page_similarity_entry(
                        target_keyword="technical seo",
                        url="https://example.com/product",
                        bge=0.9,
                        gemini_doc_retrieval=0.9,
                        gemini_semantic_similarity=0.9,
                    )
                ],
                "catalog": {"datasets": {}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = normalize_run(output_dir)

    assert catalog["datasets"]["page_content_fields"]["row_count"] > 0
    assert catalog["datasets"]["page_html"]["row_count"] > 0
    assert catalog["datasets"]["pages"]["row_count"] > 0
    assert catalog["datasets"]["passages"]["row_count"] == 0


def test_normalize_run_rejects_stored_raw_response_schema_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    raw_responses_dir = output_dir / "parquet" / "raw_responses"
    (raw_responses_dir / "endpoint=keyword_expansion").mkdir(parents=True)
    (raw_responses_dir / "endpoint=serp").mkdir(parents=True)
    (raw_responses_dir / "endpoint=page_text").mkdir(parents=True)
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "kw-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(
                    fixture_keyword_expansion_response("technical seo")
                ).encode("utf-8"),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=keyword_expansion" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "serp-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(
                    {
                        "tasks": [
                            {
                                "result": [
                                    {
                                        "items": [
                                            {
                                                "type": "organic",
                                                "rank_group": 1,
                                                "url": "https://example.com/page",
                                                "title": "Technical SEO Page",
                                                "description": "Fixture organic result.",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ).encode(
                    "utf-8"
                ),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=serp" / "part-0.parquet")
    pl.DataFrame(
        [
            {
                "run_id": "artifacts",
                "response_id": "page-resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps({"tasks": "not-a-list"}).encode(
                    "utf-8"
                ),
            }
        ]
    ).write_parquet(raw_responses_dir / "endpoint=page_text" / "part-0.parquet")

    (output_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "artifacts",
                "config": {"seed": "technical seo", "depth": 1},
                "page_similarity": [
                    _page_similarity_entry(
                        target_keyword="technical seo",
                        url="https://example.com/page",
                        bge=0.9,
                        gemini_doc_retrieval=0.9,
                        gemini_semantic_similarity=0.9,
                    )
                ],
                "catalog": {"datasets": {}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DataForSeoParseError) as exc_info:
        normalize_run(output_dir)

    error = exc_info.value
    assert error.endpoint == "page_text"
    assert error.path == "tasks"
    assert not any(
        (output_dir / "parquet" / name).exists()
        for name in CURATED_SCHEMAS
    )


def test_build_pages_and_passages_frame_keeps_page_rows_for_raw_html_without_text() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/raw-html"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/raw-html",
                                "raw_html": "<html><body>Raw HTML only</body></html>",
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-raw-html",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_pages_and_passages_frame(frame, run_id="run-1")
    rows = result.to_dicts()

    assert len(rows) == 1
    assert rows[0]["passage_id"] is None
    assert rows[0]["text"] == ""
    assert rows[0]["url"] == "https://example.com/raw-html"


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
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {
                                                "text": "Header intro with enough words."
                                            }
                                        ]
                                    },
                                    "main_topic": [
                                        {
                                            "primary_content": [
                                                {
                                                    "text": (
                                                        "Technical SEO intro paragraph "
                                                        "with enough words."
                                                    )
                                                },
                                                {
                                                    "text": (
                                                        "Site structure matters for "
                                                        "crawlability and indexation."
                                                    )
                                                },
                                            ]
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            }
        ]
    )

    result = build_pages_and_passages_frame(frame, run_id="run-1")
    rows = result.to_dicts()

    assert any(row["url"] == "https://example.com/page" for row in rows if row.get("passage_id") is None)
    assert any(
        row["text"] == "Header intro with enough words."
        for row in rows
        if row.get("passage_id") is not None
    )
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


def test_build_pages_and_passages_frame_skips_empty_text_rows_even_with_url() -> None:
    response_body = {
        "tasks": [
            {
                "data": {"url": "https://example.com/empty"},
                "result": [
                    {
                        "items": [
                            {
                                "crawl_status": "Page content is empty",
                                "items": [],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    frame = pl.DataFrame(
        [
            {
                "response_id": "resp-1",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            },
            {
                "response_id": "resp-2",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(response_body).encode("utf-8"),
            },
        ]
    )

    result = build_pages_and_passages_frame(frame, run_id="run-1")

    assert result.is_empty()


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
