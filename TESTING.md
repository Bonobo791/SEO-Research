# Testing

Pytest configuration and verification contract for SEO-Research.

## Current State

- Source directory: `src/seo_rank/`
- Test directories: `tests/unit/`, `tests/integration/`
- Test framework: `pytest`
- Run-all-tests command: `python -m pytest`
- Single-test-file command: `python -m pytest tests/unit/test_cli_run.py`
- Git-guard proof command: pinned in `.codex-sdlc/manifest.json` (`/usr/bin/python3`
  plus explicit `PYTHONPATH`) so the Node hook can run pytest without the venv
  interpreter
- Lint / type-check / build / coverage: not configured
- Expected test duration: fast (< 1s)
- **Current verification status:** 242 tests collected; 241 passing; 1 skipped

## Active Verification Command

```bash
python -m pytest
```

Live provider smoke tests are marked `integration` and skipped unless `.env`
sets the gates explicitly:

```bash
# In .env (loaded automatically):
# SEO_RANK_RUN_LIVE_INTEGRATION=1
# SEO_RANK_ENABLE_LIVE_PROVIDERS=1
# SEO_RANK_ENABLE_BGE=1               # only if using --live-bge
# SEO_RANK_ENABLE_GEMINI=1            # only if using --live-gemini
# SEO_RANK_ENABLE_TEXTRAZOR=1         # only if using --live-textrazor
# DATAFORSEO_LOGIN=...
# DATAFORSEO_PASSWORD=...
# TEXTRAZOR_API_KEY=...
# GEMINI_API_KEY=...

python -m pytest -m integration
```

Use `.env.example` as the local template. Copy it to `.env` at the project root
and fill in real credentials. Pytest loads `.env` automatically via
`tests/conftest.py` (same loader as the CLI). Values in `.env` override
conflicting shell exports. `.env` is ignored by git; `.env.example` must contain
placeholders only.

## Suite coverage (shipped)

| Test file | What it verifies |
|-----------|------------------|
| `test_cli_run.py` | CLI writes grouped per-keyword artifacts, including BGE, Gemini Doc Retrieval, and Gemini Semantic Similarity rows; run-scoped `raw_responses` Parquet + `run.json` catalog metadata; offline TextRazor include/skip; TextRazor-only config gating and helper validation; explicit live-provider gates; stored-run partial resume/backfill, stale SERP refresh, and no-op replay coverage; opt-in live Gemini, BGE, and TextRazor orchestration |
| `test_run_progress.py` | `seo-rank run` stderr progress: run phases, per-keyword substeps, progress bar, artifact-write logs |
| `test_cli_surfaces.py` | Phase 4.5 storage CLI: subcommand parser wiring, `normalize` / `build-features` / `analyze` / `replay` dispatch, missing feature-mart backfill on `analyze`, `run --stored-run` routing, exit code `2` on storage errors and unknown keyword/response |
| `test_run_normalize.py` | Stored `raw_responses` normalize into curated Parquet tables (including `similarity_scores` copied from `run.json` `page_similarity`, `page_content_fields`) via lazy scan + batch UDFs; refresh the run catalog |
| `test_data_scans_validate.py` | Raw-response scans use `pl.scan_parquet()`, lazy curated frames are built, schema-only validation rejects missing columns, and materialized row-rule checks stay off the lazy edge |
| `test_data_marts.py` | Analysis mart lazy join lives in `seo_rank.data.marts` and preserves the feature-mart contract |
| `test_feature_marts.py` | Feature marts materialize lazy joins, validate before sink, sink feature marts lazily with Parquet statistics, audit the written parquet row rules, and refresh the run catalog |
| `test_analysis_mart.py` | Feature marts materialize the lazy analysis mart, preserve unmatched SERP rows with nullable feature columns, validate before sink, audit the written parquet row rules, and refresh the run catalog |
| `test_stats_panel.py` | Guardrail evaluation (SERP-rank variance hard-fail, similarity-variance warn), panel grain filtering, full vs minimal stats artifact writing on pass/fail |
| `test_stats_spearman.py` | Benjamini-Hochberg adjustment, backend Spearman summaries, and Spearman artifact emission on passing panels |
| `test_stats_diagnostics.py` | Pooled OLS diagnostics, small-sample Shapiro handling, diagnostic artifact emission on passing panels, and skipped-backend diagnostics behavior |
| `test_stats_regression.py` | Pooled baseline and per-backend feature regressions with keyword-clustered SEs, effect-size translation, two-way-cluster sensitivity, and regression artifact emission on passing panels |
| `test_stats_plackett_luce.py` | Page-level Plackett-Luce rank-ordered logit summaries, partial-ranking handling, optimizer / leave-one-out IIA diagnostics, and PL artifact emission on passing panels |
| `test_stats_rank_depth.py` | Rank-depth confirmatory slices: spec accessors, panel filtering, per-depth Spearman/OLS/PL, monotonic row counts, `rank_depths` JSON + report sections |
| `test_round_trip.py` | Dedicated Parquet lake write → normalize → build-features → analyze round-trip regression sweep on real Parquet artifacts; validates `run.json` updates and keyword-filtered `analyze` output |
| `test_keyword_expansion.py` | 1-keyword default, deduplication, raw provider payload |
| `test_serp_normalization.py` | Organic-only SERP rows, depth cap |
| `test_env.py` | `.env` discovery, parsing, and override of shell exports |
| `test_bge_reranker.py` | Live BGE GPU gate, pinned model loading, tokenizer compatibility shim, and batched score shaping |
| `test_gemini_embeddings.py` | Live Gemini prompt formatting, model args, and score shaping with injected embeddings |
| `test_passage_normalization.py` | Passage split, short-text filter |
| `test_similarity_features.py` | Fixture passage aggregation plus BGE, Gemini Doc Retrieval, and Gemini Semantic Similarity page scoring |
| `test_analysis_gemini_nwh_similarity.py` | Analysis script block scoring with BGE, Gemini document relevance, and Gemini semantic similarity plus provider error handling |
| `test_textrazor_normalization.py` | Entity schema normalization |
| `test_textrazor_requests.py` | TextRazor parsed-text request construction, credential validation, HTTP execution |
| `test_sdlc_docs.py` | GOALS/ROADMAP/README/TESTING/ARCHITECTURE guards, manifest pytest commands, and the Slice 7 round-trip regression sweep |
| `test_live_provider_smoke.py` | Env-gated DataForSEO smoke path with optional live TextRazor, Gemini, and BGE opt-ins |
| `test_live_provider_smoke_config.py` | Optional live similarity flags are included in smoke runs when their env gates are enabled |

