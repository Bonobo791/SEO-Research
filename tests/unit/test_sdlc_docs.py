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
    assert "Phase 5" in goals
    assert "Phase 5 objective" in goals
    assert "statistical analysis" in goals
    assert "analysis_mart" in goals
    assert "analysis_spec.v1.yaml" in goals
    assert "statsmodels" in goals
    assert "Completed: Phase 4.77" in goals
    assert "Phase 4.77 acceptance criteria" not in goals
    assert "Phase 4.5" not in goals
    assert "Phase 4 acceptance criteria" not in goals
    assert "Current Backlog" in roadmap
    assert "Phase 5" in roadmap
    assert "Statistical analysis" in roadmap
    assert "analysis_spec.v1.yaml" in roadmap
    assert "Phase 4.77 shipped" in roadmap
    assert "GOALS retargeted to Phase 5" in roadmap
    assert "Phase 4.5 signed off" in roadmap
    assert "Phase 4 shipped" in roadmap


def test_readme_documents_cli_capabilities() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "What works today" in readme
    assert 'seo-rank run --seed "technical seo" --dry-run' in readme
    assert "[seo-rank]" in readme
    assert "--keyword-limit" in readme
    assert "seo-rank normalize --run" in readme
    assert "stats_diagnostics.json" in readme
    assert "runs/{run_id}/" in readme
    assert "Expand existing run" in readme
    assert "--live-bge" in readme
    assert "--live-gemini" in readme
    assert "--live-textrazor" in readme
    assert "Phase 5 stats" in readme
    assert "Fresh data" in readme
    assert "Resume stored run in place" in readme


def test_stored_run_docs_describe_partial_resume_and_current_suite_status() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "resume stored runs in place" in readme
    assert "reuses existing raw responses" in readme
    assert "`--stored-run` resumes partial runs in place" in architecture
    assert "refreshes only missing work" in architecture
    assert "242 tests collected; 241 passing; 1 skipped" in testing
    assert "resumes from the saved raw lake" in roadmap


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
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "Phase 4.5 Slice 7 shipped" in roadmap
    assert "Phase 4.5 signed off" in roadmap
    assert "`seo-rank run` defaults to `runs/{run_id}/`" in architecture
    assert "Dedicated Parquet lake write → normalize → build-features → analyze round-trip regression sweep" in testing
    assert "round-trip regression sweep" in architecture


def test_phase_45_slice_9_regression_sweep_marks_mart_sink_docs_as_shipped() -> None:
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "Phase 4.5 Slice 9 shipped" in roadmap
    assert "Phase 4.5 Slice 10 shipped" in roadmap
    assert "Phase 4.5 signed off" in roadmap
    assert "242 tests" in architecture
    assert "242 tests collected; 241 passing; 1 skipped" in testing
    assert "sink feature marts lazily with Parquet statistics" in testing


def test_phase_5_slice_1_defines_analysis_spec_v1() -> None:
    spec = (ROOT / "analysis_spec.v1.yaml").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    plan_review = (ROOT / "PHASE5-STATS-PLAN-REVIEW.md").read_text(
        encoding="utf-8"
    )

    assert "version: v1" in spec
    assert "outcome: -log(serp_rank)" in spec
    assert "plackett_luce:" in spec
    assert "rank_ordered_logit" in spec
    assert "primary_backend: bge" in spec
    assert "backend_order:" in spec
    assert "keyword_clustered_se: target_keyword_id" in spec
    assert "bh_family: per_backend_keyword_tests" in spec
    assert "bh_when_keyword_count_gte: 10" in spec
    assert "actionable_association:" in spec
    assert "analysis_spec.v1.yaml" in architecture
    assert "analysis_spec.v1.yaml" in roadmap
    assert "analysis_spec.v1.yaml" in plan_review
    assert "Phase 5 Slice 1 shipped" in roadmap
    assert "**[x] Slice 1 — Estimand & analysis spec**" in goals


