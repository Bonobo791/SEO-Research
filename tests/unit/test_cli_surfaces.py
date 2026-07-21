from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from seo_rank.cli import build_parser, main
from seo_rank.data.features import FEATURE_SCHEMA_VERSION, ensure_feature_marts_for_analysis
from seo_rank.data.marts import ANALYSIS_SCHEMA_VERSION


def test_build_parser_exposes_phase_45_commands() -> None:
    parser = build_parser()

    subparser_actions = [
        action for action in parser._actions if getattr(action, "choices", None)
    ]
    assert subparser_actions, "expected parser to define subcommands"
    subcommands = set(subparser_actions[0].choices)

    assert {"run", "normalize", "build-features", "analyze", "replay"} <= subcommands

    parsed = parser.parse_args(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            "/tmp/run-1",
        ]
    )
    assert parsed.stored_run == Path("/tmp/run-1")

    assert parser.parse_args(
        ["run", "--seed", "technical seo", "--debug", "1"]
    ).debug == 1
    assert parser.parse_args(
        ["run", "--seed", "technical seo", "--debug=0"]
    ).debug == 0

    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--seed", "technical seo", "--debug", "2"])

    analyzed = parser.parse_args(
        [
            "analyze",
            "--run",
            "/tmp/run-1",
            "--entity-id",
            "entity-a",
            "--entity-id",
            "entity-b",
        ]
    )
    assert analyzed.entity_id == ["entity-a", "entity-b"]


