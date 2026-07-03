# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 5 **statistical analysis** on the `analysis_mart` panel so the CLI
can quantify observational association between page-level similarity scores and
SERP rank, compare backends with a pre-registered estimand, and emit
guardrail-aware `stats_*` artifacts with explicit limitations (no causal claims).

Full product review and estimand defaults: `PHASE5-STATS-PLAN-REVIEW.md`.
Implementation slices and acceptance table: `ROADMAP.md` § Phase 5.
Phase 6 is planned future work for workflow-integrity guardrails and is not
part of the active Phase 5 delivery contract unless explicitly retargeted.

Prior shipped work (Phase 4.77 adapter schema validation, Phase 4.76 structured
`content_parsing/live` capture, the run-scoped Parquet lake, page-level
similarity) is documented in `ROADMAP.md` § History.
Completed: Phase 4.77 is recorded there as shipped work.

### Phase 5 objective

Measure observational association between normalized similarity scores and SERP
rank on the page-level panel (`target_keyword × SERP URL`, top 20 per keyword),
and add a separate TextRazor-derived page-signal mart at the same grain. The
similarity mart stays unchanged; the TextRazor families are additive.
**Primary inference:** keyword-level Spearman ρ per backend with Benjamini–Hochberg
within each backend family when K ≥ 10 keywords. **Secondary inference:** pooled
OLS with keyword fixed effects, length adjustment, and keyword-clustered robust
standard errors. **Pre-registered primary backend:** BGE; Gemini backends are
secondary comparisons in fixed order.

Page-level Plackett-Luce / rank-ordered logit is a secondary add-on on the same
analysis_mart panel. It stays additive to Spearman and pooled OLS. Passage-level
Plackett-Luce is deferred backlog work only and is not wired in code today.

#### Progress

**Slices:** 23 of 33 shipped, 2 partial, 8 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Estimand & analysis spec | Stats | Shipped | `analysis_spec.v1.yaml` |
| 2 | Stats module & dependencies | Stats | Shipped | `src/seo_rank/stats/` + `statsmodels` |
| 3 | Guardrails & panel prep | Stats | Shipped | Hard-fail / warn gates on `analysis_mart` |
| 4 | Spearman primary path | Stats | Shipped | Per-keyword ρ + BH per backend |
| 5 | Pooled regression (secondary) | Stats | Shipped | Keyword FE + clustered SEs |
| 6 | Pooled OLS diagnostics | Stats | Shipped (S5-11 open) | RESET, BP, Cook's D, influence flags |
| 7 | Multivariate sensitivity | Stats | Open | Joint model + VIF drop order |
| 8 | Robustness appendix (influence) | Stats | Open | Refit excluding influential rows |
| 9 | Stats artifacts & CLI | Stats | Partial | `stats_*` wired; `--no-fail-on-guardrails` + `report.md` link open |
| 10 | Golden fixtures & tests | Stats | Open | Synthetic mart + schema contracts |
| 11 | Within-keyword rank transform | Data | Phase 6.1 | `data/ranks.py` rank + pct + z |
| 12 | Analysis mart v2 columns | Data | Phase 6.1 | `analysis_mart.v2` + validation |
| 13 | Relative similarity sensitivity | Stats | Phase 6.1 | Robustness appendix on rank/pct/z |
| 14 | Relative ranks in CLI & fixtures | CLI | Phase 6.1 | Keyword report + golden invariants |
| 15 | Plackett-Luce estimand runtime wiring | Stats | Phase 6.1 (partial) | YAML block + depth `max_rank`; thresholds still hardcoded |
| 16 | Rank-depth spec and panel filtering | Stats | Shipped | `rank_depth.py` + spec `rank_depths` |
| 17 | Per-depth Spearman and pooled OLS | Stats | Shipped | Confirmatory bundles at 20/10/5/3 |
| 18 | Per-depth Plackett-Luce | Stats | Shipped | Primary PL per depth |
| 19 | Rank-depth artifacts and report | Stats | Shipped | `rank_depths` JSON + report sections |
| 20 | Rank-depth fixtures and tests | Stats | Shipped | `test_stats_rank_depth.py` |
| 21 | TextRazor-only flags and gates | CLI | Shipped | `--live-textrazor-only`, `--refresh-textrazor` |
| 22 | TextRazor ingest core | Data | Shipped | `fetch_textrazor_entities_for_pages`, endpoint registry |
| 23 | Raw lake merge for entities | Data | Shipped | `merge_raw_response_records` (keyword+url dedupe) |
| 24 | Stored-run TextRazor backfill | CLI | Shipped | `backfill_textrazor_run` from stored `page_text` |
| 25 | Brand-new TextRazor-only run | CLI | Shipped | `write_textrazor_only_artifacts` + fixture DFS + live TextRazor |
| 26 | TextRazor-only tests and docs | CLI | Shipped | CLI tests and docs; shared raw-response schema contract |
| 27 | TextRazor signal registry and family contract | Stats | Shipped | `signal_families` in spec + `families.py` registry |
| 28 | Materialize TextRazor page metrics | Data | Shipped | `textrazor_page_metrics_curated` + feature mart |
| 29 | Generalize the Phase 5 stats engine | Stats | Shipped | Family-aware Spearman, OLS, diagnostics, PL |
| 30 | Fold families into CLI output and artifacts | Stats | Shipped | Combined `stats_*` tree for all signal families |
| 31 | TextRazor signal golden fixtures and tests | Stats | Open | End-to-end fixture with known rank relationships |
| 32 | TextRazor page-metrics completeness | Data | Shipped | `textrazor_page_metrics_complete` + null-not-zero counts |
| 33 | Small-K exploratory status | Stats | Shipped | `keyword_count` + `inference_mode` in `stats_*` |

