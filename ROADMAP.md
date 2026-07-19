# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract; keep deferred and historical items here.

## Current Backlog

Active scope contract: `GOALS.md` (Phase 5).

### Phase 5 — Statistical analysis

Observational association between observed page variables and SERP rank on the
`analysis_mart` panel (`target_keyword × SERP URL`, top 20 per keyword). Full
product and estimand review: `PHASE5-STATS-PLAN-REVIEW.md`.

**Primary decision (v1):** association exists (A) + backend comparison (B) —
pooled within-keyword association per signal family, with the similarity
backends as the pre-registered starting point, **BGE as the primary backend**
and Gemini backends as secondary comparisons (fixed order: BGE → Gemini Doc
Retrieval → Gemini Semantic Similarity; not data-driven).

**Headline metric:** keyword-level Spearman ρ (primary). Pooled regression
coefficients + clustered CIs (secondary). Prefer CIs over p-values alone;
coefficients are likely conservative under similarity measurement error.

**Mart columns (absolute, v1):** `bge_normalized_score`,
`gemini_doc_retrieval_normalized_score`, `gemini_semantic_similarity_normalized_score`,
`serp_rank`, `page_text_length`, `target_keyword_id`, `canonical_url_hash`.

**Mart columns (relative, v2 — Phase 6.1):** per backend, `*_similarity_rank`,
`*_similarity_pct`, `*_similarity_z` derived within each `target_keyword_id`
from absolute scores (BGE ranks on `bge_raw_score`; Gemini on
`*_normalized_score`). Primary confirmatory estimand remains absolute scores.

**Panel dependence:** rows nest under `target_keyword_id`; the same
`canonical_url_hash` may appear under multiple keywords. Default clustering =
`target_keyword_id`. Optional sensitivity: two-way cluster (keyword × URL) in
robustness appendix only.

**BH policy (v1):** one **two-sided Spearman correlation test** per keyword per
backend; family = all keywords for that backend (size K). Apply BH at q = 0.05
**within each backend family** only when **K ≥ 10** keywords in the panel; below
K, report raw p-values with an underpowered warning and skip BH. Never
BH-adjust diagnostic p-values (RESET, Breusch–Pagan, etc.).

**Actionable association (v1, tune after golden fixtures):** set
`actionable_association: true` in `stats_summary.json` only when **all** hold
for the **BGE** backend:

- median |ρ| ≥ 0.25 across keywords;
- ≥ 60% of keywords have same-sign ρ;
- primary pooled regression 95% CI on BGE normalized score excludes 0.

**Guardrails** — see table below. On **hard-fail**, skip confirmatory inference
(BH, actionable flag, coefficient interpretation); still write guardrail status
and limitations. On **warn**, run full stats but surface warnings prominently.

