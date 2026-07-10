# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 5 **statistical analysis** on the `analysis_mart` panel so the CLI
can quantify how observed page variables relate to SERP rank, compare backends
with a pre-registered estimand, and emit guardrail-aware `stats_*` artifacts
with explicit limitations (no causal claims).

Full product review and estimand defaults: `PHASE5-STATS-PLAN-REVIEW.md`.
Implementation slices and acceptance table: `ROADMAP.md` § Phase 5.
Phase 6 is planned future work for workflow-integrity guardrails and is not
part of the active Phase 5 delivery contract unless explicitly retargeted.

Prior shipped work (Phase 4.77 adapter schema validation, Phase 4.76 structured
`content_parsing/live` capture, the run-scoped Parquet lake, page-level
similarity) is documented in `ROADMAP.md` § History.
Completed: Phase 4.77 is recorded there as shipped work.

### Phase 5 objective

Measure observational relationships between observed page variables and SERP
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

**Slices:** 27 of 42 shipped, 2 partial, 13 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Estimand & analysis spec | Stats | Shipped | `analysis_spec.v1.yaml` |
| 2 | Stats module & dependencies | Stats | Shipped | `src/seo_rank/stats/` + `statsmodels` |
| 3 | Guardrails & panel prep | Stats | Shipped | Hard-fail / warn gates on `analysis_mart` |
| 4 | Spearman primary path | Stats | Shipped | Per-keyword ρ + BH per backend |
| 5 | Pooled regression (secondary) | Stats | Shipped | Keyword FE + clustered SEs |
| 6 | Pooled OLS diagnostics | Stats | Shipped (S5-11 open) | RESET, BP, Cook's D, influence flags |
| 7 | Multivariate sensitivity | Stats | Shipped | Joint model + VIF drop order |
| 8 | Robustness appendix (influence) | Stats | Shipped | `influence_sensitivity` + influential-rows guardrail |
| 9 | Stats artifacts & CLI | Stats | Shipped | `stats_*` wired; `seo-rank analyze` exit contract |
| 10 | Golden fixtures & tests | Stats | Shipped | `test_stats_golden_fixtures.py` schema + boundary contracts |
| 11 | Within-keyword rank transform | Data | Phase 6.1 (partial) | `data/ranks.py` rank + pct + z |
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
| 34 | Signal factor dossier (Phase 5.6) | Stats | Open | See ROADMAP § Phase 5.6 (6 slices incl. entity density Slice 0) |
| 35 | Word/sense/spelling parse fix (Phase 5.7) | Data | Open | Real `sentences[].words` metrics |
| 36 | Entity salience aggregates (Phase 5.7) | Data | Open | Mean/top-k/mention salience on page mart |
| 37 | Topic & category label features (Phase 5.7) | Data | Open | Top labels + IAB classifier on main run |
| 38 | Structured relation/property/phrase features (Phase 5.7) | Data | Open | Labels and top phrases beyond counts |
| 39 | dependency-trees syntactic features (Phase 5.7) | Data | Open | New extractor + complexity scalars |
| 40 | Entity KB linkage enrichment (Phase 5.7) | Data | Open | Wikidata/types + linkage richness |
| 41 | Signal registry for new families (Phase 5.7) | Stats | Open | `analysis_spec` families + validation |
| 42 | Salience explainability & golden fixtures (Phase 5.7) | Stats | Open | Curated models + slice 31 golden path |

