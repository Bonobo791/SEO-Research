from __future__ import annotations

import json
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from seo_rank.cli import load_pages_for_textrazor
from seo_rank.cli import main
from seo_rank.cli import RAW_RESPONSE_SCHEMA
from seo_rank.data.normalize import CURATED_SCHEMAS
from seo_rank.dataforseo import fixture_page_text_response
from seo_rank.dataforseo import parsed_page_text


def _assert_textrazor_entities_raw_response_contract(parquet_path: Path) -> None:
    table = pq.ParquetFile(parquet_path).read()
    assert table.schema == RAW_RESPONSE_SCHEMA
    rows = table.to_pylist()
    assert rows
    assert {row["endpoint"] for row in rows} == {"entities"}
    assert {row["provider"] for row in rows} == {"textrazor"}


def _write_curated_pages_partition(
    run_dir: Path,
    rows: list[dict[str, object]],
) -> None:
    pages_dir = run_dir / "parquet" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(rows, schema=CURATED_SCHEMAS["pages"]),
        pages_dir / "part-0.parquet",
        compression="zstd",
    )


def test_load_pages_for_textrazor_prefers_raw_page_text_over_curated_pages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "artifacts"
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
                str(run_dir),
                "--dry-run",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    _write_curated_pages_partition(
        run_dir,
        [
            {
                "run_id": "artifacts",
                "target_keyword_id": "curated-keyword",
                "target_keyword": "technical seo",
                "response_id": "curated-response",
                "page_id": "curated-page",
                "canonical_url_hash": "curated-hash",
                "url": "https://example.com/technical-seo/1",
                "title": "Curated fallback title",
                "text": "Curated fallback text",
                "schema_version": "curated.v1",
            }
        ],
    )

    expected_page = parsed_page_text(
        fixture_page_text_response(
            "https://example.com/technical-seo/1",
            "technical seo",
        )
    )
    pages = load_pages_for_textrazor(run_dir, "technical seo")

    assert pages == [
        {
            "target_keyword": "technical seo",
            **expected_page,
        }
    ]


def test_load_pages_for_textrazor_falls_back_to_curated_pages_when_raw_page_text_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "artifacts"
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
                str(run_dir),
                "--dry-run",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    shutil.rmtree(run_dir / "parquet" / "raw_responses" / "endpoint=page_text")
    _write_curated_pages_partition(
        run_dir,
        [
            {
                "run_id": "artifacts",
                "target_keyword_id": "curated-keyword",
                "target_keyword": "technical seo",
                "response_id": "curated-response",
                "page_id": "curated-page",
                "canonical_url_hash": "curated-hash",
                "url": "https://example.com/curated",
                "title": "Curated fallback title",
                "text": "Curated fallback text",
                "schema_version": "curated.v1",
            }
        ],
    )

    pages = load_pages_for_textrazor(run_dir, "technical seo")

    assert pages == [
        {
            "target_keyword": "technical seo",
            "url": "https://example.com/curated",
            "title": "Curated fallback title",
            "text": "Curated fallback text",
        }
    ]


def test_run_stored_run_live_textrazor_only_backfills_entities_without_dataforseo_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_TEXTRAZOR", "1")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--depth",
                "1",
                "--output-dir",
                str(run_dir),
                "--dry-run",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    dataforseo_calls: list[str] = []
    textrazor_requests: list[dict[str, object]] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, body, timeout
        dataforseo_calls.append(url)
        raise AssertionError("stored-run live-textrazor-only should not call DataForSEO")

    def textrazor_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
        ) -> dict[str, object]:
        textrazor_requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
                "timeout": timeout,
            }
        )
        return {
            "response": {
                "entities": [
                    {
                        "entityId": "technical-seo-backfill",
                        "matchedText": "Technical SEO",
                        "confidenceScore": 9,
                        "relevanceScore": 0.99,
                        "type": ["Topic"],
                    }
                ],
            }
        }

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT", textrazor_transport)

    def fail_if_keyword_refresh_requested(*args, **kwargs) -> None:
        raise AssertionError("stored-run live-textrazor-only should not rebuild keywords")

    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", fail_if_keyword_refresh_requested)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(run_dir),
            "--live-textrazor-only",
        ]
    )

    assert exit_code == 0
    assert dataforseo_calls == []
    assert len(textrazor_requests) == 1

    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_textrazor_only"] is True
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 4
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=entities/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    ]
    assert payload["textrazor_entities"] == [
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "technical-seo-backfill",
            "matched_text": "Technical SEO",
            "confidence": 9.0,
            "relevance": 0.99,
            "types": ["Topic"],
            "target_keyword": "technical seo",
        }
    ]
    assert payload["keyword_results"][0]["textrazor_entities"] == payload["textrazor_entities"]
    _assert_textrazor_entities_raw_response_contract(
        run_dir / "parquet" / "raw_responses" / "endpoint=entities" / "part-0.parquet"
    )
    assert (run_dir / "stats" / "stats_summary.json").exists()
