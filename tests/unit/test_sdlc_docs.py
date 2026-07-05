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
    assert "--live-textrazor-only" in readme
    assert "--refresh-textrazor" in readme
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
    assert "400 unit tests" in testing or "400 unit tests pass" in testing
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
    assert "400 unit tests" in architecture or "400 tests" in architecture or "400 unit tests pass" in architecture
    assert "400 unit tests" in testing or "400 unit tests pass" in testing
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
    assert "signal_families:" in spec
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
    assert "signal-family registry" in architecture
    assert "families.py" in architecture
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
    assert "test_stats_families.py" in testing
    assert "test_stats_spec.py" in testing
    assert "statsmodels>=0.14" in pyproject["project"]["dependencies"]
    assert "PyYAML>=6.0" in pyproject["project"]["dependencies"]
    assert "matplotlib>=3.8" in pyproject["project"]["dependencies"]


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
    assert "Phase 5 slices 1–10" in architecture
    assert "keyword-clustered SEs" in architecture
    assert "test_stats_regression.py" in testing
    assert "Phase 5 slices 1–10 and 16–20" in testing


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


def test_phase_5_slice_7_ships_multivariate_sensitivity() -> None:
    spec = (ROOT / "analysis_spec.v1.yaml").read_text(encoding="utf-8")
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "multivariate_vif_threshold:" in spec
    assert "backend_drop_order:" in spec
    assert "**[x] Slice 7 — Multivariate sensitivity**" in goals
    assert "| 7 | Multivariate sensitivity | Stats | Shipped |" in goals
    assert "Phase 5 Slice 7 shipped" in roadmap
    assert "**[x] Slice 7 — Multivariate sensitivity**" in roadmap
    assert "multivariate_sensitivity" in architecture
    assert "### Robustness" in architecture
    assert "test_stats_diagnostics.py" in testing
    assert "multivariate sensitivity" in testing.lower()
    assert "### Robustness" in readme


def test_phase_5_slice_8_ships_influence_robustness() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "**[x] Slice 8 — Robustness appendix (influence)**" in goals
    assert "| 8 | Robustness appendix (influence) | Stats | Shipped |" in goals
    assert "Phase 5 Slices 8–10 shipped" in roadmap
    assert "**[x] Slice 8 — Robustness appendix (influence)**" in roadmap
    assert "influence_sensitivity" in architecture
    assert "influential_rows_rate" in architecture
    assert "### Influence robustness" in readme
    assert "influence refit" in testing.lower()
    assert "test_stats_golden_fixtures.py" in testing


def test_phase_5_slice_9_ships_stats_artifacts_cli() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "**[x] Slice 9 — Stats artifacts & CLI**" in goals
    assert "| 9 | Stats artifacts & CLI | Stats | Shipped |" in goals
    assert "Phase 5 Slices 8–10 shipped" in roadmap
    assert "**[x] Slice 9 — Stats artifacts & CLI**" in roadmap
    assert "run_phase5_stats()" in architecture
    assert "materialize_run_tree" in readme
    assert "run_manifest_is_dry_run()" in readme
    assert "Stats artifacts & CLI (slice 9 shipped)" in testing
    assert "test_cli_surfaces.py" in testing


def test_phase_5_slice_10_ships_golden_fixtures() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "**[x] Slice 10 — Golden fixtures & tests**" in goals
    assert "| 10 | Golden fixtures & tests | Stats | Shipped |" in goals
    assert "Phase 5 Slices 8–10 shipped" in roadmap
    assert "**[x] Slice 10 — Golden fixtures & tests**" in roadmap
    assert "test_stats_golden_fixtures.py" in testing
    assert "test_stats_golden_fixtures.py" in readme
    assert "Golden fixture" in (ROOT / "PHASE5-STATS-PLAN-REVIEW.md").read_text(
        encoding="utf-8"
    )


def test_phase_5_page_level_plackett_luce_secondary_path_is_documented() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Page-level Plackett-Luce / rank-ordered logit" in goals
    assert "Plackett-Luce (page-level, secondary)" in roadmap
    assert "passage-level Plackett-Luce" in roadmap
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


