"""Shared helpers for OnPage pipeline regression tests (Phase 7.1 slice 18)."""
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md


from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seo_rank.cli import RAW_RESPONSE_SCHEMA
from seo_rank.cli import build_raw_response_record
from seo_rank.data.normalize import _onpage_signals_row
from seo_rank.dataforseo import BACKLINKS_QUERY_SUMMARY
from seo_rank.dataforseo import fixture_backlinks_response
from seo_rank.dataforseo import fixture_onpage_instant_pages_response

NESTED_CRITICAL_COLUMNS = (
    "onpage_score",
    "is_https",
    "canonical",
    "no_h1_tag",
    "has_render_blocking_resources",
    "flesch_kincaid_readability_index",
    "time_to_first_byte_ms",
    "largest_contentful_paint_ms",
    "cumulative_layout_shift",
    "total_transfer_size",
    "has_valid_structured_data",
    "micromarkup_items_count",
    "micromarkup_errors_count",
    "micromarkup_warnings_count",
    "seo_friendly_url",
    "is_broken",
    "deprecated_html_tags",
    "title_length",
    "description_length",
    "internal_links_count",
    "external_links_count",
    "follow",
    "duplicate_meta_tags_count",
    "description_to_content_consistency",
    "title_to_content_consistency",
    "h1_count",
    "h2_count",
    "h3_count",
    "has_og_tags",
    "has_twitter_tags",
    "cache_control_cachable",
    "cache_control_ttl",
    "click_depth",
    "encoded_size",
    "total_dom_size",
    "resource_errors_count",
    "resource_warnings_count",
    "connection_time_ms",
    "time_to_secure_connection_ms",
    "request_sent_time_ms",
    "download_time_ms",
    "duration_time_ms",
    "fetch_end_ms",
    "dom_complete_ms",
    "time_to_interactive_ms",
    "first_input_delay_ms",
)

ONPAGE_STATS_SIGNAL_ASSERTIONS = (
    ("onpage_content_quality", "onpage_score"),
    ("onpage_content_quality", "flesch_kincaid_readability_index"),
    ("onpage_content_quality", "description_to_content_consistency"),
    ("onpage_core_web_vitals", "cumulative_layout_shift"),
)


def _rank_from_fixture_url(url: str) -> int:
    suffix = url.rstrip("/").rsplit("/", 1)[-1]
    return int(suffix)


def vary_onpage_fixture_response(
    url: str,
    response: dict[str, object],
) -> dict[str, object]:
    """Introduce per-URL variation so tiny panels have within-keyword signal variance."""

    rank = _rank_from_fixture_url(url)
    tasks = response["tasks"]
    assert isinstance(tasks, list) and tasks
    result = tasks[0]["result"]
    assert isinstance(result, list) and result
    items = result[0]["items"]
    assert isinstance(items, list) and items
    item = items[0]
    assert isinstance(item, dict)
    item["onpage_score"] = 85.5 - ((rank - 1) * 5.0)
    meta = item.get("meta")
    assert isinstance(meta, dict)
    meta["cumulative_layout_shift"] = 0.05 + ((rank - 1) * 0.02)
    content = meta.get("content")
    assert isinstance(content, dict)
    content["flesch_kincaid_readability_index"] = 58.0 - ((rank - 1) * 2.0)
    content["description_to_content_consistency"] = 0.4736842215061188 - (
        (rank - 1) * 0.05
    )
    return response


def fixture_onpage_item(url: str, *, vary_by_rank: bool = True) -> dict[str, object]:
    response = fixture_onpage_instant_pages_response(url)
    if vary_by_rank:
        response = vary_onpage_fixture_response(url, response)
    tasks = response["tasks"]
    assert isinstance(tasks, list) and tasks
    result = tasks[0]["result"]
    assert isinstance(result, list) and result
    items = result[0]["items"]
    assert isinstance(items, list) and items
    item = items[0]
    assert isinstance(item, dict)
    return item


def expected_onpage_curated_values(
    url: str,
    *,
    vary_by_rank: bool = True,
) -> dict[str, object]:
    row = _onpage_signals_row(
        run_id="fixture-run",
        target_keyword="fixture-keyword",
        response_id="fixture-response",
        url=url,
        item=fixture_onpage_item(url, vary_by_rank=vary_by_rank),
    )
    return {column: row[column] for column in NESTED_CRITICAL_COLUMNS if column in row}


