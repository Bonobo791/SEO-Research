import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PINNED_PROOF_TEST_COMMAND = (
    "PYTHONPATH=/var/home/user/PycharmProjects/SEO-Research/src:"
    "/var/home/user/PycharmProjects/SEO-Research/.venv/lib64/python3.14/site-packages "
    "/usr/bin/python3 -m pytest"
)
PINNED_PROOF_SINGLE_TEST_COMMAND = (
    "PYTHONPATH=/var/home/user/PycharmProjects/SEO-Research/src:"
    "/var/home/user/PycharmProjects/SEO-Research/.venv/lib64/python3.14/site-packages "
    "/usr/bin/python3 -m pytest tests/unit/test_cli_run.py"
)


def test_goals_and_roadmap_define_active_scope_and_backlog() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "active-scope contract" in goals
    assert "Active Objective" in goals
    assert "Phase 4.5" in goals
    assert "Phase 4 acceptance criteria (complete)" in goals
    assert "Current Backlog" in roadmap
    assert "Phase 4.5" in roadmap
    assert "Phase 4 shipped" in roadmap


def test_readme_reflects_phase_four_capabilities() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "What works today" in readme
    assert "Product direction" in readme
    assert "Phase 4 shipped" in readme
    assert 'seo-rank run --seed "technical seo" --dry-run' in readme
    assert "when `--output-dir` is omitted" in readme
    assert "--live-bge" in readme
    assert "--live-gemini" in readme
    assert "--live-textrazor" in readme


def test_manifest_records_resolved_pytest_commands() -> None:
    manifest = json.loads((ROOT / ".codex-sdlc/manifest.json").read_text(encoding="utf-8"))
    resolved = manifest.get("resolved_values", {})
    scan = manifest.get("scan", {})

    test_command = resolved.get("test_command") or scan.get("test_command")
    single_test_command = resolved.get("single_test_file_command") or scan.get(
        "single_test_file_command"
    )

    assert test_command == PINNED_PROOF_TEST_COMMAND
    assert single_test_command == PINNED_PROOF_SINGLE_TEST_COMMAND
    assert (resolved.get("test_framework") or scan.get("test_framework")) == "pytest"


def test_env_example_documents_live_provider_gates_without_real_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    expected_placeholders = {
        "SEO_RANK_RUN_LIVE_INTEGRATION": "0",
        "SEO_RANK_ENABLE_LIVE_PROVIDERS": "0",
        "SEO_RANK_ENABLE_BGE": "0",
        "SEO_RANK_ENABLE_GEMINI": "0",
        "SEO_RANK_ENABLE_TEXTRAZOR": "0",
        "DATAFORSEO_LOGIN": "replace-with-dataforseo-api-login",
        "DATAFORSEO_PASSWORD": "replace-with-dataforseo-api-password",
        "TEXTRAZOR_API_KEY": "replace-with-textrazor-api-key",
        "GEMINI_API_KEY": "replace-with-gemini-api-key",
    }

    for name, placeholder in expected_placeholders.items():
        assert f"{name}={placeholder}" in env_example

    assert ".env" in gitignore
    assert "analyst@example.com" not in env_example
    assert "secret" not in env_example.lower()


def test_pyproject_declares_runtime_parquet_and_polars_dependencies() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]

    assert "pyarrow>=21.0" in dependencies
    assert "polars>=1.0" in dependencies


def test_phase_45_slice_7_regression_sweep_marks_round_trip_docs_as_shipped() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "[x] Slice 7" in goals
    assert "Slice 7 shipped" in goals
    assert "7 acceptance items complete" in goals
    assert "`runs/{run_id}/` layout written for each completed run by default when" in goals
    assert "Slice 7 shipped" in readme
    assert "round-trip regression sweep" in readme
    assert "`seo-rank run` defaults to `runs/{run_id}/`" in architecture
    assert "Dedicated Parquet lake write → normalize → build-features → analyze round-trip regression sweep" in testing
    assert "round-trip regression sweep" in architecture
    assert "Phase 4.5 Slice 7 shipped" in roadmap
