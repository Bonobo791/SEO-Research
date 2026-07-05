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
- **Current verification status:** 331 unit tests pass (`python -m pytest tests/unit`); full suite collects 332 tests including 1 opt-in integration test

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
| `test_cli_run.py` | CLI writes grouped per-keyword artifacts, including BGE, Gemini Doc Retrieval, and Gemini Semantic Similarity rows; run-scoped `raw_responses` Parquet + `run.json` catalog metadata; offline TextRazor include/skip; TextRazor entity confidence/relevance in `report.md`; TextRazor-only flags (`--live-textrazor-only`, `--refresh-textrazor`), env gates, and mutual-exclusion errors; explicit live-provider gates; DataForSEO `backlinks/summary/live` two-call raw persistence (separate summary/dofollow partitions, batched per keyword, partial progress on mid-loop failure, stored-run backfill, survives later provider failure); stored-run CLI overlay (`merge_stored_run_cli_overlay`, sticky `--skip-textrazor`, offline stored run + `--live-providers` backfill); stored-run partial resume/backfill, stale SERP refresh, and no-op replay coverage; opt-in live Gemini, BGE, and TextRazor orchestration |
| `test_run_progress.py` | `seo-rank run` stderr progress: run phases, per-keyword substeps, progress bar, artifact-write logs |
| `test_cli_surfaces.py` | Phase 4.5 storage CLI: subcommand parser wiring, `normalize` / `build-features` / `analyze` / `replay` dispatch, missing feature-mart backfill on `analyze`, `run --stored-run` routing, exit code `2` on storage errors and unknown keyword/response |
| `test_run_normalize.py` | Stored `raw_responses` normalize into curated Parquet tables (including `similarity_scores` copied from `run.json` `page_similarity`, `page_content_fields`, `backlinks` from paired `backlinks/summary/live` responses, and `textrazor_page_metrics_curated` from TextRazor page-metrics responses) via lazy scan + batch UDFs; TextRazor entailment scores above 1.0 validate; dataset-name validation errors; refresh the run catalog |
| `test_data_scans_validate.py` | Raw-response scans use `pl.scan_parquet()`, lazy curated frames are built, schema-only validation rejects missing columns, and materialized row-rule checks stay off the lazy edge |
| `test_data_marts.py` | Analysis mart lazy join lives in `seo_rank.data.marts` and preserves the feature-mart contract |
| `test_feature_marts.py` | Feature marts materialize lazy joins (including `backlinks_analysis` from curated `backlinks`), validate before sink, sink feature marts lazily with Parquet statistics, audit the written parquet row rules, allow unbounded TextRazor entailment scores, surface dataset names on validation failure, and refresh the run catalog |
| `test_analysis_mart.py` | Feature marts materialize the lazy analysis mart, preserve unmatched SERP rows with nullable feature columns, validate before sink, audit the written parquet row rules, and refresh the run catalog |
| `test_stats_panel.py` | Guardrail evaluation (SERP-rank variance hard-fail, similarity-variance warn), panel grain filtering, full vs minimal stats artifact writing on pass/fail |
| `test_stats_spearman.py` | Benjamini-Hochberg adjustment, backend Spearman summaries, and Spearman artifact emission on passing panels |
| `test_stats_diagnostics.py` | Pooled OLS diagnostics, multivariate VIF sensitivity with spec drop order, influence refit (`influence_sensitivity`), small-sample Shapiro handling, diagnostic artifact emission on passing panels, and skipped-backend diagnostics behavior |
| `test_stats_regression.py` | Pooled baseline and per-backend feature regressions with keyword-clustered SEs, effect-size translation, two-way-cluster sensitivity, and regression artifact emission on passing panels |
| `test_stats_plackett_luce.py` | Page-level Plackett-Luce rank-ordered logit summaries, partial-ranking handling, optimizer / leave-one-out IIA diagnostics, and PL artifact emission on passing panels |
| `test_stats_families.py` | Declarative signal-family registry loading, ordered enumeration, panel-grain preservation, and malformed-entry rejection |
| `test_stats_family_dispatch.py` | Family-aware Spearman summaries with BH scoped per signal family (similarity vs TextRazor source marts) |
| `test_stats_family_artifacts.py` | Combined `stats_*` artifact tree for all signal families (similarity, TextRazor, `backlinks_counts`), hard-fail family skip path, and underpowered `inference_mode` labeling |
| `test_stats_rank_depth.py` | Rank-depth confirmatory slices: spec accessors, panel filtering, per-depth Spearman/OLS/PL, monotonic row counts, `rank_depths` JSON + report sections |
| `test_stats_scale.py` | Within-keyword and global z-score helpers (`stats.scale`) for OLS/PL effect-size contract |
| `test_textrazor_ingest.py` | TextRazor endpoint registry, page entity fetch, and dedupe helpers with injected transport |
| `test_textrazor_backfill.py` | Stored-run TextRazor backfill: `load_pages_for_textrazor`, `--stored-run --live-textrazor-only` CLI path, no DataForSEO HTTP |
| `test_raw_response_merge.py` | `merge_raw_response_records` for `endpoint=entities` dedupe and refresh semantics |
| `test_round_trip.py` | Dedicated Parquet lake write → normalize → build-features → analyze round-trip regression sweep on real Parquet artifacts; validates `run.json` updates and keyword-filtered `analyze` output |
| `test_keyword_expansion.py` | 1-keyword default, deduplication, raw provider payload |
| `test_serp_normalization.py` | Organic-only SERP rows, depth cap |
| `test_env.py` | `.env` discovery, parsing, and override of shell exports |
| `test_bge_reranker.py` | Live BGE GPU gate, pinned model loading, tokenizer compatibility shim, and batched score shaping |
| `test_gemini_embeddings.py` | Live Gemini prompt formatting, model args, and score shaping with injected embeddings |
| `test_passage_normalization.py` | Passage split, short-text filter |
| `test_similarity_features.py` | Fixture passage aggregation plus BGE, Gemini Doc Retrieval, and Gemini Semantic Similarity page scoring |
| `test_analysis_gemini_nwh_similarity.py` | Analysis script block scoring with BGE, Gemini document relevance, Gemini semantic similarity, extended TextRazor summaries, and provider error handling |
| `test_stats_golden_fixtures.py` | Synthetic `analysis_mart` golden panel: `stats_summary.json` / `stats_diagnostics.json` schema contracts, BH when K ≥ 10 vs underpowered, hard-fail skip path, influence refit delta, multivariate VIF drop order, clustered vs HC3 SE guard |
| `test_textrazor_ranking_explainability.py` | Ranking explainability summaries: similarity + TextRazor univariate and multivariate adjusted R², curated multivariate model, metric coverage |
| `test_ranking_explainability_viz.py` | Curated final-model and entity-relevance PNG visualizations (coefficients + fit diagnostics) |
| `test_textrazor_normalization.py` | Entity schema normalization and TextRazor page-metrics aggregation into `textrazor_page_metrics_curated` |
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