**Remaining to close the core similarity delivery:** slices 7–10 (see
`ROADMAP.md`). OLS / Plackett-Luce standardization and relative-rank work (former
Phase 5 slices 11–15) is **Phase 6.1** in `ROADMAP.md`. TextRazor-only ingestion:
slices 21–26 shipped; shared raw-response schema contract (slice 26) is shipped.
TextRazor signal expansion: slices 27–30 and 32–33 shipped; slice 31 (golden fixtures) open.
Slice 6 live E2E: **S5-11** in `FIXUPS.md` (`page_text` `tasks[].result: null`
schema drift).

#### Dev slices

**Progress:** 23 of 33 shipped, 2 partial, 8 open.

1. **[x] Slice 1 — Estimand & analysis spec**
   - Add `analysis_spec.v1.yaml`: outcome (`-log(serp_rank)`), predictors,
     keyword FE, length adjustment, clustering rule, BH family, success
     thresholds, backend drop order for multivariate sensitivity.
   - Lock primary decision (A + B), BGE-first order, warn vs hard-fail table,
     BH-when-K ≥ 10, actionable-association rule, spec versioning vs 5.75.
   - Cross-link `ARCHITECTURE.md`, `ROADMAP.md`, `PHASE5-STATS-PLAN-REVIEW.md`.

2. **[x] Slice 2 — Stats module & dependencies**
   - Add `src/seo_rank/stats/` (`spec.py`, `panel.py`, `spearman.py`,
     `regression.py`, `diagnostics.py`, `bh.py`, `artifacts.py`).
   - Declare `statsmodels` (+ existing `scipy`/`numpy`) in `pyproject.toml`.
   - Load `analysis_spec.v1.yaml` at runtime; expose estimand version in outputs.

3. **[x] Slice 3 — Guardrails & panel prep**
   - Load `runs/{run_id}/parquet/analysis_mart/part-*.parquet`.
   - Grain: `target_keyword_id × canonical_url_hash`; filter `serp_rank` 1–20;
     drop rows with null `bge_normalized_score` for the primary Spearman/regression
     panel (secondary backends may be null on individual rows).
   - Evaluate guardrail table from `analysis_spec.v1.yaml`: hard-fail when
     within-keyword `serp_rank` variance is zero; warn when within-keyword
     similarity variance is zero for any backend. Emit
     `guardrails: {name, status, value, threshold}` in `stats_summary.json`.
   - **Hard-fail behavior:** write guardrails + limitations JSON + minimal
     `stats_report.md`; skip BH, pooled inference, actionable flag.
   - Document duplicate-URL-across-keywords handling (no dedupe in v1; cluster
     on keyword; URL two-way cluster deferred to robustness).

