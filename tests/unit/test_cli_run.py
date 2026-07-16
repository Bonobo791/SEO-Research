import hashlib
import json
import logging
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from seo_rank.dataforseo import DataForSeoClientError
from seo_rank.dataforseo import DataForSeoCredentials
from seo_rank.dataforseo import fixture_backlinks_detail_response
from seo_rank.dataforseo import fixture_backlinks_response
from seo_rank.dataforseo import fixture_backlinks_response_for_request_body
from seo_rank.dataforseo import fixture_keyword_expansion_response
from seo_rank.dataforseo import fixture_page_text_response
from seo_rank.dataforseo import fixture_onpage_instant_pages_response
from seo_rank.dataforseo import fixture_serp_response
from seo_rank.dataforseo import extract_response_url
from seo_rank.dataforseo import onpage_instant_pages_response_is_usable
from seo_rank.domain_blocklist import DomainBlocklist
from seo_rank.cli import RAW_RESPONSE_SCHEMA
from seo_rank.cli import build_raw_response_record
from seo_rank.cli import build_live_payload
from seo_rank.cli import enrich_run_payload_page_similarity
from seo_rank.cli import fetch_dataforseo_backlinks_for_urls
from seo_rank.cli import fetch_onpage_signals_for_urls
from seo_rank.cli import fetch_page_text_for_urls
from seo_rank.cli import main
from seo_rank.cli import RunConfig
from seo_rank.cli import prepare_textrazor_only_context
from seo_rank.cli import render_markdown_report
from seo_rank.cli import rewrite_backlink_endpoint_partition
from seo_rank.cli import rewrite_endpoint_partition
from seo_rank.cli import merge_stored_run_cli_overlay
from seo_rank.cli import stored_serp_response_is_usable
from seo_rank.textrazor import fixture_entity_response
from seo_rank.textrazor import TextRazorCredentials


def _assert_textrazor_entities_raw_response_contract(parquet_path: Path) -> None:
    table = pq.ParquetFile(parquet_path).read()
    assert table.schema == RAW_RESPONSE_SCHEMA
    rows = table.to_pylist()
    assert rows
    assert {row["endpoint"] for row in rows} == {"entities"}
    assert {row["provider"] for row in rows} == {"textrazor"}


def _empty_page_text_response(
    url: str,
    *,
    crawl_status: str = "Page content is empty",
) -> dict[str, object]:
    return {
        "tasks": [
            {
                "data": {"url": url},
                "status_code": 20000,
                "status_message": "Ok.",
                "result": [{"items": [], "crawl_status": crawl_status}],
            }
        ]
    }


def _javascript_disabled_page_text_response(url: str) -> dict[str, object]:
    return {
        "tasks": [
            {
                "data": {"url": url},
                "status_code": 20000,
                "status_message": "Ok.",
                "result": [
                    {
                        "items": [
                            {
                                "page_content": {
                                    "main_topic": [
                                        {
                                            "primary_content": [
                                                {"text": "JavaScript is disabled"}
                                            ]
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }


def test_fetch_page_text_for_urls_stops_after_javascript_stage_success() -> None:
    url = "https://example.com/rendered"
    request_bodies: list[dict[str, object]] = []
    responses = iter(
        [
            _empty_page_text_response(url),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
    ) == [_empty_page_text_response(url)]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"])
        for body in request_bodies
    ] == [(False, False)]


def test_fetch_page_text_for_urls_stops_after_browser_stage_success() -> None:
    url = "https://example.com/rendered"
    request_bodies: list[dict[str, object]] = []
    responses = iter(
        [
            _empty_page_text_response(url),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
    ) == [_empty_page_text_response(url)]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"])
        for body in request_bodies
    ] == [(False, False)]


def test_fetch_page_text_for_urls_exhaustion_retains_browser_response() -> None:
    url = "https://example.com/empty"
    request_bodies: list[dict[str, object]] = []
    browser_response = _empty_page_text_response(
        url,
        crawl_status="browser fallback remained empty",
    )
    responses = iter(
        [
            _empty_page_text_response(url, crawl_status="baseline remained empty"),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
    ) == [_empty_page_text_response(url, crawl_status="baseline remained empty")]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"])
        for body in request_bodies
    ] == [(False, False)]


def test_fetch_page_text_for_urls_stops_after_usable_baseline_response() -> None:
    url = "https://example.com/static"
    request_bodies: list[dict[str, object]] = []
    response = fixture_page_text_response(url, "technical seo")

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return response

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
    ) == [response]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"])
        for body in request_bodies
    ] == [(False, False)]


def test_fetch_page_text_for_urls_blocklists_terminal_timeout_at_the_baseline(
    tmp_path: Path,
) -> None:
    url = "https://example.com/timeout"
    request_bodies: list[dict[str, object]] = []
    sleeps: list[float] = []
    timeout_response = {
        "tasks": [
            {
                "status_code": 50402,
                "status_message": "Timeout",
                "result": [],
            }
        ]
    }
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return timeout_response

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
        blocklist=blocklist,
        sleep=sleeps.append,
    ) == [timeout_response]
    assert sleeps == [1.0]
    assert all(body["switch_pool"] is False for body in request_bodies)
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"])
        for body in request_bodies
    ] == [(False, False), (False, False)]
    assert blocklist.is_blocked(url)


def test_fetch_page_text_for_urls_blocklists_final_empty_content(
    tmp_path: Path,
) -> None:
    url = "https://empty.example/technical-seo"
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")
    responses = iter(
        [
            {
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [
                            {
                                "url": url,
                                "crawl_status": "Page content is empty",
                                "items": [],
                            }
                        ],
                    }
                ]
            },
            _empty_page_text_response(url),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        del body
        return next(responses)

    result = fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials("login", "password"),
        transport=transport,
        blocklist=blocklist,
    )

    assert result[-1]["tasks"][0]["result"][0]["crawl_status"] == (
        "Page content is empty"
    )
    assert blocklist.is_blocked(url)


def test_fetch_page_text_for_urls_does_not_blocklist_empty_content_recovered_by_retry(
    tmp_path: Path,
) -> None:
    url = "https://recovered.example/technical-seo"
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")
    responses = iter(
        [
            {
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [
                            {
                                "url": url,
                                "crawl_status": "Page content is empty",
                                "items": [
                                    {
                                        "url": url,
                                        "crawl_status": "Page content is empty",
                                        "checks": {"is_broken": True},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            fixture_page_text_response(url, "technical seo"),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        del body
        return next(responses)

    fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials("login", "password"),
        transport=transport,
        blocklist=blocklist,
    )

    assert not blocklist.is_blocked(url)


def test_fetch_page_text_for_urls_retries_task_timeout_before_success(
    tmp_path: Path,
) -> None:
    url = "https://example.com/slow"
    request_bodies: list[dict[str, object]] = []
    sleeps: list[float] = []
    responses = iter(
        [
            {
                "tasks": [
                    {"status_code": 50402, "status_message": "Timeout", "result": []}
                ]
            },
            fixture_page_text_response(url, "technical seo"),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
        blocklist=blocklist,
        sleep=sleeps.append,
    ) == [fixture_page_text_response(url, "technical seo")]
    assert sleeps == [1.0]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"], body["switch_pool"])
        for body in request_bodies
    ] == [(False, False, False), (False, False, False)]
    assert not blocklist.is_blocked(url)


def test_fetch_page_text_for_urls_does_not_blocklist_transport_error(
    tmp_path: Path,
) -> None:
    url = "https://example.com/unavailable"
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")

    def transport(**_: object) -> dict[str, object]:
        raise OSError("connection failed")

    with pytest.raises(DataForSeoClientError):
        fetch_page_text_for_urls(
            "technical seo",
            [url],
            credentials=DataForSeoCredentials(login="user", password="pass"),
            transport=transport,
            blocklist=blocklist,
        )

    assert not blocklist.is_blocked(url)


def test_fetch_page_text_for_urls_switches_pool_after_unreachable() -> None:
    url = "https://example.com/blocked"
    request_bodies: list[dict[str, object]] = []
    sleeps: list[float] = []
    pool_response = {
        "tasks": [
            {
                "data": {"url": url},
                "status_code": 20000,
                "status_message": "Ok.",
                "result": [{"items": [], "crawl_status": "unreachable"}],
            }
        ]
    }
    responses = iter([pool_response, fixture_page_text_response(url, "technical seo")])

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
        sleep=sleeps.append,
    ) == [fixture_page_text_response(url, "technical seo")]
    assert sleeps == []
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"], body["switch_pool"])
        for body in request_bodies
    ] == [(False, False, False), (True, True, True)]


@pytest.mark.parametrize("switched_kind", ["empty", "javascript_disabled"])
def test_fetch_page_text_for_urls_advances_stage_after_empty_switched_pool_response(
    switched_kind: str,
) -> None:
    url = "https://example.com/render-after-pool-switch"
    request_bodies: list[dict[str, object]] = []
    pool_response = {
        "tasks": [
            {
                "data": {"url": url},
                "status_code": 20000,
                "status_message": "Ok.",
                "result": [{"items": [], "crawl_status": "unreachable"}],
            }
        ]
    }
    switched_response = (
        _empty_page_text_response(url, crawl_status="switched pool remained empty")
        if switched_kind == "empty"
        else _javascript_disabled_page_text_response(url)
    )
    responses = iter([pool_response, switched_response])

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
        sleep=lambda _seconds: None,
    ) == [switched_response]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"], body["switch_pool"])
        for body in request_bodies
    ] == [
        (False, False, False),
        (True, True, True),
    ]


def test_fetch_page_text_for_urls_switches_pool_after_nested_http_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    url = "https://example.com/blocked"
    request_bodies: list[dict[str, object]] = []
    responses = iter(
        [
            {
                "tasks": [
                    {
                        "data": {"url": url},
                        "status_code": 20000,
                        "result": [
                            {"items": [{"status_code": 403, "checks": {"is_4xx_code": True}}]}
                        ],
                    }
                ]
            },
            fixture_page_text_response(url, "technical seo"),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    with caplog.at_level(logging.INFO, logger="seo_rank.dataforseo"):
        assert fetch_page_text_for_urls(
            "technical seo",
            [url],
            credentials=DataForSeoCredentials(login="user", password="pass"),
            transport=transport,
        ) == [fixture_page_text_response(url, "technical seo")]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"], body["switch_pool"])
        for body in request_bodies
    ] == [(False, False, False), (True, True, True)]
    assert "attempt=1" in caplog.text
    assert "attempt=2" in caplog.text


def test_fetch_page_text_for_urls_blocklists_terminal_nested_4xx(tmp_path: Path) -> None:
    url = "https://example.com/blocked"
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")
    failed_response = {
        "tasks": [
            {
                "data": {"url": url},
                "status_code": 20000,
                "result": [
                    {"items": [{"status_code": 403, "checks": {"is_4xx_code": True}}]}
                ],
            }
        ]
    }
    request_bodies: list[dict[str, object]] = []

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return failed_response

    result = fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
        blocklist=blocklist,
        sleep=lambda _seconds: None,
    )

    assert result == [failed_response]
    assert blocklist.is_blocked(url)
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"], body["switch_pool"])
        for body in request_bodies
    ] == [(False, False, False), (True, True, True)]


def test_fetch_page_text_for_urls_does_not_repull_when_all_checks_are_false() -> None:
    url = "https://example.com/healthy"
    response = {
        "tasks": [
            {
                "data": {"url": url},
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {
                                "url": url,
                                "status_code": 403,
                                "checks": {
                                    "is_4xx_code": False,
                                    "is_5xx_code": False,
                                    "is_broken": False,
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }
    calls = 0

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return response

    assert fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
        sleep=lambda _seconds: None,
    ) == [response]
    assert calls == 1


def test_fetch_page_text_for_urls_does_not_retry_immediate_success() -> None:
    url = "https://example.com/fast"
    sleeps: list[float] = []
    calls = 0

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return fixture_page_text_response(url, "technical seo")

    fetch_page_text_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials(login="user", password="pass"),
        transport=transport,
        sleep=sleeps.append,
    )
    assert sleeps == []
    assert calls == 1


def test_run_without_output_dir_writes_stable_default_run_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    args = [
        "run",
        "--seed",
        "Technical SEO / Audits!",
        "--location",
        "United States",
        "--language",
        "en",
        "--device",
        "desktop",
        "--depth",
        "1",
        "--dry-run",
        "--skip-textrazor",
    ]

    assert main(args) == 0

    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    output_dir = run_dirs[0]
    assert output_dir.name.startswith("technical-seo-audits-")
    assert len(output_dir.name.rsplit("-", maxsplit=1)[-1]) == 12
    assert (output_dir / "run.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "parquet" / "raw_responses").exists()

    first_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert first_payload["run_id"] == output_dir.name
    assert first_payload["config"]["output_dir"] == str(Path("runs") / output_dir.name)

    assert main(args) == 0

    second_run_dirs = sorted((tmp_path / "runs").iterdir())
    assert second_run_dirs == [output_dir]
    second_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert second_payload["run_id"] == first_payload["run_id"]


def test_run_writes_offline_json_and_markdown_artifacts(
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
            "--location",
            "United States",
            "--language",
            "en",
            "--device",
            "desktop",
            "--depth",
            "3",
            "--output-dir",
            str(output_dir),
            "--model-name",
            "fixture-similarity-v1",
            "--dry-run",
            "--skip-textrazor",
        ]
    )

    assert exit_code == 0

    run_json = output_dir / "run.json"
    report_md = output_dir / "report.md"
    assert run_json.exists()
    assert report_md.exists()

    payload = json.loads(run_json.read_text(encoding="utf-8"))
    assert payload["config"] == {
        "seed": "technical seo",
        "location": "United States",
        "language": "en",
        "device": "desktop",
        "depth": 3,
        "output_dir": str(output_dir),
        "model_name": "fixture-similarity-v1",
        "dry_run": True,
        "skip_textrazor": True,
        "live_textrazor_only": False,
        "live_providers": False,
        "live_backlinks": False,
        "live_backlinks_detail": False,
        "live_bge": False,
        "live_gemini": False,
        "live_textrazor": False,
            "refresh_textrazor": False,
        "domain_blocklist_path": None,
        "debug": False,
    }
    assert payload["keywords"] == ["technical seo"]
    assert payload["run_id"] == "artifacts"
    assert "raw_provider_data" not in payload
    assert not (output_dir / "debug.json").exists()
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 5
    assert len(payload["keyword_results"]) == 1
    assert payload["keyword_results"][0]["target_keyword"] == "technical seo"
    assert all("raw_provider_data" not in keyword_result for keyword_result in payload["keyword_results"])
    assert [result["rank"] for result in payload["keyword_results"][0]["serp_results"]] == [
        1,
        2,
        3,
    ]
    assert [passage["url"] for passage in payload["keyword_results"][0]["passages"]] == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
        "https://example.com/technical-seo/3",
    ]
    assert {
        passage["target_keyword"]
        for passage in payload["keyword_results"][0]["passages"]
    } == {"technical seo"}
    assert [
        feature["url"]
        for feature in payload["keyword_results"][0]["similarity_features"]
    ] == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
    ]
    assert {
        feature["target_keyword"]
        for feature in payload["keyword_results"][0]["similarity_features"]
    } == {"technical seo"}
    assert (
        payload["keyword_results"][0]["similarity_features"][0]["passage_count"]
        == 2
    )
    assert [
        score["url"] for score in payload["keyword_results"][0]["page_similarity"]
    ] == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
    ]
    assert (
        payload["keyword_results"][0]["page_similarity"][0]["page_similarity"][
            "bge"
        ]["raw_score"]
        == 0.98
    )
    assert (
        payload["keyword_results"][0]["page_similarity"][0]["page_similarity"][
            "gemini_semantic_similarity"
        ]["normalized_score"]
        == 1.0
    )
    assert {
        score["target_keyword"]
        for score in payload["keyword_results"][0]["page_similarity"]
    } == {"technical seo"}
    assert len(payload["serp_results"]) == 3
    assert len(payload["passages"]) == sum(
        len(keyword_result["passages"])
        for keyword_result in payload["keyword_results"]
    )
    assert len(payload["similarity_features"]) == 3
    assert len(payload["page_similarity"]) == 3
    assert {passage["target_keyword"] for passage in payload["passages"]} == set(
        payload["keywords"]
    )
    assert {
        feature["target_keyword"] for feature in payload["similarity_features"]
    } == set(payload["keywords"])
    assert {score["target_keyword"] for score in payload["page_similarity"]} == set(
        payload["keywords"]
    )
    assert payload["textrazor_entities"] == []
    assert payload["network_calls"] == []

    report = report_md.read_text(encoding="utf-8")
    assert "# SEO Rank Offline Run" in report
    assert "- Seed: technical seo" in report
    assert "- Network calls: 0" in report
    assert "## Target Keyword: technical seo" in report
    assert "## Target Keyword: technical seo audit" not in report
    assert "### Page Similarity" in report
    assert "BGE: 0.98 (normalized 0.98)" in report
    assert "Gemini Doc Retrieval:" in report
    assert "Gemini Semantic Similarity:" in report


def test_run_debug_writes_full_intermediate_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "debug-artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    assert main(
        [
            "run",
            "--seed",
            "technical seo",
            "--depth",
            "1",
            "--output-dir",
            str(output_dir),
            "--dry-run",
            "--skip-textrazor",
            "--debug",
            "1",
        ]
    ) == 0

    debug_payload = json.loads(
        (output_dir / "debug.json").read_text(encoding="utf-8")
    )
    assert debug_payload["config"]["debug"] is True
    assert "raw_provider_data" in debug_payload
    assert debug_payload["raw_provider_data"]["dataforseo"]["serp"]

    assert main(
        [
            "run",
            "--seed",
            "technical seo",
            "--depth",
            "1",
            "--output-dir",
            str(output_dir),
            "--dry-run",
            "--skip-textrazor",
            "--debug",
            "0",
        ]
    ) == 0
    assert not (output_dir / "debug.json").exists()


def test_stored_run_debug_flag_is_an_explicit_overlay(tmp_path: Path) -> None:
    stored_config = RunConfig(
        seed="technical seo",
        location="United States",
        language="en",
        device="desktop",
        depth=20,
        output_dir=tmp_path,
        model_name="fixture-similarity-v1",
        dry_run=False,
        skip_textrazor=False,
        debug=True,
    )
    cli_config = RunConfig(
        seed="technical seo",
        location="United States",
        language="en",
        device="desktop",
        depth=20,
        output_dir=tmp_path,
        model_name="fixture-similarity-v1",
        dry_run=False,
        skip_textrazor=False,
        debug=False,
    )

    merged = merge_stored_run_cli_overlay(
        stored_config,
        cli_config,
        scope_overrides=frozenset({"debug"}),
    )

    assert merged.debug is False


def test_render_markdown_report_includes_textrazor_entity_metrics() -> None:
    payload = {
        "config": {
            "seed": "seo company columbus",
            "location": "United States",
            "language": "en",
            "device": "desktop",
            "depth": 20,
            "model_name": "fixture-similarity-v1",
        },
        "network_calls": [],
        "keyword_results": [
            {
                "target_keyword": "seo company columbus",
                "serp_results": [
                    {
                        "rank": 1,
                        "title": "Example",
                        "url": "https://example.com/",
                    }
                ],
                "page_similarity": [
                    {
                        "target_keyword": "seo company columbus",
                        "url": "https://example.com/",
                        "page_similarity": {
                            "bge": {"raw_score": 0.5, "normalized_score": 0.5},
                            "gemini_doc_retrieval": {
                                "raw_score": 0.8,
                                "normalized_score": 0.8,
                            },
                            "gemini_semantic_similarity": {
                                "raw_score": 0.7,
                                "normalized_score": 0.7,
                            },
                            "textrazor_entity_confidence_score": {
                                "raw_score": 12.34,
                                "normalized_score": 12.34,
                            },
                            "textrazor_entity_relevance_score": {
                                "raw_score": 0.91,
                                "normalized_score": 0.91,
                            },
                        },
                    }
                ],
            }
        ],
    }

    report = render_markdown_report(payload)

    assert "TextRazor Entity Confidence: 12.34 (normalized 12.34)" in report
    assert "TextRazor Entity Relevance: 0.91 (normalized 0.91)" in report


def test_enrich_run_payload_page_similarity_merges_textrazor_scores() -> None:
    payload = {
        "keyword_results": [
            {
                "target_keyword": "seo company columbus",
                "page_similarity": [
                    {
                        "target_keyword": "seo company columbus",
                        "url": "https://example.com/",
                        "page_similarity": {
                            "bge": {"raw_score": 0.5, "normalized_score": 0.5},
                        },
                    }
                ],
            }
        ]
    }
    lookup = {
        "seo company columbus": {
            "https://example.com/": {
                "textrazor_entity_confidence_score": {
                    "raw_score": 9.0,
                    "normalized_score": 9.0,
                },
                "textrazor_entity_relevance_score": {
                    "raw_score": 0.88,
                    "normalized_score": 0.88,
                },
            }
        }
    }

    enriched = enrich_run_payload_page_similarity(payload, lookup)

    assert enriched == 1
    page_scores = payload["keyword_results"][0]["page_similarity"][0]["page_similarity"]
    assert page_scores["textrazor_entity_confidence_score"]["raw_score"] == 9.0
    assert payload["page_similarity"][0]["page_similarity"]["textrazor_entity_relevance_score"]["raw_score"] == 0.88


def test_run_persists_textrazor_only_and_refresh_flags_in_run_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_TEXTRAZOR", "1")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)
    monkeypatch.setattr(
        "seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT",
        lambda **kwargs: {"response": {"entities": []}},
    )

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--dry-run",
            "--live-textrazor-only",
            "--refresh-textrazor",
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_textrazor_only"] is True
    assert payload["config"]["refresh_textrazor"] is True


def test_run_live_textrazor_only_dispatches_to_dedicated_writer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_TEXTRAZOR", "1")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    called: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def record_writer(*args, **kwargs) -> None:
        called.append((args, kwargs))

    monkeypatch.setattr("seo_rank.cli.write_textrazor_only_artifacts", record_writer)
    monkeypatch.setattr(
        "seo_rank.cli.write_offline_artifacts",
        lambda *args, **kwargs: pytest.fail("live-textrazor-only should not use offline artifacts"),
    )
    monkeypatch.setattr(
        "seo_rank.cli.write_live_artifacts",
        lambda *args, **kwargs: pytest.fail("live-textrazor-only should not use live-provider artifacts"),
    )

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-textrazor-only",
        ]
    )

    assert exit_code == 0
    assert len(called) == 1


def test_run_live_textrazor_only_uses_offline_dataforseo_fixtures_and_live_textrazor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_TEXTRAZOR", "1")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)

    keyword_expansion_calls: list[str] = []
    serp_calls: list[str] = []
    page_text_calls: list[str] = []
    textrazor_requests: list[dict[str, object]] = []

    def record_keyword_expansion(seed: str) -> dict[str, object]:
        keyword_expansion_calls.append(seed)
        return fixture_keyword_expansion_response(seed)

    def record_serp(keyword: str) -> dict[str, object]:
        serp_calls.append(keyword)
        return fixture_serp_response(keyword)

    def record_page_text(url: str, keyword: str) -> dict[str, object]:
        page_text_calls.append(url)
        return fixture_page_text_response(url, keyword)

    def dataforseo_transport(*args, **kwargs) -> dict[str, object]:
        raise AssertionError("live-textrazor-only should not call DataForSEO transport")

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
                        "entityId": "technical-seo-live",
                        "matchedText": "Technical SEO",
                        "confidenceScore": 9,
                        "relevanceScore": 0.99,
                        "type": ["Topic"],
                    }
                ]
            }
        }

    monkeypatch.setattr("seo_rank.cli.fixture_keyword_expansion_response", record_keyword_expansion)
    monkeypatch.setattr("seo_rank.cli.fixture_serp_response", record_serp)
    monkeypatch.setattr("seo_rank.cli.fixture_page_text_response", record_page_text)
    monkeypatch.setattr("seo_rank.cli.fixture_page_metrics_response", lambda *args, **kwargs: pytest.fail("offline TextRazor fixtures should not be used"))
    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT", textrazor_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--depth",
            "3",
            "--output-dir",
            str(output_dir),
            "--live-textrazor-only",
        ]
    )

    assert exit_code == 0
    assert keyword_expansion_calls == ["technical seo"]
    assert serp_calls == ["technical seo"]
    assert page_text_calls == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
    ]
    assert len(textrazor_requests) == 3
    assert all(
        request["body"].startswith(
            b"extractors=entities%2Ctopics%2Cwords%2Cphrases%2Crelations%2Centailments%2Csenses%2Cspelling&classifiers=textrazor_mediatopics_2023Q1&text="
        )
        and b"Fixture+Page" in request["body"]
        for request in textrazor_requests
    )

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["keywords"] == ["technical seo"]
    assert payload["network_calls"] == ["textrazor.entities"]
    assert payload["keyword_results"][0]["textrazor_entities"]
    assert payload["keyword_results"][0]["textrazor_entities"] == payload["textrazor_entities"]
    assert all(
        not call.startswith("dataforseo.")
        for call in payload["network_calls"]
    )
    assert payload["keyword_results"][0]["textrazor_entities"] == [
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "technical-seo-live",
            "matched_text": "Technical SEO",
            "confidence": 9.0,
            "relevance": 0.99,
            "types": ["Topic"],
            "target_keyword": "technical seo",
        },
        {
            "url": "https://example.com/technical-seo/2",
            "entity_id": "technical-seo-live",
            "matched_text": "Technical SEO",
            "confidence": 9.0,
            "relevance": 0.99,
            "types": ["Topic"],
            "target_keyword": "technical seo",
        },
        {
            "url": "https://example.com/technical-seo/3",
            "entity_id": "technical-seo-live",
            "matched_text": "Technical SEO",
            "confidence": 9.0,
            "relevance": 0.99,
            "types": ["Topic"],
            "target_keyword": "technical seo",
        },
    ]
    _assert_textrazor_entities_raw_response_contract(
        output_dir / "parquet" / "raw_responses" / "endpoint=entities" / "part-0.parquet"
    )


