from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from seo_rank.cli import main


def _analysis_rows(
    *,
    run_id: str,
    keyword_specs: list[tuple[str, str, float]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for keyword_order, (target_keyword_id, target_keyword, offset) in enumerate(
        keyword_specs,
        start=1,
    ):
        for serp_rank in range(1, 4):
            signal = 0.95 - (serp_rank - 1) * 0.25 + offset
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "keyword_order": keyword_order,
                    "source_response_id": f"{run_id}-{target_keyword_id}-serp",
                    "serp_item_id": f"{run_id}-{target_keyword_id}-serp-{serp_rank}",
                    "page_id": f"{run_id}-{target_keyword_id}-page-{serp_rank}",
                    "response_id": f"{run_id}-{target_keyword_id}-response-{serp_rank}",
                    "canonical_url_hash": f"{run_id}-{target_keyword_id}-url-{serp_rank}",
                    "url": f"https://example.com/{run_id}/{target_keyword_id}/{serp_rank}",
                    "serp_rank": serp_rank,
                    "title": f"{target_keyword} title {serp_rank}",
                    "description": f"{target_keyword} description {serp_rank}",
                    "page_text_length": 100 + keyword_order + serp_rank,
                    "bge_raw_score": signal,
                    "bge_normalized_score": signal,
                    "bge_rank": serp_rank,
                    "bge_pct": float((serp_rank - 1) / 2),
                    "bge_z": float(2 - serp_rank),
                    "gemini_doc_retrieval_raw_score": signal - 0.05,
                    "gemini_doc_retrieval_normalized_score": signal - 0.05,
                    "gemini_doc_retrieval_rank": serp_rank,
                    "gemini_doc_retrieval_pct": float((serp_rank - 1) / 2),
                    "gemini_doc_retrieval_z": float(2 - serp_rank),
                    "gemini_semantic_similarity_raw_score": signal - 0.1,
                    "gemini_semantic_similarity_normalized_score": signal - 0.1,
                    "gemini_semantic_similarity_rank": serp_rank,
                    "gemini_semantic_similarity_pct": float((serp_rank - 1) / 2),
                    "gemini_semantic_similarity_z": float(2 - serp_rank),
                    "schema_version": "analysis_mart.v2",
                }
            )
    return rows


def _base_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "seed": "technical seo",
        "location": "United States",
        "language": "en",
        "device": "desktop",
        "depth": 20,
        "keyword_limit": 25,
        "model_name": "fixture-similarity-v1",
        "dry_run": False,
        "skip_textrazor": True,
        "live_textrazor_only": False,
        "refresh_textrazor": False,
        "live_providers": False,
        "live_backlinks": False,
        "live_backlinks_detail": False,
        "live_bge": False,
        "live_gemini": False,
        "live_textrazor": False,
    }
    config.update(overrides)
    return config