4. **[x] Slice 4 — Spearman primary path**
   - Per `target_keyword_id`, two-sided Spearman ρ(normalized similarity,
     `serp_rank`) for each backend.
   - Summarize ρ across keywords (median, IQR, fraction same-sign).
   - BH at q = 0.05 within each backend family when K ≥ 10; else raw p-values +
     `bh_skipped_reason: underpowered`.
   - Do not BH-adjust diagnostics or regression coefficients.

5. **[x] Slice 5 — Pooled regression (secondary)**
   - Baseline: `-log(serp_rank) ~ log(page_text_length + 1) + C(target_keyword_id)`.
   - Feature: + one `*_normalized_score` at a time (univariate + keyword FE +
     length); separate model per backend.
   - Keyword-clustered robust SEs; never emit naive IID SEs in primary output.
   - **Effect size:** translate coefficient to approximate Δ rank per 1 SD
     similarity (document formula in spec).
   - Descriptive Δ adjusted R² or AIC vs baseline (not BH-adjusted).
   - **Sensitivity (robustness appendix):** refit with two-way cluster
     (keyword × `canonical_url_hash`) when URL repeats exist.

6. **[x] Slice 6 — Pooled OLS diagnostics**
   - On **pooled** feature model per backend only (not per-keyword n ≈ 20).
   - **Run:** residuals vs fitted, RESET, Breusch–Pagan (→ HC3 SEs when
     flagged), Cook's D > 4/n, leverage / studentized residuals / DFFITS /
     DFBETAs for `stats_diagnostics.json`.
   - **Skip as primary gates:** per-keyword normality; pooled Shapiro only in
     diagnostics JSON when n is small (informational, not confirmatory).
   - **Skip for v1 primary path:** LOWESS / CCPR plot files (flags only unless
     debug mode); diagnostic-driven spec changes stay out of confirmatory path.
   - **[ ] S5-11 — Live `page_text` null `result`:** DataForSEO returns
     `tasks[].result: null` on failed crawls; top-level schema validation raises
     `expected list, got NoneType` and aborts `seo-rank run --live-providers`.
     Accept or skip null `result`, align `DATAFORSEO_RESPONSE_SCHEMAS` with
     `_validate_content_parsing_response`, add unit + CLI tests. Repro:
     `seo-rank run --seed "seo company columbus" --live-providers --live-gemini
     --live-bge`. Tracked in `FIXUPS.md` **S5-11**.

7. **[ ] Slice 7 — Multivariate sensitivity**
   - Joint model: all three `*_normalized_score` + length + keyword FE.
   - Compute VIF; if any VIF > 5, drop backends in spec order (semantic
     similarity → doc retrieval → keep BGE last).
   - Write multivariate coefficients, VIF table, and drop log to
     `stats_diagnostics.json` / robustness section of `stats_report.md`.
   - Not used for actionable flag or BH.

8. **[ ] Slice 8 — Robustness appendix (influence)**
   - For each backend pooled feature model: refit excluding rows with Cook's D >
     4/n; optional WLS/RLM noted in appendix only.
   - Compare confirmatory vs sensitivity coefficients in
     `stats_diagnostics.json` (`influence_sensitivity` block).
   - Wire `influential_rows_rate` warn guardrail from pooled influence counts
     (spec threshold 5%; deferred from Slice 6).

9. **[~] Slice 9 — Stats artifacts & CLI**
   - **Done:** `stats_summary.json`, `stats_diagnostics.json`, `stats_report.md`
     with nested `rank_depths`; `seo-rank analyze` and `materialize_run_tree`
     call `run_phase5_stats()`; exit `1` on guardrail hard-fail; dry-run /
     fixture runs skip stats via `run_manifest_is_dry_run()`.
   - **Remaining:** `--no-fail-on-guardrails`; link from `report.md` to
     `stats/stats_report.md`.