| Guardrail | Default threshold | Severity |
| --------- | ----------------- | -------- |
| Within-keyword variance in `serp_rank` | > 0 per keyword with data | hard-fail |
| Within-keyword variance in each similarity column | > 0 per keyword with data | warn |
| Influential rows (Cook's D > 4/n on pooled BGE model) | report %; warn if > 5% | warn (shipped — `influential_rows_rate` guardrail in Slice 8) |

**Outputs:** `runs/{run_id}/stats/stats_summary.json` (includes per-depth
`rank_depths.*.limitations`, top-level compat shim mirroring `top_20`),
`stats_diagnostics.json` (nested `rank_depths`), `stats_report.md` (four
`## Rank depth:` sections). Link from existing `report.md` to
`stats/stats_report.md` when stats run. Limitations also belong in JSON, not
Markdown-only.

**Rank-depth confirmatory paths (shipped, slices 16–20):** `run_phase5_stats()`
runs parallel bundles at `top_20`, `top_10`, `top_5`, and `top_3`. Each depth
gets independent guardrails, Spearman, pooled OLS, page-level Plackett-Luce,
pooled diagnostics, limitations, and `actionable_association`.
`primary_rank_depth` stays `top_20`; summary metadata exposes
`actionable_association_by_rank_depth`.

**Plackett-Luce (page-level, secondary):** rank-ordered logit on the same
`analysis_mart` panel at each confirmatory rank depth, using observed page rows
per keyword with `serp_rank` capped at that depth and keyword-clustered
inference. Leave-one-out-top-rank IIA runs on `top_20` only. It is additive to
Spearman and pooled OLS, not a replacement. Passage-level Plackett-Luce remains
deferred backlog work only.

**CLI:** `seo-rank analyze --run RUN_ID` materializes `analysis_mart`, runs
Phase 5 stats when guardrails allow, writes `stats_*`. Exit **1** on guardrail
hard-fail (optional `--no-fail-on-guardrails` for CI/fixtures). Skip full stats
on explicit `--dry-run` and documented offline fixture modes only.

**Analysis spec versioning:** ship `analysis_spec.v1.yaml` for page-level
three-backend panel. Phase 5.75 adds features → `analysis_spec.v2.yaml`; do not
reinterpret v1 runs with v2 spec.

**Not in v1:** per-keyword OLS as primary inference, IV / `PanelOLS`, URL fixed
effects, rank-decile segments, keyword-heterogeneity deep-dives (Phase 5.4),
confirmatory keyword holdout and time-split validation (Phase 5.6), passage-level
Plackett-Luce analysis.

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
     deprecated HTML tag control); separate model per backend.
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
   - **Remaining (live run):** `FIXUPS.md` **S5-11** — `page_text` schema
     rejects `tasks[].result: null` from DataForSEO; blocks
     `--live-providers` E2E sign-off.

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
     with nested `rank_depths`; `seo-rank analyze` and post-run
     `materialize_run_tree()` call `run_phase5_stats()`; exit **1** on guardrail
     hard-fail; dry-run / fixture runs skip stats.

10. **[x] Slice 10 — Golden fixtures & tests**
    - Synthetic `analysis_mart` with known ρ and pooled slope per backend.
    - Schema contract for `stats_summary.json` / `stats_diagnostics.json`.
    - Tests: BH family boundaries, BH skipped when K < 10, hard-fail skip path,
      actionable flag logic, influence refit delta, multivariate VIF drop order,
      clustered vs IID SE guard; see `TESTING.md`.
    - Covered by `tests/unit/test_stats_golden_fixtures.py`.

11. **[~] Slice 11 — Within-keyword rank transform** → **Phase 6.1 Slice 3**
    - **Done:** `src/seo_rank/data/ranks.py` with Polars-lazy
      `add_within_keyword_similarity_ranks()`; unit tests in
      `tests/unit/test_within_keyword_ranks.py` (ties, `n = 1`, null scores,
      full top-20 panel).
    - **Remaining:** wire into `marts.py` and `analysis_mart.v2` (Slice 12).

12. **[ ] Slice 12 — Analysis mart v2 columns** → **Phase 6.1 Slice 4**
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

13. **[ ] Slice 13 — Relative similarity stats sensitivity** → **Phase 6.1 Slice 5**
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

14. **[x] Slice 14 — Relative ranks in CLI & fixtures** → **Phase 6.1 Slice 6**
    - `emit_keyword_analysis` / `report.md`: show `rank/pct` (and optional `z`)
      alongside absolute scores; sort Page Similarity by
      `{primary_backend}_similarity_rank`.
    - Extend Slice 10 golden `analysis_mart` with relative columns and known
      rank invariants (e.g. highest absolute score → rank 1).
    - Acceptance: rebuild `analysis_mart` on stored runs derives relative
      columns from stored absolutes without re-scoring.

15. **[~] Slice 15 — Plackett-Luce estimand runtime wiring** → **Phase 6.1 Slice 2** (partial)
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
    - `rank_depths` / `limitations_by_depth` in `analysis_spec.v1.yaml`.
    - `rank_depth.py` filter helper; `AnalysisSpec` accessors; per-depth
      limitation text.

17. **[x] Slice 17 — Per-depth Spearman and pooled OLS**
    - Confirmatory Spearman + pooled OLS at top 20 / 10 / 5 / 3.

