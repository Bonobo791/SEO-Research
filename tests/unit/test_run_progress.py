"""Tests for seo-rank run progress logging."""

from pathlib import Path

from seo_rank.cli import main
from seo_rank.progress import RunProgress


def test_run_progress_logs_offline_run_phases(
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
            "--depth",
            "1",
            "--dry-run",
            "--skip-textrazor",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    stderr = captured.err
    assert "run: starting offline" in stderr
    assert "run: expanded" in stderr
    assert "keyword 1/" in stderr
    assert "writing artifacts" in stderr


def test_run_progress_log_prefix() -> None:
    lines: list[str] = []

    class _Sink:
        def write(self, text: str) -> int:
            lines.append(text)
            return len(text)

        def flush(self) -> None:
            return None

    progress = RunProgress(stream=_Sink())
    progress.log("hello")

    assert "".join(lines) == "[seo-rank] hello\n"