def test_run_live_providers_writes_backlink_raw_responses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    backlinks_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            target = request_body[0]["target"]
            backlinks_targets.append(target)
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--keyword-limit",
            "1",
            "--depth",
            "1",
            "--live-providers",
            "--live-backlinks",
            "--skip-textrazor",
        ]
    )

    assert exit_code == 0
    assert backlinks_targets == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/1",
    ]

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 6
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=backlinks_dofollow_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=backlinks_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=onpage_instant_pages/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    ]
    summary_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_summary"
        / "part-0.parquet"
    )
    dofollow_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_dofollow_summary"
        / "part-0.parquet"
    )
    assert summary_path.exists()
    assert dofollow_path.exists()
    summary_rows = pq.ParquetFile(summary_path).read().to_pylist()
    dofollow_rows = pq.ParquetFile(dofollow_path).read().to_pylist()
    assert len(summary_rows) == 1
    assert len(dofollow_rows) == 1
    summary_response = json.loads(
        bytes(summary_rows[0]["response_body_bytes"]).decode("utf-8")
    )
    assert summary_response["url"] == "https://example.com/technical-seo/1"


def test_run_live_providers_does_not_fetch_backlinks_without_explicit_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    backlinks_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            backlinks_targets.append(request_body[0]["target"])
            raise AssertionError("backlinks should not be fetched without --live-backlinks")
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--keyword-limit",
            "1",
            "--depth",
            "1",
            "--live-providers",
            "--skip-textrazor",
        ]
    )

    assert exit_code == 0
    assert backlinks_targets == []
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert "dataforseo.backlinks_summary" not in payload["network_calls"]
    assert "dataforseo.backlinks_dofollow_summary" not in payload["network_calls"]
    assert payload["config"]["live_backlinks"] is False


def test_run_live_providers_persists_backlinks_before_later_provider_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/on_page/content_parsing/live"):
            raise DataForSeoClientError("page_text request failed after backlinks")
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--keyword-limit",
            "1",
            "--depth",
            "1",
            "--live-providers",
            "--live-backlinks",
            "--skip-textrazor",
        ]
    )

    assert exit_code == 2
    summary_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_summary"
        / "part-0.parquet"
    )
    dofollow_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_dofollow_summary"
        / "part-0.parquet"
    )
    assert summary_path.exists()
    assert dofollow_path.exists()
    assert len(pq.ParquetFile(summary_path).read().to_pylist()) == 1
    assert len(pq.ParquetFile(dofollow_path).read().to_pylist()) == 1
    assert not (output_dir / "run.json").exists()


