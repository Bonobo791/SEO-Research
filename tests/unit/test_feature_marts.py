import json
from pathlib import Path

import pyarrow.dataset as ds

from seo_rank.cli import main
from seo_rank.data.features import build_feature_marts
from seo_rank.data.normalize import normalize_run


def test_build_feature_marts_materializes_lazy_joins_from_curated_tables(
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
    catalog = build_feature_marts(output_dir)

    assert catalog["datasets"]["keyword_serp"]["row_count"] == 25
    assert catalog["datasets"]["page_features"]["row_count"] == 25
    assert catalog["datasets"]["passage_features"]["row_count"] == 74
    assert catalog["datasets"]["domain_features"]["row_count"] == 25

    keyword_serp = ds.dataset(
        output_dir / "parquet" / "keyword_serp",
        format="parquet",
    ).to_table().to_pylist()
    domain_features = ds.dataset(
        output_dir / "parquet" / "domain_features",
        format="parquet",
    ).to_table().to_pylist()

    assert any(row["serp_rank"] == 1 for row in keyword_serp)
    assert any(row["domain"] == "example.com" for row in domain_features)

    run_json = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["catalog"]["datasets"]["keyword_serp"]["row_count"] == 25
    assert run_json["catalog"]["datasets"]["domain_features"]["row_count"] == 25