## Shipped tests — Phase 5 slices 1–10 and 16–20

- **`analysis_spec.v1.yaml` contract** — `tests/unit/test_sdlc_docs.py::
  test_phase_5_slice_1_defines_analysis_spec_v1` asserts estimand fields
  (outcome, BGE primary backend, BH family, actionable-association thresholds)
  and cross-links in `ARCHITECTURE.md`, `ROADMAP.md`, and
  `PHASE5-STATS-PLAN-REVIEW.md`.
- **Spec loader and output metadata** — `tests/unit/test_stats_spec.py` loads
  `analysis_spec.v1.yaml` via `load_analysis_spec()`, verifies backend order,
  panel grain, signal-family ordering, and estimand outcome, and asserts
  `build_stats_output_metadata()` exposes `analysis_spec_version` /
  `estimand_version`.
- **Stats package surface** — `tests/unit/test_stats_spec.py::
  test_stats_package_exports_module_surface` asserts `seo_rank.stats` exports
  `spec`, `panel`, `rank_depth`, `spearman`, `regression`, `plackett_luce`,
  `diagnostics`, `bh`, `families`, and `artifacts`.
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
  influence refit (`influence_sensitivity` block), small-sample Shapiro as
  informational, skipped-backend diagnostics, and
  `stats_diagnostics.json` / `stats_report.md` emission on passing panels.
- **Multivariate sensitivity (slice 7 shipped)** — `tests/unit/test_stats_spec.py`
  and `tests/unit/test_stats_diagnostics.py` cover the spec-driven VIF threshold
  and backend drop order, plus the primary-depth `multivariate_sensitivity`
  block in `stats_diagnostics.json` and the `### Robustness` section in
  `stats_report.md`.
- **Influence robustness (slice 8 shipped)** — `tests/unit/test_stats_diagnostics.py`
  and `tests/unit/test_stats_golden_fixtures.py` cover Cook's D trimming refits,
  coefficient deltas, `### Influence robustness` report sections, and the
  `influential_rows_rate` warn guardrail.