def test_run_live_backlinks_detail_flag_fetches_and_persists_detail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    detail_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/backlinks/backlinks/live"):
            target = request_body[0]["target"]
            detail_targets.append(target)
            return fixture_backlinks_detail_response(target)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--keyword-limit",
            "1",
            "--depth",
            "1",
            "--live-providers",
            "--live-backlinks",
            "--live-backlinks-detail",
            "--skip-textrazor",
        ]
    )

    assert exit_code == 0
    assert detail_targets
    assert set(detail_targets) == {"https://example.com/technical-seo/1"}

    detail_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_detail"
        / "part-0.parquet"
    )
    assert detail_path.exists()
    detail_rows = pq.ParquetFile(detail_path).read().to_pylist()
    assert {
        json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))["url"]
        for row in detail_rows
    } == {"https://example.com/technical-seo/1"}

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_backlinks_detail"] is True


def test_run_live_backlinks_without_detail_flag_skips_detail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/backlinks/backlinks/live"):
            raise AssertionError(
                "backlinks detail should not be fetched without --live-backlinks-detail"
            )
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--keyword-limit",
            "1",
            "--depth",
            "1",
            "--live-providers",
            "--live-backlinks",
            "--skip-textrazor",
        ]
    )

    assert exit_code == 0
    detail_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_detail"
        / "part-0.parquet"
    )
    assert not detail_path.exists()

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_backlinks_detail"] is False


def test_run_live_backlinks_detail_requires_live_backlinks(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks-detail",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--live-backlinks-detail requires --live-backlinks" in captured.err
    assert not (output_dir / "run.json").exists()


def test_fetch_dataforseo_backlinks_for_urls_persists_partition_once_per_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from seo_rank.dataforseo import fixture_backlinks_response_for_request_body

    run_dir = tmp_path / "artifacts"
    rewrite_calls = 0
    api_calls = 0

    def counting_rewrite(run_dir_arg, rows, *, endpoint="backlinks_summary"):  # noqa: ANN001
        nonlocal rewrite_calls
        rewrite_calls += 1
        return rewrite_backlink_endpoint_partition(
            run_dir_arg, rows, endpoint=endpoint
        )

    monkeypatch.setattr("seo_rank.cli.rewrite_backlink_endpoint_partition", counting_rewrite)

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        nonlocal api_calls
        del method, headers, timeout
        request_body = json.loads(body.decode("utf-8"))
        assert url.endswith("/backlinks/summary/live")
        api_calls += 1
        return fixture_backlinks_response_for_request_body(request_body)

    urls = [f"https://example.com/technical-seo/{index}" for index in range(1, 4)]
    responses = fetch_dataforseo_backlinks_for_urls(
        "technical seo",
        urls,
        credentials=DataForSeoCredentials("login", "password"),
        transport=dataforseo_transport,
        run_dir=run_dir,
    )

    assert api_calls == 6
    assert len(responses) == 6
    assert rewrite_calls == 2
    summary_path = (
        run_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary" / "part-0.parquet"
    )
    dofollow_path = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_dofollow_summary"
        / "part-0.parquet"
    )
    assert summary_path.exists()
    assert dofollow_path.exists()
    assert len(pq.ParquetFile(summary_path).read().to_pylist()) == 3
    assert len(pq.ParquetFile(dofollow_path).read().to_pylist()) == 3


def test_fetch_dataforseo_backlinks_for_urls_persists_partial_progress_on_mid_loop_failure(
    tmp_path: Path,
) -> None:
    from seo_rank.dataforseo import fixture_backlinks_response_for_request_body

    run_dir = tmp_path / "artifacts"
    urls = [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
    ]

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
        target = request_body[0]["target"]
        if target == urls[2]:
            raise DataForSeoClientError("backlinks failed on third url")
        return fixture_backlinks_response_for_request_body(request_body)

    with pytest.raises(DataForSeoClientError, match="third url"):
        fetch_dataforseo_backlinks_for_urls(
            "technical seo",
            urls,
            credentials=DataForSeoCredentials("login", "password"),
            transport=dataforseo_transport,
            run_dir=run_dir,
        )

    summary_path = (
        run_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary" / "part-0.parquet"
    )
    dofollow_path = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_dofollow_summary"
        / "part-0.parquet"
    )
    assert summary_path.exists()
    assert dofollow_path.exists()
    persisted_urls = {
        json.loads(str(row["request_metadata_json"]))["url"]
        for row in pq.ParquetFile(summary_path).read().to_pylist()
    }
    persisted_dofollow_urls = {
        json.loads(str(row["request_metadata_json"]))["url"]
        for row in pq.ParquetFile(dofollow_path).read().to_pylist()
    }
    assert persisted_urls == {urls[0], urls[1]}
    assert persisted_dofollow_urls == {urls[0], urls[1]}


def test_fetch_onpage_signals_for_urls_persists_partition_once_per_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "artifacts"
    rewrite_calls = 0
    api_calls = 0

    def counting_rewrite(run_dir_arg, endpoint, rows):  # noqa: ANN001
        nonlocal rewrite_calls
        rewrite_calls += 1
        return rewrite_endpoint_partition(run_dir_arg, endpoint, rows)

    monkeypatch.setattr("seo_rank.cli.rewrite_endpoint_partition", counting_rewrite)

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        nonlocal api_calls
        del method, headers, timeout
        request_body = json.loads(body.decode("utf-8"))
        assert url.endswith("/on_page/instant_pages")
        api_calls += 1
        return fixture_onpage_instant_pages_response(request_body[0]["url"])

    urls = [f"https://example.com/technical-seo/{index}" for index in range(1, 4)]
    responses = fetch_onpage_signals_for_urls(
        "technical seo",
        urls,
        credentials=DataForSeoCredentials("login", "password"),
        transport=dataforseo_transport,
        run_dir=run_dir,
    )

    assert api_calls == 3
    assert len(responses) == 3
    assert rewrite_calls == 1
    onpage_path = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
        / "part-0.parquet"
    )
    assert onpage_path.exists()
    persisted_rows = pq.ParquetFile(onpage_path).read().to_pylist()
    assert len(persisted_rows) == 3
    metadata = json.loads(str(persisted_rows[0]["request_metadata_json"]))
    assert metadata["validate_micromarkup"] is True


def test_fetch_onpage_signals_for_urls_persists_partial_progress_on_mid_loop_failure(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    urls = [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
    ]

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
        target_url = request_body[0]["url"]
        if target_url == urls[2]:
            raise DataForSeoClientError("onpage failed on third url")
        return fixture_onpage_instant_pages_response(target_url)

    with pytest.raises(DataForSeoClientError, match="third url"):
        fetch_onpage_signals_for_urls(
            "technical seo",
            urls,
            credentials=DataForSeoCredentials("login", "password"),
            transport=dataforseo_transport,
            run_dir=run_dir,
        )

    onpage_path = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
        / "part-0.parquet"
    )
    assert onpage_path.exists()
    persisted_urls = {
        json.loads(str(row["request_metadata_json"]))["url"]
        for row in pq.ParquetFile(onpage_path).read().to_pylist()
    }
    assert persisted_urls == {urls[0], urls[1]}


def test_fetch_onpage_signals_for_urls_retains_target_page_timeout(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    urls = [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
    ]

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
        target_url = request_body[0]["url"]
        if target_url == urls[1]:
            return {
                "status_code": 20000,
                "tasks": [
                    {
                        "id": "fixture-onpage-instant-pages-timeout",
                        "status_code": 50402,
                        "status_message": "Target page took too long to respond.",
                        "result": None,
                    }
                ],
            }
        return fixture_onpage_instant_pages_response(target_url)

    sleeps: list[float] = []
    responses = fetch_onpage_signals_for_urls(
        "technical seo",
        urls,
        credentials=DataForSeoCredentials("login", "password"),
        transport=dataforseo_transport,
        run_dir=run_dir,
        sleep=sleeps.append,
    )

    assert sleeps == [1.0]
    assert [response["url"] for response in responses] == urls
    assert not onpage_instant_pages_response_is_usable(responses[1])

    onpage_path = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
        / "part-0.parquet"
    )
    assert onpage_path.exists()
    persisted_urls = {
        json.loads(str(row["request_metadata_json"]))["url"]
        for row in pq.ParquetFile(onpage_path).read().to_pylist()
    }
    assert persisted_urls == set(urls)


def test_fetch_onpage_signals_for_urls_retries_task_timeout_before_success(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    url = "https://example.com/technical-seo/1"
    sleeps: list[float] = []
    responses = iter(
        [
            {
                "status_code": 20000,
                "tasks": [
                    {
                        "id": "fixture-onpage-instant-pages-timeout",
                        "status_code": 50402,
                        "status_message": "Target page took too long to respond.",
                        "result": None,
                    }
                ],
            },
            fixture_onpage_instant_pages_response(url),
        ]
    )

    def dataforseo_transport(*, body: bytes, **_: object) -> dict[str, object]:
        del body
        return next(responses)

    result = fetch_onpage_signals_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials("login", "password"),
        transport=dataforseo_transport,
        run_dir=run_dir,
        sleep=sleeps.append,
    )

    assert sleeps == [1.0]
    assert [response["url"] for response in result] == [url]
    assert onpage_instant_pages_response_is_usable(result[0])


def test_fetch_onpage_signals_for_urls_blocklists_final_empty_content(
    tmp_path: Path,
) -> None:
    url = "https://empty.example/technical-seo/1"
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")
    empty_response = fixture_onpage_instant_pages_response(url)
    empty_result = empty_response["tasks"][0]["result"][0]
    empty_result["crawl_status"] = "Page content is empty"
    empty_result["items"] = []
    empty_result["items_count"] = 0
    responses = iter([empty_response])

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        del body
        return next(responses)

    fetch_onpage_signals_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials("login", "password"),
        transport=transport,
        blocklist=blocklist,
    )

    assert blocklist.is_blocked(url)


def test_fetch_onpage_signals_for_urls_does_not_blocklist_empty_content_recovered_by_retry(
    tmp_path: Path,
) -> None:
    url = "https://recovered.example/technical-seo/1"
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")
    first_response = fixture_onpage_instant_pages_response(url)
    first_result = first_response["tasks"][0]["result"][0]
    first_result["crawl_status"] = "Page content is empty"
    first_result["items"][0]["checks"] = {"is_broken": True}
    responses = iter([first_response, fixture_onpage_instant_pages_response(url)])

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        del body
        return next(responses)

    fetch_onpage_signals_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials("login", "password"),
        transport=transport,
        blocklist=blocklist,
    )

    assert not blocklist.is_blocked(url)


def test_fetch_onpage_signals_for_urls_switches_pool_after_nested_http_failure() -> None:
    url = "https://example.com/technical-seo/1"
    request_bodies: list[dict[str, object]] = []
    responses = iter(
        [
            {
                "status_code": 20000,
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [
                            {"items": [{"status_code": 403, "checks": {"is_4xx_code": True}}]}
                        ],
                    }
                ],
            },
            fixture_onpage_instant_pages_response(url),
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    result = fetch_onpage_signals_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials("login", "password"),
        transport=transport,
        sleep=lambda _seconds: None,
    )

    assert onpage_instant_pages_response_is_usable(result[0])
    assert [body["switch_pool"] for body in request_bodies] == [False, True]
    assert all(body["enable_javascript"] is True for body in request_bodies)


def test_fetch_onpage_signals_for_urls_blocklists_only_after_second_pool_switch(
    tmp_path: Path,
) -> None:
    url = "https://example.com/technical-seo/1"
    blocklist = DomainBlocklist.load(tmp_path / "blocklist.txt")
    failed_response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {"items": [{"status_code": 403, "checks": {"is_4xx_code": True}}]}
                ],
            }
        ],
    }
    request_bodies: list[dict[str, object]] = []

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return failed_response

    fetch_onpage_signals_for_urls(
        "technical seo",
        [url],
        credentials=DataForSeoCredentials("login", "password"),
        transport=transport,
        blocklist=blocklist,
        sleep=lambda _seconds: None,
    )

    assert blocklist.is_blocked(url)
    assert [body["switch_pool"] for body in request_bodies] == [False, True]
    assert all(
        body["enable_javascript"] and body["enable_browser_rendering"]
        for body in request_bodies
    )