def _write_run(
    run_dir: Path,
    *,
    run_id: str,
    keyword_specs: list[tuple[str, str, float]],
    config_overrides: dict[str, object] | None = None,
    combined_analysis: dict[str, object] | None = None,
) -> None:
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True, exist_ok=True)
    pl.DataFrame(_analysis_rows(run_id=run_id, keyword_specs=keyword_specs)).write_parquet(
        run_dir / "parquet" / "analysis_mart" / "part-0.parquet"
    )

    payload: dict[str, object] = {
        "run_id": run_id,
        "config": _base_config(**(config_overrides or {})),
        "catalog": {
            "datasets": {
                "analysis_mart": {
                    "schema_version": "feature_marts.v1",
                    "row_count": len(keyword_specs) * 3,
                    "files": ["parquet/analysis_mart/part-0.parquet"],
                }
            }
        },
    }
    if combined_analysis is not None:
        payload["combined_analysis"] = combined_analysis
    (run_dir / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_analyze_requires_output_dir_when_combining_runs(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "runs" / "run-a"
    run_b = tmp_path / "runs" / "run-b"
    _write_run(run_a, run_id="run-a", keyword_specs=[("kw-1", "keyword 1", 0.0)])
    _write_run(run_b, run_id="run-b", keyword_specs=[("kw-2", "keyword 2", 0.05)])

    exit_code = main(
        [
            "analyze",
            "--run",
            str(run_a),
            "--run",
            str(run_b),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--output-dir is required when combining multiple runs" in captured.err


def test_analyze_combines_runs_into_synthetic_output_dir_with_last_run_wins(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_a = tmp_path / "runs" / "run-a"
    run_b = tmp_path / "runs" / "run-b"
    combined_dir = tmp_path / "runs" / "combined"
    _write_run(
        run_a,
        run_id="run-a",
        keyword_specs=[
            ("kw-1", "keyword 1", 0.00),
            ("kw-2", "keyword 2", 0.01),
        ],
    )
    _write_run(
        run_b,
        run_id="run-b",
        keyword_specs=[
            ("kw-2", "keyword 2", 0.08),
            ("kw-3", "keyword 3", 0.02),
        ],
        config_overrides={"device": "mobile"},
    )

    monkeypatch.setattr("seo_rank.cli.ensure_feature_marts_for_analysis", lambda path: None)
    monkeypatch.setattr("seo_rank.cli.build_analysis_mart", lambda path: {"datasets": {}})

    exit_code = main(
        [
            "analyze",
            "--run",
            str(run_a),
            "--run",
            str(run_b),
            "--output-dir",
            str(combined_dir),
        ]
    )

    assert exit_code == 0

    manifest = json.loads((combined_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["combined_analysis"]["source_runs"] == [
        str(run_a),
        str(run_b),
    ]
    assert manifest["combined_analysis"]["keyword_merge_policy"] == "last_run_wins"
    assert manifest["combined_analysis"]["run_priority"] == "cli_order"
    assert manifest["combined_analysis"]["compatibility_warnings"]
    assert manifest["combined_analysis"]["keyword_overlaps"]["kw-2"] == {
        "selected_run": str(run_b),
        "dropped_runs": [str(run_a)],
    }

    frame = pl.read_parquet(combined_dir / "parquet" / "analysis_mart" / "part-0.parquet")
    kw2_rows = frame.filter(pl.col("target_keyword_id") == "kw-2")
    assert kw2_rows.get_column("run_id").unique().to_list() == ["run-b"]
    assert frame.get_column("target_keyword_id").n_unique() == 3

    summary = json.loads((combined_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    report = (combined_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")
    assert summary["metadata"]["combined_analysis"]["source_runs"] == [
        str(run_a),
        str(run_b),
    ]
    assert summary["metadata"]["combined_analysis"]["compatibility_warnings"]
    assert "## Source runs" in report
    assert str(run_a) in report
    assert str(run_b) in report


def test_analyze_reuses_persisted_combined_run_without_rebuilding_marts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    combined_dir = tmp_path / "runs" / "combined"
    _write_run(
        combined_dir,
        run_id="combined",
        keyword_specs=[
            ("kw-1", "keyword 1", 0.00),
            ("kw-2", "keyword 2", 0.04),
            ("kw-3", "keyword 3", 0.08),
        ],
        combined_analysis={
            "source_runs": ["runs/run-a", "runs/run-b"],
            "keyword_merge_policy": "last_run_wins",
            "run_priority": "cli_order",
            "compatibility_warnings": [],
            "keyword_overlaps": {},
        },
    )

    monkeypatch.setattr(
        "seo_rank.cli.build_analysis_mart",
        lambda path: (_ for _ in ()).throw(AssertionError("build_analysis_mart should not run")),
    )

    exit_code = main(["analyze", "--run", str(combined_dir)])

    assert exit_code == 0
    assert (combined_dir / "stats" / "stats_summary.json").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["normalize"],
        ["build-features"],
        ["replay", "--response-id", "resp-1"],
    ],
)
def test_non_analysis_commands_reject_combined_runs(
    tmp_path: Path,
    capsys,
    argv: list[str],
) -> None:
    combined_dir = tmp_path / "runs" / "combined"
    _write_run(
        combined_dir,
        run_id="combined",
        keyword_specs=[("kw-1", "keyword 1", 0.00)],
        combined_analysis={
            "source_runs": ["runs/run-a", "runs/run-b"],
            "keyword_merge_policy": "last_run_wins",
            "run_priority": "cli_order",
            "compatibility_warnings": [],
            "keyword_overlaps": {},
        },
    )

    exit_code = main([*argv, "--run", str(combined_dir)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "combined run" in captured.err
