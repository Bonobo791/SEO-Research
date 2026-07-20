import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import polars as pl
import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.marts import ANALYSIS_SCHEMA_VERSION
from tests.fixtures.onpage_pipeline import assert_onpage_row_matches_fixture
from tests.fixtures.onpage_pipeline import assert_onpage_stats_families
from tests.fixtures.onpage_pipeline import write_backlinks_summary_raw_row
from tests.fixtures.onpage_pipeline import write_onpage_instant_pages_raw_row


def _read_run_payload(run_dir: Path) -> dict[str, object]:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def _set_run_not_dry(run_dir: Path) -> None:
    payload = _read_run_payload(run_dir)
    config = payload.get("config")
    if isinstance(config, dict):
        config["dry_run"] = False
    payload["dry_run"] = False
    (run_dir / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assert_dataset_materialized(run_dir: Path, dataset_name: str) -> int:
    dataset_dir = run_dir / "parquet" / dataset_name
    assert dataset_dir.exists()
    return ds.dataset(dataset_dir, format="parquet").count_rows()


def test_cli_round_trip_materializes_real_artifacts_without_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)
    monkeypatch.delenv("SEO_RANK_RUN_LIVE_INTEGRATION", raising=False)

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

    run_payload = _read_run_payload(output_dir)
    assert (output_dir / "parquet" / "raw_responses").exists()
    assert run_payload["catalog"]["datasets"]["raw_responses"]["row_count"] == _assert_dataset_materialized(
        output_dir,
        "raw_responses",
    )

    write_onpage_instant_pages_raw_row(
        output_dir,
        target_keyword="technical seo",
        url="https://example.com/technical-seo/1",
    )
    assert main(["normalize", "--run", str(output_dir)]) == 0

    normalized_payload = _read_run_payload(output_dir)
    assert normalized_payload["catalog"]["datasets"]["keywords"]["row_count"] == _assert_dataset_materialized(
        output_dir,
        "keywords",
    )
    assert normalized_payload["catalog"]["datasets"]["similarity_scores"]["row_count"] == _assert_dataset_materialized(
        output_dir,
        "similarity_scores",
    )

    assert main(["build-features", "--run", str(output_dir)]) == 0

    feature_payload = _read_run_payload(output_dir)
    assert feature_payload["catalog"]["datasets"]["keyword_serp"]["row_count"] == _assert_dataset_materialized(
        output_dir,
        "keyword_serp",
    )
    assert feature_payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == _assert_dataset_materialized(
        output_dir,
        "analysis_mart",
    )

    stdout = StringIO()
    with redirect_stdout(stdout):
        assert (
            main(
                [
                    "analyze",
                    "--run",
                    str(output_dir),
                    "--keyword",
                    "technical seo",
                ]
            )
            == 0
        )

    analysis_payload = _read_run_payload(output_dir)
    analysis_rows = json.loads(stdout.getvalue())
    assert analysis_payload["catalog"]["datasets"]["analysis_mart"]["row_count"] == _assert_dataset_materialized(
        output_dir,
        "analysis_mart",
    )
    assert len(analysis_rows) == 1
    row = analysis_rows[0]
    assert row["run_id"] == output_dir.name
    assert row["target_keyword"] == "technical seo"
    assert row["serp_rank"] == 1
    assert row["schema_version"] == ANALYSIS_SCHEMA_VERSION
    assert row["page_text_length"] > 0
    assert row["bge_raw_score"] == 0.98
    assert row["gemini_doc_retrieval_normalized_score"] == 1.0
    assert row["gemini_semantic_similarity_normalized_score"] == 1.0