def test_fetch_onpage_signals_for_urls_blocklists_terminal_timeout(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_dir = tmp_path / "artifacts"
    blocklist_path = tmp_path / "blocklist.txt"
    blocklist = DomainBlocklist.load(blocklist_path)
    url = "https://example.com/technical-seo/1"
    sleeps: list[float] = []
    timeout_response = {
        "status_code": 20000,
        "tasks": [
            {
                "id": "fixture-onpage-instant-pages-timeout",
                "status_code": 50402,
                "status_message": "Target page took too long to respond.",
                "result": None,
            }
        ],
    }

    def dataforseo_transport(*, body: bytes, **_: object) -> dict[str, object]:
        del body
        return timeout_response

    with caplog.at_level(logging.WARNING, logger="seo_rank.dataforseo.onpage"):
        result = fetch_onpage_signals_for_urls(
            "technical seo",
            [url],
            credentials=DataForSeoCredentials("login", "password"),
            transport=dataforseo_transport,
            run_dir=run_dir,
            blocklist=blocklist,
            sleep=sleeps.append,
        )

    assert sleeps == [1.0]
    assert [response["url"] for response in result] == [url]
    assert not onpage_instant_pages_response_is_usable(result[0])
    assert "Skipping onpage_instant_pages" in caplog.text

    onpage_path = (
        run_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
        / "part-0.parquet"
    )
    assert onpage_path.exists()
    persisted_urls = {
        json.loads(str(row["request_metadata_json"]))["url"]
        for row in pq.ParquetFile(onpage_path).read().to_pylist()
    }
    assert persisted_urls == {url}

    assert blocklist.is_blocked(url)
    assert DomainBlocklist.load(blocklist_path).is_blocked(url)


def test_fetch_onpage_signals_for_urls_raises_on_non_timeout_task_failure(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "artifacts"
    url = "https://example.com/technical-seo/1"

    def dataforseo_transport(*, body: bytes, **_: object) -> dict[str, object]:
        del body
        return {
            "status_code": 20000,
            "tasks": [
                {
                    "id": "fixture-onpage-instant-pages-error",
                    "status_code": 40501,
                    "status_message": "Internal Error.",
                    "result": None,
                }
            ],
        }

    with pytest.raises(DataForSeoClientError):
        fetch_onpage_signals_for_urls(
            "technical seo",
            [url],
            credentials=DataForSeoCredentials("login", "password"),
            transport=dataforseo_transport,
            run_dir=run_dir,
            sleep=lambda _seconds: None,
        )


def test_build_live_payload_includes_backlinks_in_raw_provider_data(
    monkeypatch,
) -> None:
    def fake_prepare_live_run_context(*args, **kwargs):  # noqa: ANN001, ANN003
        del args, kwargs
        return {
            "credentials": type(
                "LiveCredentials",
                (),
                {"dataforseo": DataForSeoCredentials("login", "password")},
            )(),
            "live_bge_enabled": False,
            "bge_reranker": None,
            "gemini_api_key": None,
            "textrazor_credentials": None,
            "location_code": 123,
        }

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.prepare_live_run_context", fake_prepare_live_run_context)

    payload = build_live_payload(
        RunConfig(
            seed="technical seo",
            location="United States",
            language="en",
            device="desktop",
            depth=1,
            keyword_limit=1,
            output_dir=Path("/tmp/artifacts"),
            model_name="fixture-similarity-v1",
            dry_run=False,
            skip_textrazor=True,
            live_textrazor_only=False,
            refresh_textrazor=False,
            live_providers=True,
            live_backlinks=True,
            live_bge=False,
            live_gemini=False,
            live_textrazor=False,
        ),
        env={},
        dataforseo_transport=dataforseo_transport,
        textrazor_transport=lambda **kwargs: None,
    )

    backlinks_summary = payload["raw_provider_data"]["dataforseo"]["backlinks_summary"]
    backlinks_dofollow = payload["raw_provider_data"]["dataforseo"]["backlinks_dofollow_summary"]
    assert isinstance(backlinks_summary, list)
    assert isinstance(backlinks_dofollow, list)
    assert len(backlinks_summary) == 1
    assert len(backlinks_dofollow) == 1
    assert backlinks_summary[0]["url"] == "https://example.com/technical-seo/1"
    assert backlinks_dofollow[0]["url"] == "https://example.com/technical-seo/1"
    onpage_responses = payload["raw_provider_data"]["dataforseo"]["onpage_instant_pages"]
    assert isinstance(onpage_responses, list)
    assert len(onpage_responses) == 1
    assert onpage_responses[0]["url"] == "https://example.com/technical-seo/1"
    assert "dataforseo.onpage_instant_pages" in payload["network_calls"]


def test_run_live_warns_and_continues_after_short_keyword_expansion(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    requested_urls: list[str] = []

    def dataforseo_transport(*, url: str, **_: object) -> dict[str, object]:
        requested_urls.append(url)
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            response = fixture_keyword_expansion_response("technical seo")
            response["tasks"][0]["result"] = response["tasks"][0]["result"][:25]
            return response
        raise AssertionError(f"unexpected DataForSEO request: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    def build_live_keyword_result(config: RunConfig, *, target_keyword: str, **_: object):
        from seo_rank.cli import build_offline_keyword_result

        return build_offline_keyword_result(config, target_keyword=target_keyword)

    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", build_live_keyword_result)

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--output-dir",
                str(tmp_path / "artifacts"),
                "--keyword-limit",
                "50",
                "--live-providers",
                "--skip-textrazor",
            ]
        )
        == 0
    )
    assert "Requested 50 keywords, but DataForSEO returned 24 unique keywords; continuing" in capsys.readouterr().err
    assert len(requested_urls) == 1


def test_build_live_payload_uses_requested_keyword_limit_when_available(
    monkeypatch,
) -> None:
    def fake_prepare_live_run_context(*args, **kwargs):  # noqa: ANN001, ANN003
        del args, kwargs
        return {
            "credentials": type(
                "LiveCredentials",
                (),
                {"dataforseo": DataForSeoCredentials("login", "password")},
            )(),
            "live_bge_enabled": False,
            "bge_reranker": None,
            "gemini_api_key": None,
            "textrazor_credentials": None,
            "location_code": 123,
        }

    def dataforseo_transport(*, url: str, **_: object) -> dict[str, object]:
        assert url.endswith("/keywords_data/google_ads/keywords_for_keywords/live")
        response = fixture_keyword_expansion_response("technical seo")
        response["tasks"][0]["result"].extend(
            {"keyword": f"technical seo extra {index}"} for index in range(1, 18)
        )
        return response

    def build_live_keyword_result(config: RunConfig, *, target_keyword: str, **_: object):
        from seo_rank.cli import build_offline_keyword_result

        return build_offline_keyword_result(config, target_keyword=target_keyword)

    monkeypatch.setattr("seo_rank.cli.prepare_live_run_context", fake_prepare_live_run_context)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", build_live_keyword_result)

    payload = build_live_payload(
        RunConfig(
            seed="technical seo",
            location="United States",
            language="en",
            device="desktop",
            depth=1,
            keyword_limit=50,
            output_dir=Path("/tmp/artifacts"),
            model_name="fixture-similarity-v1",
            dry_run=False,
            skip_textrazor=True,
            live_providers=True,
        ),
        env={},
        dataforseo_transport=dataforseo_transport,
        textrazor_transport=lambda **kwargs: None,
    )

    assert len(payload["keywords"]) == 50
    assert len(payload["keyword_results"]) == 50


def test_run_stored_run_cli_live_providers_fetches_onpage_when_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/on_page/instant_pages"):
            target_url = request_body[0]["url"]
            live_onpage_targets.append(target_url)
            return fixture_onpage_instant_pages_response(target_url)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is False
    assert not (
        output_dir / "parquet" / "raw_responses" / "endpoint=onpage_instant_pages"
    ).exists()

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
    assert len(live_onpage_targets) == 2
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is True
    assert "dataforseo.onpage_instant_pages" in payload["network_calls"]
    onpage_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
        / "part-0.parquet"
    )
    assert onpage_path.exists()
    assert len(pq.ParquetFile(onpage_path).read().to_pylist()) == 2


def test_build_resumed_keyword_result_fetches_only_missing_onpage_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from seo_rank.cli import build_resumed_keyword_result

    target_keyword = "technical seo"
    url_a = "https://example.com/technical-seo/1"
    url_b = "https://example.com/technical-seo/2"
    serp_response = fixture_serp_response(target_keyword)
    config = RunConfig(
        seed=target_keyword,
        location="United States",
        language="en",
        device="desktop",
        depth=2,
        keyword_limit=1,
        output_dir=tmp_path / "artifacts",
        model_name="fixture-similarity-v1",
        dry_run=False,
        skip_textrazor=True,
        live_providers=True,
    )
    fetched_urls: list[str] = []

    def capture_fetch_onpage(
        target_keyword_arg: str,
        urls,
        *,
        credentials,
        transport,
        progress=None,
        run_dir=None,
        blocklist=None,
    ):
        del target_keyword_arg, credentials, transport, progress, run_dir, blocklist
        fetched_urls.extend(urls)
        return [
            {**fixture_onpage_instant_pages_response(url), "url": url}
            for url in urls
        ]

    monkeypatch.setattr(
        "seo_rank.cli.fetch_onpage_signals_for_urls",
        capture_fetch_onpage,
    )
    monkeypatch.setattr(
        "seo_rank.cli.fetch_dataforseo_backlinks_for_urls",
        lambda *args, **kwargs: [],
    )

    def _raw_record(
        *,
        endpoint: str,
        response: dict[str, object],
        url: str,
    ) -> dict[str, object]:
        return build_raw_response_record(
            config.output_dir.name,
            endpoint=endpoint,
            provider="dataforseo",
            response={**response, "url": url},
            target_keyword=target_keyword,
            request_metadata={"target_keyword": target_keyword, "url": url},
            recorded_at="2026-07-05T12:00:00+00:00",
        )

    raw_keyword_records = {
        "serp": [
            _raw_record(endpoint="serp", response=serp_response, url=url_a),
        ],
        "page_text": [
            _raw_record(
                endpoint="page_text",
                response=fixture_page_text_response(url_a, target_keyword),
                url=url_a,
            ),
            _raw_record(
                endpoint="page_text",
                response=fixture_page_text_response(url_b, target_keyword),
                url=url_b,
            ),
        ],
        "onpage_instant_pages": [
            _raw_record(
                endpoint="onpage_instant_pages",
                response=fixture_onpage_instant_pages_response(url_a),
                url=url_a,
            ),
        ],
    }
    live_context = {
        "credentials": type(
            "LiveCredentials",
            (),
            {"dataforseo": DataForSeoCredentials("login", "password")},
        )(),
        "live_bge_enabled": False,
        "bge_reranker": None,
        "gemini_api_key": None,
        "textrazor_credentials": None,
        "location_code": 2840,
    }

    result = build_resumed_keyword_result(
        config,
        target_keyword=target_keyword,
        stored_keyword_result=None,
        raw_keyword_records=raw_keyword_records,
        live_context=live_context,
        network_calls=[],
    )

    assert fetched_urls == [url_b]
    onpage_responses = result["raw_provider_data"]["dataforseo"]["onpage_instant_pages"]
    assert len(onpage_responses) == 2
    assert onpage_responses[0]["url"] == url_a
    assert onpage_responses[1]["url"] == url_b


def test_build_resumed_keyword_result_stages_missing_page_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from seo_rank.cli import build_resumed_keyword_result

    target_keyword = "technical seo"
    url = "https://example.com/technical-seo/1"
    serp_response = fixture_serp_response(target_keyword)
    final_response = fixture_page_text_response(url, target_keyword)
    config = RunConfig(
        seed=target_keyword,
        location="United States",
        language="en",
        device="desktop",
        depth=1,
        keyword_limit=1,
        output_dir=tmp_path / "artifacts",
        model_name="fixture-similarity-v1",
        dry_run=False,
        skip_textrazor=True,
        live_providers=True,
    )
    request_bodies: list[dict[str, object]] = []
    responses = iter(
        [
            _empty_page_text_response(url),
            final_response,
        ]
    )

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request_bodies.append(json.loads(body.decode("utf-8"))[0])
        return next(responses)

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", transport)
    monkeypatch.setattr(
        "seo_rank.cli.fetch_onpage_signals_for_urls",
        lambda *args, **kwargs: [],
    )

    def raw_record(
        *,
        endpoint: str,
        response: dict[str, object],
        response_url: str,
    ) -> dict[str, object]:
        return build_raw_response_record(
            config.output_dir.name,
            endpoint=endpoint,
            provider="dataforseo",
            response={**response, "url": response_url},
            target_keyword=target_keyword,
            request_metadata={"target_keyword": target_keyword, "url": response_url},
            recorded_at="2026-07-05T12:00:00+00:00",
        )

    live_context = {
        "credentials": type(
            "LiveCredentials",
            (),
            {"dataforseo": DataForSeoCredentials("login", "password")},
        )(),
        "live_bge_enabled": False,
        "bge_reranker": None,
        "gemini_api_key": None,
        "textrazor_credentials": None,
        "location_code": 2840,
    }
    network_calls: list[str] = []

    result = build_resumed_keyword_result(
        config,
        target_keyword=target_keyword,
        stored_keyword_result=None,
        raw_keyword_records={
            "serp": [
                raw_record(endpoint="serp", response=serp_response, response_url=url)
            ],
            "page_text": [],
        },
        live_context=live_context,
        network_calls=network_calls,
    )

    assert result["raw_provider_data"]["dataforseo"]["page_text"] == [final_response]
    assert network_calls == ["dataforseo.page_text"]
    assert [
        (body["enable_javascript"], body["enable_browser_rendering"])
        for body in request_bodies
    ] == [(False, False), (True, True)]


@pytest.mark.parametrize("live_textrazor", [False, True], ids=["drop", "regenerate"])
def test_build_resumed_keyword_result_refetches_nonusable_stored_page_text(
    tmp_path: Path,
    monkeypatch,
    live_textrazor: bool,
) -> None:
    from seo_rank.cli import build_resumed_keyword_result

    target_keyword = "technical seo"
    usable_url = "https://example.com/technical-seo/1"
    stale_url = "https://example.com/technical-seo/2"
    serp_response = fixture_serp_response(target_keyword)
    usable_response = fixture_page_text_response(usable_url, target_keyword)
    replacement_response = fixture_page_text_response(stale_url, target_keyword)
    config = RunConfig(
        seed=target_keyword,
        location="United States",
        language="en",
        device="desktop",
        depth=2,
        keyword_limit=1,
        output_dir=tmp_path / "artifacts",
        model_name="fixture-similarity-v1",
        dry_run=False,
        skip_textrazor=not live_textrazor,
        live_providers=True,
        live_textrazor=live_textrazor,
    )
    requested_urls: list[str] = []
    textrazor_requested_urls: list[str] = []

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        request = json.loads(body.decode("utf-8"))[0]
        requested_urls.append(request["url"])
        assert request["url"] == stale_url
        return replacement_response

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", transport)
    monkeypatch.setattr(
        "seo_rank.cli.fetch_onpage_signals_for_urls",
        lambda *args, **kwargs: [],
    )

    def fetch_textrazor(pages, **_: object) -> list[dict[str, object]]:
        textrazor_requested_urls.extend(str(page["url"]) for page in pages)
        return [
            {
                **fixture_entity_response(str(page["url"]), "replacement page text"),
                "target_keyword": target_keyword,
            }
            for page in pages
        ]

    monkeypatch.setattr(
        "seo_rank.cli.fetch_textrazor_entities_for_pages",
        fetch_textrazor,
    )

    def raw_record(
        *,
        endpoint: str,
        response: dict[str, object],
        response_url: str,
        provider: str = "dataforseo",
    ) -> dict[str, object]:
        return build_raw_response_record(
            config.output_dir.name,
            endpoint=endpoint,
            provider=provider,
            response={**response, "url": response_url},
            target_keyword=target_keyword,
            request_metadata={"target_keyword": target_keyword, "url": response_url},
            recorded_at="2026-07-11T12:00:00+00:00",
        )

    def cached_score(url: str, value: float) -> dict[str, object]:
        return {
            "url": url,
            "page_similarity": {
                backend: {"raw_score": value, "normalized_score": value}
                for backend in (
                    "bge",
                    "gemini_doc_retrieval",
                    "gemini_semantic_similarity",
                )
            },
        }

    stored_keyword_result = {
        "page_similarity": [
            cached_score(usable_url, 0.11),
            cached_score(stale_url, 0.22),
        ],
        "similarity_features": [
            {
                "url": stale_url,
                "target_keyword": target_keyword,
                "passage_count": 999,
            }
        ],
    }

    live_context = {
        "credentials": type(
            "LiveCredentials",
            (),
            {"dataforseo": DataForSeoCredentials("login", "password")},
        )(),
        "live_bge_enabled": False,
        "bge_reranker": None,
        "gemini_api_key": None,
        "textrazor_credentials": TextRazorCredentials(api_key="textrazor-secret")
        if live_textrazor
        else None,
        "location_code": 2840,
    }
    network_calls: list[str] = []

    result = build_resumed_keyword_result(
        config,
        target_keyword=target_keyword,
        stored_keyword_result=stored_keyword_result,
        raw_keyword_records={
            "serp": [
                raw_record(
                    endpoint="serp",
                    response=serp_response,
                    response_url=usable_url,
                )
            ],
            "page_text": [
                raw_record(
                    endpoint="page_text",
                    response=usable_response,
                    response_url=usable_url,
                ),
                raw_record(
                    endpoint="page_text",
                    response=_empty_page_text_response(stale_url),
                    response_url=stale_url,
                ),
            ],
            "entities": [
                raw_record(
                    endpoint="entities",
                    response=fixture_entity_response(usable_url, "usable stored text"),
                    response_url=usable_url,
                    provider="textrazor",
                ),
                raw_record(
                    endpoint="entities",
                    response=fixture_entity_response(stale_url, "stale stored text"),
                    response_url=stale_url,
                    provider="textrazor",
                ),
            ],
        },
        live_context=live_context,
        network_calls=network_calls,
    )

    assert requested_urls == [stale_url]
    assert result["raw_provider_data"]["dataforseo"]["page_text"] == [
        {**usable_response, "url": usable_url},
        replacement_response,
    ]
    scores_by_url = {score["url"]: score for score in result["page_similarity"]}
    assert scores_by_url[usable_url]["page_similarity"]["bge"]["raw_score"] == 0.11
    assert scores_by_url[stale_url]["page_similarity"]["bge"]["raw_score"] != 0.22
    assert all(feature.get("passage_count") != 999 for feature in result["similarity_features"])
    assert [
        response["url"]
        for response in result["raw_provider_data"]["textrazor"]["entities"]
    ] == ([usable_url, stale_url] if live_textrazor else [usable_url])
    assert textrazor_requested_urls == ([stale_url] if live_textrazor else [])
    assert network_calls == (
        ["dataforseo.page_text", "textrazor.entities"]
        if live_textrazor
        else ["dataforseo.page_text"]
    )