10. **[ ] Slice 10 — Golden fixtures & tests**
    - Synthetic `analysis_mart` with known ρ and pooled slope per backend.
    - Schema contract for `stats_summary.json` / `stats_diagnostics.json`.
    - Tests: BH family boundaries, BH skipped when K < 10, hard-fail skip path,
      actionable flag logic, influence refit delta, multivariate VIF drop order,
      clustered vs IID SE guard; see `TESTING.md`.

11. **[ ] Slice 11 — Within-keyword rank transform**
    - Add `src/seo_rank/data/ranks.py` with
      `add_within_keyword_similarity_ranks()` (Polars lazy).
    - Per backend, derive from absolute scores within each `target_keyword_id`:
      `{backend}_similarity_rank` (1 = highest; average rank on ties),
      `{backend}_similarity_pct` (`(rank - 1) / (n - 1)` when `n > 1`; else
      `null`), `{backend}_similarity_z` (within-keyword z-score; `null` when
      `n < 2` or `σ = 0`).
    - **Ranking source:** BGE on `bge_raw_score`; Gemini backends on
      `*_normalized_score`.
    - Unit tests: ties, `n = 1`, full top-20 panel, descending order, null
      when backend score is null (`tests/unit/test_within_keyword_ranks.py`).

12. **[ ] Slice 12 — Analysis mart v2 columns**
    - Wire rank transform in `marts.py` after `keyword_serp` ⨝ `page_features`
      join; bump `schema_version` to `analysis_mart.v2`.
    - Extend `FEATURE_VALIDATION_RULES`, `ANALYSIS_REQUIRED_COLUMNS`, bounded
      columns (`similarity_rank` 1–20, `similarity_pct` 0–1).
    - Nine new columns per run (3 backends × rank/pct/z); absolute score
      columns unchanged.
    - Tests: mart integration (`test_analysis_mart_ranks.py`), round-trip
      extension in `test_round_trip.py`.
    - Update `ARCHITECTURE.md` mart column list and BGE scoring note (sigmoid per
      page today; relative ranks are mart-derived).

13. **[ ] Slice 13 — Relative similarity stats sensitivity**
    - Extend `analysis_spec.v1.yaml` `sensitivity.relative_similarity` block:
      rank/pct/z column names per backend; robustness-only (not primary
      estimand).
    - **Primary estimand unchanged:** absolute `*_normalized_score` + Spearman ρ.
    - **Robustness appendix:** (a) Spearman ρ on `*_similarity_rank` as sanity
      check vs absolute path; (b) pooled OLS refits with `*_similarity_z` and
      `*_similarity_pct` per backend (keyword FE + length + clustered SEs).
    - Add limitation text: relative ranks are within observed top-20 SERP rows
      only, not vs the full web.
    - Write sensitivity coefficients to `stats_diagnostics.json`
      (`relative_similarity_sensitivity` block); not used for actionable flag
      or BH.

14. **[ ] Slice 14 — Relative ranks in CLI & fixtures**
    - `emit_keyword_analysis` / `report.md`: show `rank/pct` (and optional `z`)
      alongside absolute scores; sort Page Similarity by
      `{primary_backend}_similarity_rank`.
    - Extend Slice 10 golden `analysis_mart` with relative columns and known
      rank invariants (e.g. highest absolute score → rank 1).
    - Acceptance: rebuild `analysis_mart` on stored runs derives relative
      columns from stored absolutes without re-scoring.