**Remaining to close the core Phase 5 delivery:** slice 31 (TextRazor golden
fixtures; see `ROADMAP.md`). OLS / Plackett-Luce standardization and relative-rank work (former
Phase 5 slices 11–15) is **Phase 6.1** in `ROADMAP.md`. TextRazor-only ingestion:
slices 21–26 shipped; shared raw-response schema contract (slice 26) is shipped.
TextRazor signal expansion: slices 27–30 and 32–33 shipped; slice 31 (golden fixtures) open.
Backlinks count analysis: **Phase 6.2** shipped (`backlinks_analysis` mart +
`backlinks_counts` family in `stats_*`).
OnPage page signals: **Phase 7.1** slices **1–18 shipped** (`onpage_instant_pages`
→ `onpage_signals` (46 `checks` booleans; 18 `meta` metrics) → `onpage_features` → three
`onpage_metric` families with
full Spearman / OLS / diagnostics / Plackett-Luce in `stats_*`; Slice 18 stored-run
regression + full-layer CLI pipeline tests). See `ROADMAP.md` § 7.1 and `TESTING.md` § OnPage instant_pages.
Signal proxy / factor diagnostics: **Phase 5.6** (slice 34 tracker). Precursor:
`analysis/textrazor_ranking_r2.py` (similarity + TextRazor adjusted R²,
curated multivariate model, PNG charts via `ranking_explainability_viz.py`).
TextRazor structured signals & salience depth: **Phase 5.7** (slices 35–42).
See `ROADMAP.md` § Phase 5.7 for the gap analysis against
[TextRazor REST docs](https://www.textrazor.com/docs/rest) (`relevanceScore` =
entity salience).
Slice 6 live E2E: **S5-11** in `FIXUPS.md` (`page_text` `tasks[].result: null`
schema drift).

#### Dev slices

**Progress:** 27 of 42 shipped, 2 partial, 13 open.

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
   - Baseline: `-log(serp_rank) ~ log(deprecated_html_tags + 1) + log(time_to_first_byte_ms + 1) + C(target_keyword_id)`.
   - Feature: + one `*_normalized_score` at a time (univariate + keyword FE +
     both adjustment controls); separate model per backend.
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

7. **[x] Slice 7 — Multivariate sensitivity**
   - Joint model: all three `*_normalized_score` + length + keyword FE.
   - Compute VIF; if any VIF > 5, drop backends in spec order (semantic
     similarity → doc retrieval → keep BGE last).
   - Write multivariate coefficients, VIF table, and drop log to
     `stats_diagnostics.json` / robustness section of `stats_report.md`.
   - Not used for actionable flag or BH.

8. **[x] Slice 8 — Robustness appendix (influence)**
   - For each backend pooled feature model: refit excluding rows with Cook's D >
     4/n; optional WLS/RLM noted in appendix only.
   - Compare confirmatory vs sensitivity coefficients in
     `stats_diagnostics.json` (`influence_sensitivity` block).
   - Wire `influential_rows_rate` warn guardrail from pooled influence counts
     (spec threshold 5%; deferred from Slice 6).
   - Covered by `tests/unit/test_stats_diagnostics.py` and
     `tests/unit/test_stats_golden_fixtures.py`.

9. **[x] Slice 9 — Stats artifacts & CLI**
   - **Done:** `stats_summary.json`, `stats_diagnostics.json`, `stats_report.md`
     with nested `rank_depths`; `seo-rank analyze` and `materialize_run_tree`
     call `run_phase5_stats()`; exit `1` on guardrail hard-fail; dry-run /
     fixture runs skip stats via `run_manifest_is_dry_run()`.

10. **[x] Slice 10 — Golden fixtures & tests**
    - Synthetic `analysis_mart` with known ρ and pooled slope per backend.
    - Schema contract for `stats_summary.json` / `stats_diagnostics.json`.
    - Tests: BH family boundaries, BH skipped when K < 10, hard-fail skip path,
      actionable flag logic, influence refit delta, multivariate VIF drop order,
      clustered vs IID SE guard; see `TESTING.md`.
    - Covered by `tests/unit/test_stats_golden_fixtures.py`.

11. **[~] Slice 11 — Within-keyword rank transform**
    - **Done**
      - `src/seo_rank/data/ranks.py` with Polars-lazy
        `add_within_keyword_similarity_ranks()` (rank, pct, z per backend).
      - Unit tests: ties, `n = 1`, full top-20 panel, null scores
        (`tests/unit/test_within_keyword_ranks.py`).
    - **Remaining**
      - Wire into `marts.py` and `analysis_mart.v2` (Slice 12).

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

14. **[x] Slice 14 — Relative ranks in CLI & fixtures**
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
      - Replace hardcoded constants in `plackett_luce.py`
        (`DEFAULT_MAX_SERP_RANK`, `HESSIAN_CONDITION_NUMBER_THRESHOLD`,
        `OPTIMIZER_GRADIENT_TOLERANCE`) with spec-driven values and keep the
        reported formula aligned to the fitted score column.
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