18. **[x] Slice 18 — Per-depth Plackett-Luce**
    - Primary PL per depth; leave-one-out IIA on `top_20` only.

19. **[x] Slice 19 — Rank-depth artifacts and report**
    - `rank_depths` in `stats_summary.json` / `stats_diagnostics.json`.
    - Four `## Rank depth:` sections in `stats_report.md`; top-20 compat shim.

20. **[x] Slice 20 — Rank-depth fixtures and tests**
    - `test_stats_rank_depth.py`; depth-divergent fixture; acceptance table.

#### TextRazor-only ingestion (data plane — prerequisite for slices 27–31)

Enable `seo-rank run --live-textrazor-only` to fetch live TextRazor data without
any DataForSEO network calls. Works for **existing runs** (`--stored-run`) and
**brand-new runs** (fixture SERP/page structure + live TextRazor). Writes into
the existing `raw_responses` lake using `endpoint=entities`, `provider=textrazor`
(same `RAW_RESPONSE_SCHEMA` as DataForSEO rows; no partition collisions).

21. **[x] Slice 21 — TextRazor-only flags and gates**
    - `--live-textrazor-only`, `--refresh-textrazor` on `seo-rank run`.
    - Validation: mutual exclusion with `--live-providers` and `--skip-textrazor`;
      requires `SEO_RANK_ENABLE_TEXTRAZOR=1` + `TEXTRAZOR_API_KEY` only.
    - `prepare_textrazor_only_context(env)` — no DataForSEO credential check.
    - Persist flags in `run.json` `config`.
    - Tests: flag combos, env gate, rejection messages (`test_cli_run.py`).

22. **[x] Slice 22 — TextRazor ingest core**
    - `TEXTRAZOR_ENDPOINTS` registry in `textrazor.py` (`entities` ships first).
    - `fetch_textrazor_entities_for_pages()`, `pages_missing_textrazor()`.
    - Unit tests with injected transport (`test_textrazor_ingest.py`).

23. **[x] Slice 23 — Raw lake merge for entities**
    - `merge_raw_response_records()` + partition rewrite for `endpoint=entities`.
    - Dedupe `(target_keyword, url)`; default skips existing rows and
      `--refresh-textrazor` latest-wins replaces them.
    - Other endpoint partitions unchanged (`test_raw_response_merge.py`).

24. **[x] Slice 24 — Stored-run TextRazor backfill**
    - `load_pages_for_textrazor()` from `raw_responses` `page_text` (authoritative).
    - `backfill_textrazor_run()` — no `build_live_keyword_result` / no DFS HTTP.
    - Update `run.json` entity summaries; `materialize_run_tree` refresh.
    - Covered by `test_textrazor_backfill.py`.

25. **[x] Slice 25 — Brand-new TextRazor-only run**
    - `write_textrazor_only_artifacts()` / `build_textrazor_only_payload()`:
      fixture expansion/SERP/page_text, live TextRazor, fixture similarity.
    - `main()` dispatches when `--live-textrazor-only` without `--stored-run`.
    - Zero `dataforseo.*` in `network_calls`; covered by `test_cli_run.py`.

26. **[x] Slice 26 — TextRazor-only tests and docs**
    - **Done:** stored-run backfill (`test_textrazor_backfill.py`); CLI
      flag/gate, brand-new textrazor-only run tests (`test_cli_run.py`), and
      the shared raw-response schema contract in `README.md`, `TESTING.md`, and
      `ARCHITECTURE.md`.
    - **Remaining:** optional TextRazor connectivity probe in
      `test_provider_connectivity.py`.

**Example usage:**

```bash
# Brand-new: fixture structure + live TextRazor (shipped)
seo-rank run --seed "technical seo" --live-textrazor-only --output-dir runs/demo

# Backfill entities on an existing run (shipped)
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only

# Force re-fetch
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only --refresh-textrazor
```

#### TextRazor signal expansion (stats plane — depends on slices 21–26)