15. **[~] Slice 15 — Plackett-Luce estimand runtime wiring**
    - **Done**
      - `analysis_spec.v1.yaml` `estimand.plackett_luce` block (outcome,
        formula, clustered_se, choice_set_scope, `iia_sensitivity`).
      - `test_load_analysis_spec_includes_plackett_luce_secondary_estimand`
        validates the committed YAML shape.
      - `artifacts.py` passes `max_rank=spec.rank_depth_limit(depth_key)` per
        confirmatory depth (aligned with slices 16–18).
      - Page-level PL fit, diagnostics, leave-one-out IIA, and artifact
        emission in `test_stats_plackett_luce.py`.
    - **Remaining**
      - Add convergence thresholds and IIA cutoffs to the YAML estimand block
        (today only `leave_one_out_top_rank: true` is specified).
      - `AnalysisSpec` accessor / typed loader for `estimand.plackett_luce`
        settings.
      - Replace hardcoded constants in `plackett_luce.py` (`FORMULA`,
        `DEFAULT_MAX_SERP_RANK`, `HESSIAN_CONDITION_NUMBER_THRESHOLD`,
        `OPTIMIZER_GRADIENT_TOLERANCE`) with spec-driven values.
      - Drive IIA enablement from `estimand.plackett_luce.iia_sensitivity`
        instead of `depth_key == spec.primary_rank_depth` in `artifacts.py`.
      - Tests: spec-driven threshold loader and regression coverage that spec
        edits change runtime estimator settings.

16. **[x] Slice 16 — Rank-depth spec and panel filtering**
    - Add `rank_depths` and `limitations_by_depth` to `analysis_spec.v1.yaml`.
    - Add `src/seo_rank/stats/rank_depth.py` with `filter_panel_by_max_rank()`.
    - Extend `AnalysisSpec` accessors and per-depth limitation text in
      `panel.py`.

17. **[x] Slice 17 — Per-depth Spearman and pooled OLS**
    - Run confirmatory Spearman and pooled regression at ranks 1–20, 1–10,
      1–5, and 1–3 with independent guardrails and `actionable_association`.

18. **[x] Slice 18 — Per-depth Plackett-Luce**
    - Primary PL fit per depth (not IIA subset refit from top-20).
    - Retire top-10 IIA report section; keep leave-one-out on `top_20` only.

19. **[x] Slice 19 — Rank-depth artifacts and report**
    - Nest outputs under `stats_summary.json` → `rank_depths`.
    - Emit four `## Rank depth:` sections in `stats_report.md`.
    - Top-level compat shim mirrors `rank_depths.top_20`.

20. **[x] Slice 20 — Rank-depth fixtures and tests**
    - `tests/unit/test_stats_rank_depth.py` with depth-divergent fixture.
    - Acceptance: monotonic row counts, per-depth actionable map, PL choice-set
      bounds; see `TESTING.md`.

21. **[x] Slice 21 — TextRazor-only flags and gates**
    - Add `--live-textrazor-only` and `--refresh-textrazor` to `seo-rank run`.
    - Mutual exclusion: cannot combine with `--live-providers` or `--skip-textrazor`.
    - Env gate: `SEO_RANK_ENABLE_TEXTRAZOR=1` + `TEXTRAZOR_API_KEY` only (no
      `SEO_RANK_ENABLE_LIVE_PROVIDERS`).
    - `prepare_textrazor_only_context(env)` returns `TextRazorCredentials` without
      validating DataForSEO credentials.
    - Persist `live_textrazor_only` and `refresh_textrazor` in `run.json` config.
    - Without `--stored-run`, `main()` calls `write_textrazor_only_artifacts()`
      (slice 25). With `--stored-run`, `replay_stored_run()` calls
      `backfill_textrazor_run()` (slice 24).

22. **[x] Slice 22 — TextRazor ingest core**
    - Add `TEXTRAZOR_ENDPOINTS` registry in `src/seo_rank/textrazor.py` (`entities`
      now; future extractors get their own `raw_responses` endpoint partitions).
    - `fetch_textrazor_entities_for_pages()` wraps `build_entity_request` +
      `execute_textrazor_request`; `pages_missing_textrazor()` dedupe helper.
    - Unit tests with injected transport (no network).

23. **[x] Slice 23 — Raw lake merge for entities**
    - `merge_raw_response_records(run_dir, new_records, *, endpoint, refresh)`.
    - Dedupe key for `endpoint=entities`: `(target_keyword, url)`; default skip
      existing; `--refresh-textrazor` latest-wins replace.
    - Rewrite only the `entities` partition; leave `keyword_expansion`, `serp`,
      and `page_text` untouched; recompute catalog checksums.
    - Tests: `tests/unit/test_raw_response_merge.py`.