34. **[ ] Slice 34 — Signal factor dossier (Phase 5.6 tracker)**
    - Umbrella tracker; full specification in `ROADMAP.md` § Phase 5.6.
    - Precursor: `analysis/textrazor_ranking_r2.py` +
      `src/seo_rank/stats/textrazor_explainability.py` +
      `ranking_explainability_viz.py`.

35. **[ ] Slice 35 — Word/sense/spelling parse fix (Phase 5.7)**
    - Parse tokens from `response.sentences[].words`, not a top-level `words`
      array or fixture-only `isGrammar` / `isSense` / `isSpelling` flags.
    - Materialize real `senses` scores and `spellingSuggestions` counts into
      `textrazor_page_metrics` (replace or supersede current word-quality counts).
    - Live-shaped fixture JSON + `tests/unit/test_textrazor_normalization.py`.

36. **[ ] Slice 36 — Entity salience aggregates (Phase 5.7)**
    - Aggregate `relevanceScore` from `parquet/entities/` per page:
      mean, median, top-k max, mention-weighted salience, unique-entity count.
    - Join salience columns onto `textrazor_page_metrics` at
      `target_keyword × canonical_url_hash` (similarity mart unchanged).
    - Optional: keyword–top-entity overlap feature (exploratory).

37. **[ ] Slice 37 — Topic & category label features (Phase 5.7)**
    - Persist top topic `label` + `score` and top category `label` +
      `classifierId` (not only `max(score)`).
    - Add `textrazor_iab_content_taxonomy_3.0` to the main run classifier list
      alongside `textrazor_mediatopics_2023Q1`.
    - Curated columns + validation bounds on scores.

38. **[ ] Slice 38 — Structured relation/property/phrase features (Phase 5.7)**
    - Beyond relation/property/noun-phrase **counts**: top noun-phrase texts,
      relation predicate/param labels where `words` offsets resolve, property
      names, entailment `priorScore` / `contextScore` usage in curated models.
    - Reconstruct phrase text via `sentences[].words` + `nounPhrases.wordPositions`.

39. **[ ] Slice 39 — dependency-trees syntactic features (Phase 5.7)**
    - Add `dependency-trees` to `TEXTRAZOR_PAGE_METRIC_EXTRACTORS`.
    - Parse `parentPosition`, `relationToParent`, `partOfSpeech`; emit page-level
      syntactic complexity scalars (depth, dependency-type diversity).
    - Document extractor cost in `ARCHITECTURE.md`.

40. **[ ] Slice 40 — Entity KB linkage enrichment (Phase 5.7)**
    - Extend `normalize_entities()` / `entities` curated: `entityEnglishId`,
      `wikidataId`, `wikiLink`, `freebaseTypes`, optional enriched `data` keys.
    - Page-level linkage richness (linked fraction, type entropy) joined to
      `textrazor_page_metrics`.

41. **[ ] Slice 41 — Signal registry for new families (Phase 5.7)**
    - Register new columns in `analysis_spec.v1.yaml` `signal_families` (or
      document `analysis_spec.v2.yaml` extension if grain changes).
    - Wire Phase 5 family dispatch, feature-mart validation, and `stats_*`
      family blocks for salience and structured TextRazor families.

42. **[ ] Slice 42 — Salience explainability & golden fixtures (Phase 5.7)**
    - Extend `textrazor_explainability.py` and `analysis/textrazor_ranking_r2.py`
      with salience aggregates and topic/category candidates in curated models.
    - End-to-end golden fixture (complements slice 31) with known rank
      relationships for new TextRazor columns.

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
- **Robustness appendix (slices 7–8 shipped)** — primary-depth multivariate VIF
  sensitivity with spec-driven backend drop order; influence refit excluding
  Cook's D > 4/n rows with `influence_sensitivity` coefficient comparison; not
  used for BH or actionable flag.
