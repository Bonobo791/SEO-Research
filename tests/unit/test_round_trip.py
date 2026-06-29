import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pyarrow.dataset as ds

from seo_rank.cli import main


def _read_run_payload(run_dir: Path) -> dict[str, object]:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


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
    assert "analysis_mart" not in feature_payload["catalog"]["datasets"]

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
    assert row["schema_version"] == "analysis_mart.v1"
    assert row["page_text_length"] > 0
    assert row["bge_raw_score"] == 0.98
    assert row["gemini_doc_retrieval_normalized_score"] == 1.0
    assert row["gemini_semantic_similarity_normalized_score"] == 1.0