def test_storage_commands_dispatch_to_data_layer(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "seo_rank.cli.normalize_run",
        lambda path: calls.append(("normalize", path)) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.build_feature_marts",
        lambda path: calls.append(("build-features", path)) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.build_analysis_mart",
        lambda path: calls.append(("analyze", path)) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.run_phase5_stats",
        lambda path: calls.append(("phase5-stats", path))
        or SimpleNamespace(hard_fail=False),
    )
    monkeypatch.setattr(
        "seo_rank.cli.scan_raw_responses",
        lambda _path: pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "response_id": "resp-1",
                    "endpoint": "serp",
                    "response_body_bytes": b'{"id": 1}',
                }
            ]
        ).lazy(),
    )
    monkeypatch.setattr(
        "seo_rank.cli.scan_analysis_mart",
        lambda _path: pl.DataFrame(
            [
                {
                    "target_keyword": "technical seo",
                    "url": "https://example.com/seo",
                    "serp_rank": 1,
                },
                {
                    "target_keyword": "other keyword",
                    "url": "https://example.com/other",
                    "serp_rank": 2,
                },
            ]
        ).lazy(),
    )
    monkeypatch.setattr(
        "seo_rank.cli.ensure_feature_marts_for_analysis",
        lambda _path: None,
    )

    assert main(["normalize", "--run", str(run_dir)]) == 0
    assert main(["build-features", "--run", str(run_dir)]) == 0
    assert main(["analyze", "--run", str(run_dir), "--keyword", "technical seo"]) == 0

    exit_code = main(
        [
            "replay",
            "--run",
            str(run_dir),
            "--response-id",
            "resp-1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    output_lines = captured.out.strip().splitlines()
    assert output_lines == [
        '[{"serp_rank":1,"target_keyword":"technical seo","url":"https://example.com/seo"}]',
        '{"id": 1}',
    ]
    assert calls == [
        ("normalize", run_dir),
        ("build-features", run_dir),
        ("analyze", run_dir),
        ("phase5-stats", run_dir),
    ]


def test_ensure_feature_marts_for_analysis_rebuilds_when_onpage_features_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text('{"catalog": {"datasets": {}}}', encoding="utf-8")
    parquet_dir = run_dir / "parquet"
    for name in (
        "keyword_serp",
        "page_features",
        "passage_features",
        "domain_features",
        "backlinks_analysis",
    ):
        (parquet_dir / name).mkdir(parents=True)
        pl.DataFrame([{"run_id": "run-1"}]).write_parquet(parquet_dir / name / "part-0.parquet")

    build_calls: list[Path] = []
    monkeypatch.setattr(
        "seo_rank.data.features.build_feature_marts",
        lambda path: build_calls.append(path) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.data.features.build_analysis_mart",
        lambda _path: (_ for _ in ()).throw(AssertionError("helper must not rebuild analysis")),
    )

    ensure_feature_marts_for_analysis(run_dir)

    assert build_calls == [run_dir]


def test_ensure_feature_marts_for_analysis_rebuilds_stale_feature_marts_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text('{"catalog": {"datasets": {}}}', encoding="utf-8")
    parquet_dir = run_dir / "parquet"
    for name in (
        "keyword_serp",
        "page_features",
        "passage_features",
        "domain_features",
        "backlinks_analysis",
        "onpage_features",
        "entity_signals",
    ):
        (parquet_dir / name).mkdir(parents=True)
        pl.DataFrame([{"schema_version": "feature_marts.v3"}]).write_parquet(
            parquet_dir / name / "part-0.parquet"
        )
    (parquet_dir / "analysis_mart").mkdir()
    pl.DataFrame([{"schema_version": ANALYSIS_SCHEMA_VERSION}]).write_parquet(
        parquet_dir / "analysis_mart" / "part-0.parquet"
    )

    feature_calls: list[Path] = []
    monkeypatch.setattr(
        "seo_rank.data.features.build_feature_marts",
        lambda path: feature_calls.append(path) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.data.features.build_analysis_mart",
        lambda _path: (_ for _ in ()).throw(AssertionError("helper must not rebuild analysis")),
    )

    ensure_feature_marts_for_analysis(run_dir)

    assert feature_calls == [run_dir]


def test_ensure_feature_marts_for_analysis_noops_when_marts_are_current(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text('{"catalog": {"datasets": {}}}', encoding="utf-8")
    parquet_dir = run_dir / "parquet"
    for name in (
        "keyword_serp",
        "page_features",
        "passage_features",
        "domain_features",
        "backlinks_analysis",
        "onpage_features",
        "entity_signals",
    ):
        (parquet_dir / name).mkdir(parents=True)
        pl.DataFrame([{"schema_version": FEATURE_SCHEMA_VERSION}]).write_parquet(
            parquet_dir / name / "part-0.parquet"
        )
    (parquet_dir / "analysis_mart").mkdir()
    pl.DataFrame([{"schema_version": ANALYSIS_SCHEMA_VERSION}]).write_parquet(
        parquet_dir / "analysis_mart" / "part-0.parquet"
    )

    monkeypatch.setattr(
        "seo_rank.data.features.build_feature_marts",
        lambda _path: (_ for _ in ()).throw(AssertionError("feature marts should be current")),
    )
    monkeypatch.setattr(
        "seo_rank.data.features.build_analysis_mart",
        lambda _path: (_ for _ in ()).throw(AssertionError("analysis mart should be current")),
    )

    ensure_feature_marts_for_analysis(run_dir)


def test_analyze_rebuilds_onpage_features_for_legacy_run_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text('{"catalog": {"datasets": {}}}', encoding="utf-8")
    parquet_dir = run_dir / "parquet"
    for name in (
        "keyword_serp",
        "page_features",
        "passage_features",
        "domain_features",
        "backlinks_analysis",
    ):
        (parquet_dir / name).mkdir(parents=True)
        pl.DataFrame([{"run_id": "run-1"}]).write_parquet(parquet_dir / name / "part-0.parquet")

    build_calls: list[Path] = []
    monkeypatch.setattr(
        "seo_rank.data.features.build_feature_marts",
        lambda path: build_calls.append(path) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.data.features.build_analysis_mart",
        lambda _path: (_ for _ in ()).throw(AssertionError("helper must not rebuild analysis")),
    )
    monkeypatch.setattr(
        "seo_rank.cli.build_analysis_mart",
        lambda _path: {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.run_phase5_stats",
        lambda _path: SimpleNamespace(hard_fail=False),
    )

    exit_code = main(["analyze", "--run", str(run_dir)])

    assert exit_code == 0
    assert build_calls == [run_dir]


def test_ensure_feature_marts_for_analysis_noops_without_run_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)

    build_calls: list[Path] = []
    monkeypatch.setattr(
        "seo_rank.data.features.build_feature_marts",
        lambda path: build_calls.append(path) or {"datasets": {}},
    )

    ensure_feature_marts_for_analysis(run_dir)

    assert build_calls == []


def test_run_stored_run_replays_existing_tree_without_provider_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stored_run = tmp_path / "runs" / "run-1"
    stored_run.mkdir(parents=True)

    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "seo_rank.cli.replay_stored_run",
        lambda path, config, *, progress=None: calls.append(
            ("replay", path, config.output_dir)
        ),
    )
    monkeypatch.setattr(
        "seo_rank.cli.write_offline_artifacts",
        lambda config, *, progress=None: (_ for _ in ()).throw(
            AssertionError("offline run should not execute")
        ),
    )
    monkeypatch.setattr(
        "seo_rank.cli.write_live_artifacts",
        lambda config, env, *, progress=None: (_ for _ in ()).throw(
            AssertionError("live run should not execute")
        ),
    )

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--stored-run",
            str(stored_run),
        ]
    )

    assert exit_code == 0
    assert calls == [("replay", stored_run, stored_run)]


