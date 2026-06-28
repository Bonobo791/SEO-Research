import json
from pathlib import Path

from seo_rank.cli import main


def test_run_writes_offline_json_and_markdown_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "artifacts"

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
            "--javascript-parsing",
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
        "javascript_parsing": True,
        "dry_run": True,
        "skip_textrazor": True,
    }
    assert len(payload["keywords"]) == 25
    assert payload["keywords"][:3] == [
        "technical seo",
        "technical seo audit",
        "technical seo checklist",
    ]
    assert payload["raw_provider_data"]["dataforseo"]["keyword_expansion"]["provider"] == "dataforseo"
    assert [result["rank"] for result in payload["serp_results"]] == [1, 2, 3]
    assert payload["network_calls"] == []

    report = report_md.read_text(encoding="utf-8")
    assert "# SEO Rank Offline Run" in report
    assert "- Seed: technical seo" in report
    assert "- Network calls: 0" in report