def test_textrazor_only_ingestion_docs_cross_link() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "**[x] Slice 21 — TextRazor-only flags and gates**" in goals
    assert "**[x] Slice 24 — Stored-run TextRazor backfill**" in goals
    assert "**[x] Slice 25 — Brand-new TextRazor-only run**" in goals
    assert "Phase 5 Slices 21–26 shipped" in roadmap
    assert "raw_responses/endpoint=entities" in readme
    assert "provider=textrazor" in readme
    assert "RAW_RESPONSE_SCHEMA" in readme
    assert (
        "TextRazor-only ingestion writes the same `RAW_RESPONSE_SCHEMA` into the existing lake, partitioned only by `endpoint`."
        in architecture
    )
    assert "shared raw-response schema contract" in testing
    assert "test_textrazor_backfill.py" in testing
    assert "Backfill live TextRazor on a stored run" in readme
    assert "Brand-new run with live TextRazor only" in readme


def test_textrazor_signal_expansion_docs_cross_link() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plan_review = (ROOT / "PHASE5-STATS-PLAN-REVIEW.md").read_text(
        encoding="utf-8"
    )

    assert "**[x] Slice 27 — TextRazor signal registry and family contract**" in goals
    assert "**[x] Slice 28 — Materialize TextRazor page metrics**" in goals
    assert "Phase 5 Slices 27–28 shipped" in roadmap
    assert "textrazor_page_metrics_curated" in architecture
    assert "textrazor_page_metrics" in architecture
    assert "families.py" in architecture
    assert "test_stats_family_dispatch.py" in testing
    assert "test_stats_family_artifacts.py" in testing
    assert "textrazor_page_metrics_curated" in readme
    assert "TextRazor signal families" in plan_review
    assert "**[x] Slice 29 — Generalize the Phase 5 stats engine**" in goals
    assert "**[x] Slice 30 — Fold families into CLI output and artifacts**" in goals
    assert "**[x] Slice 32 — TextRazor page-metrics completeness**" in goals
    assert "**[x] Slice 33 — Small-K exploratory status**" in goals
    assert "Phase 5.7 — TextRazor structured signals" in roadmap
    assert "**[ ] Slice 35 — Word/sense/spelling parse fix" in goals
    assert "Phase 5 Slices 29–30 shipped" in roadmap


def test_phase_5_progress_counts_are_aligned() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "27 of 42 shipped, 2 partial, 13 open" in goals
    assert "27 of 42 shipped, 2 partial, 13 open" in roadmap


def test_ranking_explainability_docs_cross_link() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")

    assert "analysis/textrazor_ranking_r2.py" in readme
    assert "stats/ranking_r2.json" in readme
    assert "ranking_r2_curated_model.png" in readme
    assert "ranking_explainability_viz.py" in architecture
    assert "test_ranking_explainability_viz.py" in testing
    assert "test_stats_golden_fixtures.py" in testing
    assert "**[x] Slice 8 — Robustness appendix (influence)**" in (ROOT / "GOALS.md").read_text(
        encoding="utf-8"
    )
    assert "**[x] Slice 10 — Golden fixtures & tests**" in (ROOT / "GOALS.md").read_text(
        encoding="utf-8"
    )


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


def test_phase_6_1_plans_ols_pl_standardization() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    fixups = (ROOT / "FIXUPS.md").read_text(encoding="utf-8")

    assert "Phase 6.1 — OLS / Plackett-Luce standardization and reporting" in roadmap
    assert "within_keyword_sd_rms" in roadmap
    assert "Phase 6.1" in goals
    assert "Phase 6.1" in architecture
    assert "test_stats_scaling_contract.py" in testing
    assert "6.1 Slice 1" in fixups


def test_phase_7_1_onpage_slices_1_9_shipped() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    testing = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Phase 7.1 acceptance criteria (OnPage instant_pages)" in goals
    assert "9 of 10 slices shipped" in goals
    assert "onpage_instant_pages" in goals
    assert "onpage_features" in goals
    assert "ensure_feature_marts_for_analysis()" in goals
    assert "#### 7.1 — OnPage page signals" in roadmap
    assert "**Progress:** 9 of 10 shipped." in roadmap
    assert "**[x] Slice 9 — Artifacts follow-ups**" in roadmap
    assert "Phase 7.1 slices 1–9 shipped (2026-07-05)" in roadmap
    assert "onpage_signals" in architecture
    assert "onpage_features" in architecture
    assert "ensure_feature_marts_for_analysis()" in architecture
    assert "Phase 7.1 slices 1–9" in testing
    assert "test_onpage_stats_golden_contract_with_combined_feature_marts" in testing
    assert "endpoint=onpage_instant_pages" in readme
    assert "onpage_features" in readme
    assert "onpage_content_quality" in readme