Unit tests use fixtures/mocks only. Live provider smoke tests are opt-in and
must never run without the explicit environment gates above. DataForSEO is
always required for a live run; Gemini, BGE, and TextRazor are optional and
require their own CLI flags plus env gates when requested.

## Required Workflow

Follow `AGENTS.md` and `SDLC-LOOP.md` for code-shaped changes:

1. Define the red check before editing.
2. Write the failing test first.
3. Confirm RED, implement minimal fix, confirm GREEN.
4. Run `python -m pytest` before commit.

## Mocking Philosophy

Mock nondeterministic or destructive external effects (network, paid APIs,
credentials). Prefer integration tests at real boundaries once live clients
exist.

## Shipped tests — Phase 5 slices 1–6 and 16–20

- **`analysis_spec.v1.yaml` contract** — `tests/unit/test_sdlc_docs.py::
  test_phase_5_slice_1_defines_analysis_spec_v1` asserts estimand fields
  (outcome, BGE primary backend, BH family, actionable-association thresholds)
  and cross-links in `ARCHITECTURE.md`, `ROADMAP.md`, and
  `PHASE5-STATS-PLAN-REVIEW.md`.
- **Spec loader and output metadata** — `tests/unit/test_stats_spec.py` loads
  `analysis_spec.v1.yaml` via `load_analysis_spec()`, verifies backend order and
  estimand outcome, and asserts `build_stats_output_metadata()` exposes
  `analysis_spec_version` / `estimand_version`.
- **Stats package surface** — `tests/unit/test_stats_spec.py::
  test_stats_package_exports_module_surface` asserts `seo_rank.stats` exports
  `spec`, `panel`, `rank_depth`, `spearman`, `regression`, `plackett_luce`,
  `diagnostics`, `bh`, and `artifacts`.
- **Guardrail evaluation and hard-fail artifacts** —
  `tests/unit/test_stats_panel.py` covers top-20 filtering, primary-backend
  null dropping, SERP-rank variance hard-fail, similarity-variance warn, full
  stats artifacts on pass, and minimal summary/report on hard-fail.
- **Spearman primary path + BH** — `tests/unit/test_stats_spearman.py` covers
  BH adjustment, keyword-level Spearman summaries, underpowered BH skipping,
  and stats artifact emission on passing panels.
- **Pooled regression secondary path** — `tests/unit/test_stats_regression.py`
  covers baseline vs feature models, keyword-clustered SEs only in the primary
  output, the explicit Δ-rank effect-size formula, repeated-URL two-way-cluster
  sensitivity, and regression sections in `stats_summary.json` /
  `stats_report.md`.
- **Page-level Plackett-Luce secondary path** —
  `tests/unit/test_stats_plackett_luce.py` covers the rank-ordered logit fit,
  partial-ranking row dropping, optimizer convergence / non-convergence,
  choice-set sizing, leave-one-out IIA on `top_20`, and per-depth PL sections in
  `stats_summary.json` / `stats_diagnostics.json` / `stats_report.md`.
