import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_goals_and_roadmap_define_active_scope_and_backlog() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "active-scope contract" in goals
    assert "Build the first offline-verifiable Python CLI scaffold" in goals
    assert "Current Backlog" in roadmap
    assert "When `GOALS.md` exists, it is the active" in roadmap


def test_manifest_records_resolved_pytest_commands() -> None:
    manifest = json.loads((ROOT / ".codex-sdlc/manifest.json").read_text(encoding="utf-8"))
    resolved = manifest.get("resolved_values", {})
    scan = manifest.get("scan", {})

    test_command = resolved.get("test_command") or scan.get("test_command")
    single_test_command = resolved.get("single_test_file_command") or scan.get(
        "single_test_file_command"
    )

    assert test_command == "python -m pytest"
    assert single_test_command == "python -m pytest tests/unit/test_cli_run.py"
    assert (resolved.get("test_framework") or scan.get("test_framework")) == "pytest"