def write_onpage_instant_pages_raw_row(
    run_dir: Path,
    *,
    target_keyword: str,
    url: str,
    recorded_at: str = "2026-07-05T12:00:00+00:00",
    vary_by_rank: bool = True,
) -> None:
    onpage_dir = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
    )
    onpage_dir.mkdir(parents=True, exist_ok=True)
    response = fixture_onpage_instant_pages_response(url)
    if vary_by_rank:
        response = vary_onpage_fixture_response(url, response)
    onpage_record = build_raw_response_record(
        run_dir.name,
        endpoint="onpage_instant_pages",
        provider="dataforseo",
        response=response,
        target_keyword=target_keyword,
        request_metadata={
            "target_keyword": target_keyword,
            "url": url,
        },
        recorded_at=recorded_at,
    )
    part_path = onpage_dir / "part-0.parquet"
    if part_path.exists():
        existing = pq.ParquetFile(part_path).read().to_pylist()
        existing.append(onpage_record)
        pq.write_table(
            pa.Table.from_pylist(existing, schema=RAW_RESPONSE_SCHEMA),
            part_path,
        )
    else:
        pq.write_table(
            pa.Table.from_pylist([onpage_record], schema=RAW_RESPONSE_SCHEMA),
            part_path,
        )


def write_backlinks_summary_raw_row(
    run_dir: Path,
    *,
    target_keyword: str,
    url: str,
    recorded_at: str = "2026-07-02T12:00:00+00:00",
) -> None:
    summary_dir = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_summary"
    )
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_record = build_raw_response_record(
        run_dir.name,
        endpoint="backlinks_summary",
        provider="dataforseo",
        response=fixture_backlinks_response(url),
        target_keyword=target_keyword,
        request_metadata={
            "target_keyword": target_keyword,
            "url": url,
            "variant": BACKLINKS_QUERY_SUMMARY,
        },
        recorded_at=recorded_at,
    )
    part_path = summary_dir / "part-0.parquet"
    if part_path.exists():
        existing = pq.ParquetFile(part_path).read().to_pylist()
        existing.append(summary_record)
        pq.write_table(
            pa.Table.from_pylist(existing, schema=RAW_RESPONSE_SCHEMA),
            part_path,
        )
    else:
        pq.write_table(
            pa.Table.from_pylist([summary_record], schema=RAW_RESPONSE_SCHEMA),
            part_path,
        )


def assert_onpage_row_matches_fixture(
    row: Mapping[str, object],
    url: str,
    *,
    columns: tuple[str, ...] = NESTED_CRITICAL_COLUMNS,
) -> None:
    expected = expected_onpage_curated_values(url)
    for column in columns:
        assert column in row, f"missing column {column!r} in row"
        actual = row[column]
        target = expected[column]
        if isinstance(target, float):
            assert actual == pytest.approx(target)
        else:
            assert actual == target


def assert_onpage_stats_families(summary: Mapping[str, object], report: str) -> None:
    rank_depths = summary["rank_depths"]
    assert isinstance(rank_depths, Mapping)
    top_20 = rank_depths["top_20"]
    assert isinstance(top_20, Mapping)
    families = top_20["families"]
    assert isinstance(families, Mapping)

    for family_key in (
        "onpage_content_quality",
        "onpage_core_web_vitals",
        "onpage_technical_checks",
    ):
        assert family_key in families
        assert f"#### Family: {family_key}" in report

    for family_key, signal in ONPAGE_STATS_SIGNAL_ASSERTIONS:
        family = families[family_key]
        assert isinstance(family, Mapping)
        spearman = family["spearman"]
        assert isinstance(spearman, Mapping)
        signals = spearman["signals"]
        assert isinstance(signals, Mapping)
        signal_summary = signals[signal]
        keyword_tests = signal_summary.get("keyword_tests")
        assert isinstance(keyword_tests, list) and keyword_tests, (
            f"expected keyword-level spearman tests for {family_key}/{signal}"
        )
        assert signal_summary["status"] in {"computed", "skipped"}
        if signal_summary["status"] == "skipped":
            assert signal_summary.get("bh_skipped_reason") == "underpowered"

        regression = family["regression"]
        assert isinstance(regression, Mapping)
        regression_signals = regression["signals"]
        assert isinstance(regression_signals, Mapping)
        regression_summary = regression_signals[signal]
        if regression_summary.get("invalid_controls") == [
            {"column": "site_scale", "reason": "missing_values"}
        ]:
            pytest.skip("OnPage fixture does not provide every site_scale component")
        assert regression_summary["status"] in {"computed", "skipped"}
        assert regression_summary.get("skipped_reason") != "missing_signal_column"