24. **[x] Slice 24 — Stored-run TextRazor backfill**
    - `load_pages_for_textrazor(run_dir, target_keyword)` from authoritative
      `raw_responses` `endpoint=page_text` (fallback: curated `pages`).
    - `backfill_textrazor_run()` for `--stored-run … --live-textrazor-only`; no
      `build_live_keyword_result` / no DataForSEO HTTP.
    - Merge entities into raw lake; refresh `textrazor_entities` in `run.json`;
      `materialize_run_tree(..., respect_dry_run=False)`.
    - Covered by `tests/unit/test_textrazor_backfill.py`.

25. **[x] Slice 25 — Brand-new TextRazor-only run**
    - `write_textrazor_only_artifacts()` / `build_textrazor_only_payload()`:
      fixture keyword expansion, SERP, and `page_text`; live TextRazor on parsed
      pages; fixture similarity scoring.
    - Wired in `main()` when `--live-textrazor-only` without `--stored-run`.
    - `network_calls` records `textrazor.entities` only (no `dataforseo.*`).
    - Covered by `tests/unit/test_cli_run.py` (dedicated writer dispatch + end-to-end
      fixture/live TextRazor path).

26. **[x] Slice 26 — TextRazor-only tests and docs**
    - **Done:** stored-run backfill (`test_textrazor_backfill.py`); CLI flag/gate
      and brand-new textrazor-only run tests (`test_cli_run.py`).
    - **Remaining:** optional TextRazor connectivity probe.

27. **[x] Slice 27 — TextRazor signal registry and family contract**
    - Signal-family registry at `target_keyword × SERP URL` grain (see
      `ROADMAP.md` slice 27 for full contract).
    - **Depends on slices 24–26** for live entity ingestion without DataForSEO.

28. **[x] Slice 28 — Materialize TextRazor page metrics**
    - `build_textrazor_page_metrics_frame()` in `normalize.py`; curated table
      `textrazor_page_metrics_curated` (one row per `target_keyword × SERP URL`).
    - Feature mart `textrazor_page_metrics` in `features.py`; join keys match
      `analysis_mart` (`run_id`, `target_keyword_id`, `canonical_url_hash`).
    - TextRazor requests use the full page-metrics extractor set
      (`entities`, `topics`, `categories`, `entailments`, `words`, `relations`,
      `properties`, `nounPhrases`); raw bodies still land in
      `raw_responses/endpoint=entities`.
    - Covered by `tests/unit/test_textrazor_normalization.py` and
      `tests/unit/test_feature_marts.py`.

29. **[x] Slice 29 — Generalize the Phase 5 stats engine**
    - Family-aware Spearman, pooled OLS, diagnostics, and Plackett-Luce per
      registered signal family; BH scoped per family.
    - Covered by `tests/unit/test_stats_family_dispatch.py` and
      `tests/unit/test_stats_family_artifacts.py`.

30. **[x] Slice 30 — Fold families into CLI output and artifacts**
    - Combined `stats_summary.json`, `stats_diagnostics.json`, and
      `stats_report.md` tree with nested `rank_depths.*.families` for similarity
      and TextRazor families; top-level similarity blocks kept for compatibility.
    - Hard-fail still skips confirmatory inference but writes family blocks as
      `skipped`.
    - Covered by `tests/unit/test_stats_family_artifacts.py`.

31. **[ ] Slice 31 — TextRazor signal golden fixtures and tests**
    - End-to-end fixture proving similarity results unchanged when TextRazor
      families are added.

32. **[x] Slice 32 — TextRazor page-metrics completeness**
    - `textrazor.py` tracks per-section presence; missing extractors yield
      `null` counts, not silent zeros.
    - `textrazor_page_metrics_complete` on curated and feature marts records
      whether all page-metrics sections were present in the upstream response.
    - Covered by `tests/unit/test_textrazor_normalization.py` and
      `tests/unit/test_feature_marts.py`.

33. **[x] Slice 33 — Small-K exploratory status**
    - `stats_*` artifacts surface `keyword_count` and `inference_mode` per rank
      depth and backend (`confirmatory` when K ≥ 10, `exploratory` when 2 ≤ K < 10,
      `underpowered` when K = 1).
    - Report wording suppresses confirmatory language on underpowered runs.
    - Covered by `tests/unit/test_stats_family_artifacts.py`.                          