def test_phase_5_slice_2_ships_stats_package_scaffold() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "Phase 5 Slice 2 shipped" in roadmap
    assert "**[x] Slice 2 — Stats module & dependencies**" in goals
    assert "src/seo_rank/stats/" in architecture
    assert "load_analysis_spec" in architecture or "spec.py" in architecture
    assert "test_stats_spec.py" in testing
    assert "statsmodels>=0.14" in pyproject["project"]["dependencies"]
    assert "PyYAML>=6.0" in pyproject["project"]["dependencies"]


def test_phase_5_slice_5_ships_pooled_regression_secondary_path() -> None:
    spec = (ROOT / "analysis_spec.v1.yaml").read_text(encoding="utf-8")
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")

    assert "formula: median_rank * (exp(-(coefficient * similarity_sd)) - 1)" in spec
    assert "**[x] Slice 5 — Pooled regression (secondary)**" in goals
    assert "| 5 | Pooled regression (secondary) | Stats | Shipped |" in goals
    assert "Phase 5 Slice 5 shipped" in roadmap
    assert "**[x] Slice 5 — Pooled regression (secondary)**" in roadmap
    assert "slices 1–6 and 16–20 shipped" in architecture
    assert "keyword-clustered SEs" in architecture
    assert "test_stats_regression.py" in testing
    assert "Phase 5 slices 1–6 and 16–20" in testing


def test_phase_5_slice_6_ships_pooled_ols_diagnostics() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "**[x] Slice 6 — Pooled OLS diagnostics**" in goals
    assert "| 6 | Pooled OLS diagnostics | Stats | Shipped (S5-11 open) |" in goals
    assert "S5-11" in goals
    assert "Phase 5 Slice 6 shipped" in roadmap
    assert "**[x] Slice 6 — Pooled OLS diagnostics**" in roadmap
    assert "stats_diagnostics.json" in architecture
    assert "page_similarity" in architecture
    assert "test_stats_diagnostics.py" in testing
    assert "stats_diagnostics.json" in readme


def test_phase_5_page_level_plackett_luce_secondary_path_is_documented() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Page-level Plackett-Luce / rank-ordered logit" in goals
    assert "Plackett-Luce (page-level, secondary)" in roadmap
    assert "passage-level Plackett-Luce analysis" in roadmap
    assert "Slice 15 — Plackett-Luce estimand runtime wiring" in goals
    assert "Slice 15 — Plackett-Luce estimand runtime wiring" in roadmap
    assert "Plackett-Luce (page-level, secondary)" in architecture
    assert "page-level Plackett-Luce summaries" in readme
    assert "test_stats_plackett_luce.py" in testing


def test_phase_5_rank_depth_slices_are_documented() -> None:
    spec = (ROOT / "analysis_spec.v1.yaml").read_text(encoding="utf-8")
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plan_review = (ROOT / "PHASE5-STATS-PLAN-REVIEW.md").read_text(
        encoding="utf-8"
    )

    assert "rank_depths:" in spec
    assert "limitations_by_depth:" in spec
    assert "leave_one_out_top_rank: true" in spec
    assert "**[x] Slice 16 — Rank-depth spec and panel filtering**" in goals
    assert "Parallel confirmatory rank depths (20/10/5/3)" in roadmap
    assert "Rank-depth confirmatory paths (shipped)" in architecture
    assert "test_stats_rank_depth.py" in testing
    assert "actionable_association_by_rank_depth" in readme
    assert "Rank-depth confirmatory paths" in plan_review


def test_phase_6_plans_workflow_integrity_guardrails() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")

    assert "Phase 6 — Workflow Integrity Guardrails" in roadmap
    assert "workflow_contracts.v1.yaml" in roadmap
    assert "logical run is complete only when every required accounting unit has a permitted terminal disposition" in roadmap
    assert "Phase 6 is planned future work" in goals
    assert "workflow_contracts.v1.yaml" in architecture
    assert "artifact-derived reconciliation" in architecture
    assert "contract-schema tests" in testing
    assert "partial-write and commit-failure tests" in testing
