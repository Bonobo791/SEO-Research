import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_goals_and_roadmap_define_active_scope_and_backlog() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "active-scope contract" in goals
    assert "Active Objective" in goals
    assert "Phase 4" in goals
    assert "live similarity" in goals.lower()
    assert "Current Backlog" in roadmap
    assert "When `GOALS.md` exists, it is the active" in roadmap


def test_readme_reflects_phase_three_direction() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "What works today" in readme
    assert "Product direction (Phase 4)" in readme
    assert "Phase 3 shipped" in readme


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


def test_env_example_documents_live_provider_gates_without_real_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    expected_placeholders = {
        "SEO_RANK_RUN_LIVE_INTEGRATION": "0",
        "SEO_RANK_ENABLE_LIVE_PROVIDERS": "0",
        "DATAFORSEO_LOGIN": "replace-with-dataforseo-api-login",
        "DATAFORSEO_PASSWORD": "replace-with-dataforseo-api-password",
        "TEXTRAZOR_API_KEY": "replace-with-textrazor-api-key",
    }

    for name, placeholder in expected_placeholders.items():
        assert f"{name}={placeholder}" in env_example

    assert ".env" in gitignore
    assert "analyst@example.com" not in env_example
    assert "secret" not in env_example.lower()
