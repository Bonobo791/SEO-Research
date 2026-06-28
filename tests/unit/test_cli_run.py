import json
from pathlib import Path

from seo_rank.cli import main


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
        "live_providers": False,
    }
    assert len(payload["keywords"]) == 25
    assert payload["keywords"][:3] == [
        "technical seo",
        "technical seo audit",
        "technical seo checklist",
    ]
    assert payload["raw_provider_data"]["dataforseo"]["keyword_expansion"]["provider"] == "dataforseo"
    assert len(payload["raw_provider_data"]["dataforseo"]["page_text"]) == 3
    assert [result["rank"] for result in payload["serp_results"]] == [1, 2, 3]
    assert [passage["url"] for passage in payload["passages"]] == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
        "https://example.com/technical-seo/3",
    ]
    assert [feature["url"] for feature in payload["similarity_features"]] == [
        "https://example.com/technical-seo/1",
        "https://example.com/technical-seo/2",
        "https://example.com/technical-seo/3",
    ]
    assert payload["similarity_features"][0]["passage_count"] == 2
    assert payload["textrazor_entities"] == []
    assert "textrazor" not in payload["raw_provider_data"]
    assert payload["network_calls"] == []

    report = report_md.read_text(encoding="utf-8")
    assert "# SEO Rank Offline Run" in report
    assert "- Seed: technical seo" in report
    assert "- Network calls: 0" in report


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
    assert len(payload["raw_provider_data"]["textrazor"]["entities"]) == 1
    assert [entity["entity_id"] for entity in payload["textrazor_entities"]] == [
        "technical-seo",
        "crawler",
    ]


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


def test_run_rejects_live_providers_with_missing_credentials_without_secret_leaks(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.delenv("TEXTRAZOR_API_KEY", raising=False)

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
    assert "TEXTRAZOR_API_KEY" in captured.err
    assert "analyst@example.com" not in captured.err
    assert "dataforseo-secret" not in captured.err
    assert not (output_dir / "run.json").exists()


def test_run_rejects_live_providers_after_gate_until_clients_exist(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "artifacts"
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")

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
    assert "Live provider execution is not implemented" in captured.err
    assert "analyst@example.com" not in captured.err
    assert "dataforseo-secret" not in captured.err
    assert "textrazor-secret" not in captured.err
    assert not (output_dir / "run.json").exists()
