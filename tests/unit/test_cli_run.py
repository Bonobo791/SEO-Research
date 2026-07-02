import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from seo_rank.dataforseo import DataForSeoClientError
from seo_rank.dataforseo import fixture_keyword_expansion_response
from seo_rank.cli import main


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
        "live_providers": False,
        "live_bge": False,
        "live_gemini": False,
        "live_textrazor": False,
    }
    assert payload["keywords"] == ["technical seo"]
    assert payload["run_id"] == "artifacts"
    assert "raw_provider_data" not in payload
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
                                            "url": "https://example.com/live/technical-seo/1",
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
                                            "url": "https://example.com/live/technical-seo-audit/1",
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
                "--keyword-limit",
                "2",
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
    assert page_text_urls == ["https://example.com/live/technical-seo-audit/1"]

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["keywords"] == ["technical seo", "technical seo audit"]
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 5
    assert payload["catalog"]["datasets"]["keyword_serp"]["row_count"] == 2
    assert payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == 2
    assert (output_dir / "stats" / "stats_summary.json").exists()


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
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "SEO_RANK_ENABLE_LIVE_PROVIDERS" in captured.err
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
        ]
    )

    assert exit_code == 0
    assert len(dataforseo_calls) == 3
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["textrazor_entities"] == []
    assert "raw_provider_data" not in payload
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 3
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
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
            "--live-textrazor",
        ]
    )

    assert exit_code == 0
    assert len(dataforseo_calls) == 3
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
        "dataforseo.page_text",
        "textrazor.entities",
    ]
    assert "raw_provider_data" not in payload
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 4
    assert payload["catalog"]["datasets"]["raw_responses"]["files"] == [
        "parquet/raw_responses/endpoint=entities/part-0.parquet",
        "parquet/raw_responses/endpoint=keyword_expansion/part-0.parquet",
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