- **Stats artifacts & CLI (slice 9 shipped)** — `tests/unit/test_stats_panel.py`,
  `test_stats_spearman.py`, and `test_cli_surfaces.py` cover
  `run_phase5_stats()` emission under `runs/{run_id}/stats/`, nested
  `rank_depths` in summary and diagnostics JSON, `seo-rank analyze` dispatch,
  guardrail hard-fail exit code `1`, and dry-run skip via
  `run_manifest_is_dry_run()`.
- **Golden fixtures (slice 10 shipped)** — `tests/unit/test_stats_golden_fixtures.py`
  pins synthetic `analysis_mart` panels with known Spearman ρ and pooled slopes,
  schema metadata contracts, BH boundaries, hard-fail skip path, actionable flag
  logic, influence refit delta, multivariate VIF drop order, and clustered vs
  HC3 SE guards.

## Shipped tests — Ranking explainability

- **Similarity + TextRazor adjusted R² summaries** — `tests/unit/test_textrazor_ranking_explainability.py`
  covers univariate and multivariate pooled OLS adjusted R² for similarity backends
  and TextRazor page metrics via `seo_rank.stats.textrazor_explainability`.
- **Curated-model PNG charts** — `tests/unit/test_ranking_explainability_viz.py`
  covers coefficient/fit visualizations for the curated multivariate model and the
  entity-relevance-only model (`ranking_explainability_viz.py`; optional
  `matplotlib` display via `analysis/textrazor_ranking_r2.py --no-show`).

## Shipped tests — TextRazor-only ingestion (slices 21–25)

- **CLI flags and gates** — `tests/unit/test_cli_run.py` covers
  `--live-textrazor-only` / `--refresh-textrazor` persistence, mutual exclusion
  with `--live-providers` and `--skip-textrazor`, and env-gated credential
  validation without DataForSEO credentials.
- **Brand-new textrazor-only run** — `test_cli_run.py` covers
  `write_textrazor_only_artifacts()` dispatch, fixture DataForSEO
  expansion/SERP/page_text (no HTTP transport), live TextRazor entity fetch, and
  `network_calls == ["textrazor.entities"]`.
- **Ingest core** — `tests/unit/test_textrazor_ingest.py` covers
  `TEXTRAZOR_ENDPOINTS`, `fetch_textrazor_entities_for_pages()`, and
  `pages_missing_textrazor()` with injected transport.
- **Raw lake merge** — `tests/unit/test_raw_response_merge.py` covers
  `merge_raw_response_records()` dedupe on `(target_keyword, url)` and
  `--refresh-textrazor` latest-wins replace for `endpoint=entities` only.
- **Stored-run backfill** — `tests/unit/test_textrazor_backfill.py` covers
  `load_pages_for_textrazor()` (raw `page_text` authoritative over curated
  `pages`) and the `--stored-run --live-textrazor-only` CLI path with zero
  DataForSEO network calls.
- **Shared raw-response schema contract** — the TextRazor-only CLI tests verify
  `raw_responses/endpoint=entities` rows use `provider=textrazor` and the
  shared `RAW_RESPONSE_SCHEMA`. This is the shared raw-response schema contract.

## Shipped tests — TextRazor signal expansion (slices 27–29 partial)

- **Signal-family registry** — `tests/unit/test_stats_families.py` and
  `test_stats_spec.py` load `signal_families` from `analysis_spec.v1.yaml`,
  preserve panel grain, and derive similarity `backend_order` from the registry.
- **Page-metrics curation** — `tests/unit/test_textrazor_normalization.py`
  covers `normalize_page_metrics()` / `build_textrazor_page_metrics_frame()`.
- **Page-metrics feature mart** — `tests/unit/test_feature_marts.py` materializes
  `textrazor_page_metrics` from curated page metrics.
- **Family-aware stats (slices 29–30 shipped)** —
  `tests/unit/test_stats_family_dispatch.py` covers
  `summarize_spearman_families()` with per-family BH boundaries.
  `tests/unit/test_stats_family_artifacts.py` covers combined `stats_*` output,
  hard-fail family skip path, and underpowered `inference_mode` labeling.
  Similarity golden fixtures shipped (slice 10); TextRazor end-to-end golden
  path remains open (slice 31).
- **TextRazor page-metrics completeness (slice 32 shipped)** —
  `tests/unit/test_textrazor_normalization.py` and `test_feature_marts.py`
  cover `textrazor_page_metrics_complete` and null-not-zero section counts.