def test_cli_round_trip_materializes_structured_only_page_text_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)
    monkeypatch.delenv("SEO_RANK_RUN_LIVE_INTEGRATION", raising=False)

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
    structured_response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/structured-only"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/structured-only",
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
                                "raw_html": "<html><body><main>Structured only</main></body></html>",
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
                "run_id": output_dir.name,
                "response_id": "page-resp-structured-only",
                "target_keyword": "technical seo",
                "response_body_bytes": json.dumps(structured_response).encode("utf-8"),
            }
        ]
    ).write_parquet(page_text_dir / "part-structured-only.parquet")

    run_payload = _read_run_payload(output_dir)
    run_payload.setdefault("page_similarity", []).append(
        {
            "target_keyword": "technical seo",
            "url": "https://example.com/structured-only",
            "page_similarity": {
                "bge": {"raw_score": 0.9, "normalized_score": 0.9},
                "gemini_doc_retrieval": {"raw_score": 0.9, "normalized_score": 0.9},
                "gemini_semantic_similarity": {"raw_score": 0.9, "normalized_score": 0.9},
            },
        }
    )
    (output_dir / "run.json").write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert main(["normalize", "--run", str(output_dir)]) == 0

    normalized_payload = _read_run_payload(output_dir)
    assert normalized_payload["catalog"]["datasets"]["page_content_fields"]["row_count"] > 0
    assert normalized_payload["catalog"]["datasets"]["page_html"]["row_count"] > 0

    page_rows = ds.dataset(output_dir / "parquet" / "pages", format="parquet").to_table().to_pylist()
    field_rows = ds.dataset(
        output_dir / "parquet" / "page_content_fields",
        format="parquet",
    ).to_table().to_pylist()
    html_rows = ds.dataset(output_dir / "parquet" / "page_html", format="parquet").to_table().to_pylist()

    page_row = next(
        row
        for row in page_rows
        if row["response_id"] == "page-resp-structured-only"
    )
    field_row = next(
        row
        for row in field_rows
        if row["response_id"] == "page-resp-structured-only"
        and row["field_name"] == "status_code"
    )
    html_row = next(
        row for row in html_rows if row["response_id"] == "page-resp-structured-only"
    )

    assert page_row["text"] == ""
    assert field_row["field_path"] == "tasks[0].result[0].items[0].status_code"
    assert field_row["structured_value"] == "200"
    assert html_row["raw_html"] == "<html><body><main>Structured only</main></body></html>"


def test_cli_round_trip_materializes_onpage_through_storage_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    target_keyword = "technical seo"
    monkeypatch.delenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", raising=False)
    monkeypatch.delenv("SEO_RANK_RUN_LIVE_INTEGRATION", raising=False)

    assert (
        main(
            [
                "run",
                "--seed",
                target_keyword,
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

    run_payload = _read_run_payload(output_dir)
    page_similarity = run_payload.get("page_similarity", [])
    assert isinstance(page_similarity, list) and page_similarity
    for entry in page_similarity:
        assert isinstance(entry, dict)
        write_onpage_instant_pages_raw_row(
            output_dir,
            target_keyword=str(entry["target_keyword"]),
            url=str(entry["url"]),
        )
        write_backlinks_summary_raw_row(
            output_dir,
            target_keyword=str(entry["target_keyword"]),
            url=str(entry["url"]),
        )

    assert main(["normalize", "--run", str(output_dir)]) == 0
    assert main(["build-features", "--run", str(output_dir)]) == 0

    feature_payload = _read_run_payload(output_dir)
    serp_count = feature_payload["catalog"]["datasets"]["keyword_serp"]["row_count"]
    assert feature_payload["catalog"]["datasets"]["onpage_signals"]["row_count"] == serp_count
    assert feature_payload["catalog"]["datasets"]["onpage_features"]["row_count"] == serp_count

    onpage_signals = ds.dataset(
        output_dir / "parquet" / "onpage_signals",
        format="parquet",
    ).to_table().to_pylist()
    onpage_features = ds.dataset(
        output_dir / "parquet" / "onpage_features",
        format="parquet",
    ).to_table().to_pylist()

    for row in onpage_signals:
        assert_onpage_row_matches_fixture(row, row["url"])
    for row in onpage_features:
        assert_onpage_row_matches_fixture(row, row["url"])

    _set_run_not_dry(output_dir)
    assert main(["analyze", "--run", str(output_dir)]) == 0

    summary = json.loads(
        (output_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8")
    )
    report = (output_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")
    assert_onpage_stats_families(summary, report)