def test_build_resumed_keyword_result_refetches_empty_stored_onpage_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from seo_rank.cli import build_resumed_keyword_result

    target_keyword = "technical seo"
    url_a = "https://example.com/technical-seo/1"
    url_b = "https://example.com/technical-seo/2"
    serp_response = fixture_serp_response(target_keyword)
    config = RunConfig(
        seed=target_keyword,
        location="United States",
        language="en",
        device="desktop",
        depth=2,
        keyword_limit=1,
        output_dir=tmp_path / "artifacts",
        model_name="fixture-similarity-v1",
        dry_run=False,
        skip_textrazor=True,
        live_providers=True,
    )
    fetched_urls: list[str] = []

    def capture_fetch_onpage(
        target_keyword_arg: str,
        urls,
        *,
        credentials,
        transport,
        progress=None,
        run_dir=None,
        blocklist=None,
    ):
        del target_keyword_arg, credentials, transport, progress, run_dir, blocklist
        fetched_urls.extend(urls)
        return [
            {**fixture_onpage_instant_pages_response(url), "url": url}
            for url in urls
        ]

    monkeypatch.setattr(
        "seo_rank.cli.fetch_onpage_signals_for_urls",
        capture_fetch_onpage,
    )
    monkeypatch.setattr(
        "seo_rank.cli.fetch_dataforseo_backlinks_for_urls",
        lambda *args, **kwargs: [],
    )

    empty_onpage_response = {
        "status_code": 20000,
        "url": url_a,
        "tasks": [{"status_code": 20000, "result": None}],
    }

    def _raw_record(
        *,
        endpoint: str,
        response: dict[str, object],
        url: str,
    ) -> dict[str, object]:
        return build_raw_response_record(
            config.output_dir.name,
            endpoint=endpoint,
            provider="dataforseo",
            response={**response, "url": url},
            target_keyword=target_keyword,
            request_metadata={"target_keyword": target_keyword, "url": url},
            recorded_at="2026-07-05T12:00:00+00:00",
        )

    raw_keyword_records = {
        "serp": [
            _raw_record(endpoint="serp", response=serp_response, url=url_a),
        ],
        "page_text": [
            _raw_record(
                endpoint="page_text",
                response=fixture_page_text_response(url_a, target_keyword),
                url=url_a,
            ),
            _raw_record(
                endpoint="page_text",
                response=fixture_page_text_response(url_b, target_keyword),
                url=url_b,
            ),
        ],
        "onpage_instant_pages": [
            _raw_record(
                endpoint="onpage_instant_pages",
                response=empty_onpage_response,
                url=url_a,
            ),
        ],
    }
    live_context = {
        "credentials": type(
            "LiveCredentials",
            (),
            {"dataforseo": DataForSeoCredentials("login", "password")},
        )(),
        "live_bge_enabled": False,
        "bge_reranker": None,
        "gemini_api_key": None,
        "textrazor_credentials": None,
        "location_code": 2840,
    }

    result = build_resumed_keyword_result(
        config,
        target_keyword=target_keyword,
        stored_keyword_result=None,
        raw_keyword_records=raw_keyword_records,
        live_context=live_context,
        network_calls=[],
    )

    assert fetched_urls == [url_a, url_b]
    onpage_responses = result["raw_provider_data"]["dataforseo"]["onpage_instant_pages"]
    assert len(onpage_responses) == 2
    assert onpage_responses[0]["url"] == url_a
    assert onpage_responses[1]["url"] == url_b


def test_run_materializes_feature_marts_analysis_and_stats_for_fresh_runs(
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
            "--skip-textrazor",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "parquet" / "analysis_mart").exists()
    assert (output_dir / "stats" / "stats_summary.json").exists()

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 1
    assert payload["catalog"]["datasets"]["keyword_serp"]["row_count"] == 1


def test_run_stored_run_finishes_existing_tree_with_stats(
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
                "--skip-textrazor",
            ]
        )
        == 0
    )

    assert not (output_dir / "stats" / "stats_summary.json").exists()

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "stats" / "stats_summary.json").exists()


def test_run_stored_run_expands_existing_tree_in_place(
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
                "--skip-textrazor",
            ]
        )
        == 0
    )

    initial_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert initial_payload["keywords"] == ["technical seo"]
    assert not (output_dir / "stats" / "stats_summary.json").exists()

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--keyword-limit",
            "3",
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))

    assert payload["config"]["keyword_limit"] == 3
    assert payload["keywords"] == [
        "technical seo",
        "technical seo audit",
        "technical seo checklist",
    ]
    assert len({keyword.casefold() for keyword in payload["keywords"]}) == len(
        payload["keywords"]
    )
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 7
    assert payload["catalog"]["datasets"]["keyword_serp"]["row_count"] == 3
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 3
    assert (output_dir / "stats" / "stats_summary.json").exists()


def test_run_stored_run_applies_explicit_scope_and_refetches_shallow_serps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
                "1",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    live_configs: list[RunConfig] = []

    def build_live_keyword_result(config: RunConfig, *, target_keyword: str, **_: object):
        from seo_rank.cli import build_offline_keyword_result

        live_configs.append(config)
        return build_offline_keyword_result(config, target_keyword=target_keyword)

    monkeypatch.setattr(
        "seo_rank.cli.build_live_keyword_result",
        build_live_keyword_result,
    )

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--stored-run",
                str(output_dir),
                "--keyword-limit",
                "1",
                "--depth",
                "2",
                "--device",
                "mobile",
                "--live-providers",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    assert [(config.depth, config.device) for config in live_configs] == [(2, "mobile")]
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["depth"] == 2
    assert payload["config"]["device"] == "mobile"
    assert len(payload["keyword_results"][0]["serp_results"]) == 2


def test_run_stored_run_warns_and_continues_after_shallow_live_serp(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
                "20",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    requests: list[tuple[str, dict[str, object]]] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        request_body = json.loads(body.decode("utf-8"))[0]
        requests.append((url, request_body))
        if url.endswith("/serp/google/organic/live/advanced"):
            return {
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": rank,
                                        "url": f"https://example.com/result-{rank}",
                                        "title": f"Result {rank}",
                                    }
                                    for rank in range(1, 50)
                                ]
                            }
                        ],
                    }
                ]
            }
        raise AssertionError(f"unexpected downstream DataForSEO request: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.materialize_run_tree", lambda *args, **kwargs: None)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--keyword-limit",
            "1",
            "--depth",
            "50",
            "--device",
            "mobile",
            "--live-providers",
            "--skip-textrazor",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert (
        "technical seo: requested 50 organic SERP results; DataForSEO returned 49, "
        "but 0 remained after domain blocklist filtering; continuing with available results"
    ) in captured.err
    assert len(requests) == 1
    assert requests[0][1]["depth"] == 50
    assert requests[0][1]["device"] == "mobile"


def test_run_stored_run_warns_and_continues_after_short_refreshed_keyword_expansion(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
                "--skip-textrazor",
            ]
        )
        == 0
    )

    requested_urls: list[str] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, body, timeout
        requested_urls.append(url)
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            response = fixture_keyword_expansion_response("technical seo")
            response["tasks"][0]["result"] = response["tasks"][0]["result"][:25]
            return response
        raise AssertionError(f"unexpected DataForSEO request: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    def build_live_keyword_result(config: RunConfig, *, target_keyword: str, **_: object):
        from seo_rank.cli import build_offline_keyword_result

        return build_offline_keyword_result(config, target_keyword=target_keyword)

    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", build_live_keyword_result)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--keyword-limit",
            "50",
            "--live-providers",
            "--skip-textrazor",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Requested 50 keywords, but DataForSEO returned 24 unique keywords; continuing" in captured.err
    assert len(requested_urls) == 1


def test_run_stored_run_uses_persisted_keyword_limit_when_omitted(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--keyword-limit=50",
                "--depth",
                "1",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--stored-run",
                str(output_dir),
                "--skip-textrazor",
            ]
        )
        == 0
    )
    assert "Requested 50 keywords, but DataForSEO returned 33 unique keywords; continuing" in capsys.readouterr().err


def test_keyword_limit_cli_forms_are_equivalent() -> None:
    from seo_rank.cli import build_parser

    parser = build_parser()
    equals = parser.parse_args(["run", "--seed", "technical seo", "--keyword-limit=50"])
    separate = parser.parse_args(["run", "--seed", "technical seo", "--keyword-limit", "50"])

    assert equals.keyword_limit == separate.keyword_limit == 50


@pytest.mark.parametrize("value", ["0", "-1"])
def test_keyword_limit_rejects_non_positive_values(value: str) -> None:
    from seo_rank.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["run", "--seed", "technical seo", "--keyword-limit", value]
        )