- **Small-K inference labeling (slice 33 shipped)** —
  `tests/unit/test_stats_family_artifacts.py` covers `keyword_count` and
  `inference_mode` on single-keyword runs.

## Shipped tests — DataForSEO backlinks (Jul 2026)

- **Backlinks summary endpoint (two-call design)** —
  `tests/unit/test_dataforseo_requests.py` covers
  `build_backlinks_summary_request()` and `build_backlinks_dofollow_summary_request()`
  against `/v3/backlinks/summary/live`, target formatting (page URL vs domain),
  per-variant schema validation (`backlinks` + `referring_domains` vs dofollow-only
  `backlinks`), top-level and task-level `status_code` failures, task `cost`
  logging via `caplog`, and retry on 429/5xx.
- **CLI persistence and stored-run backfill** — `tests/unit/test_cli_run.py`
  covers two summary calls per SERP URL, separate
  `endpoint=backlinks_summary` / `endpoint=backlinks_dofollow_summary` partitions
  (dedupe on `(target_keyword, url, variant)`), partial persistence on mid-loop
  failure via `finally`, resume fetching only missing variants, survival when a
  later provider step fails, stored-run `--live-providers` overlay on offline runs,
  and sticky `--skip-textrazor` on replay.
- **Backlink merge** — `tests/unit/test_raw_response_merge.py` covers
  `merge_backlink_raw_response_rows()` variant-aware dedupe and
  `persist_backlink_raw_responses()` partition rewrite per batch.
- **Curated normalization** — `tests/unit/test_run_normalize.py` covers
  `backlinks` table materialization from paired raw responses (42 / 12 / 35),
  null `dofollow_backlinks_count` when the dofollow variant is absent,
  legacy `endpoint=backlinks` read-compat, hard-fail on malformed summary
  aggregates,   and distribution maps as JSON-string columns.

## Shipped tests — OnPage instant_pages (Phase 7.1 slices 1–6, Jul 2026)

- **OnPage instant_pages endpoint (offline contract)** —
  `tests/unit/test_dataforseo_requests.py` covers
  `build_onpage_instant_pages_request()` against
  `/v3/on_page/instant_pages/live` (JS rendering, resource loading,
  `validate_micromarkup`), schema accept on `fixture_onpage_instant_pages_response()`,
  score and url type-drift rejection, null/missing optional sections
  (`page_timing`, `checks`, `content`, `total_transfer_size`, micromarkup flags),
  sparse items (url + score only), and required-leaf parity cases (missing
  `url` or `onpage_score`).
- **OnPage fetch + persistence (Phase 7.1 slice 3)** —
  `tests/unit/test_cli_run.py` covers `fetch_onpage_signals_for_urls()` against
  `/v3/on_page/instant_pages/live` (one call per URL, request metadata with
  rendering/micromarkup flags), single-partition persistence to
  `endpoint=onpage_instant_pages`, one rewrite per batch, and partial durability
  on mid-loop failure via `finally`.
  `tests/unit/test_raw_response_merge.py` covers
  `persist_onpage_raw_responses()` merge/dedupe on `(target_keyword, url)` without
  touching unrelated partitions.
- **OnPage live-run wiring (Phase 7.1 slice 4)** —
  `tests/unit/test_cli_run.py` covers fresh live runs (`build_live_payload`
  includes `raw_provider_data.dataforseo.onpage_instant_pages` and
  `dataforseo.onpage_instant_pages` in `network_calls`), stored-run live overlay
  when the partition is absent, and resume backfill that fetches only missing SERP
  URLs (`test_build_resumed_keyword_result_fetches_only_missing_onpage_urls`).
- **OnPage stored-run backfill (Phase 7.1 slice 5)** —
  `tests/unit/test_cli_run.py` covers in-place backfill of a single missing
  onpage partition row (`test_run_stored_run_backfills_only_missing_onpage_in_place`),
  no-op replay when the partition is complete
  (`test_run_stored_run_does_not_refetch_onpage_when_partition_complete`), and
  refetch when a stored row is schema-valid but item-less
  (`test_run_stored_run_refetches_empty_onpage_partition_row`; contrast with
  `test_run_stored_run_reuses_successful_empty_backlink_summaries`).
  `tests/unit/test_dataforseo_requests.py` locks
  `onpage_instant_pages_response_is_usable()` rejecting empty payloads.