- **Stats artifacts (slice 9 shipped)** — `stats_summary.json`,
  `stats_diagnostics.json`, and `stats_report.md` under `runs/{run_id}/stats/`;
  wired through `seo-rank analyze` and post-run `materialize_run_tree()`; exit
  `1` on guardrail hard-fail; dry-run skip.
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
  `*_similarity_z` via `src/seo_rank/data/ranks.py` (transform shipped; mart
  columns in `analysis_mart.v2` — **Phase 6.1** Slice 12).
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
- Signal factor & proxy diagnostics — **Phase 5.6** (slice 34 tracker). Includes
  **entity density** metrics (mention/unique counts, word- and char-normalized
  densities) as dossier candidates with explicit proxy tests vs length and BGE.
  Precursor: `analysis/textrazor_ranking_r2.py` +
  `src/seo_rank/stats/textrazor_explainability.py` +
  `ranking_explainability_viz.py` (exploratory adjusted R² + curated-model charts).
- TextRazor structured signals & entity salience (`relevanceScore`) — **Phase 5.7**
  (slices 35–42). Full gap analysis and slices: `ROADMAP.md` § Phase 5.7.
- Backlinks count signals on `backlinks_analysis` — **Phase 6.2** shipped
  (`backlinks_counts` family in `stats_*`; `analysis_mart.v1` unchanged).
- OnPage instant_pages pipeline — **Phase 7.1** slices 1–14 shipped: raw
  `endpoint=onpage_instant_pages`, curated `onpage_signals` (46 `checks`
  booleans; 18 `meta` metrics), feature mart `onpage_features`, three `onpage_metric` families
  (`onpage_content_quality`, `onpage_core_web_vitals`, `onpage_technical_checks`)
  with full family stats in `stats_*`; `ensure_feature_marts_for_analysis()`
  rebuilds missing `onpage_features` on legacy run trees before analyze /
  `run_phase5_stats`.
- Phase 5 slice 33 follow-up: streaming TextRazor persistence
  - Flush each pulled TextRazor entity/section to disk as it arrives instead of
    buffering the full run in memory.
  - Keep curated normalization and feature-mart materialization as a downstream
    end-of-run step.
  - Use deterministic per-response writes so `--refresh-textrazor` and stored-run
    re-materialization rewrite the same raw partitions cleanly.

## Out Of Scope

- Passage-level similarity scoring (Phase 5.5).
- Domain-level URL inventory scoring (Phase 5.5).
- Phase 5.75 BGE hybrid / retrieve-then-rerank pipeline (separate spec v2).
- Phase 5.7 TextRazor request tuning (`cleanup.mode`, custom dictionaries,
  Prolog `rules`, `url` fetch mode) — deferred unless a slice explicitly adds CLI
  flags.
- Phase 5.1 DataForSEO live fail-fast (`ROADMAP.md` § 5.1).
- Phase 5.2 Gemini/BGE empty-output fail-fast (`ROADMAP.md` § 5.2).
- Phase 5.4 exploratory extensions (rank-decile segments; keyword holdout and
  time-split validation in Phase 5.6).
- Expanded report sections and OLS/PL standardization (`ROADMAP.md` § Phase 6.1).
- Custom URL/text manifest ingestion for TextRazor-only runs (no fixture SERP).
- Direct page fetching outside DataForSEO (TextRazor receives parsed text only).
- Causal claims about ranking factors.
- IV / `PanelOLS`, URL fixed effects, per-keyword OLS as primary inference.
- CI, deployment, production hosting.
- Parquet `Variant` type for semi-structured provider payloads.

## Phase 5 acceptance criteria