27. **[x] Slice 27 — TextRazor signal registry and family contract**
    - `analysis_spec.v1.yaml` `signal_families` block: three similarity families
      plus six TextRazor scalar/structural families at
      `target_keyword_id × canonical_url_hash` grain.
    - `src/seo_rank/stats/families.py` loads the registry; `spec.py` derives
      `backend_order` from similarity-family keys and validates against
      `decision.backend_order`.
    - Covered by `tests/unit/test_stats_families.py` and
      `tests/unit/test_stats_spec.py`.

28. **[x] Slice 28 — Materialize TextRazor page metrics**
    - `build_textrazor_page_metrics_frame()` aggregates entity/topic/category/
      entailment/structural counts from TextRazor page-metrics responses.
    - Curated `textrazor_page_metrics_curated` and feature mart
      `textrazor_page_metrics` (same grain as `analysis_mart`; not joined into
      the similarity mart).
    - TextRazor HTTP uses the full extractor set; responses still partition under
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
      `stats_report.md` with nested `rank_depths.*.families` for similarity and
      TextRazor families; top-level similarity blocks kept for compatibility.
    - Hard-fail still skips confirmatory inference but writes family blocks as
      `skipped`.
    - Covered by `tests/unit/test_stats_family_artifacts.py`.

31. **[ ] Slice 31 — TextRazor signal golden fixtures and tests**
    - Add synthetic fixtures that include both similarity rows and TextRazor
      rows with known rank relationships.
    - Add tests for family registry loading, TextRazor page-metric aggregation,
      BH gating at `K >= 10`, pooled regression and diagnostics on the new
      families, artifact serialization, and CLI output.
    - Keep one end-to-end fixture that proves the same Phase 5 stack works on a
      similarity family and the new TextRazor families without changing the
      current similarity results.

32. **[x] Slice 32 — TextRazor page-metrics completeness**
    - `textrazor.py` tracks per-section presence; missing extractors yield
      `null` counts, not silent zeros.
    - `textrazor_page_metrics_complete` on curated and feature marts.
    - Covered by `tests/unit/test_textrazor_normalization.py` and
      `tests/unit/test_feature_marts.py`.

33. **[x] Slice 33 — Small-K exploratory status**
    - `stats_*` artifacts surface `keyword_count` and `inference_mode` per rank
      depth and backend.
    - Covered by `tests/unit/test_stats_family_artifacts.py`.

34. **[ ] Slice 34 — Signal factor dossier (Phase 5.6 tracker)**
    - Umbrella tracker in the Phase 5 slice table; full specification in
      **Phase 5.6** below (six slices: entity density materialization + dossier
      + proxy diagnostics).
    - **Precursor (partial, ad hoc):** `analysis/textrazor_ranking_r2.py`,
      `src/seo_rank/stats/textrazor_explainability.py`, and
      `ranking_explainability_viz.py` (similarity + TextRazor adjusted R²,
      curated multivariate model, PNG charts).

35. **[ ] Slice 35 — Word/sense/spelling parse fix (Phase 5.7 tracker)**
    - Full specification in **Phase 5.7** below.

36. **[ ] Slice 36 — Entity salience aggregates (Phase 5.7 tracker)**
    - See **Phase 5.7** below.

37. **[ ] Slice 37 — Topic & category label features (Phase 5.7 tracker)**
    - See **Phase 5.7** below.

38. **[ ] Slice 38 — Structured relation/property/phrase features (Phase 5.7 tracker)**
    - See **Phase 5.7** below.

39. **[ ] Slice 39 — dependency-trees syntactic features (Phase 5.7 tracker)**
    - See **Phase 5.7** below.

40. **[ ] Slice 40 — Entity KB linkage enrichment (Phase 5.7 tracker)**
    - See **Phase 5.7** below.

41. **[ ] Slice 41 — Signal registry for new families (Phase 5.7 tracker)**
    - See **Phase 5.7** below.

42. **[ ] Slice 42 — Salience explainability & golden fixtures (Phase 5.7 tracker)**
    - See **Phase 5.7** below; complements slice 31.

