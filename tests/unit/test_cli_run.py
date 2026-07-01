import json
from pathlib import Path

import pyarrow.dataset as ds

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
    assert len(payload["keywords"]) == 25
    assert payload["keywords"][:3] == [
        "technical seo",
        "technical seo audit",
        "technical seo checklist",
    ]
    assert payload["run_id"] == "artifacts"
    assert "raw_provider_data" not in payload
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 101
    assert len(payload["keyword_results"]) == 25
    assert payload["keyword_results"][0]["target_keyword"] == "technical seo"
    assert payload["keyword_results"][1]["target_keyword"] == "technical seo audit"
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
    assert len(payload["serp_results"]) == 75
    assert len(payload["passages"]) == sum(
        len(keyword_result["passages"])
        for keyword_result in payload["keyword_results"]
    )
    assert len(payload["similarity_features"]) == 75
    assert len(payload["page_similarity"]) == 75
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
    assert "## Target Keyword: technical seo audit" in report
    assert "### Page Similarity" in report
    assert "BGE: 0.98 (normalized 0.98)" in report
    assert "Gemini Doc Retrieval:" in report
    assert "Gemini Semantic Similarity:" in report


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

    assert len(rows) == 51
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
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 51
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
    assert len(payload["keyword_results"]) == 25
    assert all("raw_provider_data" not in keyword_result for keyword_result in payload["keyword_results"])
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 76
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
    assert len(dataforseo_calls) == 5
    assert len(textrazor_calls) == 2

    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is True
    assert payload["keywords"] == ["technical seo", "technical seo audit"]
    assert [result["target_keyword"] for result in payload["keyword_results"]] == [
        "technical seo",
        "technical seo audit",
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
    assert payload["keyword_results"][1]["serp_results"] == [
        {
            "keyword": "technical seo audit",
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
        "dataforseo.serp",
        "dataforseo.page_text",
        "textrazor.entities",
    ]
    assert "raw_provider_data" not in payload
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 7
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
    assert (
        payload["keyword_results"][1]["passages"][0]["target_keyword"]
        == "technical seo audit"
    )
    assert (
        payload["keyword_results"][1]["similarity_features"][0]["target_keyword"]
        == "technical seo audit"
    )
    assert (
        payload["keyword_results"][1]["page_similarity"][0]["target_keyword"]
        == "technical seo audit"
    )
    assert (
        payload["keyword_results"][1]["textrazor_entities"][0]["target_keyword"]
        == "technical seo audit"
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