def test_run_stored_run_live_providers_refetches_nonusable_page_text_in_place(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    target_keyword = "technical seo"
    usable_url = "https://example.com/technical-seo/1"
    stale_url = "https://example.com/technical-seo/2"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    assert (
        main(
            [
                "run",
                "--seed",
                target_keyword,
                "--depth",
                "2",
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    page_text_path = (
        output_dir / "parquet" / "raw_responses" / "endpoint=page_text" / "part-0.parquet"
    )
    page_text_table = pq.ParquetFile(page_text_path).read()
    original_rows = page_text_table.to_pylist()

    def response_url(row: dict[str, object]) -> str | None:
        response = json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))
        return extract_response_url(response)

    original_usable_body = next(
        bytes(row["response_body_bytes"])
        for row in original_rows
        if response_url(row) == usable_url
    )
    stale_record = build_raw_response_record(
        output_dir.name,
        endpoint="page_text",
        provider="dataforseo",
        response={**_empty_page_text_response(stale_url), "url": stale_url},
        target_keyword=target_keyword,
        request_metadata={"target_keyword": target_keyword, "url": stale_url},
        recorded_at="2026-07-11T12:00:00+00:00",
    )
    pq.write_table(
        pa.Table.from_pylist(
            [
                row
                for row in original_rows
                if response_url(row) == usable_url
            ]
            + [stale_record],
            schema=page_text_table.schema,
        ),
        page_text_path,
    )
    entities_path = (
        output_dir / "parquet" / "raw_responses" / "endpoint=entities"
    )
    rewrite_endpoint_partition(
        output_dir,
        "entities",
        [
            build_raw_response_record(
                output_dir.name,
                endpoint="entities",
                provider="textrazor",
                response=fixture_entity_response(stale_url, "stale stored text"),
                target_keyword=target_keyword,
                request_metadata={"target_keyword": target_keyword, "url": stale_url},
                recorded_at="2026-07-11T12:00:00+00:00",
            )
        ],
    )

    page_text_requested_urls: list[str] = []

    def dataforseo_transport(*, url: str, body: bytes, **_: object) -> dict[str, object]:
        request = json.loads(body.decode("utf-8"))[0]
        if url.endswith("/on_page/content_parsing/live"):
            page_text_requested_urls.append(request["url"])
            return fixture_page_text_response(request["url"], target_keyword)
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request["url"])
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    assert (
        main(
            [
                "run",
                "--seed",
                target_keyword,
                "--stored-run",
                str(output_dir),
                "--live-providers",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    assert page_text_requested_urls == [stale_url]
    refreshed_rows = pq.ParquetFile(page_text_path).read().to_pylist()
    refreshed_bodies = {
        response_url(row): bytes(row["response_body_bytes"])
        for row in refreshed_rows
    }
    assert refreshed_bodies[usable_url] == original_usable_body
    assert json.loads(refreshed_bodies[stale_url].decode("utf-8")) == fixture_page_text_response(
        stale_url,
        target_keyword,
    )

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert not entities_path.exists()
    assert all(
        "endpoint=entities" not in file_path
        for file_path in payload["catalog"]["datasets"]["raw_responses"]["files"]
    )
    assert payload["catalog"]["datasets"]["entities"]["row_count"] == 0
    stale_page_scores = next(
        score["page_similarity"]
        for score in payload["page_similarity"]
        if score["url"] == stale_url
    )
    assert "textrazor_entity_confidence_score" not in stale_page_scores
    assert "textrazor_entity_relevance_score" not in stale_page_scores
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 6
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 2
    assert (output_dir / "stats" / "stats_summary.json").exists()


def test_run_stored_run_resumes_missing_page_text_in_place(
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
                "3",
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--skip-textrazor",
                "--keyword-limit",
                "3",
            ]
        )
        == 0
    )

    run_json_path = output_dir / "run.json"
    raw_response_path = (
        output_dir / "parquet" / "raw_responses" / "endpoint=page_text" / "part-0.parquet"
    )
    original_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    page_text_table = pq.ParquetFile(raw_response_path).read()
    page_text_rows = [
        row
        for row in page_text_table.to_pylist()
        if row["target_keyword"] == "technical seo"
    ]
    pq.write_table(
        pa.Table.from_pylist(page_text_rows, schema=page_text_table.schema),
        raw_response_path,
    )

    partial_keyword_results = []
    for keyword_result in original_payload["keyword_results"]:
        if keyword_result["target_keyword"] == "technical seo":
            partial_keyword_results.append(keyword_result)
        else:
            partial_keyword_results.append(
                {
                    "target_keyword": keyword_result["target_keyword"],
                    "serp_results": [],
                    "passages": [],
                    "similarity_features": [],
                    "page_similarity": [],
                    "textrazor_entities": [],
                }
            )
    original_payload["keyword_results"] = partial_keyword_results
    original_payload["passages"] = [
        passage
        for keyword_result in partial_keyword_results
        for passage in keyword_result["passages"]
    ]
    original_payload["serp_results"] = [
        result
        for keyword_result in partial_keyword_results
        for result in keyword_result["serp_results"]
    ]
    original_payload["similarity_features"] = [
        feature
        for keyword_result in partial_keyword_results
        for feature in keyword_result["similarity_features"]
    ]
    original_payload["page_similarity"] = [
        score
        for keyword_result in partial_keyword_results
        for score in keyword_result["page_similarity"]
    ]
    original_payload["textrazor_entities"] = []
    original_payload["catalog"]["datasets"]["raw_responses"]["row_count"] = 1 + 3 + 3
    run_json_path.write_text(
        json.dumps(original_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    def _fail_if_keyword_refresh_requested(*args, **kwargs) -> None:
        raise AssertionError("stored-run should resume from existing SERP rows")

    monkeypatch.setattr("seo_rank.cli.build_offline_keyword_result", _fail_if_keyword_refresh_requested)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", _fail_if_keyword_refresh_requested)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--keyword-limit",
            "3",
        ]
    )

    assert exit_code == 0
    payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    assert payload["keywords"] == [
        "technical seo",
        "technical seo audit",
        "technical seo checklist",
    ]
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 13
    assert payload["catalog"]["datasets"]["keyword_serp"]["row_count"] == 9
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 9
    assert len(payload["keyword_results"]) == 3
    assert all(len(keyword_result["page_similarity"]) == 3 for keyword_result in payload["keyword_results"])
    assert (output_dir / "stats" / "stats_summary.json").exists()


def test_run_stored_run_backfills_only_missing_backlinks_in_place(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_backlink_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            target = request_body[0]["target"]
            live_backlink_targets.append(target)
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    missing_url = "https://example.com/technical-seo/2"
    for endpoint in ("backlinks_summary", "backlinks_dofollow_summary"):
        partition_path = (
            output_dir
            / "parquet"
            / "raw_responses"
            / f"endpoint={endpoint}"
            / "part-0.parquet"
        )
        partition_table = pq.ParquetFile(partition_path).read()
        kept_rows = [
            row
            for row in partition_table.to_pylist()
            if json.loads(row["request_metadata_json"])["url"] != missing_url
        ]
        pq.write_table(
            pa.Table.from_pylist(kept_rows, schema=partition_table.schema),
            partition_path,
        )

    live_backlink_targets.clear()

    def fail_if_rebuilt(*args, **kwargs) -> None:
        raise AssertionError("stored-run should not rebuild the whole keyword result")

    monkeypatch.setattr("seo_rank.cli.build_offline_keyword_result", fail_if_rebuilt)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", fail_if_rebuilt)

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
    assert live_backlink_targets == [missing_url, missing_url]

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 10
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=backlinks_dofollow_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=backlinks_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=onpage_instant_pages/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    ]
    for endpoint in ("backlinks_summary", "backlinks_dofollow_summary"):
        partition_rows = pq.ParquetFile(
            output_dir
            / "parquet"
            / "raw_responses"
            / f"endpoint={endpoint}"
            / "part-0.parquet"
        ).read().to_pylist()
        assert len(partition_rows) == 2
        assert {
            json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))["url"]
            for row in partition_rows
        } == {
            "https://example.com/technical-seo/1",
            "https://example.com/technical-seo/2",
        }


def test_run_stored_run_backfills_legacy_backlinks_detail_via_opt_in(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_summary_targets: list[str] = []
    live_detail_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            live_summary_targets.append(request_body[0]["target"])
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/backlinks/backlinks/live"):
            target = request_body[0]["target"]
            live_detail_targets.append(target)
            return fixture_backlinks_detail_response(target)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    detail_partition_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_detail"
        / "part-0.parquet"
    )
    assert not detail_partition_path.exists()

    live_summary_targets.clear()
    live_detail_targets.clear()

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--live-backlinks-detail",
            "--keyword-limit",
            "1",
        ]
    )

    assert exit_code == 0
    assert live_summary_targets == []
    assert live_detail_targets == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
    ]

    assert detail_partition_path.exists()
    detail_rows = pq.ParquetFile(detail_partition_path).read().to_pylist()
    assert {
        json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))["url"]
        for row in detail_rows
    } == {
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
    }


def test_run_stored_run_backfills_only_missing_backlinks_detail_in_place(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_summary_targets: list[str] = []
    live_detail_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            target = request_body[0]["target"]
            live_summary_targets.append(target)
            return fixture_backlinks_response_for_request_body(request_body)
        if url.endswith("/backlinks/backlinks/live"):
            target = request_body[0]["target"]
            live_detail_targets.append(target)
            return fixture_backlinks_detail_response(target)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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
                "--live-backlinks-detail",
                "--keyword-limit",
                "1",
                "--depth",
                "2",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    run_json_path = output_dir / "run.json"
    payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    payload["config"]["live_backlinks_detail"] = False
    run_json_path.write_text(json.dumps(payload), encoding="utf-8")

    missing_url = "https://example.com/technical-seo/2"
    detail_partition_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_detail"
        / "part-0.parquet"
    )
    partition_table = pq.ParquetFile(detail_partition_path).read()
    kept_rows = [
        row
        for row in partition_table.to_pylist()
        if json.loads(row["request_metadata_json"])["url"] != missing_url
    ]
    pq.write_table(
        pa.Table.from_pylist(kept_rows, schema=partition_table.schema),
        detail_partition_path,
    )

    live_summary_targets.clear()
    live_detail_targets.clear()

    def fail_if_rebuilt(*args, **kwargs) -> None:
        raise AssertionError("stored-run should not rebuild the whole keyword result")

    monkeypatch.setattr("seo_rank.cli.build_offline_keyword_result", fail_if_rebuilt)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", fail_if_rebuilt)

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
    assert live_summary_targets == []
    assert live_detail_targets == [missing_url]

    detail_rows = pq.ParquetFile(detail_partition_path).read().to_pylist()
    assert len(detail_rows) == 2
    assert {
        json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))["url"]
        for row in detail_rows
    } == {
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
    }

    for endpoint in ("backlinks_summary", "backlinks_dofollow_summary"):
        partition_rows = pq.ParquetFile(
            output_dir
            / "parquet"
            / "raw_responses"
            / f"endpoint={endpoint}"
            / "part-0.parquet"
        ).read().to_pylist()
        assert len(partition_rows) == 2


def test_run_stored_run_backfills_only_missing_onpage_in_place(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_onpage_targets: list[str] = []
    live_backlink_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            target_url = request_body[0]["url"]
            live_onpage_targets.append(target_url)
            return fixture_onpage_instant_pages_response(target_url)
        if url.endswith("/backlinks/summary/live"):
            target = request_body[0]["target"]
            live_backlink_targets.append(target)
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    live_onpage_targets.clear()
    live_backlink_targets.clear()

    def fail_if_rebuilt(*args, **kwargs) -> None:
        raise AssertionError("stored-run should not rebuild the whole keyword result")

    monkeypatch.setattr("seo_rank.cli.build_offline_keyword_result", fail_if_rebuilt)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", fail_if_rebuilt)

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
    assert live_onpage_targets == [missing_url]
    assert live_backlink_targets == []

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert "dataforseo.onpage_instant_pages" in payload["network_calls"]
    onpage_rows = pq.ParquetFile(onpage_partition_path).read().to_pylist()
    assert len(onpage_rows) == 2
    assert {
        json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))["url"]
        for row in onpage_rows
    } == {
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
    }


def test_run_stored_run_does_not_refetch_onpage_when_partition_complete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            target_url = request_body[0]["url"]
            live_onpage_targets.append(target_url)
            return fixture_onpage_instant_pages_response(target_url)
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    seed_network_calls = json.loads(
        (output_dir / "run.json").read_text(encoding="utf-8")
    )["network_calls"]
    seed_onpage_call_count = seed_network_calls.count("dataforseo.onpage_instant_pages")
    assert seed_onpage_call_count >= 1
    assert len(live_onpage_targets) == 2

    live_onpage_targets.clear()

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
    assert live_onpage_targets == []
    replay_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert (
        replay_payload["network_calls"].count("dataforseo.onpage_instant_pages")
        == seed_onpage_call_count
    )


def test_run_stored_run_refetches_empty_onpage_partition_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            target_url = request_body[0]["url"]
            live_onpage_targets.append(target_url)
            return fixture_onpage_instant_pages_response(target_url)
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    empty_url = "https://example.com/technical-seo/1"
    onpage_partition_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=onpage_instant_pages"
        / "part-0.parquet"
    )
    rewritten_rows = []
    for row in pq.ParquetFile(onpage_partition_path).read().to_pylist():
        metadata = json.loads(row["request_metadata_json"])
        target_url = metadata["url"]
        if target_url == empty_url:
            empty_response = {
                "status_code": 20000,
                "url": target_url,
                "tasks": [
                    {
                        "status_code": 20000,
                        "path": ["v3", "on_page", "instant_pages"],
                        "result": None,
                        "result_count": 0,
                    }
                ],
            }
            rewritten_rows.append(
                build_raw_response_record(
                    output_dir.name,
                    endpoint="onpage_instant_pages",
                    provider="dataforseo",
                    response=empty_response,
                    target_keyword=row["target_keyword"],
                    request_metadata=metadata,
                    recorded_at=row["timestamp"],
                )
            )
        else:
            rewritten_rows.append(row)
    pq.write_table(
        pa.Table.from_pylist(rewritten_rows, schema=RAW_RESPONSE_SCHEMA),
        onpage_partition_path,
    )

    live_onpage_targets.clear()

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
    assert live_onpage_targets == [empty_url]

    onpage_rows = pq.ParquetFile(onpage_partition_path).read().to_pylist()
    assert len(onpage_rows) == 2
    for row in onpage_rows:
        response = json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))
        assert response["tasks"][0]["result"] is not None


def test_run_stored_run_cli_live_providers_backfills_backlinks_when_stored_config_offline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_backlink_targets: list[str] = []

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
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            target = request_body[0]["target"]
            live_backlink_targets.append(target)
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is False
    assert payload["config"]["live_backlinks"] is False
    assert not (
        output_dir / "parquet" / "raw_responses" / "endpoint=backlinks_summary"
    ).exists()

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
    assert len(live_backlink_targets) == 4
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is True
    assert payload["config"]["live_backlinks"] is True
    assert "dataforseo.backlinks_summary" in payload["network_calls"]
    assert "dataforseo.backlinks_dofollow_summary" in payload["network_calls"]
    summary_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_summary"
        / "part-0.parquet"
    )
    dofollow_path = (
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_dofollow_summary"
        / "part-0.parquet"
    )
    assert summary_path.exists()
    assert dofollow_path.exists()
    assert payload["catalog"]["datasets"]["backlinks"]["row_count"] == 2


def test_run_stored_run_live_providers_refetches_legacy_shaped_backlinks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_backlink_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            target = request_body[0]["target"]
            live_backlink_targets.append(target)
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    legacy_rows = []
    for endpoint in ("backlinks_summary", "backlinks_dofollow_summary"):
        partition_path = (
            output_dir
            / "parquet"
            / "raw_responses"
            / f"endpoint={endpoint}"
            / "part-0.parquet"
        )
        for row in pq.ParquetFile(partition_path).read().to_pylist():
            metadata = json.loads(row["request_metadata_json"])
            target_url = metadata["url"]
            legacy_response = {
                "status_code": 20000,
                "url": target_url,
                "tasks": [
                    {
                        "status_code": 20000,
                        "path": ["v3", "backlinks", "backlinks", "live"],
                        "result": [
                            {
                                "target": target_url,
                                "total_count": 1,
                                "items_count": 0,
                                "items": None,
                            }
                        ],
                    }
                ],
            }
            legacy_rows.append(
                build_raw_response_record(
                    output_dir.name,
                    endpoint=endpoint,
                    provider="dataforseo",
                    response=legacy_response,
                    target_keyword=row["target_keyword"],
                    request_metadata=metadata,
                    recorded_at=row["timestamp"],
                )
            )
        shutil.rmtree(partition_path.parent)
    for endpoint in ("backlinks_summary", "backlinks_dofollow_summary"):
        partition_dir = (
            output_dir / "parquet" / "raw_responses" / f"endpoint={endpoint}"
        )
        partition_dir.mkdir(parents=True, exist_ok=True)
        endpoint_rows = [row for row in legacy_rows if row["endpoint"] == endpoint]
        pq.write_table(
            pa.Table.from_pylist(endpoint_rows, schema=RAW_RESPONSE_SCHEMA),
            partition_dir / "part-0.parquet",
        )

    live_backlink_targets.clear()

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
    assert live_backlink_targets == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
    ]
    summary_rows = pq.ParquetFile(
        output_dir
        / "parquet"
        / "raw_responses"
        / "endpoint=backlinks_summary"
        / "part-0.parquet"
    ).read().to_pylist()
    for row in summary_rows:
        body = json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))
        result = body["tasks"][0]["result"][0]
        assert "backlinks" in result
        assert "referring_domains" in result