#### Phase 5 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `analysis_spec.v1.yaml` loaded; estimand version in outputs | 1, 2 | Shipped |
| Guardrail hard-fail skips inference; warn surfaces in JSON | 3, 9, 16–20 | Shipped (per depth) |
| Spearman + BH per backend when K ≥ 10 | 4, 17 | Shipped |
| Pooled regression with keyword-clustered SEs only in primary output | 5, 17 | Shipped |
| Effect-size translation + actionable_association rule | 5, 9, 17 | Shipped (per depth) |
| Pooled diagnostics + influence sensitivity in diagnostics JSON | 6, 8, 17 | Shipped (per depth) |
| `influential_rows_rate` warn guardrail on primary backend | 8 | Shipped |
| Multivariate sensitivity with VIF drop order | 7 | Shipped |
| Limitations in JSON and Markdown | 9, 19 | Shipped (per depth) |
| `seo-rank analyze` exit code + dry-run skip | 9 | Shipped |
| Golden fixture ρ/slope + schema/boundary contracts | 10 | Shipped |
| Within-keyword rank/pct/z columns in `analysis_mart.v2` | 11, 12 | Open |
| Relative similarity robustness in `stats_diagnostics.json` | 13 | Open |
| CLI keyword report surfaces relative ranks | 14 | Open |
| Parallel confirmatory rank depths (20/10/5/3) | 16–20 | Shipped |
| `actionable_association_by_rank_depth` in summary JSON | 19 | Shipped |
| `rank_depths` nested JSON + four `## Rank depth:` report sections | 19 | Shipped |
| `--live-textrazor-only` without DataForSEO network (stored-run backfill) | 21, 24 | Shipped |
| `--live-textrazor-only` brand-new run (fixture structure + live TextRazor) | 25 | Shipped |
| Stored-run entity backfill merges `endpoint=entities` only | 23, 24 | Shipped |
| `parquet/entities/` after textrazor-only ingest + normalize | 21–25 | Shipped |
| TextRazor cross-doc schema contract | 26 | Shipped |
| TextRazor signal registry and page-metrics mart | 27, 28 | Shipped |
| Family-aware Spearman, OLS, diagnostics, and PL per signal family | 29 | Shipped |
| Combined `stats_*` artifact tree for all signal families | 30 | Shipped |
| `textrazor_page_metrics_complete` on curated and feature marts | 32 | Shipped |
| `keyword_count` and `inference_mode` on underpowered runs | 33 | Shipped |
| Similarity + TextRazor golden fixtures and CLI tests | 31 | Open |
| Factor vs proxy report (`signal_factor_report.json` + CLI) | 5.6 | Open |
| NDCG@k (sort-by-metric vs observed rank) | 5.6 | Open |
| Incremental TextRazor after BGE/similarity (proxy-test ladder) | 5.6 | Open |
| Partial correlation controlling for similarity | 5.6 | Open |
| Leave-one-keyword-out stability | 5.6 | Open |
| Keyword holdout + optional time-split validation | 5.6 | Open |
| Negative controls (null predictors) | 5.6 | Open |
| Same-length / same-similarity subset analyses | 5.6 | Open |
| Entity count + word-normalized density in `textrazor_page_metrics` | 5.6 Slice 0 | Open |
| Entity density in dossier registry + proxy ladder | 5.6 | Open |
| TextRazor word/sense/spelling parsed from API-shaped responses | 5.7 Slice 35 | Open |
| Entity salience aggregates on `textrazor_page_metrics` | 5.7 Slice 36 | Open |
| Top topic/category labels + IAB classifier on main run | 5.7 Slice 37 | Open |
| Structured relation/property/phrase features | 5.7 Slice 38 | Open |
| `dependency-trees` syntactic features | 5.7 Slice 39 | Open |
| Entity KB linkage enrichment | 5.7 Slice 40 | Open |
| Phase 5.7 signal-family registry and stats dispatch | 5.7 Slice 41 | Open |
| Salience explainability + Phase 5.7 golden fixtures | 5.7 Slice 42 | Open |