- **OnPage curated builder (Phase 7.1 slice 6)** —
  `tests/unit/test_run_normalize.py` covers `normalize_run` materializing
  `parquet/onpage_signals` from fixture raw rows
  (`test_normalize_run_materializes_onpage_signals_from_fixture`), sparse items
  with null optional sections
  (`test_normalize_run_onpage_signals_sparse_item_nulls_optional_sections`),
  skipping unusable empty raw rows
  (`test_normalize_run_skips_unusable_onpage_raw_rows`), and
  `build_onpage_signals_frame` dedupe by `(target_keyword, url)` on latest
  `timestamp` with `response_id` tie-break
  (`test_build_onpage_signals_frame_dedupes_by_target_keyword_and_url`).
- **OnPage feature mart (Phase 7.1 slice 7)** —
  `tests/unit/test_feature_marts.py` covers `onpage_features` materialization
  from curated `onpage_signals` left-joined onto the analysis panel
  (`test_build_feature_marts_materializes_lazy_joins_from_curated_tables`),
  null OnPage columns when the raw partition is absent
  (`test_build_feature_marts_onpage_features_null_when_partition_missing`),
  and bounded validation via `ONPAGE_FEATURES_REQUIRED_COLUMNS`
  (`test_build_feature_marts_validates_each_feature_frame_before_sinking`).

## Shipped tests — Phase 6.2 backlinks count analysis (Jul 2026)

- **Feature mart** — `tests/unit/test_feature_marts.py` covers
  `backlinks_analysis` materialization from curated `backlinks`, bounded count
  validation (`BACKLINKS_ANALYSIS_REQUIRED_COLUMNS`), and catalog refresh.
- **Signal family registry** — `tests/unit/test_stats_families.py` and
  `test_stats_spec.py` cover `backlinks_counts` (`backlinks_metric` kind) and
  the three count signal columns.
- **Stats artifacts** — `tests/unit/test_stats_family_artifacts.py` covers
  combined `stats_*` output with `#### Family: backlinks_counts` in
  `stats_report.md` and per-signal Spearman / OLS / diagnostics / PL blocks.
- **Curated null semantics** — `tests/unit/test_run_normalize.py` covers null
  `dofollow_backlinks_count` when the dofollow variant is absent (upstream of
  the analysis mart).
- **Raw partition CLI** — Phase 5.91 tests in `test_cli_run.py` (see § DataForSEO
  backlinks above).

## Shipped tests — Phase 6.1 partial (within-keyword ranks)

- **Within-keyword rank transform (Phase 6.1 Slice 3 partial)** —
  `tests/unit/test_within_keyword_ranks.py` covers Polars-lazy
  `add_within_keyword_similarity_ranks()` in `src/seo_rank/data/ranks.py`: ties,
  `n = 1`, null backend scores, zero variance, and full top-20 panels. Mart
  wiring and `analysis_mart.v2` remain open (Phase 6.1 Slice 4).

## Planned tests (not yet in suite) — Phase 5 active scope

See `GOALS.md` and `ROADMAP.md` § Phase 5 slice 31; standardization and
relative ranks are Phase 6.1.

- Feature marts and `analysis_mart` join keys (`run_id`, `target_keyword_id`,
  `canonical_url_hash`, `response_id`, `passage_id`)
- Passage / domain similarity scopes (feature marts; Phase 5.5 scoring)

### Phase 5 — statistical analysis (see `ROADMAP.md` slices 31+)

- **TextRazor golden fixture** — end-to-end panel with TextRazor families and
  known rank relationships (slice 31; complements slice 10 similarity golden
  fixtures).

## Planned tests (not yet in suite) — Phase 6.1 standardization and reporting

See `ROADMAP.md` § Phase 6.1.

- **Scaling contract** — `test_stats_scaling_contract.py`: OLS and PL report the
  same `similarity_within_keyword_sd` on an identical panel; `stats.scale` export.
- **Analysis mart v2** — `test_analysis_mart_ranks.py`: rank/pct/z columns,
  bounded validation, rank invariants.
- **Relative similarity sensitivity** — `test_stats_relative_similarity.py`:
  Spearman on rank, OLS on z/pct, skip on `analysis_mart.v1`, excluded from
  actionable flag.
- **Plackett-Luce spec runtime** — spec threshold edits change convergence and
  IIA enablement (`test_stats_plackett_luce.py`, `test_stats_spec.py`).
- **CLI relative ranks** — keyword report shows rank/pct; sort by primary backend
  similarity rank.

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
