import json
from pathlib import Path

import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.features import build_analysis_mart, build_feature_marts
from seo_rank.data.normalize import normalize_run


def test_build_analysis_mart_materializes_one_row_per_serp_url(
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

    normalize_run(output_dir)
    build_feature_marts(output_dir)
    catalog = build_analysis_mart(output_dir)

    assert catalog["datasets"]["analysis_mart"]["row_count"] == 25

    analysis_mart = ds.dataset(
        output_dir / "parquet" / "analysis_mart",
        format="parquet",
    ).to_table().to_pylist()

    assert len(analysis_mart) == 25
    assert all(row["serp_rank"] == 1 for row in analysis_mart)
    assert any(row["target_keyword"] == "technical seo" for row in analysis_mart)
    assert any(row["page_text_length"] > 0 for row in analysis_mart)

    run_json = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["catalog"]["datasets"]["analysis_mart"]["row_count"] == 25
