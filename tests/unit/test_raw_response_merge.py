from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from seo_rank.cli import RAW_RESPONSE_SCHEMA
from seo_rank.cli import build_raw_response_record
from seo_rank.cli import merge_backlink_raw_response_rows
from seo_rank.cli import merge_raw_response_records
from seo_rank.cli import persist_backlink_raw_responses
from seo_rank.cli import persist_onpage_raw_responses
from seo_rank.dataforseo import fixture_backlinks_response
from seo_rank.dataforseo import fixture_onpage_instant_pages_response
from seo_rank.textrazor import fixture_entity_response


def _write_raw_response_partition(
    partition_dir: Path,
    rows: list[dict[str, object]],
) -> None:
    partition_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(rows, schema=RAW_RESPONSE_SCHEMA),
        partition_dir / "part-0.parquet",
        compression="zstd",
    )


def _raw_response_record(
    *,
    run_id: str,
    response_id: str,
    endpoint: str,
    provider: str,
    target_keyword: str,
    url: str,
    text: str,
) -> dict[str, object]:
    row = build_raw_response_record(
        run_id,
        endpoint=endpoint,
        provider=provider,
        response=fixture_entity_response(url=url, text=text),
        target_keyword=target_keyword,
        request_metadata={"target_keyword": target_keyword, "url": url},
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    row["response_id"] = response_id
    return row


def _raw_response_rows_by_key(
    rows: list[dict[str, object]],
) -> dict[tuple[str, str], dict[str, object]]:
    keyed_rows: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        metadata = json.loads(str(row["request_metadata_json"]))
        key = (
            str(row["target_keyword"]).casefold().strip(),
            str(metadata["url"]).strip(),
        )
        keyed_rows[key] = row
    return keyed_rows


def test_merge_raw_response_records_skips_existing_entities_and_leaves_other_partitions_unchanged(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    raw_responses_dir = run_dir / "parquet" / "raw_responses"
    entities_dir = raw_responses_dir / "endpoint=entities"
    keyword_expansion_dir = raw_responses_dir / "endpoint=keyword_expansion"
    serp_dir = raw_responses_dir / "endpoint=serp"
    page_text_dir = raw_responses_dir / "endpoint=page_text"

    existing_entity = _raw_response_record(
        run_id="artifacts",
        response_id="entity-existing",
        endpoint="entities",
        provider="textrazor",
        target_keyword="Technical SEO",
        url="https://example.com/a",
        text="Technical SEO helps crawlers discover the page.",
    )
    existing_other_rows = {
        "keyword_expansion": _raw_response_record(
            run_id="artifacts",
            response_id="kw-1",
            endpoint="keyword_expansion",
            provider="dataforseo",
            target_keyword="Technical SEO",
            url="https://example.com/keywords",
            text="Keyword expansion fixture.",
        ),
        "serp": _raw_response_record(
            run_id="artifacts",
            response_id="serp-1",
            endpoint="serp",
            provider="dataforseo",
            target_keyword="Technical SEO",
            url="https://example.com/serp",
            text="SERP fixture.",
        ),
        "page_text": _raw_response_record(
            run_id="artifacts",
            response_id="page-1",
            endpoint="page_text",
            provider="dataforseo",
            target_keyword="Technical SEO",
            url="https://example.com/page",
            text="Page text fixture.",
        ),
    }

    _write_raw_response_partition(entities_dir, [existing_entity])
    _write_raw_response_partition(
        keyword_expansion_dir,
        [existing_other_rows["keyword_expansion"]],
    )
    _write_raw_response_partition(serp_dir, [existing_other_rows["serp"]])
    _write_raw_response_partition(page_text_dir, [existing_other_rows["page_text"]])

    original_partition_bytes = {
        path: path.read_bytes()
        for path in [
            keyword_expansion_dir / "part-0.parquet",
            serp_dir / "part-0.parquet",
            page_text_dir / "part-0.parquet",
        ]
    }

    incoming_duplicate = _raw_response_record(
        run_id="artifacts",
        response_id="entity-duplicate",
        endpoint="entities",
        provider="textrazor",
        target_keyword=" technical seo ",
        url="https://example.com/a ",
        text="Technical SEO replacement should be skipped.",
    )
    incoming_new_key = _raw_response_record(
        run_id="artifacts",
        response_id="entity-new",
        endpoint="entities",
        provider="textrazor",
        target_keyword="technical seo",
        url="https://example.com/b",
        text="Technical SEO for a second page.",
    )

    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "artifacts",
                "catalog": {"datasets": {}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = merge_raw_response_records(
        run_dir,
        [incoming_duplicate, incoming_new_key],
        endpoint="entities",
        refresh=False,
    )

    merged_entities = pq.ParquetFile(entities_dir / "part-0.parquet").read().to_pylist()
    merged_rows_by_key = _raw_response_rows_by_key(merged_entities)

    assert len(merged_entities) == 2
    assert merged_rows_by_key[
        ("technical seo", "https://example.com/a")
    ]["response_id"] == "entity-existing"
    assert merged_rows_by_key[
        ("technical seo", "https://example.com/b")
    ]["response_id"] == "entity-new"
    assert (keyword_expansion_dir / "part-0.parquet").read_bytes() == original_partition_bytes[
        keyword_expansion_dir / "part-0.parquet"
    ]
    assert (serp_dir / "part-0.parquet").read_bytes() == original_partition_bytes[
        serp_dir / "part-0.parquet"
    ]
    assert (page_text_dir / "part-0.parquet").read_bytes() == original_partition_bytes[
        page_text_dir / "part-0.parquet"
    ]

    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    raw_responses_catalog = payload["catalog"]["datasets"]["raw_responses"]

    assert raw_responses_catalog == catalog["datasets"]["raw_responses"]
    assert raw_responses_catalog["row_count"] == 5
    assert raw_responses_catalog["source_response_ids"] == sorted(
        [
            "entity-existing",
            "entity-new",
            "kw-1",
            "page-1",
            "serp-1",
        ]
    )
    assert raw_responses_catalog["files"] == [
        "parquet/raw_responses/endpoint=entities/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    ]
    assert raw_responses_catalog["file_checksums"][
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet"
    ] == catalog["datasets"]["raw_responses"]["file_checksums"][
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet"
    ]


def test_merge_raw_response_records_refreshes_entities_latest_wins(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    raw_responses_dir = run_dir / "parquet" / "raw_responses"
    entities_dir = raw_responses_dir / "endpoint=entities"
    keyword_expansion_dir = raw_responses_dir / "endpoint=keyword_expansion"
    serp_dir = raw_responses_dir / "endpoint=serp"
    page_text_dir = raw_responses_dir / "endpoint=page_text"

    existing_entity = _raw_response_record(
        run_id="artifacts",
        response_id="entity-existing",
        endpoint="entities",
        provider="textrazor",
        target_keyword="Technical SEO",
        url="https://example.com/a",
        text="Technical SEO helps crawlers discover the page.",
    )
    _write_raw_response_partition(entities_dir, [existing_entity])
    _write_raw_response_partition(
        keyword_expansion_dir,
        [
            _raw_response_record(
                run_id="artifacts",
                response_id="kw-1",
                endpoint="keyword_expansion",
                provider="dataforseo",
                target_keyword="Technical SEO",
                url="https://example.com/keywords",
                text="Keyword expansion fixture.",
            )
        ],
    )
    _write_raw_response_partition(
        serp_dir,
        [
            _raw_response_record(
                run_id="artifacts",
                response_id="serp-1",
                endpoint="serp",
                provider="dataforseo",
                target_keyword="Technical SEO",
                url="https://example.com/serp",
                text="SERP fixture.",
            )
        ],
    )
    _write_raw_response_partition(
        page_text_dir,
        [
            _raw_response_record(
                run_id="artifacts",
                response_id="page-1",
                endpoint="page_text",
                provider="dataforseo",
                target_keyword="Technical SEO",
                url="https://example.com/page",
                text="Page text fixture.",
            )
        ],
    )

    replacement_entity = _raw_response_record(
        run_id="artifacts",
        response_id="entity-replacement",
        endpoint="entities",
        provider="textrazor",
        target_keyword=" technical seo ",
        url="https://example.com/a ",
        text="Technical SEO replacement wins.",
    )
    incoming_new_key = _raw_response_record(
        run_id="artifacts",
        response_id="entity-new",
        endpoint="entities",
        provider="textrazor",
        target_keyword="technical seo",
        url="https://example.com/b",
        text="Technical SEO for a second page.",
    )

    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "artifacts",
                "catalog": {"datasets": {}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = merge_raw_response_records(
        run_dir,
        [replacement_entity, incoming_new_key],
        endpoint="entities",
        refresh=True,
    )

    merged_entities = pq.ParquetFile(entities_dir / "part-0.parquet").read().to_pylist()
    merged_rows_by_key = _raw_response_rows_by_key(merged_entities)

    assert len(merged_entities) == 2
    assert merged_rows_by_key[
        ("technical seo", "https://example.com/a")
    ]["response_id"] == "entity-replacement"
    assert merged_rows_by_key[
        ("technical seo", "https://example.com/a")
    ]["response_body_bytes"] != existing_entity["response_body_bytes"]
    assert merged_rows_by_key[
        ("technical seo", "https://example.com/b")
    ]["response_id"] == "entity-new"

    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    raw_responses_catalog = payload["catalog"]["datasets"]["raw_responses"]

    assert raw_responses_catalog == catalog["datasets"]["raw_responses"]
    assert raw_responses_catalog["row_count"] == 5
    assert raw_responses_catalog["source_response_ids"] == sorted(
        [
            "entity-new",
            "entity-replacement",
            "kw-1",
            "page-1",
            "serp-1",
        ]
    )
    assert raw_responses_catalog["file_checksums"][
        "parquet/raw_responses/endpoint=entities/part-0.parquet"
    ] == catalog["datasets"]["raw_responses"]["file_checksums"][
        "parquet/raw_responses/endpoint=entities/part-0.parquet"
    ]


def _backlink_raw_response_record(
    *,
    run_id: str,
    response_id: str,
    target_keyword: str,
    url: str,
    endpoint: str = "backlinks_summary",
    variant: str = "summary",
) -> dict[str, object]:
    row = build_raw_response_record(
        run_id,
        endpoint=endpoint,
        provider="dataforseo",
        response={**fixture_backlinks_response(url, dofollow_only=variant == "dofollow"), "url": url},
        target_keyword=target_keyword,
        request_metadata={
            "target_keyword": target_keyword,
            "url": url,
            "variant": variant,
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    row["response_id"] = response_id
    return row


def test_merge_backlink_raw_response_rows_dedupes_by_keyword_url_and_variant() -> None:
    existing_summary = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-a-summary-old",
        target_keyword="technical seo",
        url="https://example.com/a",
        endpoint="backlinks_summary",
        variant="summary",
    )
    incoming_summary = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-a-summary-new",
        target_keyword=" technical seo ",
        url="https://example.com/a",
        endpoint="backlinks_summary",
        variant="summary",
    )
    incoming_new = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-b-summary",
        target_keyword="technical seo",
        url="https://example.com/b",
        endpoint="backlinks_summary",
        variant="summary",
    )
    incoming_tracked = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-a-summary-tracked",
        target_keyword="technical seo",
        url="https://example.com/a?utm_source=google&srsltid=click",
        endpoint="backlinks_summary",
        variant="summary",
    )

    merged_summary = merge_backlink_raw_response_rows(
        [existing_summary],
        [incoming_summary, incoming_new, incoming_tracked],
        endpoint="backlinks_summary",
    )

    assert len(merged_summary) == 2
    merged_by_id = {str(row["response_id"]): row for row in merged_summary}
    assert merged_by_id["backlink-a-summary-tracked"]["response_id"] == "backlink-a-summary-tracked"
    assert merged_by_id["backlink-b-summary"]["response_id"] == "backlink-b-summary"

    existing_dofollow = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-a-dofollow-old",
        target_keyword="technical seo",
        url="https://example.com/a",
        endpoint="backlinks_dofollow_summary",
        variant="dofollow",
    )
    incoming_dofollow = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-a-dofollow-new",
        target_keyword="technical seo",
        url="https://example.com/a",
        endpoint="backlinks_dofollow_summary",
        variant="dofollow",
    )

    merged_dofollow = merge_backlink_raw_response_rows(
        [existing_dofollow],
        [incoming_dofollow],
        endpoint="backlinks_dofollow_summary",
    )

    assert len(merged_dofollow) == 1
    assert merged_dofollow[0]["response_id"] == "backlink-a-dofollow-new"


def test_persist_backlink_raw_responses_rewrites_each_partition_once(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    summary_dir = run_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    dofollow_dir = (
        run_dir / "parquet" / "raw_responses" / "endpoint=backlinks_dofollow_summary"
    )
    existing = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-existing",
        target_keyword="technical seo",
        url="https://example.com/existing",
        endpoint="backlinks_summary",
        variant="summary",
    )
    _write_raw_response_partition(summary_dir, [existing])
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "artifacts", "catalog": {"datasets": {}}}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    incoming = [
        _backlink_raw_response_record(
            run_id="artifacts",
            response_id=f"backlink-summary-{index}",
            target_keyword="technical seo",
            url=f"https://example.com/{index}",
            endpoint="backlinks_summary",
            variant="summary",
        )
        for index in range(3)
    ] + [
        _backlink_raw_response_record(
            run_id="artifacts",
            response_id=f"backlink-dofollow-{index}",
            target_keyword="technical seo",
            url=f"https://example.com/{index}",
            endpoint="backlinks_dofollow_summary",
            variant="dofollow",
        )
        for index in range(3)
    ]

    persist_backlink_raw_responses(run_dir, incoming)

    merged_summary = pq.ParquetFile(summary_dir / "part-0.parquet").read().to_pylist()
    merged_dofollow = pq.ParquetFile(dofollow_dir / "part-0.parquet").read().to_pylist()
    assert len(merged_summary) == 4
    assert len(merged_dofollow) == 3


def _onpage_raw_response_record(
    *,
    run_id: str,
    response_id: str,
    target_keyword: str,
    url: str,
) -> dict[str, object]:
    row = build_raw_response_record(
        run_id,
        endpoint="onpage_instant_pages",
        provider="dataforseo",
        response={**fixture_onpage_instant_pages_response(url), "url": url},
        target_keyword=target_keyword,
        request_metadata={
            "target_keyword": target_keyword,
            "url": url,
            "enable_javascript": True,
            "enable_browser_rendering": True,
            "load_resources": True,
            "validate_micromarkup": True,
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    row["response_id"] = response_id
    return row


def test_persist_onpage_raw_responses_merges_by_target_keyword_and_url(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    onpage_dir = run_dir / "parquet" / "raw_responses" / "endpoint=onpage_instant_pages"
    backlinks_dir = run_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    existing_onpage = _onpage_raw_response_record(
        run_id="artifacts",
        response_id="onpage-existing-old",
        target_keyword="technical seo",
        url="https://example.com/existing",
    )
    existing_backlink = _backlink_raw_response_record(
        run_id="artifacts",
        response_id="backlink-existing",
        target_keyword="technical seo",
        url="https://example.com/existing",
        endpoint="backlinks_summary",
        variant="summary",
    )
    _write_raw_response_partition(onpage_dir, [existing_onpage])
    _write_raw_response_partition(backlinks_dir, [existing_backlink])
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "artifacts", "catalog": {"datasets": {}}}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    incoming = [
        _onpage_raw_response_record(
            run_id="artifacts",
            response_id="onpage-existing-new",
            target_keyword=" technical seo ",
            url="https://example.com/existing",
        ),
        *[
            _onpage_raw_response_record(
                run_id="artifacts",
                response_id=f"onpage-{index}",
                target_keyword="technical seo",
                url=f"https://example.com/{index}",
            )
            for index in range(3)
        ],
    ]

    persist_onpage_raw_responses(run_dir, incoming)

    merged_onpage = pq.ParquetFile(onpage_dir / "part-0.parquet").read().to_pylist()
    merged_backlinks = pq.ParquetFile(backlinks_dir / "part-0.parquet").read().to_pylist()
    assert len(merged_onpage) == 4
    merged_by_id = {str(row["response_id"]): row for row in merged_onpage}
    assert merged_by_id["onpage-existing-new"]["response_id"] == "onpage-existing-new"
    assert len(merged_backlinks) == 1
    assert merged_backlinks[0]["response_id"] == "backlink-existing"
