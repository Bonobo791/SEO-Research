"""Stored-run end-to-end regressions for OnPage pipeline (Phase 7.1 slice 18)."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from seo_rank.cli import main
from seo_rank.cli import RAW_RESPONSE_SCHEMA
from seo_rank.cli import build_raw_response_record
from seo_rank.dataforseo import fixture_backlinks_response_for_request_body
from seo_rank.dataforseo import fixture_keyword_expansion_response
from seo_rank.dataforseo import fixture_onpage_instant_pages_response
from seo_rank.dataforseo import fixture_page_text_response
from seo_rank.dataforseo import fixture_serp_response
from seo_rank.domain_blocklist import DomainBlocklist
from tests.fixtures.onpage_pipeline import assert_onpage_row_matches_fixture
from tests.fixtures.onpage_pipeline import assert_onpage_stats_families
from tests.fixtures.onpage_pipeline import vary_onpage_fixture_response


def _dataforseo_transport_factory(
    live_onpage_targets: list[str],
    *,
    include_backlinks: bool = True,
    live_call_log: list[str] | None = None,
):
    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        if live_call_log is not None:
            live_call_log.append(url)
        request_body = json.loads(body.decode("utf-8"))
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return fixture_keyword_expansion_response("technical seo")
        if url.endswith("/serp/google/organic/live/advanced"):
            return fixture_serp_response("technical seo")
        if url.endswith("/backlinks/summary/live") or url.endswith("/backlinks/backlinks/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            target_url = request_body[0]["url"]
            live_onpage_targets.append(target_url)
            return vary_onpage_fixture_response(
                target_url,
                fixture_onpage_instant_pages_response(target_url),
            )
        if include_backlinks and url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    return dataforseo_transport


def test_stored_run_onpage_backfill_materializes_full_pipeline_without_touching_unrelated_partitions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_onpage_targets: list[str] = []
    live_call_log: list[str] = []
    monkeypatch.setattr(
        "seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT",
        _dataforseo_transport_factory(
            live_onpage_targets,
            live_call_log=live_call_log,
        ),
    )

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--keyword-limit",
                "1",
                "--depth",
                "2",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    assert not (
        output_dir / "parquet" / "raw_responses" / "endpoint=onpage_instant_pages"
    ).exists()

    seed_call_count = len(live_call_log)
    live_call_log.clear()

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--keyword-limit",
            "1",
        ]
    )

    assert exit_code == 0
    assert seed_call_count == 0
    assert len(live_onpage_targets) == 2
    assert {
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
    } == set(live_onpage_targets)
    assert all("/on_page/instant_pages" in url or "/backlinks/summary/live" in url for url in live_call_log)
    assert not any("/serp/google/organic/live/advanced" in url for url in live_call_log)
    assert not any("/on_page/content_parsing/live" in url for url in live_call_log)
    assert not any(
        "/keywords_data/google_ads/keywords_for_keywords/live" in url
        for url in live_call_log
    )

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["catalog"]["datasets"]["onpage_features"]["row_count"] == 2
    assert (output_dir / "stats" / "stats_summary.json").exists()

    onpage_signals = ds.dataset(
        output_dir / "parquet" / "onpage_signals",
        format="parquet",
    ).to_table().to_pylist()
    onpage_features = ds.dataset(
        output_dir / "parquet" / "onpage_features",
        format="parquet",
    ).to_table().to_pylist()

    for url in live_onpage_targets:
        signals_row = next(row for row in onpage_signals if row["url"] == url)
        features_row = next(row for row in onpage_features if row["url"] == url)
        assert_onpage_row_matches_fixture(signals_row, url)
        assert_onpage_row_matches_fixture(features_row, url)

    summary = json.loads(
        (output_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8")
    )
    report = (output_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")
    assert_onpage_stats_families(summary, report)


def test_stored_run_depth_refresh_reuses_existing_usable_onpage_rows(
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
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--keyword-limit",
                "1",
                "--depth",
                "2",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    kept_url = "https://example.com/technical-seo/1"
    existing_url = "https://example.com/technical-seo/2"
    new_url = "https://example.com/technical-seo/3"
    onpage_partition_path = (
        output_dir / "parquet" / "raw_responses" / "endpoint=onpage_instant_pages" / "part-0.parquet"
    )
    onpage_partition_path.parent.mkdir(parents=True, exist_ok=True)
    seed_rows = [
        build_raw_response_record(
            output_dir.name,
            endpoint="onpage_instant_pages",
            provider="dataforseo",
            response=vary_onpage_fixture_response(
                kept_url,
                fixture_onpage_instant_pages_response(kept_url),
            ),
            target_keyword="technical seo",
            request_metadata={
                "target_keyword": "technical seo",
                "url": kept_url,
            },
            recorded_at="2026-07-05T12:00:00+00:00",
        ),
        build_raw_response_record(
            output_dir.name,
            endpoint="onpage_instant_pages",
            provider="dataforseo",
            response=vary_onpage_fixture_response(
                existing_url,
                fixture_onpage_instant_pages_response(existing_url),
            ),
            target_keyword="technical seo",
            request_metadata={
                "target_keyword": "technical seo",
                "url": existing_url,
            },
            recorded_at="2026-07-05T12:00:00+00:00",
        ),
    ]
    pq.write_table(pa.Table.from_pylist(seed_rows, schema=RAW_RESPONSE_SCHEMA), onpage_partition_path)

    live_onpage_targets: list[str] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        request_body = json.loads(body.decode("utf-8"))
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return fixture_keyword_expansion_response("technical seo")
        if url.endswith("/serp/google/organic/live/advanced"):
            return fixture_serp_response("technical seo")
        if url.endswith("/backlinks/summary/live") or url.endswith("/backlinks/backlinks/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            target_url = request_body[0]["url"]
            live_onpage_targets.append(target_url)
            return fixture_onpage_instant_pages_response(target_url)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setattr(
        "seo_rank.cli.DomainBlocklist.load",
        lambda *_args, **_kwargs: DomainBlocklist(output_dir / "blocklist.txt", set()),
    )
    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--stored-run",
                str(output_dir),
                "--live-providers",
                "--live-backlinks",
                "--keyword-limit",
                "1",
                "--depth",
                "3",
            ]
        )
        == 0
    )

    assert live_onpage_targets == [new_url]


def test_stored_run_partial_onpage_backfill_preserves_existing_row_and_materializes_downstream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_onpage_targets: list[str] = []
    monkeypatch.setattr(
        "seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT",
        _dataforseo_transport_factory(live_onpage_targets),
    )

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--output-dir",
                str(output_dir),
                "--live-providers",
                "--live-backlinks",
                "--keyword-limit",
                "1",
                "--depth",
                "2",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    kept_url = "https://example.com/technical-seo/1"
    missing_url = "https://example.com/technical-seo/2"
    onpage_partition_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
        / "part-0.parquet"
    )
    onpage_table = pq.ParquetFile(onpage_partition_path).read()
    kept_onpage_rows = [
        row
        for row in onpage_table.to_pylist()
        if json.loads(row["request_metadata_json"])["url"] != missing_url
    ]
    pq.write_table(
        pa.Table.from_pylist(kept_onpage_rows, schema=onpage_table.schema),
        onpage_partition_path,
    )

    pre_signals = ds.dataset(
        output_dir / "parquet" / "onpage_signals",
        format="parquet",
    ).to_table().to_pylist()
    pre_kept_row = next(row for row in pre_signals if row["url"] == kept_url)

    live_onpage_targets.clear()

    def fail_if_rebuilt(*args, **kwargs) -> None:
        raise AssertionError("stored-run should not rebuild the whole keyword result")

    monkeypatch.setattr("seo_rank.cli.build_offline_keyword_result", fail_if_rebuilt)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", fail_if_rebuilt)

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--stored-run",
                str(output_dir),
                "--live-providers",
                "--live-backlinks",
                "--keyword-limit",
                "1",
            ]
        )
        == 0
    )

    assert live_onpage_targets == [missing_url]

    post_signals = ds.dataset(
        output_dir / "parquet" / "onpage_signals",
        format="parquet",
    ).to_table().to_pylist()
    post_features = ds.dataset(
        output_dir / "parquet" / "onpage_features",
        format="parquet",
    ).to_table().to_pylist()

    post_kept_signals = next(row for row in post_signals if row["url"] == kept_url)
    post_kept_features = next(row for row in post_features if row["url"] == kept_url)
    assert post_kept_signals["flesch_kincaid_readability_index"] == pre_kept_row[
        "flesch_kincaid_readability_index"
    ]
    assert post_kept_signals["cumulative_layout_shift"] == pre_kept_row["cumulative_layout_shift"]
    assert_onpage_row_matches_fixture(post_kept_signals, kept_url)
    assert_onpage_row_matches_fixture(post_kept_features, kept_url)

    backfilled_signals = next(row for row in post_signals if row["url"] == missing_url)
    backfilled_features = next(row for row in post_features if row["url"] == missing_url)
    assert_onpage_row_matches_fixture(backfilled_signals, missing_url)
    assert_onpage_row_matches_fixture(backfilled_features, missing_url)

    summary = json.loads(
        (output_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8")
    )
    report = (output_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")
    assert_onpage_stats_families(summary, report)