**Status:** 27 of 42 slices shipped, 2 partial, 13 open.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `analysis_spec.v1.yaml` loaded; estimand version in outputs | 1, 2 | Shipped |
| Guardrail hard-fail skips inference; warn surfaces in JSON | 3, 9, 16–20 | Shipped (per depth) |
| Spearman + BH per backend when K ≥ 10 | 4, 17 | Shipped (per depth) |
| Pooled regression with keyword-clustered SEs only in primary output | 5, 17 | Shipped (per depth) |
| Effect-size translation + `actionable_association` rule | 5, 9, 17 | Shipped (per depth) |
| Pooled diagnostics + influence sensitivity in diagnostics JSON | 6, 8, 17 | Shipped (per depth) |
| `influential_rows_rate` warn guardrail on primary backend | 8 | Shipped |
| `page_text` accepts `tasks[].result: null`; live run continues (S5-11) | 6 | Open |
| Multivariate sensitivity with VIF drop order | 7 | Shipped |
| Limitations in JSON and Markdown | 9, 19 | Shipped (per depth) |
| `seo-rank analyze` exit code + dry-run skip | 9 | Shipped |
| Golden fixture ρ/slope + schema/boundary contracts | 10 | Shipped |
| Within-keyword rank transform (`data/ranks.py`) | 11 | Phase 6.1 (partial) |
| Within-keyword rank/pct/z columns in `analysis_mart.v2` | 12 | Phase 6.1 |
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
| Similarity + TextRazor golden fixtures and CLI tests | 31, 42 | Open |
| TextRazor word/sense/spelling parsed from API-shaped responses | 35 | Open |
| Entity salience aggregates on page mart | 36 | Open |
| Topic/category label features + IAB classifier on main run | 37 | Open |
| Structured relation/property/phrase features | 38 | Open |
| dependency-trees syntactic features | 39 | Open |
| Entity KB linkage enrichment | 40 | Open |
| Phase 5.7 signal-family registry and stats dispatch | 41 | Open |
| Salience explainability + Phase 5.7 golden fixtures | 42 | Open |

## Phase 6.2 acceptance criteria

**Status:** 4 of 4 slices shipped.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `backlinks_analysis` feature mart at `analysis_mart` grain with bounded count validation | 1 | Shipped |
| `backlinks_counts` family (`backlinks_metric` kind) in spec + registry | 2 | Shipped |
| Family-aware stats emit backlinks blocks in `stats_*` | 3 | Shipped |
| Mart materialization + stats regressions cover backlinks analysis path | 4 | Shipped |

Backlinks count signals (`backlinks_count`, `referring_domains_count`,
`dofollow_backlinks_count`) are additive: they live on `parquet/backlinks_analysis/`
and join into stats via `SOURCE_MART_BY_KIND["backlinks_metric"]`. The similarity
`analysis_mart` contract (`analysis_mart.v1`) is unchanged.

---

## Phase 7.1 acceptance criteria (OnPage instant_pages)

**Status:** 18 of 18 slices shipped.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `build_onpage_instant_pages_request()` + schema + offline fixture | 1 | Shipped |
| Offline request/schema tests in `test_dataforseo_requests.py` | 2 | Shipped |
| `fetch_onpage_signals_for_urls` + `endpoint=onpage_instant_pages` persistence | 3 | Shipped |
| Live-run wiring alongside backlinks fetch | 4 | Shipped |
| Stored-run backfill for missing `(target_keyword, url)` OnPage rows | 5 | Shipped |
| Curated `parquet/onpage_signals` (`build_onpage_signals_frame`) | 6 | Shipped |
| `parquet/onpage_features` feature mart at panel grain | 7 | Shipped |
| Three `onpage_metric` families without `analysis_mart` schema bump | 8 | Shipped |
| Full family stats (Spearman / OLS / diagnostics / PL) + legacy mart rebuild guard | 9 | Shipped |
| Stored-run end-to-end regression + full-layer CLI pipeline tests | 18 | Shipped |
| Full `checks` coverage (46 booleans on `onpage_signals`) | 11 | Shipped |
| `meta` block metrics (18 columns on `onpage_signals`) | 12 | Shipped |
| `htags` counts + `social_media_tags` presence flags (5 columns) | 13 | Shipped |
| Resource/cache/DOM/size metrics | 14 | Shipped |
| Feature mart + bounded validation for new columns | 16 | Shipped |
| Full `page_timing` expansion | 15 | Shipped |

OnPage signals are additive: they live on `parquet/onpage_features/` and join
into stats via `SOURCE_MART_BY_KIND["onpage_metric"]`. The similarity
`analysis_mart` contract (`analysis_mart.v1`) is unchanged. Legacy run directories
created before Slice 8 get `onpage_features` materialized (null OnPage columns when
raw data is absent) via `ensure_feature_marts_for_analysis()` in
`data/features.py`, invoked from `seo-rank analyze` and `run_phase5_stats()`.

---

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest` (unit tests only;
  live integration requires `python -m pytest tests/integration -m integration`),
  before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