def test_run_stored_run_reuses_successful_empty_backlink_summaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    live_backlink_targets: list[str] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            target = request_body[0]["target"]
            live_backlink_targets.append(target)
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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

    for endpoint in ("backlinks_summary", "backlinks_dofollow_summary"):
        partition_path = (
            output_dir
            / "parquet"
            / "raw_responses"
            / f"endpoint={endpoint}"
            / "part-0.parquet"
        )
        empty_rows = []
        for row in pq.ParquetFile(partition_path).read().to_pylist():
            metadata = json.loads(row["request_metadata_json"])
            target_url = metadata["url"]
            empty_response = {
                "status_code": 20000,
                "url": target_url,
                "tasks": [
                    {
                        "status_code": 20000,
                        "path": ["v3", "backlinks", "summary", "live"],
                        "result": None,
                        "result_count": 0,
                    }
                ],
            }
            empty_rows.append(
                build_raw_response_record(
                    output_dir.name,
                    endpoint=endpoint,
                    provider="dataforseo",
                    response=empty_response,
                    target_keyword=row["target_keyword"],
                    request_metadata=metadata,
                    recorded_at=row["timestamp"],
                )
            )
        pq.write_table(
            pa.Table.from_pylist(empty_rows, schema=RAW_RESPONSE_SCHEMA),
            partition_path,
        )

    live_backlink_targets.clear()

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
    assert live_backlink_targets == []


def test_run_stored_run_skip_textrazor_disables_stored_live_textrazor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("SEO_RANK_ENABLE_TEXTRAZOR", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
    textrazor_requests: list[dict[str, object]] = []

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
        if url.endswith("/on_page/content_parsing/live"):
            return fixture_page_text_response(request_body[0]["url"], "technical seo")
        if url.endswith("/on_page/instant_pages"):
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

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
                        "entityId": "technical-seo-live",
                        "matchedText": "Technical SEO",
                        "confidenceScore": 9,
                        "relevanceScore": 0.99,
                        "type": ["Topic"],
                    }
                ]
            }
        }

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT", textrazor_transport)

    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--output-dir",
                str(output_dir),
                "--live-providers",
                "--live-textrazor",
                "--keyword-limit",
                "1",
                "--depth",
                "2",
            ]
        )
        == 0
    )

    initial_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert initial_payload["config"]["live_textrazor"] is True
    assert initial_payload["config"]["skip_textrazor"] is False
    assert textrazor_requests

    shutil.rmtree(output_dir / "parquet" / "raw_responses" / "endpoint=serp")

    monkeypatch.setattr(
        "seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT",
        lambda *args, **kwargs: pytest.fail(
            "stored-run replay should not invoke the TextRazor transport when --skip-textrazor is set"
        ),
    )

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--skip-textrazor",
            "--keyword-limit",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["skip_textrazor"] is True
    assert payload["config"]["live_textrazor"] is False
    assert len(textrazor_requests) == 2


def test_run_stored_run_fills_missing_backend_scores_without_overwriting_existing_gemini_scores(
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
                "3",
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    run_json_path = output_dir / "run.json"
    payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    original_gemini = payload["page_similarity"][0]["page_similarity"]["gemini_doc_retrieval"][
        "normalized_score"
    ]
    payload["page_similarity"][0]["page_similarity"].pop("bge")
    payload["keyword_results"][0]["page_similarity"][0]["page_similarity"].pop("bge")
    run_json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    def _fail_if_keyword_refresh_requested(*args, **kwargs) -> None:
        raise AssertionError("stored-run should not rebuild the whole keyword result")

    monkeypatch.setattr("seo_rank.cli.build_offline_keyword_result", _fail_if_keyword_refresh_requested)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", _fail_if_keyword_refresh_requested)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    repaired_score = payload["page_similarity"][0]["page_similarity"]
    assert repaired_score["bge"]["normalized_score"] == 0.98
    assert repaired_score["gemini_doc_retrieval"]["normalized_score"] == original_gemini
    assert repaired_score["gemini_semantic_similarity"]["normalized_score"] == 1.0
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 5
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 3


def test_run_stored_run_on_complete_tree_only_rematerializes_downstream_artifacts(
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
                "3",
                "--output-dir",
                str(output_dir),
                "--dry-run",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    def _fail_if_keyword_refresh_requested(*args, **kwargs) -> None:
        raise AssertionError("complete stored runs should not refresh keywords")

    monkeypatch.setattr("seo_rank.cli.build_offline_keyword_result", _fail_if_keyword_refresh_requested)
    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", _fail_if_keyword_refresh_requested)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 5
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 3
    assert (output_dir / "stats" / "stats_summary.json").exists()


def test_run_stored_run_refreshes_textrazor_entities_latest_wins_without_touching_other_raw_partitions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)
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
                str(output_dir),
                "--dry-run",
                "--skip-textrazor",
            ]
        )
        == 0
    )

    raw_responses_dir = output_dir / "parquet" / "raw_responses"
    original_partition_bytes = {
        path: path.read_bytes()
        for path in [
            raw_responses_dir / "endpoint=keyword_expansion" / "part-0.parquet",
            raw_responses_dir / "endpoint=serp" / "part-0.parquet",
            raw_responses_dir / "endpoint=page_text" / "part-0.parquet",
        ]
    }

    existing_entity = build_raw_response_record(
        "artifacts",
        endpoint="entities",
        provider="textrazor",
        response=fixture_entity_response(
            url="https://example.com/technical-seo/1",
            text="Technical SEO helps crawlers discover the page.",
        ),
        target_keyword="technical seo",
        request_metadata={
            "target_keyword": "technical seo",
            "url": "https://example.com/technical-seo/1",
        },
        recorded_at="2026-07-02T12:00:00+00:00",
    )
    existing_entity["response_id"] = "entity-existing"
    entities_dir = raw_responses_dir / "endpoint=entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist([existing_entity], schema=RAW_RESPONSE_SCHEMA),
        entities_dir / "part-0.parquet",
        compression="zstd",
    )

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, body, timeout
        raise AssertionError("stored-run refresh should not call DataForSEO")

    def textrazor_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, url, headers, timeout
        return {
            "response": {
                "entities": [
                    {
                        "entityId": "technical-seo-refresh",
                        "matchedText": "Technical SEO",
                        "confidenceScore": 10,
                        "relevanceScore": 0.95,
                        "type": ["Topic"],
                    }
                ],
            }
        }

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT", textrazor_transport)

    def fail_if_keyword_refresh_requested(*args, **kwargs) -> None:
        raise AssertionError("refresh-only stored run should not rebuild keywords")

    monkeypatch.setattr("seo_rank.cli.build_live_keyword_result", fail_if_keyword_refresh_requested)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--live-textrazor-only",
            "--refresh-textrazor",
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 4
    assert payload["textrazor_entities"] == [
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "technical-seo-refresh",
            "matched_text": "Technical SEO",
            "confidence": 10.0,
            "relevance": 0.95,
            "types": ["Topic"],
            "target_keyword": "technical seo",
        }
    ]
    assert payload["keyword_results"][0]["textrazor_entities"] == payload["textrazor_entities"]
    assert (
        raw_responses_dir / "endpoint=keyword_expansion" / "part-0.parquet"
    ).read_bytes() == original_partition_bytes[
        raw_responses_dir / "endpoint=keyword_expansion" / "part-0.parquet"
    ]
    assert (raw_responses_dir / "endpoint=serp" / "part-0.parquet").read_bytes() == original_partition_bytes[
        raw_responses_dir / "endpoint=serp" / "part-0.parquet"
    ]
    assert (
        raw_responses_dir / "endpoint=page_text" / "part-0.parquet"
    ).read_bytes() == original_partition_bytes[
        raw_responses_dir / "endpoint=page_text" / "part-0.parquet"
    ]
    _assert_textrazor_entities_raw_response_contract(
        raw_responses_dir / "endpoint=entities" / "part-0.parquet"
    )
    assert (output_dir / "stats" / "stats_summary.json").exists()


def test_run_stored_run_refreshes_only_stale_serps_in_place(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    serp_keywords: list[str] = []
    page_text_urls: list[str] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {"keyword": "technical seo", "search_volume": 1000},
                            {"keyword": "technical seo audit", "search_volume": 720},
                        ],
                    }
                ],
            }
        if url.endswith("/serp/google/organic/live/advanced"):
            request_body = json.loads(body.decode("utf-8"))
            keyword = request_body[0]["keyword"]
            serp_keywords.append(keyword)
            if keyword == "technical seo":
                return {
                    "tasks": [
                        {
                            "result": [
                                {
                                    "items": [
                                        {
                                            "type": "organic",
                                            "rank_group": 1,
                                            "url": "https://fixture.test/live/technical-seo/1",
                                            "title": "Live Result",
                                            "description": "Live provider result.",
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            if keyword == "technical seo audit":
                return {
                    "tasks": [
                        {
                            "result": [
                                {
                                    "items": [
                                        {
                                            "type": "organic",
                                            "rank_group": 1,
                                            "url": "https://fixture.test/live/technical-seo-audit/1",
                                            "title": "Audit Result",
                                            "description": "Live provider result.",
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            raise AssertionError(f"unexpected keyword: {keyword}")
        if url.endswith("/on_page/content_parsing/live"):
            request_body = json.loads(body.decode("utf-8"))
            page_text_urls.append(request_body[0]["url"])
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "url": request_body[0]["url"],
                                "title": "Parsed Page",
                                "text": "Technical SEO helps crawlers find pages.",
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/instant_pages"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

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
            "2",
            "--depth",
            "1",
            "--skip-textrazor",
            ]
        )
        == 0
    )

    serp_path = (
        output_dir / "parquet" / "raw_responses" / "endpoint=serp" / "part-0.parquet"
    )
    serp_table = pq.ParquetFile(serp_path).read()
    serp_rows = serp_table.to_pylist()
    stale_keyword = "technical seo audit"
    failed_response = {
        "tasks": [
            {
                "keyword": stale_keyword,
                "result": None,
                "status_code": 40207,
                "status_message": "Access denied. Your IP is not whitelisted.",
            }
        ]
    }
    failed_response_body = json.dumps(failed_response, sort_keys=True).encode("utf-8")
    for row in serp_rows:
        if row["target_keyword"] != stale_keyword:
            continue
        row["response_body_bytes"] = failed_response_body
        row["sha256"] = hashlib.sha256(failed_response_body).hexdigest()
        row["response_id"] = hashlib.sha256(
            (
                f"{output_dir.name}|serp|{stale_keyword}|"
                f"{row['sha256']}"
            ).encode("utf-8")
        ).hexdigest()[:32]
        break
    pq.write_table(pa.Table.from_pylist(serp_rows, schema=serp_table.schema), serp_path)

    serp_keywords.clear()
    page_text_urls.clear()

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(output_dir),
            "--keyword-limit",
            "2",
        ]
    )

    assert exit_code == 0
    assert serp_keywords == ["technical seo audit"]
    assert page_text_urls == ["https://fixture.test/live/technical-seo-audit/1"]

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["keywords"] == ["technical seo", "technical seo audit"]
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 11
    assert payload["catalog"]["datasets"]["keyword_serp"]["row_count"] == 2
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 2
    assert (output_dir / "stats" / "stats_summary.json").exists()


def test_stored_serp_response_is_usable_rejects_empty_result_list() -> None:
    assert not stored_serp_response_is_usable(
        {
            "tasks": [
                {
                    "keyword": "technical seo",
                    "result": [],
                }
            ]
        }
    )


def test_stored_serp_response_is_usable_rejects_empty_organic_items() -> None:
    assert not stored_serp_response_is_usable(
        {
            "tasks": [
                {
                    "keyword": "technical seo",
                    "result": [
                        {
                            "items": [],
                        }
                    ],
                }
            ]
        }
    )


def test_stored_serp_response_is_usable_honors_depth_above_default_cap() -> None:
    response = {
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {
                                "type": "organic",
                                "rank_group": rank,
                                "url": f"https://example.com/{rank}",
                                "title": f"Result {rank}",
                            }
                            for rank in range(1, 51)
                        ]
                    }
                ],
            }
        ]
    }

    assert stored_serp_response_is_usable(response, depth=50)
    assert not stored_serp_response_is_usable(response, depth=51)


def test_stored_serp_response_is_usable_requires_retained_rows_at_requested_depth(
    tmp_path: Path,
) -> None:
    response = {
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {
                                "type": "organic",
                                "rank_group": rank,
                                "url": f"https://example.com/{rank}",
                                "title": f"Result {rank}",
                            }
                            for rank in range(1, 51)
                        ]
                    }
                ],
            }
        ]
    }
    blocklist = DomainBlocklist(tmp_path / "blocklist.txt", {"example.com"})

    assert not stored_serp_response_is_usable(response, depth=50, blocklist=blocklist)


def test_run_writes_raw_response_parquet_and_catalog_metadata(
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
            "--skip-textrazor",
        ]
    )

    assert exit_code == 0

    raw_responses_dir = output_dir / "parquet" / "raw_responses"
    assert raw_responses_dir.exists()
    assert (raw_responses_dir / "endpoint=keyword_expansion").exists()
    assert (raw_responses_dir / "endpoint=serp").exists()
    assert (raw_responses_dir / "endpoint=page_text").exists()

    table = ds.dataset(
        raw_responses_dir,
        format="parquet",
        partitioning="hive",
    ).to_table()
    rows = table.to_pylist()

    assert len(rows) == 3
    assert {row["endpoint"] for row in rows} == {
        "keyword_expansion",
        "serp",
        "page_text",
    }
    assert all(row["run_id"] == "artifacts" for row in rows)
    assert all(isinstance(row["response_id"], str) and row["response_id"] for row in rows)
    assert all(isinstance(row["sha256"], str) and len(row["sha256"]) == 64 for row in rows)
    assert all(row["content_type"] == "application/json" for row in rows)
    assert all(row["status"] == 200 for row in rows)

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "artifacts"
    assert "raw_provider_data" not in payload
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 3
    assert payload["catalog"]["datasets"]["raw_responses"]["source_response_ids"] == sorted(
        row["response_id"] for row in rows
    )
    assert set(payload["catalog"]["datasets"]["raw_responses"]["files"]) == {
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    }


def test_run_includes_offline_textrazor_entities_when_not_skipped(tmp_path: Path) -> None:
    output_dir = tmp_path / "artifacts"

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

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert len(payload["keyword_results"]) == 1
    assert all("raw_provider_data" not in keyword_result for keyword_result in payload["keyword_results"])
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 4
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=entities/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    ]
    assert [entity["entity_id"] for entity in payload["keyword_results"][0]["textrazor_entities"]] == [
        "technical-seo",
        "crawler",
    ]
    assert {
        entity["target_keyword"]
        for entity in payload["keyword_results"][0]["textrazor_entities"]
    } == {"technical seo"}
    assert {
        entity["target_keyword"] for entity in payload["textrazor_entities"]
    } == set(payload["keywords"])