def test_analyze_rejects_unknown_keyword_with_exit_code_2(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.cli.build_analysis_mart",
        lambda _path: {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.run_phase5_stats",
        lambda _path: SimpleNamespace(hard_fail=False),
    )
    monkeypatch.setattr(
        "seo_rank.cli.ensure_feature_marts_for_analysis",
        lambda _path: None,
    )
    monkeypatch.setattr(
        "seo_rank.cli.scan_analysis_mart",
        lambda _path: pl.DataFrame(
            [{"target_keyword": "other keyword", "url": "https://example.com"}]
        ).lazy(),
    )

    exit_code = main(
        ["analyze", "--run", str(run_dir), "--keyword", "technical seo"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "technical seo" in captured.err


def test_analyze_returns_exit_code_1_when_phase5_guardrails_fail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.cli.build_analysis_mart",
        lambda _path: {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.run_phase5_stats",
        lambda _path: SimpleNamespace(hard_fail=True),
    )
    monkeypatch.setattr(
        "seo_rank.cli.ensure_feature_marts_for_analysis",
        lambda _path: None,
    )

    assert main(["analyze", "--run", str(run_dir)]) == 1


def test_analyze_builds_feature_marts_when_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet").mkdir(parents=True)
    (run_dir / "run.json").write_text('{"dry_run": false, "catalog": {"datasets": {}}}', encoding="utf-8")

    calls: list[tuple[str, Path]] = []

    monkeypatch.setattr(
        "seo_rank.data.features.build_feature_marts",
        lambda path: calls.append(("build-features", path)) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.build_analysis_mart",
        lambda path: calls.append(("analyze", path)) or {"datasets": {}},
    )
    monkeypatch.setattr(
        "seo_rank.cli.run_phase5_stats",
        lambda path: calls.append(("phase5-stats", path)) or SimpleNamespace(hard_fail=False),
    )

    assert main(["analyze", "--run", str(run_dir)]) == 0
    assert calls == [
        ("build-features", run_dir),
        ("analyze", run_dir),
        ("phase5-stats", run_dir),
    ]


def test_storage_commands_return_exit_code_2_on_storage_errors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    def fail(path: Path):
        del path
        raise FileNotFoundError("run.json missing")

    monkeypatch.setattr("seo_rank.cli.normalize_run", fail)

    exit_code = main(["normalize", "--run", str(run_dir)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "run.json missing" in captured.err


def test_replay_returns_exit_code_2_without_traceback_on_missing_response(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "seo_rank.cli.scan_raw_responses",
        lambda _path: pl.DataFrame(
            [{"response_id": "other-id", "response_body_bytes": b"{}"}]
        ).lazy(),
    )

    exit_code = main(["replay", "--run", str(run_dir), "--response-id", "resp-1"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "response_id=resp-1" in captured.err