#### Phase 5 intent

- **Estimand lock** — ship `analysis_spec.v1.yaml` (outcome `-log(serp_rank)`,
  predictors, keyword FE, clustering, BH family, actionable-association
  thresholds, backend drop order). Version separately from Phase 5.75.
- **Guardrails first** — hard-fail skips confirmatory inference; warn surfaces in
  JSON; CLI exit 1 on hard-fail unless `--no-fail-on-guardrails`.
- **Spearman-first** — per-keyword ρ as headline; BH only when K ≥ 10; never BH-adjust
  diagnostic p-values.
- **Pooled regression secondary** — one backend per model; keyword-clustered SEs
  only in primary output; effect-size translation and `actionable_association`
  rule on BGE.
- **Limitations in JSON** — observational, depth-specific truncation (top 20 / 10 /
  5 / 3), measurement-error conservatism, no causal claims per rank depth in
  `stats_summary.json` and `stats_report.md`.
- **Tests** — golden `analysis_mart`, schema contracts, guardrail skip path,
  BH boundaries, influence refit per `TESTING.md`.
- **Relative similarity (Phase 6.1)** — within-keyword rank, percentile, and
  z-score per backend in `analysis_mart.v2`; robustness-only stats path; CLI
  surfaces ranks alongside absolute scores. Primary confirmatory estimand stays
  on absolute `*_normalized_score`.

## In Scope (current and near-term)

- `analysis_spec.v1.yaml` and runtime spec loader.
- `src/seo_rank/stats/` package (`spec`, `families`, `panel`, `rank_depth`,
  `spearman`, `regression`, `diagnostics`, `bh`, `artifacts`, `plackett_luce`).
- TextRazor page-signal curation and feature mart (`textrazor_page_metrics_curated`,
  `textrazor_page_metrics`) at `target_keyword × SERP URL` grain; similarity
  `analysis_mart` unchanged.
- Parallel confirmatory rank depths (`top_20`, `top_10`, `top_5`, `top_3`) with
  per-depth guardrails, Spearman, pooled OLS, Plackett-Luce, and
  `actionable_association_by_rank_depth` in `stats_summary.json`.
- `statsmodels` dependency in `pyproject.toml` (plus existing `scipy` / `numpy`).
- Guardrail evaluation on `runs/{run_id}/parquet/analysis_mart/`.
- Spearman + BH, pooled OLS, diagnostics, multivariate sensitivity, influence
  robustness appendix.
- `stats_summary.json`, `stats_diagnostics.json`, `stats_report.md` under
  `runs/{run_id}/stats/`.
- `seo-rank analyze --run RUN_ID` materialization and exit-code contract.
- Unit tests and golden fixtures in `tests/unit/`.
- Within-keyword relative similarity: `*_similarity_rank`, `*_similarity_pct`,
  `*_similarity_z` in `analysis_mart.v2` (`src/seo_rank/data/ranks.py`) — **Phase 6.1**.
- Stats robustness appendix for relative predictors — **Phase 6.1** (Slice 13).
- OLS / PL scaling polish and PL spec runtime wiring — **Phase 6.1** (FIXUPS
  S5-14–S5-19; `ROADMAP.md` § Phase 6.1).
- TextRazor-only ingestion (slices 21–26 shipped): CLI flags/gates, ingest core,
  raw-lake entity merge, stored-run backfill, brand-new `--live-textrazor-only`
  runs (fixture DataForSEO structure + live TextRazor, zero `dataforseo.*` in
  `network_calls`), and the shared raw-response schema contract.
- Family-aware confirmatory stats across similarity and TextRazor signal
  families in `stats_*` artifacts (slices 29–30 shipped); golden fixtures
  (slice 31) open.
- TextRazor page-metrics completeness flag (`textrazor_page_metrics_complete`;
  slice 32 shipped).
- Small-K inference labeling (`keyword_count`, `inference_mode`; slice 33 shipped).

## Out Of Scope