- **Rank-depth confirmatory slices** — `tests/unit/test_stats_rank_depth.py`
  covers spec accessors, `filter_panel_by_max_rank`, per-depth Spearman/OLS/PL,
  monotonic row counts, `actionable_association_by_rank_depth`, and four
  `## Rank depth:` report sections.
- **Pooled OLS diagnostics** — `tests/unit/test_stats_diagnostics.py` covers
  RESET, Breusch–Pagan with HC3 recommendation, Cook's D and influence flags,
  small-sample Shapiro as informational, skipped-backend diagnostics, and
  `stats_diagnostics.json` / `stats_report.md` emission on passing panels.

## Planned tests (not yet in suite) — Phase 5 active scope

See `GOALS.md` and `ROADMAP.md` § Phase 5 slices 7–15.

- Feature marts and `analysis_mart` join keys (`run_id`, `target_keyword_id`,
  `canonical_url_hash`, `response_id`, `passage_id`)
- Passage / domain similarity scopes (feature marts; Phase 5.5 scoring)

### Phase 5 — statistical analysis (see `ROADMAP.md` slices 7–15)

- **Golden `analysis_mart` fixture** — synthetic panel with known Spearman ρ and
  pooled slope per backend; tolerance bands for regression coefficients,
  correlation summaries, and effect-size translation.
- **`stats_summary.json` schema** — estimand version, `primary_rank_depth`,
  `confirmatory_rank_depths`, nested `rank_depths` (guardrails, limitations,
  per-backend ρ median/IQR, BH q-values or `bh_skipped_reason`, pooled
  coefficients + clustered CIs, `actionable_association`,
  `actionable_association_by_rank_depth`); top-level compat shim mirrors
  `rank_depths.top_20`; assert naive IID SEs absent.
- **`stats_diagnostics.json` schema** — nested `rank_depths` with RESET/BP
  flags, influence counts and %, leverage/DFFITS/DFBETAs, multivariate VIF +
  drop log, `influence_sensitivity` block, optional two-way-cluster CIs;
  leave-one-out IIA under `rank_depths.top_20.plackett_luce` only.
- **Guardrail gates** — hard-fail skips BH and actionable flag; warn still emits
  full stats; CLI exit 1 on hard-fail unless `--no-fail-on-guardrails`.
- **BH policy** — within-backend family only; skipped when K < 10; diagnostics
  excluded from BH.
- **Multivariate sensitivity** — VIF > 5 triggers backend drop order from spec.
- **Influence robustness** — refit without Cook's D > 4/n rows; coefficient
  delta vs confirmatory model.
- **Dry-run / fixture skip** — `seo-rank analyze` on documented fixture modes
  does not require full stats output.

## Planned tests (not yet in suite) — Phase 6 workflow integrity

See `ROADMAP.md` § Phase 6.

- **contract-schema tests** — validate `workflow_contracts.v1.yaml`, required
  fields, owners, boundary status, and contract-version policy.
- **contract-coverage tests** — every executable stage transition has exactly
  one registered contract row, and every contract row maps to a real transition.
- **Reconciliation tests** — audit committed artifacts, not self-reported stage
  counts; validate distinct input/matched counts, duplicate detection,
  unexplained gap counts, and canonical ID digests.
- **Provenance and reuse tests** — verify `logical_run_id`, `execution_id`,
  `artifact_id`, `input_snapshot_id`, `source_execution_id`, and
  contract-version compatibility across fresh runs, `--stored-run`, retries,
  and dry runs.
- **State-model tests** — assert `planned → running → materialized → reconciled
  → committed`; fail on open `running` stages or missing committed artifacts.
- **partial-write and commit-failure tests** — staged outputs must not be
  treated as valid downstream inputs; reconciliation must occur before commit.
- **Silent-failure regression fixtures** — keyword expanded but SERP never
  fetched; stage omitted entirely; ledger says success but committed artifact is
  missing; stale artifact reused; partial stored-run expansion leaves
  unexplained gaps.
- **Exception-policy tests** — undeclared empty outputs fail; allowed skip/empty
  behavior requires explicit owner, reason code, scope, retry rule, max volume,
  and review date; required `deferred` or `failed_final` units prevent green
  completion.
- **Operational-surface tests** — reconciliation gap count, stale-provenance
  rejection, missing committed artifacts, skip-rate spikes, retry exhaustion,
  and contract-version mismatch are emitted in operator-visible outputs.

Keep optional live flags aligned with `.env.example` when adding integration tests.

See phased backlog in `ROADMAP.md` and planned pipeline in `ARCHITECTURE.md`.

## Maintaining This File

Update in the same slice that changes the verification contract (commands, test
count, or required gates).