def test_run_rejects_live_providers_without_explicit_env_gate(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "SEO_RANK_ENABLE_LIVE_PROVIDERS" in captured.err
    assert not (output_dir / "run.json").exists()


def test_run_rejects_live_backlinks_without_live_providers(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-backlinks",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--live-backlinks requires --live-providers" in captured.err
    assert not (output_dir / "run.json").exists()


def test_run_live_providers_without_optional_flags_does_not_require_optional_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.delenv("TEXTRAZOR_API_KEY", raising=False)

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {"keyword": "technical seo", "search_volume": 1000},
                        ],
                    }
                ],
            }
        if url.endswith("/serp/google/organic/live/advanced"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "url": "https://example.com/live",
                                        "title": "SERP Result",
                                        "description": "Live provider result.",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/content_parsing/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "url": "https://example.com/live",
                                "title": "Parsed Page",
                                "text": "Technical SEO helps crawlers find pages.",
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/instant_pages"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is True
    assert payload["config"]["live_textrazor"] is False
    assert payload["config"]["live_gemini"] is False
    assert payload["textrazor_entities"] == []


def test_run_rejects_live_provider_schema_drift_before_normalization(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, body, timeout
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return {"tasks": "not-a-list"}
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "DataForSEO keyword_expansion response schema drift" in captured.err
    assert not (output_dir / "run.json").exists()


def test_run_rejects_live_serp_schema_drift_before_normalization(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, body, timeout
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return fixture_keyword_expansion_response("technical seo")
        if url.endswith("/serp/google/organic/live/advanced"):
            return {"tasks": "not-a-list"}
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "DataForSEO serp response schema drift" in captured.err
    assert not (output_dir / "run.json").exists()


def test_run_rejects_live_gemini_without_live_providers(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-gemini",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--live-gemini requires --live-providers" in captured.err


def test_run_rejects_live_bge_without_live_providers(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-bge",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--live-bge requires --live-providers" in captured.err


def test_run_rejects_live_textrazor_without_live_providers(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-textrazor",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--live-textrazor requires --live-providers" in captured.err


def test_run_rejects_live_textrazor_only_with_live_providers(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-textrazor-only",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--live-textrazor-only cannot be combined with --live-providers" in captured.err


def test_run_rejects_live_textrazor_only_with_skip_textrazor(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "artifacts"

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-textrazor-only",
            "--skip-textrazor",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--live-textrazor-only cannot be combined with --skip-textrazor" in captured.err


def test_run_rejects_live_gemini_without_env_gate_or_key(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.delenv("SEO_RANK_ENABLE_GEMINI", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--live-gemini",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "SEO_RANK_ENABLE_GEMINI=1" in captured.err
    assert "GEMINI_API_KEY" in captured.err


def test_run_rejects_live_bge_without_env_gate(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.delenv("SEO_RANK_ENABLE_BGE", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--live-bge",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "SEO_RANK_ENABLE_BGE=1" in captured.err


def test_run_live_gemini_uses_live_gemini_page_scores(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("SEO_RANK_ENABLE_GEMINI", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    gemini_calls: list[dict[str, object]] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {"keyword": "technical seo", "search_volume": 1000},
                        ],
                    }
                ],
            }
        if url.endswith("/serp/google/organic/live/advanced"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "url": "https://example.com/live",
                                        "title": "SERP Result",
                                        "description": "Live provider result.",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/content_parsing/live"):
            assert b"https://example.com/live" in body
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "url": "https://example.com/live",
                                "title": "Parsed Page",
                                "text": "Technical SEO helps crawlers find pages.",
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/instant_pages"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    def fake_compute_gemini_scores(
        keyword: str,
        pages: list[dict[str, str]],
        *,
        api_key: str,
        embed_content=None,
        on_page_progress=None,
    ) -> list[dict[str, object]]:
        gemini_calls.append(
            {
                "keyword": keyword,
                "pages": pages,
                "api_key": api_key,
                "embed_content": embed_content,
            }
        )
        return [
            {
                "url": "https://example.com/live",
                "page_similarity": {
                    "bge": {"raw_score": 0.98, "normalized_score": 0.98},
                    "gemini_doc_retrieval": {
                        "raw_score": 0.654321,
                        "normalized_score": 0.654321,
                    },
                    "gemini_semantic_similarity": {
                        "raw_score": 0.765432,
                        "normalized_score": 0.765432,
                    },
                },
            }
        ]

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr(
        "seo_rank.cli.compute_gemini_page_similarity_scores",
        fake_compute_gemini_scores,
    )

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--live-gemini",
        ]
    )

    assert exit_code == 0
    assert gemini_calls == [
        {
            "keyword": "technical seo",
            "pages": [
                {
                    "url": "https://example.com/live",
                    "title": "SERP Result",
                    "text": "Technical SEO helps crawlers find pages.",
                }
            ],
            "api_key": "gemini-secret",
            "embed_content": None,
        }
    ]

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["keyword_results"][0]["page_similarity"] == [
        {
            "url": "https://example.com/live",
            "page_similarity": {
                "bge": {"raw_score": 0.98, "normalized_score": 0.98},
                "gemini_doc_retrieval": {
                    "raw_score": 0.654321,
                    "normalized_score": 0.654321,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 0.765432,
                    "normalized_score": 0.765432,
                },
            },
            "target_keyword": "technical seo",
        }
    ]
    assert payload["network_calls"] == [
        "dataforseo.keyword_expansion",
        "dataforseo.serp",
        "dataforseo.backlinks_summary",
        "dataforseo.backlinks_dofollow_summary",
        "dataforseo.onpage_instant_pages",
        "dataforseo.page_text",
        "genai.embed_content",
    ]


def test_run_live_bge_replaces_only_bge_page_scores(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("SEO_RANK_ENABLE_BGE", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    bge_calls: list[dict[str, object]] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {"keyword": "technical seo", "search_volume": 1000},
                        ],
                    }
                ],
            }
        if url.endswith("/serp/google/organic/live/advanced"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "url": "https://example.com/live",
                                        "title": "SERP Result",
                                        "description": "Live provider result.",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/content_parsing/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "url": "https://example.com/live",
                                "title": "Parsed Page",
                                "text": "Technical SEO helps crawlers find pages.",
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/instant_pages"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    def fake_compute_bge_scores(
        keyword: str,
        pages: list[dict[str, str]],
        *,
        reranker=None,
        load_reranker=None,
    ) -> list[dict[str, object]]:
        bge_calls.append(
            {
                "keyword": keyword,
                "pages": pages,
                "reranker": reranker,
                "load_reranker": load_reranker,
            }
        )
        return [
            {
                "url": "https://example.com/live",
                "page_similarity": {
                    "bge": {"raw_score": 7.0, "normalized_score": 0.999089}
                },
            }
        ]

    bge_reranker = object()
    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.load_bge_reranker", lambda: bge_reranker)
    monkeypatch.setattr(
        "seo_rank.cli.compute_bge_page_similarity_scores",
        fake_compute_bge_scores,
    )

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--live-bge",
        ]
    )

    assert exit_code == 0
    assert bge_calls == [
        {
            "keyword": "technical seo",
            "pages": [
                {
                    "url": "https://example.com/live",
                    "title": "Parsed Page",
                    "text": "Technical SEO helps crawlers find pages.",
                }
            ],
            "reranker": bge_reranker,
            "load_reranker": None,
        }
    ]

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_bge"] is True
    assert payload["keyword_results"][0]["page_similarity"] == [
        {
            "url": "https://example.com/live",
            "page_similarity": {
                "bge": {"raw_score": 7.0, "normalized_score": 0.999089},
                "gemini_doc_retrieval": {"raw_score": 1.0, "normalized_score": 1.0},
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
            },
            "target_keyword": "technical seo",
        }
    ]
    assert payload["network_calls"] == [
        "dataforseo.keyword_expansion",
        "dataforseo.serp",
        "dataforseo.backlinks_summary",
        "dataforseo.backlinks_dofollow_summary",
        "dataforseo.onpage_instant_pages",
        "dataforseo.page_text",
    ]


def test_run_rejects_live_textrazor_without_env_gate(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
    monkeypatch.delenv("SEO_RANK_ENABLE_TEXTRAZOR", raising=False)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--live-textrazor",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "SEO_RANK_ENABLE_TEXTRAZOR=1" in captured.err


def test_run_live_providers_skips_textrazor_when_not_requested(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    dataforseo_calls: list[str] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        dataforseo_calls.append(url)
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {"keyword": "technical seo", "search_volume": 1000},
                        ],
                    }
                ],
            }
        if url.endswith("/serp/google/organic/live/advanced"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "url": "https://example.com/live",
                                        "title": "Live Result",
                                        "description": "Live provider result.",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/content_parsing/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "url": "https://example.com/live",
                                "title": "Live Page",
                                "text": "Technical SEO helps crawlers find pages.",
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/instant_pages"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    def textrazor_transport(**kwargs) -> dict[str, object]:
        del kwargs
        raise AssertionError("TextRazor should not be called")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT", textrazor_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
        ]
    )

    assert exit_code == 0
    assert len(dataforseo_calls) == 6
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["textrazor_entities"] == []
    assert "raw_provider_data" not in payload
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 6
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=backlinks_dofollow_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=backlinks_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=onpage_instant_pages/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    ]
    assert "textrazor.entities" not in payload["network_calls"]


def test_run_live_providers_writes_artifacts_with_injected_transports(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("SEO_RANK_ENABLE_TEXTRAZOR", "1")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
    dataforseo_calls: list[str] = []
    textrazor_calls: list[bytes] = []

    def dataforseo_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, headers, timeout
        dataforseo_calls.append(url)
        if url.endswith("/keywords_data/google_ads/keywords_for_keywords/live"):
            return {
                "tasks": [
                    {
                        "result": [
                            {"keyword": "technical seo", "search_volume": 1000},
                            {"keyword": "technical seo audit", "search_volume": 720},
                        ],
                    }
                ],
            }
        if url.endswith("/serp/google/organic/live/advanced"):
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "url": "https://example.com/live",
                                        "title": "Live Result",
                                        "description": "Live provider result.",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/content_parsing/live"):
            assert b"https://example.com/live" in body
            return {
                "tasks": [
                    {
                        "result": [
                            {
                                "url": "https://example.com/live",
                                "title": "Live Page",
                                "text": "Technical SEO helps crawlers find pages.",
                            }
                        ],
                    }
                ],
            }
        if url.endswith("/on_page/instant_pages"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_onpage_instant_pages_response(request_body[0]["url"])
        if url.endswith("/backlinks/summary/live"):
            request_body = json.loads(body.decode("utf-8"))
            return fixture_backlinks_response_for_request_body(request_body)
        raise AssertionError(f"unexpected DataForSEO URL: {url}")

    def textrazor_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        del method, url, headers, timeout
        textrazor_calls.append(body)
        return {
            "response": {
                "entities": [
                    {
                        "entityId": "technical-seo",
                        "matchedText": "Technical SEO",
                        "confidenceScore": 8,
                        "relevanceScore": 0.9,
                        "type": ["Topic"],
                    }
                ],
            }
        }

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", dataforseo_transport)
    monkeypatch.setattr("seo_rank.cli.DEFAULT_TEXTRAZOR_TRANSPORT", textrazor_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
            "--live-backlinks",
            "--live-textrazor",
        ]
    )

    assert exit_code == 0
    assert len(dataforseo_calls) == 6
    assert len(textrazor_calls) == 1

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is True
    assert payload["keywords"] == ["technical seo"]
    assert [result["target_keyword"] for result in payload["keyword_results"]] == [
        "technical seo",
    ]
    assert payload["keyword_results"][0]["serp_results"] == [
        {
            "keyword": "technical seo",
            "rank": 1,
            "url": "https://example.com/live",
            "title": "Live Result",
            "description": "Live provider result.",
        }
    ]
    assert payload["network_calls"] == [
        "dataforseo.keyword_expansion",
        "dataforseo.serp",
        "dataforseo.backlinks_summary",
        "dataforseo.backlinks_dofollow_summary",
        "dataforseo.onpage_instant_pages",
        "dataforseo.page_text",
        "textrazor.entities",
    ]
    assert "raw_provider_data" not in payload
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 7
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=backlinks_dofollow_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=backlinks_summary/part-0.parquet",
        "parquet/raw_responses/endpoint=entities/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
        "parquet/raw_responses/endpoint=onpage_instant_pages/part-0.parquet",
        "parquet/raw_responses/endpoint=page_text/part-0.parquet",
        "parquet/raw_responses/endpoint=serp/part-0.parquet",
    ]
    assert "raw_provider_data" not in payload["keyword_results"][0]
    assert payload["keyword_results"][0]["textrazor_entities"][0]["entity_id"] == "technical-seo"
    assert payload["keyword_results"][0]["passages"][0]["target_keyword"] == "technical seo"
    assert (
        payload["keyword_results"][0]["similarity_features"][0]["target_keyword"]
        == "technical seo"
    )
    assert (
        payload["keyword_results"][0]["page_similarity"][0]["target_keyword"]
        == "technical seo"
    )
    assert (
        payload["keyword_results"][0]["textrazor_entities"][0]["target_keyword"]
        == "technical seo"
    )
    _assert_textrazor_entities_raw_response_contract(
        output_dir / "parquet" / "raw_responses" / "endpoint=entities" / "part-0.parquet"
    )


def test_run_rejects_live_provider_client_failure_without_secret_leaks(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("SEO_RANK_ENABLE_TEXTRAZOR", "1")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")

    def failing_transport(**kwargs) -> dict[str, object]:
        del kwargs
        raise DataForSeoClientError("DataForSEO request failed")

    monkeypatch.setattr("seo_rank.cli.DEFAULT_DATAFORSEO_TRANSPORT", failing_transport)

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--output-dir",
            str(output_dir),
            "--live-providers",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "DataForSEO request failed" in captured.err
    assert "analyst@example.com" not in captured.err
    assert "dataforseo-secret" not in captured.err
    assert "textrazor-secret" not in captured.err
    assert not (output_dir / "run.json").exists()


def test_prepare_textrazor_only_context_requires_only_textrazor_credentials() -> None:
    assert prepare_textrazor_only_context(
        {
            "SEO_RANK_ENABLE_TEXTRAZOR": "1",
            "TEXTRAZOR_API_KEY": "textrazor-secret",
        }
    ) == TextRazorCredentials(api_key="textrazor-secret")