- Passage-level similarity scoring (Phase 5.5).
- Domain-level URL inventory scoring (Phase 5.5).
- Phase 5.75 BGE hybrid / retrieve-then-rerank pipeline (separate spec v2).
- Phase 5.1 DataForSEO live fail-fast (`ROADMAP.md` § 5.1).
- Phase 5.2 Gemini/BGE empty-output fail-fast (`ROADMAP.md` § 5.2).
- Phase 5.4 exploratory extensions (rank-decile segments, keyword holdout).
- Expanded report sections and OLS/PL standardization (`ROADMAP.md` § Phase 6.1).
- Custom URL/text manifest ingestion for TextRazor-only runs (no fixture SERP).
- Direct page fetching outside DataForSEO (TextRazor receives parsed text only).
- Causal claims about ranking factors.
- IV / `PanelOLS`, URL fixed effects, per-keyword OLS as primary inference.
- CI, deployment, production hosting.
- Parquet `Variant` type for semi-structured provider payloads.

## Phase 5 acceptance criteria

**Status:** 23 of 33 slices shipped, 2 partial, 8 open.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `analysis_spec.v1.yaml` loaded; estimand version in outputs | 1, 2 | Shipped |
| Guardrail hard-fail skips inference; warn surfaces in JSON | 3, 9, 16–20 | Shipped (per depth) |
| Spearman + BH per backend when K ≥ 10 | 4, 17 | Shipped (per depth) |
| Pooled regression with keyword-clustered SEs only in primary output | 5, 17 | Shipped (per depth) |
| Effect-size translation + `actionable_association` rule | 5, 9, 17 | Shipped (per depth) |
| Pooled diagnostics + influence % in diagnostics JSON | 6, 8, 17 | Shipped (per depth; influence guardrail Slice 8 open) |
| `page_text` accepts `tasks[].result: null`; live run continues (S5-11) | 6 | Open |
| Multivariate sensitivity with VIF drop order | 7 | Open |
| Limitations in JSON and Markdown | 9, 19 | Shipped (per depth) |
| `seo-rank analyze` exit code + dry-run skip | 9 | Partial (`--no-fail-on-guardrails` open) |
| Golden fixture ρ/slope within tolerance | 10 | Open |
| Within-keyword rank/pct/z columns in `analysis_mart.v2` | 11, 12 | Phase 6.1 |
| Relative similarity robustness in `stats_diagnostics.json` | 13 | Phase 6.1 |
| CLI keyword report surfaces relative ranks | 14 | Phase 6.1 |
| Plackett-Luce estimand runtime wiring from YAML | 15 | Phase 6.1 (partial) |
| OLS/PL shared `within_keyword_sd_rms` effect-size contract | 6.1 Slice 1 | Phase 6.1 |
| Parallel confirmatory rank depths (20/10/5/3) | 16–20 | Shipped |
| `actionable_association_by_rank_depth` in summary JSON | 19 | Shipped |
| `rank_depths` nested JSON + four `## Rank depth:` report sections | 19 | Shipped |
| TextRazor-only CLI flags, gates, and `run.json` config persistence | 21 | Shipped |
| `merge_raw_response_records` entities dedupe + partition rewrite | 23 | Shipped |
| Stored-run backfill writes `endpoint=entities` without touching DFS partitions | 24 | Shipped |
| `--live-textrazor-only` brand-new run (fixture DFS + live TextRazor, zero `dataforseo.*` in `network_calls`) | 25 | Shipped |
| `parquet/entities/` populated after textrazor-only ingest + normalize | 21–25 | Shipped |
| TextRazor cross-doc schema contract | 26 | Shipped |
| TextRazor signal registry and page-metrics mart | 27, 28 | Shipped |
| Family-aware Spearman, OLS, diagnostics, and PL per signal family | 29 | Shipped |
| Combined `stats_*` artifact tree for all signal families | 30 | Shipped |
| `textrazor_page_metrics_complete` on curated and feature marts | 32 | Shipped |
| `keyword_count` and `inference_mode` on underpowered runs | 33 | Shipped |
| Similarity + TextRazor golden fixtures and CLI tests | 31 | Open |

---

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
