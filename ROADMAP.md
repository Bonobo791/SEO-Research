# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract; keep deferred and historical items here.

## Current Backlog

Active scope contract: `GOALS.md` (Phase 5).

### Phase 5 — Statistical analysis

Observational association between similarity scores and SERP rank on the
`analysis_mart` panel (`target_keyword × SERP URL`, top 20 per keyword). Full
product and estimand review: `PHASE5-STATS-PLAN-REVIEW.md`.

**Primary decision (v1):** association exists (A) + backend comparison (B) —
pooled within-keyword association per similarity backend, with **BGE as the
pre-registered primary backend** and Gemini backends as secondary comparisons
(fixed order: BGE → Gemini Doc Retrieval → Gemini Semantic Similarity; not
data-driven).

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
   - Baseline: `-log(serp_rank) ~ log(deprecated_html_tags + 1) + C(target_keyword_id)`.
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
      - Replace hardcoded constants in `plackett_luce.py` (`FORMULA`,
        `DEFAULT_MAX_SERP_RANK`, `HESSIAN_CONDITION_NUMBER_THRESHOLD`,
        `OPTIMIZER_GRADIENT_TOLERANCE`) with spec-driven values.
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
    - Dedupe `(target_keyword, url)`; `--refresh-textrazor` latest-wins replace.
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

### Phase 5.1 — Live provider fail-fast on DataForSEO denial

Stop multi-keyword live runs as soon as DataForSEO returns a **fatal** task error
(e.g. `40207` IP not whitelisted, auth failures) instead of treating
`tasks[].result: null` as an empty SERP and continuing through the keyword
loop. Prevents burning API quota and writing poisoned `parquet/raw_responses`
rows that downstream normalize silently drops. Empty Gemini/BGE scoring after
upstream fetches is **Phase 5.2**.

**Root cause (Columbus run, 2026-07-02):** SERP schema allows `result: null`;
`normalize_serp_results()` returns `[]` without checking `status_code`. Runs
before `raise_for_failed_dataforseo_tasks()` (shipped in `74ea7c0`) looped all
keywords and persisted failed payloads. The current `--stored-run` path
resumes from the saved raw lake and existing keyword results, so completed work
survives replay; interrupting mid-run still loses in-RAM SERP + embedding
progress for in-flight refresh work.

**Primary behavior**

- Classify DataForSEO task `status_code` values as success (`20000`) vs fatal
  (abort entire run with exit **2**).
- Call the classifier on **every** live DataForSEO endpoint: `keyword_expansion`,
  `serp`, and each `page_text` response.
- Distinguish **fatal auth/IP errors** from **per-URL crawl failures** (S5-11):
  skip individual `page_text` tasks with `result: null` on crawl failure; still
  abort on fatal codes.
- Optional preflight probe (reuse `scripts/test_provider_connectivity.py` logic)
  before loading BGE and entering a multi-keyword loop.
- `replay_stored_run` / `expand_stored_run`: CLI `--live-providers`,
  `--live-gemini`, `--live-bge` override stale `run.json` config for execution.
- On stale-SERP refresh, replace failed raw rows for refreshed keywords; do not
  OR-retain unusable SERP parquet over newer success (FIXUPS S6-10).

**CLI contract:** live `seo-rank run` exits **2** on first fatal DataForSEO task;
stderr message includes `status_code`, endpoint, and `target_keyword` when known.
No `run.json` / raw parquet write on abort mid-loop (today's behavior for
`DataForSeoClientError`).

**Related FIXUPS:** S5-11 (page_text crawl `null` vs fatal), S6-10 (stale SERP
retention), S6-12 (shared fatal classifier with `stored_serp_response_is_usable`),
S6-15 (stored-run live replay exits `2` on SERP task failure).

#### Dev slices

**Progress:** 0 of 5 shipped, 5 open.

1. **[ ] Slice 1 — Shared fatal task classifier**
   - Add `dataforseo_task_is_fatal()` / `dataforseo_task_is_success()` in
     `dataforseo.py` (fatal set: `40207`, `40101`, `40102`; extend from
     DataForSEO docs as needed).
   - Wire `raise_for_failed_dataforseo_tasks()` and
     `stored_serp_response_is_usable()` through the shared helper (S6-12).
   - Unit tests in `tests/unit/test_dataforseo_requests.py`.

2. **[ ] Slice 2 — Fail-fast on all live DataForSEO endpoints**
   - `raise_for_failed_dataforseo_tasks()` after `keyword_expansion` in
     `write_live_artifacts`.
   - After each live `page_text` response in `build_live_keyword_result`; fatal
     codes abort, crawl-null skips per S5-11.
   - CLI tests: expansion `40207` → exit `2`; SERP `40207` on keyword 2 of 3 →
     keyword 3 never requested; page_text `40207` → exit `2` (S6-15).

3. **[ ] Slice 3 — DataForSEO preflight before multi-keyword loops**
   - Cheap DataForSEO connectivity / auth probe before keyword iteration on
     live `run` and live `stored-run` refresh paths (BGE defer + Gemini preflight:
     Phase 5.2).
   - Clear stderr when IP whitelist is the likely fix (link to DataForSEO API
     access panel).
   - Unit test: probe failure → exit `2` without network keyword loop.

4. **[ ] Slice 4 — Stored-run respects CLI live flags**
   - Pass CLI `RunConfig` into `expand_stored_run`; merge `--live-providers`,
     `--live-gemini`, `--live-bge`, `--live-textrazor` over stored `run.json`
     config for execution.
   - Test: stored `live_providers: false` + CLI `--live-providers` uses live path.

5. **[ ] Slice 5 — Safer stale-SERP raw retention (optional)**
   - On `expand_stored_run` refresh, latest-wins per keyword for `endpoint=serp`
     raw rows; drop retained failed row when refresh succeeds (S6-10).
   - Test: inject stale `40207` parquet row, successful live refresh replaces it.

#### Phase 5.1 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Shared fatal classifier; no drift vs `stored_serp_response_is_usable` | 1 | Open |
| Live expansion / SERP / page_text abort on fatal `status_code` | 2 | Open |
| Crawl-null `page_text` still skips URL without aborting run (S5-11) | 2 | Open |
| Preflight before multi-keyword live loop (DataForSEO) | 3 | Open |
| CLI `--live-*` flags override stored config on replay | 4 | Open |
| Stale failed SERP rows not retained after successful refresh | 5 | Open |

### Phase 5.2 — Live Gemini/BGE fail-fast on empty scoring work

Stop multi-keyword live runs when a keyword produces **no scorable panel rows**
after upstream fetches, instead of logging `gemini embeddings` / `bge scoring`,
burning API calls on empty inputs, or loading GPU models for doomed runs.
Complements Phase 5.1 (DataForSEO fatal task codes); does not replace it.

**Root cause (Columbus run, 2026-07-02):** after SERP denial or all-empty
`page_text`, the keyword loop continued. Progress looked healthy while
`page_similarity` stayed empty. User saw **no Google Cloud billing** because
live Gemini uses **Google AI Studio** (`genai.Client(vertexai=False,
api_key=GEMINI_API_KEY)`), not Vertex/GCP console billing. BGE is **local CUDA**
only — never appears in cloud spend.

**Observed gaps today**

- `compute_gemini_page_similarity_scores()` issues **two keyword embed API calls**
  even when `pages` is empty (doc-retrieval + semantic queries).
- `network_calls` records `genai.embed_content` only when `parsed_pages` is
  non-empty — undercounts actual Gemini calls on empty keywords.
- `prepare_live_run_context()` loads the full BGE reranker before any keyword;
  `compute_bge_page_similarity_scores()` returns `[]` silently when there are no
  valid pages but the run still logs `bge scoring` and advances.
- No abort when SERP returned URLs but **every** `page_text` parse is empty
  (distinct from S5-11 per-URL crawl skip).
- No run-start clarity on **where Gemini bills** (AI Studio vs GCP).

**Primary behavior**

- After each keyword's SERP + `page_text` merge in live mode: if
  `len(parsed_pages) == 0` and the keyword had SERP URLs (or live providers
  were enabled for that keyword), **abort entire run** with exit **2** and a
  message naming `target_keyword`, upstream stage, and likely fix (DataForSEO IP
  whitelist, crawl failures, stale stored replay).
- After similarity merge: if `--live-gemini` and/or `--live-bge` is on but
  `page_similarity` for this keyword is empty while SERP had candidates, abort
  (catches silent embed/rerank failures).
- **Defer BGE model load** until the first keyword with `len(parsed_pages) > 0`
  (or until first keyword passes SERP+page_text gate).
- **Skip Gemini query embeds** when `len(pages) == 0` — do not spend API quota
  on keywords with nothing to score.
- **Accurate `network_calls`:** count each live `embed_content` and BGE
  `compute_score` batch; surface in `run.json` metadata and progress.
- **Run-start billing note** on `--live-gemini`: stderr one-liner that billing
  is Google AI Studio / API key usage, not GCP project billing unless Vertex is
  added later.
- Optional **Gemini embed probe** before multi-keyword loop (reuse connectivity
  script or one cheap embed); abort on `404` / auth errors (FIXUPS S476-13).

**CLI contract:** live `seo-rank run` exits **2** on first keyword with zero
scorable output when live Gemini or BGE is enabled; stderr includes
`target_keyword`, `parsed_pages` count, and whether Gemini/BGE were live.
No partial `run.json` flush on abort mid-loop (same as Phase 5.1).

**Related FIXUPS:** S476-13 (Gemini embed health / model endpoint),
S5-11 (per-URL `page_text` null skip vs keyword-level empty panel abort).

**Depends on:** Phase 5.1 slice 4 (CLI `--live-*` override on stored-run) so
empty-output guards run against the intended live/offline config.

#### Dev slices

**Progress:** 0 of 6 shipped, 6 open.

1. **[ ] Slice 1 — Keyword-level empty panel guard**
   - After `build_live_keyword_result` assembles `parsed_pages`, if live
     providers or live Gemini/BGE and `parsed_pages` empty while SERP had items
     (or expansion included this keyword), raise `CliCommandError` → exit `2`.
   - Unit + CLI tests: SERP ok + all `page_text` empty → abort before Gemini;
     zero SERP rows after successful task → abort (or defer to 5.1 if already
     fatal).

2. **[ ] Slice 2 — Skip wasteful Gemini calls on empty pages**
   - Short-circuit `compute_gemini_page_similarity_scores()` when `pages` is
     empty (no query embeds).
   - Align `network_calls` with actual `embed_content` invocations.
   - Test: empty pages → zero embed calls; N pages → `2 + 4N` calls.

3. **[ ] Slice 3 — Defer BGE load until scorable work exists**
   - Move `load_bge_reranker()` from run start to first keyword with
     `parsed_pages > 0` when `--live-bge`.
   - Test: keyword 1 empty → model not loaded; keyword 1 has pages → load once,
     reuse for keyword 2.

4. **[ ] Slice 4 — Empty similarity output guard**
   - After Gemini/BGE merge, if live scoring enabled and `similarity_scores`
     empty for keyword with non-empty `parsed_pages`, abort exit `2`.
   - Test: mock embed failure → no silent advance to next keyword.

5. **[ ] Slice 5 — Billing clarity and optional Gemini preflight**
   - Stderr banner for `--live-gemini` (AI Studio billing target).
   - Optional cheap embed probe before keyword loop; fail fast on S476-13
     conditions.
   - Document in `README.md` / `TESTING.md` where to check Gemini usage.

6. **[ ] Slice 6 — Stored-run + progress honesty**
   - Progress lines distinguish `similarity (fixture)` vs `gemini embeddings
     (live)` vs skipped (empty panel).
   - Stored-run refresh: apply guards when CLI `--live-gemini` / `--live-bge`
     override stored config (requires 5.1 slice 4).

#### Phase 5.2 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Abort when keyword has SERP URLs but zero `parsed_pages` in live mode | 1 | Open |
| No Gemini query embeds when `pages` is empty | 2 | Open |
| `network_calls` matches actual live embed invocations | 2 | Open |
| BGE model loads only after first scorable keyword | 3 | Open |
| Abort when live scoring yields zero `page_similarity` rows | 4 | Open |
| Run-start Gemini billing note + optional embed preflight | 5 | Open |
| Progress distinguishes fixture vs live vs skipped | 6 | Open |

### Phase 5.4 — Exploratory extensions (deferred)

- Rank-decile segments (ranks 1–3 vs 4–10 vs 11–20).
- Keyword heterogeneity deep-dives (decision C): per-keyword slopes as
  exploratory only, separate BH family if promoted to confirmatory.
- Random 20% keyword holdout for confirmatory pass — **Phase 5.6** (slice 5).
- LOWESS / CCPR diagnostic plots as optional artifacts.

### Phase 5.5 - Analysis Expansion

- Per keyword: top-20 SERP; passage and domain URL scoring vs target
  keyword; domain URL cap 1000; skip domains over 1000 URLs

### Phase 5.6 — Signal factor & proxy diagnostics

Observational methods to distinguish **candidate ranking signals** from
**likely proxies** (signals that co-move with rank because they track length,
semantic relevance, template type, or other confounders). Complements Phase 5
Spearman / pooled OLS / Plackett-Luce confirmatory paths; does **not** replace
them and does **not** support causal claims about Google's ranking function.

**Tracked in Phase 5 slice 34** (umbrella only). **Precursor (partial):**
`analysis/textrazor_ranking_r2.py`, `src/seo_rank/stats/textrazor_explainability.py`,
and `ranking_explainability_viz.py` (similarity + TextRazor univariate and joint
adjusted R², curated multivariate model, PNG charts).

**Panel:** same grain as Phase 5 (`target_keyword_id × canonical_url_hash`,
top-N SERP rows); TextRazor metrics from `textrazor_page_metrics` left-joined
onto `analysis_mart`. **Primary backend for proxy ladder:** `bge_normalized_score`
(pre-registered in `analysis_spec.v1.yaml`).

#### Methods planned

| Method | Purpose | Notes |
| ------ | ------- | ----- |
| **NDCG@k** | Sort-by-metric vs Google order | Per keyword: treat signal as relevance (higher = better), compute NDCG@k vs `serp_rank`; macro mean/median across keywords. Default k = 10; configurable. |
| **Incremental regression after BGE** | Explicit proxy test | Pooled OLS ladder with keyword FE + `log(deprecated_html_tags + 1)`: baseline → `+ bge_normalized_score` → `+ candidate signal(s)`. Report coefficient, p-value, Δ adjusted R² at each step; shrinkage after BGE ⇒ likely proxy. |
| **Partial correlation** | Association net of similarity | Within-keyword or pooled partial ρ / partial regression of signal vs rank controlling for `bge_normalized_score` and deprecated HTML tags. |
| **Leave-one-keyword-out (LOKO)** | Stability | Recompute headline metrics (Spearman median, NDCG macro mean, incremental Δ R²) dropping one keyword at a time; flag dominant-keyword dependence. |
| **Out-of-sample validation** | Generalization beyond fit sample | (a) **Keyword holdout:** seeded split by `target_keyword_id` (default 20% held out). (b) **Time-split:** compare metrics across two `run_id`s on overlapping keywords (exploratory). Label `exploratory` when K_train or K_test < 10. |
| **Negative controls** | Falsification | Deliberately null or shuffled predictors (e.g. permuted signal within keyword) should show ρ ≈ 0, Δ R² ≈ 0; candidate must beat controls. |
| **Same-length / same-similarity subsets** | Discriminating comparisons | Restrict to URLs with similar `page_text_length` (binned) or similar `bge_normalized_score` (binned); re-test association within slices. |
| **Factor vs proxy report** | Single dossier artifact | `analysis/signal_factor_report.py` → terminal summary + `runs/{run_id}/stats/signal_factor_report.json` with limitations block. |

**Core module:** `src/seo_rank/stats/signal_dossier.py` (computations) +
`analysis/signal_factor_report.py` (CLI). **v1 dossier candidate registry:**
scalar/structural TextRazor metrics plus an **entity density bundle** (see
below). Registry is exploratory-only in 5.6 — not added to confirmatory
`analysis_spec.v1.yaml` `signal_families` unless promoted after dossier
evidence.

**Scalar / structural candidates (existing):** `textrazor_entity_confidence_score`,
`textrazor_entity_relevance_score`, `textrazor_entailment_score`,
`textrazor_relation_count`, `textrazor_property_count`.

**Entity density bundle (new):** counts and length-normalized rates derived from
TextRazor `entities` and joined `page_text_length` from `analysis_mart`.
Canonical dedupe key matches `analysis/gemini_nwh_similarity.py`:
`entityEnglishId` → `entityId` → `matchedText`.

| Column | Definition | Persisted in `textrazor_page_metrics` | Null when |
| ------ | ---------- | ------------------------------------- | --------- |
| `textrazor_entity_mention_count` | `len(entities)` | yes | `entities` section absent |
| `textrazor_unique_entity_count` | deduped entity rows | yes | `entities` section absent |
| `textrazor_unique_entity_density_per_1k_words` | `unique_count × 1000 / textrazor_word_count` | yes | entities absent or `word_count ≤ 0` |
| `textrazor_entity_mention_density_per_1k_words` | `mention_count × 1000 / textrazor_word_count` | yes | entities absent or `word_count ≤ 0` |
| `textrazor_unique_entity_density_per_1k_chars` | `unique_count × 1000 / page_text_length` | no (derived at dossier panel load) | entities absent or `page_text_length ≤ 0` |

**Proxy-test expectations for density (document in dossier JSON + limitations):**

| Metric class | Expected behavior in incremental ladder |
| ------------ | --------------------------------------- |
| Raw counts | High Δ adjusted R² after length step; often collapses after BGE |
| Word-normalized density | Smaller length-step gain; may still collapse after BGE if tracking relevance |
| Char-normalized density | Same-length bins should show more stable association than raw counts when density is real |

Shared counting logic lives in `src/seo_rank/textrazor.py` (extract from
`gemini_nwh_similarity.py` to avoid drift). Re-normalizing stored runs with
TextRazor responses materializes persisted columns without re-fetching API data.

**Out of scope for 5.6 density v1:** keyword–entity overlap, type-weighted density,
passage-level density (Phase 5.5), confirmatory Spearman/BH on density families.

**Out of scope for 5.6 overall:** causal inference, IV / `PanelOLS`, URL fixed
effects, confirmatory promotion to `actionable_association`, BH adjustment across
dossier tests (exploratory appendix only).

#### Dev slices

**Progress:** 0 of 6 shipped.

0. **[ ] Slice 0 — Entity count & density materialization**
   - Add shared `_entity_dedupe_key()` / `_count_entities()` in `textrazor.py`;
     refactor `analysis/gemini_nwh_similarity.py` to import the helper.
   - Extend `normalize_page_metrics()` with mention count, unique count, and
     word-normalized density columns (`null` when section missing, not silent zero).
   - Update `textrazor_page_metrics_curated` and feature mart schemas in
     `normalize.py` / `features.py` (bounded columns, validation rules).
   - Tests: `test_textrazor_normalization.py`, `test_feature_marts.py` (dedupe,
     null semantics, density formula).

1. **[ ] Slice 1 — Core dossier module + factor vs proxy report**
   - Add `src/seo_rank/stats/signal_dossier.py`: panel load via
     `build_family_source_frames`, dossier candidate registry (including density
     bundle), derive `textrazor_unique_entity_density_per_1k_chars` at panel
     load, JSON-serializable summary envelope, limitations text.
   - Add `analysis/signal_factor_report.py`: `--run`, `--depth`, writes
     `runs/{run_id}/stats/signal_factor_report.json` + terminal table (Density
     metrics section).
   - Wire univariate adjusted R² from existing `textrazor_explainability` where
     applicable; extend `TEXTRAZOR_RANKING_METRICS` with count/density columns.
   - Tests: `tests/unit/test_signal_dossier.py` (panel load, JSON shape,
     char-density derivation).

2. **[ ] Slice 2 — NDCG@k + incremental regression ladder**
   - **NDCG@k** per signal per keyword; macro summaries; configurable k.
   - **Incremental OLS ladder:** baseline → length + keyword FE → `+ bge` →
     `+ textrazor_*` (per metric and joint, including density bundle);
     keyword-clustered SEs when K ≥ 2.
   - Report Δ adjusted R² and coefficient stability at each rung; label proxy
     expectations for raw counts vs word/char density.
   - Tests: synthetic panel where signal matches rank; proxy signal vanishes
     after BGE step; raw count tracks length, density retains signal after length
     step in designed fixture.

3. **[ ] Slice 3 — Partial correlation + subset analyses**
   - **Partial correlation** of each candidate vs rank controlling for BGE
     (and optionally length), within-keyword and pooled variants.
   - **Deprecated-tag strata:** re-run Spearman / NDCG within deprecated-tag
     strata (primary discriminant for structural checks vs raw counts).
   - **Same-similarity bins:** bins on `bge_normalized_score`; re-test within
     bins (discriminating "same relevance, different rank" cases).
   - Tests: partial ρ drops when signal is pure function of BGE; subset slices
     retain signal when confound is binned out.

4. **[ ] Slice 4 — Stability + negative controls**
   - **Leave-one-keyword-out:** median Spearman, NDCG macro mean, incremental
     Δ R² with one keyword removed; surface max influence keyword.
   - **Negative controls:** within-keyword permuted signal (including density
     columns); expect null association; compare candidate metrics to control
     distribution.
   - Optional: rank-decile segments (ranks 1–3 vs 4–10 vs 11–20) as
     exploratory slices (absorbs part of Phase 5.4 backlog).
   - Tests: permuted control ≈ 0; LOKO stable when no single-keyword dominance.

5. **[ ] Slice 5 — Out-of-sample validation + CLI polish**
   - **Keyword holdout:** `--holdout`, `--holdout-fraction` (default 0.2),
     `--seed`; metrics on train vs held-out keywords separately.
   - **Time-split:** `--compare-run RUN_ID_B` for overlapping keywords across
     two crawls; report metric drift (exploratory).
   - Complete terminal report sections; document in `TESTING.md`.
   - Tests: holdout split reproducibility; time-split requires overlapping
     keyword set or explicit skip reason.

#### Phase 5.6 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Entity counts + word densities in `textrazor_page_metrics` | 0 | Open |
| Shared entity dedupe helper (no drift vs `gemini_nwh_similarity`) | 0 | Open |
| Dossier registry includes density bundle + char-density derivation | 1 | Open |
| `signal_dossier.py` + `signal_factor_report.json` schema | 1 | Open |
| NDCG@k per signal with macro summaries | 2 | Open |
| Incremental OLS ladder through BGE then TextRazor (incl. density) | 2 | Open |
| Partial correlation controlling for BGE | 3 | Open |
| Same-length and same-similarity subset re-tests | 3 | Open |
| Leave-one-keyword-out stability block | 4 | Open |
| Negative controls (permuted signal, incl. density) | 4 | Open |
| Keyword holdout validation | 5 | Open |
| Optional time-split across two runs | 5 | Open |
| Limitations: observational, no causal claims; word vs char denominator note | 0–5 | Open |

### Phase 5.7 — TextRazor structured signals & entity salience

Deepen TextRazor usage beyond page-level max scores and structural counts.
Today the main pipeline requests `entities`, `topics`, `words`, `phrases`,
`relations`, `entailments`, `senses`, and `spelling`, but normalizes only a
subset: `max(confidenceScore)`, `max(relevanceScore)` (entity salience per
[TextRazor REST docs](https://www.textrazor.com/docs/rest)), topic/category
max scores, entailment maxes, and relation/property/noun-phrase **counts**.
`parquet/entities/` stores per-mention `relevance` but is not joined into
`analysis_mart` or ranking explainability. Word-quality metrics use a
fixture-only top-level `words` shape instead of `sentences[].words` with real
`senses` and `spellingSuggestions`. The analysis script
`analysis/gemini_nwh_similarity.py` parses more fields but is not wired into
`seo-rank run` or Phase 5 artifacts.

**Tracked in Phase 5 slices 35–42.** **Depends on** shipped TextRazor ingest
(slices 21–28) and family-aware stats (slices 29–30). **Complements** Phase 5.6
(proxy/factor dossier) and slice 31 (golden fixtures). **Does not** replace the
Phase 5 confirmatory estimand on similarity backends.

**Entity salience:** TextRazor exposes salience as `Entity.relevanceScore`
(0–1, document importance) distinct from `confidenceScore` (validity). Phase
5.7 expands salience from a single page `max(relevanceScore)` to distributional
and per-entity features usable in family stats and curated explainability.

**Panel:** same grain (`target_keyword_id × canonical_url_hash`, top-N SERP).
New columns land in `textrazor_page_metrics` (and optionally enriched
`entities` curated); `analysis_mart` similarity columns unchanged.

**Not requested today (deferred unless a future slice adds CLI flags):**
`dependency-trees` (slice 39 adds it), `url` input, Prolog `rules`, custom
entity dictionaries, `cleanup.mode` / `languageOverride`, entity type filters,
Account API quota probes.

#### Unused API surface this phase targets

| Area | Currently | Phase 5.7 target |
| ---- | --------- | ---------------- |
| Entity salience | `max(relevanceScore)` only | Mean, top-k, mention-weighted aggregates; optional keyword overlap |
| Entity metadata | `entity_id`, `matched_text`, `types` in `entities` | `wikidataId`, `wikiLink`, `entityEnglishId`, `freebaseTypes`, `data` |
| Topics | `textrazor_topic_score` max | Top `label`, `wikidataId`, `wikiLink` |
| Categories | Max `score` / `classifierScore`; one classifier | Top label + `classifierId`; add IAB taxonomy on main run |
| Words / senses / spelling | Fixture booleans on wrong key | `sentences[].words`, `senses[]`, `spellingSuggestions[]` |
| Relations / properties / phrases | Counts only | Resolved text/labels where offsets allow |
| Entailments | Max score/prior/context in families only | Promote into curated explainability where useful |
| Syntax | Not requested | `dependency-trees` complexity scalars (slice 39) |

#### Dev slices

**Progress:** 0 of 8 shipped.

1. **[ ] Slice 35 — Word/sense/spelling parse fix**
   - Refactor `normalize_page_metrics()` to walk `response.sentences[].words`.
   - Replace `isGrammar` / `isSense` / `isSpelling` with API fields:
     `senses` (max sense score), `spellingSuggestions` (flag count).
   - Update fixtures to REST-shaped JSON; keep `textrazor_page_metrics_complete`
     section-presence logic accurate.
   - Tests: `tests/unit/test_textrazor_normalization.py` with live-shaped payloads.

2. **[ ] Slice 36 — Entity salience aggregates**
   - Add salience aggregation from `entities.relevance` per page: mean, median,
     top-3 max, mention count, unique entities (extend page-metrics builder).
   - Join onto `textrazor_page_metrics` feature mart at existing keys.
   - Optional exploratory: overlap of top-k salient `entity_id` vs keyword
     tokens (document limitation in JSON).
   - Tests: synthetic entity rows → expected aggregates.

3. **[ ] Slice 37 — Topic & category label features**
   - Persist `textrazor_top_topic_label`, `textrazor_top_topic_score`,
     `textrazor_top_category_label`, `textrazor_top_category_classifier_id`.
   - Add `textrazor_iab_content_taxonomy_3.0` to
     `TEXTRAZOR_PAGE_METRIC_CLASSIFIERS` for main `seo-rank run` requests.
   - Validation: scores in [0, 1]; labels UTF-8 non-null when section present.
   - Tests: multi-classifier fixture → both IPTC and IAB top rows materialized.

4. **[ ] Slice 38 — Structured relation/property/phrase features**
   - Reconstruct top noun phrases from `wordPositions` + sentence words.
   - Emit bounded top-phrase representation and named property samples.
   - Parse relation `params` (SUBJECT/OBJECT) when word offsets resolve.
   - Tests: offset reconstruction + empty-offset graceful degradation.

5. **[ ] Slice 39 — dependency-trees syntactic features**
   - Append `dependency-trees` to `TEXTRAZOR_PAGE_METRIC_EXTRACTORS`.
   - Compute page-level scalars: mean dependency depth, unique
     `relationToParent` count, optional mean sentence length from tokens.
   - Document added latency/token cost in `ARCHITECTURE.md` and `README.md`.
   - Tests: dependency-tree fixture → non-null syntactic columns.

6. **[ ] Slice 40 — Entity KB linkage enrichment**
   - Extend `normalize_entities()` with `entity_english_id`, `wikidata_id`,
     `wiki_link`, `freebase_types`, optional `data` key list (bounded).
   - Page-level: `textrazor_linked_entity_fraction`,
     `textrazor_entity_type_entropy` joined to page mart.
   - Tests: linked vs unlinked entity mix → expected fractions.

7. **[ ] Slice 41 — Signal registry for new families**
   - Add Phase 5.7 columns to `analysis_spec.v1.yaml` `signal_families` (or ship
     `analysis_spec.v2.yaml` if column cardinality forces a version bump).
   - Extend `features.py` validation, `families.py` dispatch, and `stats_*`
     nested `rank_depths.*.families` for new TextRazor families.
   - Tests: `test_stats_spec.py`, `test_stats_family_artifacts.py` with synthetic
     panel including salience + label columns.

8. **[ ] Slice 42 — Salience explainability & golden fixtures**
   - Extend `textrazor_explainability.py` curated candidates with salience
     aggregates and topic/category labels; update
     `ranking_explainability_viz.py` when a new primary salience column wins.
   - Wire `analysis/textrazor_ranking_r2.py` to report new metrics.
   - Golden end-to-end fixture (complements slice 31): known rank ordering for at
     least one salience aggregate vs `serp_rank` on synthetic panel.
   - Tests: `test_textrazor_ranking_explainability.py` + new golden test module.

#### Phase 5.7 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Word metrics parsed from `sentences[].words` | 35 | Open |
| Real sense and spelling suggestion scores materialized | 35 | Open |
| Entity salience aggregates on `textrazor_page_metrics` | 36 | Open |
| Top topic/category labels + IAB classifier on main run | 37 | Open |
| Structured phrase/relation/property features beyond counts | 38 | Open |
| `dependency-trees` extractor + syntactic scalars | 39 | Open |
| Entity KB linkage fields in `entities` + page mart | 40 | Open |
| New TextRazor families in `analysis_spec` and `stats_*` | 41 | Open |
| Salience columns in explainability + golden fixture | 42 | Open |
| Limitations: observational; salience ≠ causal ranking factor | 42 | Open |

### Phase 5.75 — BGE Google-like scoring pipeline

Extend the live BGE path beyond single-shot `bge-reranker-v2-m3` on full page
text so similarity features better mirror hybrid search-engine retrieval
(lexical recall + neural rerank). Gemini backends stay separate.

- **Hybrid lexical signal** — add a BM25 or BGE-M3 sparse score per
  `(keyword, page)` and fuse it with the cross-encoder reranker output.
  Normalize lexical and neural scores before fusion (raw BM25 and cosine/rerank
  scales differ). Persist fused score alongside existing `bge` raw/normalized
  fields for Phase 5 OLS comparison.
- **Two-stage retrieve-then-rerank** — first stage: bi-encoder retrieval with
  `BAAI/bge-m3` or `BAAI/bge-large-en-v1.5` (query instruction on keyword
  only for v1.5; documents unmodified). Second stage: rerank the SERP candidate
  set with `BAAI/bge-reranker-v2-m3`. Expose retrieval score, rerank score, and
  optional combined rank for observational analysis against observed Google
  positions.

#### Dev slices

1. **[ ] Slice 1 — Lexical / sparse feature**
   - Implement BM25 (Pyserini or equivalent) or BGE-M3 sparse weights per page.
   - Score normalization and fusion contract with existing `similarity_scores`.

2. **[ ] Slice 2 — Bi-encoder retrieval stage**
   - Embed keyword + page corpus with `bge-m3` or `bge-large-en-v1.5`.
   - Emit dense retrieval score per SERP URL before reranking.

3. **[ ] Slice 3 — Pipeline wiring and tests**
   - Wire retrieve → rerank in CLI live path (`--live-bge`) and curated
     `similarity_scores` schema.
   - Unit tests for score shaping; optional env-gated integration smoke.

### Phase 5.9 — Crash-Safe DataForSEO Persistence and Reuse

Persist validated DataForSEO responses immediately after each request returns,
so a crash leaves behind usable partial data instead of only end-of-run output.
When a new run matches a prior pull by effective request configuration, prompt
the user before reusing the existing DataForSEO data. Matching is based on the
effective config, not raw argv text: compare the seed plus every
request-affecting flag actually used in the run, treating omitted flags as
their effective defaults.

**Primary behavior**

- Save each validated DataForSEO response as soon as it is received.
- Update the run catalog incrementally so crash recovery reflects what is
  already on disk.
- Store provenance for the effective DataForSEO request config, including the
  seed and all request-affecting flags used in the run.
- Treat omitted flags as their effective defaults when comparing a new run to
  prior pulls.
- Prompt the user before reusing matching prior DataForSEO data.
- Fail explicitly in non-interactive mode if reuse would otherwise require a
  prompt.
- Record the reuse decision in run metadata so operators can tell whether a
  run reused prior data or performed fresh pulls.

**Test plan**

- Crash-safety test: simulate failure after the first DataForSEO response and
  verify that the first response is already on disk.
- Reuse-matching test: confirm the effective config is compared by seed plus
  the actual flag set in use.
- Prompt-path test: verify the CLI asks before reusing a matching prior
  DataForSEO pull.
- Non-interactive test: verify matching data does not get reused implicitly.
- Catalog/provenance test: confirm the saved metadata is sufficient to identify
  prior matching pulls.

### Phase 5.91 — Backlinks two-call dofollow correctness

The 2026-07-03 backlinks summary migration (`/v3/backlinks/summary/live`)
shipped `_dofollow_backlinks_count()` deriving "total dofollow backlinks" by
subtracting a fabricated `referring_links_attributes.nofollow` field that
does not exist in real DataForSEO summary responses — every live run
silently persisted `dofollow_backlinks_count = 0`. A true dofollow count
requires a **second, filtered** call to the same endpoint
(`backlinks_filters: ["dofollow", "=", true]`); it cannot be derived from one
unfiltered call. This phase replaces the one-call design with a two-call
design end-to-end: request building, separate raw partitions, curated
merge/null semantics, and an expanded curated schema capturing the fields
DataForSEO actually returns.

**Non-negotiables:** missing dofollow data is `null` (never defaulted to
`0`), the two call variants persist to **separate** raw partitions
(`endpoint=backlinks_summary`, `endpoint=backlinks_dofollow_summary`, not one
partition distinguished only by a metadata tag), and the curated schema is
expanded now rather than deferred.

**Out of scope:** root-domain backlink rollups (this stays page-level, one
row per SERP URL); changing `backlinks_status_type` off `"live"` or
`include_subdomains` off `true`; concurrency changes to DataForSEO request
execution.

**Unblocks:** Phase 6.2 (Backlinks count family and analysis surfacing) —
shipped against the expanded schema and separate
`endpoint=backlinks_summary` / `endpoint=backlinks_dofollow_summary`
partitions.

#### Dev slices

**Progress:** 6 of 6 shipped.

1. **[x] Slice 1 — Request builders, fixtures, and schema (`dataforseo.py`)**
   - `format_backlinks_target()` target-format helper (domain strip vs.
     absolute page URL passthrough); shared `_build_backlinks_base_body()`
     (`target`, `include_subdomains: true`, `backlinks_status_type: "live"`,
     `internal_list_limit: 1000`).
   - `build_backlinks_summary_request()` (renamed from
     `build_backlinks_request`) and `build_backlinks_dofollow_summary_request()`
     both build off the shared base body; the latter layers
     `BACKLINKS_DOFOLLOW_FILTERS`.
   - `fixture_backlinks_response(url, *, dofollow_only=False)` drops the
     fabricated `referring_links_attributes.nofollow` derivation; dofollow
     fixture returns `backlinks=35` directly. New
     `fixture_backlinks_response_for_request_body()` picks the fixture
     variant from a request body's `backlinks_filters`.
   - Restored per-variant `DATAFORSEO_RESPONSE_SCHEMAS["backlinks_summary"]`
     (`target`, `backlinks`, `referring_domains`) and
     `["backlinks_dofollow_summary"]` (`target`, `backlinks`); malformed/missing
     aggregates now hard-fail validation instead of silently coercing to zero.
   - Top-level `response.status_code == 20000` check added to
     `raise_for_failed_dataforseo_tasks()` (shared across all DataForSEO
     endpoints); per-task `cost` logging; exponential-backoff retry in
     `execute_dataforseo_request()` on 429/5xx only, bounded attempts,
     injectable `sleep`.

2. **[x] Slice 2 — Two-call fetch, separate partitions, dedupe key (`cli.py`)**
   - `fetch_dataforseo_backlinks_for_urls()` takes a `variants` sequence
     (default: both) and issues one request per `(url, variant)`, tagging
     full request metadata (`target`, `variant`, `include_subdomains`,
     `backlinks_status_type`, `internal_list_limit`, `backlinks_filters`
     when present).
   - `backlink_raw_response_key()` is now a `(target_keyword, url, variant)`
     3-tuple (previously 2-tuple) — the critical fix preventing one variant
     from silently overwriting the other in
     `merge_backlink_raw_response_rows()` / `rewrite_backlink_endpoint_partition()`;
     missing `variant` defaults to `"summary"` for legacy rows.
   - `persist_backlink_raw_responses()` splits records by endpoint and writes
     each to its own partition directory
     (`endpoint=backlinks_summary`, `endpoint=backlinks_dofollow_summary`).
   - Resume/backfill (`build_resumed_keyword_result`) now tracks existing
     `(url, variant)` pairs and fetches only the missing variant(s) per URL,
     not always both.
   - `raw_provider_data["dataforseo"]` carries two collections
     (`backlinks_summary`, `backlinks_dofollow_summary`) everywhere a
     keyword result's provider data is built, merged, or replayed
     (`build_keyword_result_from_responses`, `build_raw_response_records`,
     `merge_stored_run_cli_overlay`, textrazor-only/offline payload builders).

3. **[x] Slice 3 — Curated merge, expanded schema, null semantics (`normalize.py`)**
   - `build_backlinks_frame()` groups raw records from both partitions (plus
     legacy `endpoint=backlinks` rows, read-compatibly as the summary
     variant) by `(target_keyword, url)` and emits one curated row per URL.
   - `backlinks_count` / `referring_domains_count` come from the summary
     variant; `dofollow_backlinks_count` comes directly from the dofollow
     variant's `backlinks` field (no subtraction). When the dofollow variant
     is absent: `dofollow_backlinks_count = null`,
     `backlinks_metrics_complete = false`.
   - Curated schema gains: `rank`, `backlinks_spam_score`,
     `target_spam_score`, `new_backlinks`, `lost_backlinks`,
     `new_referring_domains`, `lost_referring_domains`, `referring_pages`,
     `referring_main_domains`, `referring_ips`, `referring_subnets`,
     `broken_backlinks`, `broken_pages`, `referring_domains_nofollow`,
     `crawled_pages`, `internal_links_count`, `external_links_count`,
     `first_seen`, `lost_date`, `dofollow_referring_domains_count`,
     distribution maps as JSON-string columns (`referring_links_types_json`,
     `referring_links_tld_json`, `referring_links_platform_types_json`,
     `referring_links_semantic_locations_json`,
     `referring_links_attributes_json`, `referring_links_countries_json`),
     and traceability (`summary_response_id`, `dofollow_summary_response_id`,
     `backlinks_metrics_complete`).
   - Drops `_dofollow_backlinks_count()`'s items-loop and
     `referring_links_attributes` subtraction path entirely.

4. **[x] Slice 4 — Tests (TDD)**
   - Request builders: exact unfiltered/dofollow bodies; target-format rules.
   - Response handling: top-level and task-level failure surfacing; cost
     logging; retry fires only on retryable errors, succeeds on 2nd attempt.
   - Raw persistence: separate partitions; dedupe key includes `variant`
     (fix `test_raw_response_merge.py`); resume fetches only missing
     variants; mid-loop failure preserves completed rows (3 URLs, failure on
     URL 3 → 4 rows persisted).
   - Normalization: paired responses → one curated row with all three counts
     plus expanded columns; missing dofollow → `null` +
     `backlinks_metrics_complete = false` (remove any test asserting `0`);
     malformed aggregates hard-fail; distribution maps serialize to JSON.
   - Update stale `test_validate_dataforseo_response_accepts_backlinks_live_shape`
     and siblings in `test_dataforseo_requests.py` to real new-shape fields.
   - CLI: exactly 2 summary calls per SERP URL (3 URLs → 6 calls, 6 raw rows
     split across two partitions); zero calls to `/v3/backlinks/backlinks/live`.

5. **[x] Slice 5 — Docs**
   - Updated `README.md`, `ROADMAP.md` backlog/history, `ARCHITECTURE.md`, and
     `TESTING.md`: two-call pattern (`2 calls × N` SERP URLs), separate
     `endpoint=backlinks_summary` / `endpoint=backlinks_dofollow_summary`
     partitions, ~$0.04/target, null dofollow semantics.

6. **[x] Slice 6 — Verification**
   - Targeted backlinks test run, then full `tests/unit` suite (offline; green).
   - Manual `--live-providers` trace with real DataForSEO credentials (operator
     step; not CI-runnable): confirm 2 raw records per URL across the two
     partitions and 1 correct curated row per URL. Offline `--dry-run` path is
     covered by the unit suite.

**Implementation order:** Slice 1 → Slice 2 → Slice 3 (each depends on the
previous). Slice 4 can start once Slice 1 lands and grows alongside Slices
2–3. Slice 5 after Slice 3. Slice 6 last.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Dofollow count sourced from a real filtered call, never fabricated | 1, 3 | Shipped |
| Raw variants land in separate `endpoint=` partitions | 1, 2 | Shipped |
| Dedupe key prevents one variant overwriting the other | 2 | Shipped |
| Resume fetches only missing variant(s) per URL | 2 | Shipped |
| Curated row has expanded columns + null/`backlinks_metrics_complete` semantics | 3 | Shipped |
| Tests cover request bodies, persistence, normalization, and CLI call counts | 4 | Shipped |
| Docs describe the two-call pattern and cost | 5 | Shipped |
| Full unit suite green | 6 | Shipped |

### Phase 6 — Workflow Integrity Guardrails

Standard:

> A logical run is complete only when every required accounting unit has a permitted terminal disposition at each applicable boundary, proven from committed artifacts with valid provenance.

First-pass scope: enforce the highest-risk path only:

- expansion → SERP collection
- raw provider responses → curated records
- stored-run / retry provenance on reused committed artifacts

Later boundaries (`curated → feature marts`, `feature marts → analysis_mart`,
`analysis_mart → stats artifacts`) must still be registered, but start as
`deferred` until the control model is implemented there.

#### Dev slices

1. **[ ] Slice 1 — Contract registry and boundary coverage**
   - Add planned artifact: `workflow_contracts.v1.yaml`.
   - Register every executable stage transition with:
     `boundary_id`, `contract_version`, `owner`, `status`,
     `accounting_unit`, `relation`, `input_selector`, `output_selector`,
     `terminal_dispositions`, `reconciliation_equation`,
     `validation_point`, `mode_policies`, `provenance_requirements`,
     `empty_result_policy`, `failure_policy`, and `compatibility_policy`.
   - Fail CI when a stage exists without a contract or a contract row maps to
     no real transition.

2. **[ ] Slice 2 — Run identity, provenance, and reuse semantics**
   - Treat current `run_id` as the compatibility-era `logical_run_id`.
   - Add planned provenance fields:
     `execution_id`, `artifact_id`, `input_snapshot_id`,
     `source_execution_id`, `contract_version`.
   - Define fresh-run, stored-run, retry/resume, and dry-run reuse rules by
     contract mode rather than hard-coded `run_id` equality.

3. **[ ] Slice 3 — Stage state model and atomic commit semantics**
   - Stage lifecycle: `planned → running → materialized → reconciled → committed`;
     terminal failure = `failed_final`.
   - Record stage start before work begins.
   - Reconcile staged outputs before commit/promote.
   - Downstream stages read committed artifacts only.

4. **[ ] Slice 4 — Artifact-derived reconciliation engine**
   - Audit from committed artifacts plus `workflow_contracts.v1.yaml`, not from
     stage self-reported counts.
   - Per boundary derive:
     distinct input count, distinct matched count, duplicate count,
     unexplained gap count, canonical ID digest, sampled missing/unexpected IDs,
     provenance compatibility, and contract-version compatibility.
   - Missing declared boundary entries or open `running` stages fail closed.

5. **[ ] Slice 5 — High-risk boundary enforcement v1**
   - Enforce `expansion → SERP`, `raw_responses → curated`, and provenance
     checks for reused committed artifacts on those boundaries.
   - Register but defer `curated → feature marts`, `feature marts → analysis_mart`,
     and `analysis_mart → stats artifacts`.

6. **[ ] Slice 6 — Exception policy and terminal disposition rules**
   - Supported terminal states:
     `produced`, `skipped`, `deferred`, `failed_final`.
   - Allowed empty / skip declarations require:
     `owner`, `reason_code`, `scope`, `max_volume`, `retry_required`,
     and `review_by`.
   - Default v1 policy: any required `deferred` unit blocks completion; any
     required `failed_final` unit fails the run.

7. **[ ] Slice 7 — Verification strategy and regression fixtures**
   - Planned tests:
     contract-schema tests, contract-coverage tests, reconciliation tests,
     provenance tests, partial-write and commit-failure tests,
     silent-failure regression fixtures, and targeted mutation-style guards.
   - Required regressions:
     keyword expanded but SERP never fetched; stage omitted entirely; ledger
     says success but committed artifact missing; stale artifact reused; partial
     stored-run expansion leaves unexplained gaps.

8. **[ ] Slice 8 — Operational metrics and alert surfaces**
   - Emit and surface:
     reconciliation gap count, zero-output required boundaries,
     stale-provenance rejection, skip-rate spikes, retry exhaustion,
     missing committed artifacts, and contract-version mismatch.
   - A green run with a nonzero unexplained gap must be impossible.

#### Phase 6 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `workflow_contracts.v1.yaml` defines every executable boundary | 1 | Open |
| Contract rows map one-to-one with executable stage transitions | 1 | Open |
| Provenance compatibility is defined separately from raw `run_id` equality | 2 | Open |
| Staged outputs reconcile before promotion to committed artifacts | 3, 4 | Open |
| Reconciliation is artifact-derived, not ledger-derived | 4 | Open |
| First-pass enforcement covers `expansion → SERP` and `raw_responses → curated` | 5 | Open |
| Required `deferred` or `failed_final` units prevent green completion | 6 | Open |
| Silent completeness failures are reproduced by regression fixtures | 7 | Open |
| Gap, provenance, skip, and commit metrics are visible operationally | 8 | Open |

### Phase 6.1 — OLS / Plackett-Luce standardization and reporting

Complete the standardization track for pooled OLS and page-level Plackett-Luce:
close post-ship scaling polish (FIXUPS S5-14–S5-18), finish Plackett-Luce estimand
runtime wiring (Phase 5 Slice 15 partial), add `analysis_mart.v2` relative rank
columns (Slices 11–12), wire robustness-only stats on rank/pct/z predictors (Slice
13), and surface relative ranks in CLI reports (Slice 14). **Primary confirmatory
estimand unchanged:** absolute `*_normalized_score`, keyword-level Spearman, pooled
OLS and PL on raw scores.

**Shipped baseline (Jul 2026):** both paths share
`within_keyword_sd_rms()` in `src/seo_rank/stats/scale.py` for post-hoc per-1-SD
effect reporting (`effect_size.approximate_delta_rank_per_1sd` in OLS;
`log_odds_per_1sd` / `odds_ratio_per_1sd` in PL). Models still fit on raw
similarity scores; z-score helpers in `scale.py` are tested but not wired to
production paths yet.

**Out of scope for 6.1:** fitting Plackett-Luce on z-scored predictors; changing
the primary estimand or BH policy; passage-level Plackett-Luce.

**Also in 6.1 (reporting):** expanded `report.md` sections for observational
limits and top-20 censoring; generated `runs/{run_id}/` trees remain out of
source control (layout ships in Phase 4.5).

#### Dev slices

**Progress:** 0 of 7 shipped, 2 partial (Slice 15 + Slice 3 from Phase 5 Slice 11).

1. **[ ] Slice 1 — Scaling polish (FIXUPS S5-14–S5-18)**
   - Update `analysis_spec.v1.yaml` `effect_size.note` to document RMS of
     per-keyword SDs (`within_keyword_sd_rms`), not pooled panel SD.
   - Expand `scale.py` module docstring: production uses `within_keyword_sd_rms`;
     `within_keyword_zscore` / `global_zscore` are prep for Slices 3–4.
   - `regression.py`: pass `fit.score_column` into `_two_way_cluster_sensitivity()`
     instead of `exog_names[1]`.
   - `plackett_luce.py`: document IIA subset refit scaling (`reference_similarity_sd`
     from main fit); add diagnostics field e.g.
     `scaling_reference: main_fit_similarity_within_keyword_sd`.
   - `test_stats_spec.py`: assert `stats.scale` export.
   - New `test_stats_scaling_contract.py`: same panel → OLS and PL report identical
     `similarity_within_keyword_sd`.

2. **[~] Slice 2 — Plackett-Luce estimand runtime wiring (Phase 5 Slice 15)**
   - **Done:** `estimand.plackett_luce` YAML block; depth `max_rank` from spec;
     PL fit, diagnostics, IIA, artifact emission (`test_stats_plackett_luce.py`).
   - **Remaining**
     - Add `convergence` thresholds to YAML (`hessian_condition_number_threshold`,
       `optimizer_gradient_tolerance`).
     - `AnalysisSpec` typed accessors for `estimand.plackett_luce`.
     - Replace hardcoded constants in `plackett_luce.py` with spec-driven settings.
     - Drive IIA from `estimand.plackett_luce.iia_sensitivity`, not
       `depth_key == spec.primary_rank_depth` in `artifacts.py`.
     - Tests: spec threshold edits change runtime convergence / IIA behavior.
   - FIXUPS **S5-19**.

3. **[~] Slice 3 — Within-keyword rank transform (Phase 5 Slice 11)**
   - **Done:** `src/seo_rank/data/ranks.py` with Polars-lazy
     `add_within_keyword_similarity_ranks()`; per backend within
     `target_keyword_id`: `{backend}_similarity_rank`, `{backend}_similarity_pct`,
     `{backend}_similarity_z` (BGE ranks on `bge_raw_score`; Gemini on
     `*_normalized_score`). Tests: `tests/unit/test_within_keyword_ranks.py`.
   - **Remaining:** wire into `marts.py` and `analysis_mart.v2` (Slice 4).

4. **[ ] Slice 4 — Analysis mart v2 columns (Phase 5 Slice 12)**
   - Wire rank transform in `marts.py`; bump `schema_version` to `analysis_mart.v2`.
   - Extend `FEATURE_VALIDATION_RULES`, `ANALYSIS_REQUIRED_COLUMNS`, bounded
     columns (`similarity_rank` 1–20, `similarity_pct` 0–1) in `features.py`.
   - Nine new columns (3 backends × rank/pct/z); absolute score columns unchanged.
   - Tests: `test_analysis_mart_ranks.py`; stats fixtures may stay on v1 for
     primary-path tests.

5. **[ ] Slice 5 — Relative similarity stats sensitivity (Phase 5 Slice 13)**
   - Add `sensitivity.relative_similarity` to `analysis_spec.v1.yaml` (column names
     per backend; `robustness_only: true`).
   - New `src/seo_rank/stats/sensitivity.py`: Spearman on `*_similarity_rank`;
     pooled OLS refits on `*_similarity_z` and `*_similarity_pct` (keyword FE +
     length + clustered SEs); skip gracefully on `analysis_mart.v1`.
   - Wire `relative_similarity_sensitivity` into `stats_diagnostics.json` per rank
     depth; append limitation text (relative ranks within observed top-N SERP only).
   - Not used for `actionable_association` or BH.
   - Tests: `test_stats_relative_similarity.py`.

6. **[x] Slice 6 — Relative ranks in CLI and fixtures (Phase 5 Slice 14)**
   - `emit_keyword_analysis` / `report.md`: show rank/pct (optional z) alongside
     absolute scores; sort Page Similarity by `{primary_backend}_similarity_rank`.
   - Extend golden `analysis_mart` with relative columns and known rank invariants.
   - Rebuild on stored runs derives relative columns from absolutes without
     re-scoring.

7. **[ ] Slice 7 — Docs and FIXUPS closure**
   - Mark FIXUPS S5-14–S5-19 `done`; sync `TESTING.md` / `test_sdlc_docs.py` test
     counts (S5-12).
   - Cross-link `GOALS.md`, `ARCHITECTURE.md`, `FIXUPS.md`.

**Implementation order:** Slice 1 and Slice 2 can land in parallel. Slice 3 →
Slice 4 → Slice 5 (mart columns required before sensitivity). Slice 6 after
Slice 4. Slice 7 last.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `effect_size.note` documents `within_keyword_sd_rms` | 1 | Open |
| OLS / PL share `similarity_within_keyword_sd` on same panel | 1 | Open |
| `estimand.plackett_luce` drives runtime thresholds and IIA | 2 | Partial |
| `analysis_mart.v2` rank/pct/z columns materialized | 3, 4 | Open |
| `relative_similarity_sensitivity` in diagnostics JSON | 5 | Open |
| CLI keyword report surfaces relative ranks | 6 | Open |
| FIXUPS S5-14–S5-19 closed | 1, 2, 7 | Open |

### Phase 6.2 — Backlinks count family and analysis surfacing

Build a single backlinks-count signal family on top of the existing
`analysis_mart` panel. This phase uses the curated backlinks counts already
normalized from the DataForSEO backlinks endpoint, keeps `analysis_mart.v1` as
the panel contract, and adds one family with three signals:
`backlinks_count`, `referring_domains_count`, and
`dofollow_backlinks_count`. The goal is to make backlinks a first-class analysis
path without splitting it into multiple families or bumping the panel schema.

**Out of scope for 6.2:** a separate referring-networks metric,
`analysis_mart.v2`, or any new rank-depth contract. If exact network counts are
needed later, they belong to the dedicated Backlinks API endpoint, not this
family.

**Depends on Phase 5.91:** the raw response storage path is split across
`raw_responses/endpoint=backlinks_summary` and
`raw_responses/endpoint=backlinks_dofollow_summary` (legacy
`endpoint=backlinks` remains read-compatible on normalize), and
`dofollow_backlinks_count` is `null` when the dofollow variant is missing.

**Implementation note:** backlinks count signals live on a separate
`backlinks_analysis` feature mart (`analysis_mart` panel grain plus curated
`backlinks` columns). `analysis_mart.v1` stays similarity-only; stats load
`backlinks_analysis` via the `backlinks_metric` source-mart mapping in
`families.py`.

#### Dev slices

**Progress:** 4 of 4 shipped.

1. **[x] Slice 1 — Panel contract and feature validation**
   - Materialize `backlinks_analysis` from `analysis_mart` + curated
     `backlinks` with bounded non-negative validation on count columns
     (`dofollow_backlinks_count` nullable).
   - Keep `schema_version` on `analysis_mart.v1`; `backlinks_analysis` uses
     `feature_marts.v1`.
   - Raw response storage remains under
     `raw_responses/endpoint=backlinks_summary` and
     `raw_responses/endpoint=backlinks_dofollow_summary`.

2. **[x] Slice 2 — Backlinks signal family registry**
   - One registry entry, `backlinks_counts`, with kind `backlinks_metric`
     and the three backlinks count columns.
   - `src/seo_rank/stats/families.py` and `analysis_spec.v1.yaml` load the
     family without a second backlinks family.
   - Family ordering keeps all three count signals in one family block for
     reports and BH scope.

3. **[x] Slice 3 — Family-aware stats and reporting**
   - Backlinks family wired into `spearman`, `regression`, `diagnostics`, and
     Plackett-Luce artifact generation via `backlinks_analysis` source mart.
   - `stats_summary.json`, `stats_diagnostics.json`, and `stats_report.md`
     surface `#### Family: backlinks_counts` with all three signals together.

4. **[x] Slice 4 — Fixtures and regressions**
   - `test_feature_marts.py` covers `backlinks_analysis` materialization and
     validation; `test_stats_family_artifacts.py` covers combined `stats_*`
     output for the backlinks family.
   - Raw partition CLI regressions shipped in Phase 5.91 (`test_cli_run.py`);
     `ensure_feature_marts_for_analysis` requires `backlinks_analysis` and
     `onpage_features` before analyze; `run_phase5_stats` calls the same guard so
     legacy run trees cannot silently skip OnPage families.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `analysis_mart.v1` unchanged; backlinks counts on `backlinks_analysis` without panel schema bump | 1 | Shipped |
| One backlinks family (`backlinks_counts`) is registered | 2 | Shipped |
| Family-aware stats emit backlinks blocks in `stats_*` | 3 | Shipped |
| Mart materialization + stats regressions cover backlinks analysis path | 4 | Shipped |

### Phase 7 — DataForSEO datapoint expansion

Widen the factor set with DataForSEO data already paid for but unused:
on-page content/CWV/structured-data signals, backlink quality and
anchor-relevance (not just counts), backlink velocity, domain authority,
domain technology/age, and SERP feature presence. Every new source is
**additive** — new signal families and feature marts, no `analysis_mart`
schema bump — raw-persisted to disk immediately per call (DataForSEO Live
endpoints are not retained provider-side), backfillable onto existing runs
via `run --stored-run` without refetching unrelated data, and covered by
offline fixtures before any live wiring. Partial/missing per-source data is
represented as null (mirrors `dofollow_backlinks_count` /
`backlinks_metrics_complete`), never as a fetch failure — a run missing one
new source must still produce full stats for every other family.

**Depends on Phase 6.2:** reuses the `backlinks_metric` family kind and
`backlinks_analysis` mart pattern established there.

**Shared implementation pattern per source** (apply once per sub-phase, not
restated per slice): (1) client module — request builder(s), a response
schema table (new `DATAFORSEO_RESPONSE_SCHEMAS` entries for DataForSEO
endpoints in `dataforseo.py`), one `fixture_*_response()`, offline
request/schema tests, no live wiring yet; (2) fetch + partial-durability
persistence — a `fetch_<source>_for_*` function building raw records via
`build_raw_response_record(..., endpoint="<partition>")`, persisted in a
`finally:` block so a mid-batch crash keeps prior progress (copy
`fetch_dataforseo_backlinks_for_urls` / `persist_backlink_raw_responses` in
`cli.py`, including the dedupe key and `refresh_run_json_raw_response_catalog`);
(3) live-run wiring alongside the existing backlinks fetch so new runs
collect the source automatically; (4) `--stored-run` backfill — extend
`expand_stored_run` / `build_resumed_keyword_result`'s reuse-check (mirrors
`_register_usable_backlink_response`) so only missing URLs/domains are
(re)fetched; this is the **one** general backfill mechanism for every source
in this phase, not a per-source CLI flag; (5) curated builder in
`data/normalize.py`, feature mart entry in `data/features.py` joined on the
correct grain (URL sources join like `backlinks_analysis` on
`["run_id","target_keyword_id","canonical_url_hash","url"]`; domain sources
derive `domain` the way `domain_features` does), a new family `kind` in
`stats/families.py` (`VALID_SIGNAL_FAMILY_KINDS` + `SOURCE_MART_BY_KIND`),
and a family block appended (never reordered) to
`analysis_spec.v1.yaml` `signal_families.families`; (6) artifacts wiring
(spearman/regression/diagnostics/Plackett-Luce per new family) plus golden
fixtures and a stored-run regression proving only the missing source gets
(re)fetched.

#### 7.1 — OnPage page signals (`on_page/instant_pages`)

URL grain (`canonical_url_hash` + `url`), one synchronous live call per SERP
URL with `enable_javascript`, `enable_browser_rendering`, `load_resources`,
and `validate_micromarkup: true` all set on the same request — structured-data
validation rides along in one call, no separate `on_page/microdata` endpoint
or task id needed, and no `task_post` crawl/poll flow.

##### Dev slices

**Progress:** 18 of 18 shipped.

1. **[x] Slice 1 — Request/schema/fixture** — `build_onpage_instant_pages_request()`,
   `DATAFORSEO_RESPONSE_SCHEMAS["onpage_instant_pages"]`,
   `fixture_onpage_instant_pages_response()` in `dataforseo.py`.
2. **[x] Slice 2 — Offline tests** — request shape, schema-accept, schema-drift
   rejection, null/missing optional sections, required-leaf parity cases in
   `tests/unit/test_dataforseo_requests.py`.
3. **[x] Slice 3 — Fetch + persistence** — `fetch_onpage_signals_for_urls` in
   `cli.py`, one call per unique `(target_keyword, url)`, persisted to
   `raw_responses/endpoint=onpage_instant_pages`. Copy
   `fetch_dataforseo_backlinks_for_urls` / `persist_backlink_raw_responses`:
   `execute_validated_dataforseo_request("onpage_instant_pages", …)` with
   `build_onpage_instant_pages_request(url)`, dedupe key `(target_keyword, url)`,
   `build_raw_response_record(..., endpoint="onpage_instant_pages")`, partial
   batch persistence in a `finally:` block, request metadata
   (`target_keyword`, `url`, rendering/micromarkup flags). Tests in
   `tests/unit/test_cli_run.py` and `tests/unit/test_raw_response_merge.py`.
4. **[x] Slice 4 — Live-run wiring** — call alongside the existing backlinks
   fetch in the live keyword-result build path. Filter to missing
   ``(target_keyword, url)`` pairs before calling
   ``fetch_onpage_signals_for_urls``; the fetch helper does not dedupe its
   ``urls`` input, so the call site must guarantee uniqueness to avoid duplicate
   live API calls (mirrors backlinks missing-url filtering ~1166–1174).
   Wired into `build_live_keyword_result`, `build_resumed_keyword_result`
   (missing-URL overlay), `build_keyword_result_from_responses`,
   `build_live_payload`, `expand_stored_run`, and `build_raw_response_records`.
   Tests in `tests/unit/test_cli_run.py`.
5. **[x] Slice 5 — Stored-run backfill** — reuse-check parity for the
   `onpage_instant_pages` partition inside `build_resumed_keyword_result`
   (`_usable_onpage_by_url_from_records`, `_missing_serp_urls`); backfill only
   missing SERP URLs when `--stored-run --live-providers`. Empty schema-valid
   rows (`result: null`, no page items) are **not** reusable (unlike backlinks
   empty summaries). CLI regressions in `tests/unit/test_cli_run.py`.
6. **[x] Slice 6 — Curated builder** — `build_onpage_signals_frame` in
   `normalize.py`: URL-grain `parquet/onpage_signals` with `onpage_score`, 12
   check booleans, content/readability metrics, CWV timing, `total_transfer_size`,
   and microdata summary (`micromarkup_*` counts when nested object present,
   `has_valid_structured_data` derived from `has_micromarkup*` flags). Skips
   unusable empty raw rows; dedupes by `(target_keyword, url)` on latest
   `timestamp` with `response_id` tie-break. Tests in
   `tests/unit/test_run_normalize.py`.
7. **[x] Slice 7 — Feature mart** — `onpage_features`, URL-grain join of
   curated `onpage_signals` onto the `analysis_mart` panel
   (`build_feature_lazyframes` left join on
   `run_id`, `target_keyword_id`, `canonical_url_hash`, `url`); bounded
   validation (`onpage_score` 0–100, non-negative counts/timing). Tests in
   `tests/unit/test_feature_marts.py`.
8. **[x] Slice 8 — Family registry + stats source wiring** — new kind `onpage_metric` mapped to
   `onpage_features` in `stats/families.py`; three families appended to
   `analysis_spec.v1.yaml`: `onpage_content_quality` (score + readability),
   `onpage_core_web_vitals` (TTFB, LCP, CLS, transfer size),
   `onpage_technical_checks` (12 SEO/tech booleans + structured-data summary).
   `build_family_source_frames()` loads `onpage_features` when the mart partition
   exists; boolean predictors are coerced to 0/1 before pooled OLS. Registry/spec
   tests in `test_stats_families.py` and `test_stats_spec.py`; integration in
   `test_stats_family_artifacts.py`.
9. **[x] Slice 9 — Artifacts follow-ups** — family Plackett-Luce enabled for
   `onpage_metric` with shared-prep perf refactor (`FAMILY_PLACKETT_LUCE_OPTIMIZER_OPTIONS`,
   zero-variance fast skip), `ensure_feature_marts_for_analysis()` in
   `data/features.py` (requires `onpage_features`; rebuilds when `run.json`
   exists), same guard from `run_phase5_stats()` for legacy upgrade paths,
   golden contract + hard-fail OnPage assertions.
10. **[x] Slice 10 — Fix `meta.content`/CLS nesting bug + schema/fixture
    correction.** Fix `_onpage_signals_row` to read `item["meta"]["content"]`
    and `item["meta"]["cumulative_layout_shift"]` (keep the existing
    item-top-level fallback for backward compatibility with any
    already-persisted raw rows that used the flat shape, but prefer nested).
    Correct `fixture_onpage_instant_pages_response` to nest `content` and
    `cumulative_layout_shift` under `meta`, matching the real payload. Update
    `DATAFORSEO_RESPONSE_SCHEMAS["onpage_instant_pages"]` field-schema entries
    in `normalize.py:117-156` accordingly. Regression test asserting the
    readability/CLS fields populate from a fixture shaped like the real
    response (nested), not just the old flat shape.
11. **[x] Slice 11 — Expand `checks` coverage.** Grow
    `ONPAGE_CURATED_CHECK_FIELDS` (`normalize.py:52-65`) from 12 to the full
    46-field set: `deprecated_html_tags`, `duplicate_title_tag`, `flash`,
    `frame`, `from_sitemap`, `has_html_doctype`, `has_meta_refresh_redirect`,
    `has_micromarkup`, `has_micromarkup_errors`, `high_character_count`,
    `high_content_rate`, `high_loading_time`, `high_waiting_time`,
    `https_to_http_links`, `irrelevant_meta_keywords`, `irrelevant_title`,
    `is_4xx_code`, `is_5xx_code`, `is_broken`, `is_redirect`, `is_www`,
    `large_page_size`, `lorem_ipsum`, `low_content_rate`,
    `meta_charset_consistency`, `no_content_encoding`, `no_doctype`,
    `no_encoding_meta_tag`, `no_favicon`, `no_image_alt`, `no_image_title`,
    `seo_friendly_url`, `size_greater_than_3mb`, `small_page_size`. Extend
    `CURATED_SCHEMAS["onpage_signals"]` and `CURATED_VALIDATION_RULES` with the
    new boolean columns. `_optional_onpage_check_bool()` reads `checks` first
    and falls back to item-level flags for `has_micromarkup`,
    `has_micromarkup_errors`, and `from_sitemap`. Tests in
    `tests/unit/test_run_normalize.py`.
12. **[x] Slice 12 — `meta` block metrics.** Add columns to
    `onpage_signals`/curated schema for: `description_length`,
    `title_length`, `external_links_count`, `internal_links_count`,
    `images_count`, `images_size`, `scripts_count`, `scripts_size`,
    `stylesheets_count`, `stylesheets_size`,
    `render_blocking_scripts_count`, `render_blocking_stylesheets_count`,
    `follow` (bool), `inbound_links_count`, `duplicate_meta_tags_count`
    (array length), and the 3 consistency scores from `meta.content`
    (`description_to_content_consistency`, `title_to_content_consistency`,
    `meta_keywords_to_content_consistency`). New helper
    `_optional_mapping_len` for array-length counts (`duplicate_meta_tags`,
    `htags.h1/h2/h3`, reused by Slice 13). Tests in
    `tests/unit/test_run_normalize.py`.
13. **[x] Slice 13 — `htags` counts + `social_media_tags` presence flags.**
    Add `h1_count`/`h2_count`/`h3_count` (derived from `meta.htags` array
    lengths; heading text itself stays out of scope) and
    `has_og_tags`/`has_twitter_tags` (boolean presence of any `og:*`/
    `twitter:*` key in `meta.social_media_tags`; tag values are not stored,
    since title/description/canonical are already captured elsewhere).
    Tests in `tests/unit/test_run_normalize.py`.
14. **[x] Slice 14 — Resource/cache/DOM/size metrics.** Add columns for
    `cache_control.cachable`, `cache_control.ttl`, `resource_errors_count`
    and `resource_warnings_count` (lengths of the `errors`/`warnings`
    arrays), `broken_links`, `broken_resources`, `duplicate_content`,
    `duplicate_description`, `duplicate_title`, `click_depth`,
    `encoded_size`, `total_dom_size`. Tests in
    `tests/unit/test_run_normalize.py`.
15. **[x] Slice 15 — Full `page_timing` expansion.** Add the remaining
    timing columns beyond the existing TTFB/LCP/CLS:
    `connection_time`, `time_to_secure_connection`, `request_sent_time`,
    `download_time`, `duration_time`, `fetch_end`, `dom_complete`,
    `time_to_interactive`, `first_input_delay`. Tests in
    `tests/unit/test_run_normalize.py`.
16. **[x] Slice 16 — Feature mart + bounded validation.** Extend
    `ONPAGE_FEATURES_EXTRA_COLUMNS`/`ONPAGE_FEATURES_EXPECTED_SCHEMA`/
    `ONPAGE_FEATURES_BOUNDED_COLUMNS` (`features.py:444-487`) to carry all
    new columns (Slices 11-15) into `onpage_features` (non-negative bounds
    on new numeric/count/size/timing columns; new booleans unbounded).
    Tests in `tests/unit/test_feature_marts.py`.
17. **[x] Slice 17 — Analysis family wiring for new fields.** Extend the
    three existing `onpage_metric` families in `analysis_spec.v1.yaml` (or
    add a 4th, e.g. `onpage_resource_profile`, if the existing three don't
    fit thematically): link/image/script/DOM/size metrics and new technical
    booleans into a technical/structural family, timing extensions into
    `onpage_core_web_vitals`, consistency scores into
    `onpage_content_quality`. No `analysis_mart` schema bump, mirroring
    Slice 8. Tests in `test_stats_families.py`/`test_stats_spec.py`.
18. **[x] Slice 18 — Fixtures and regressions** — stored-run end-to-end
    regression, full-layer CLI pipeline tests beyond analyze/mart guards,
    now covering the full expanded field set including the corrected nested
    `meta.content`/CLS shape.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| OnPage instant_pages request/schema/fixture | 1 | Shipped |
| Offline request/schema tests | 2 | Shipped |
| Fetch + raw partition persistence | 3 | Shipped |
| Live-run wiring | 4 | Shipped |
| Stored-run backfill (OnPage partition only) | 5 | Shipped |
| Curated `onpage_signals` | 6 | Shipped |
| Feature mart `onpage_features` | 7 | Shipped |
| Three `onpage_metric` families; no `analysis_mart` schema bump | 8 | Shipped |
| Full family stats + legacy `onpage_features` rebuild on analyze | 9 | Shipped |
| Fix `meta.content`/CLS nesting bug + fixture correction | 10 | Shipped |
| Full `checks` coverage (46 booleans) | 11 | Shipped |
| `meta` block metrics (links/images/scripts/stylesheets/consistency) | 12 | Shipped |
| `htags` counts + `social_media_tags` presence flags | 13 | Shipped |
| Resource/cache/DOM/size metrics | 14 | Shipped |
| Full `page_timing` expansion | 15 | Shipped |
| Feature mart + bounded validation for new columns | 16 | Shipped |
| Analysis family wiring for new fields | 17 | Shipped |
| Stored-run regression + full-layer CLI tests | 18 | Shipped |

#### 7.2 — Backlink quality & anchor relevance (`backlinks/backlinks/live`)

URL grain. One call per SERP URL, `mode: one_per_domain`, `limit: 100`,
`order_by` on `rank` descending. Anchor-text relevance is derived from the
`anchor` field already on this response — the dedicated
`backlinks/anchors/live` endpoint is skipped as redundant, cutting an entire
API source.

##### Dev slices

**Progress:** 5 of 9 shipped.

1. **[x] Slice 1 — Request/schema/fixture** — `build_backlinks_detail_request()`,
   `BACKLINKS_QUERY_DETAIL` variant, `DATAFORSEO_RESPONSE_SCHEMAS["backlinks_detail"]`,
   `fixture_backlinks_detail_response()` in `dataforseo.py`. Offline request/schema
   tests in `tests/unit/test_dataforseo_requests.py`.
2. **[x] Slice 2 — Offline tests.** Covered alongside Slice 1
   (`test_dataforseo_requests.py`) and Slices 4/5 (`test_cli_run.py`).
3. **[x] Slice 3 — Fetch + persistence.** Folded into the existing
   `fetch_dataforseo_backlinks_for_urls` variant loop rather than a standalone
   function — `BACKLINKS_QUERY_DETAIL` added to `BACKLINKS_VARIANT_ENDPOINTS` /
   `BACKLINKS_VARIANT_PROVIDER_DATA_KEYS`, persisted to
   `raw_responses/endpoint=backlinks_detail` alongside the summary/dofollow
   variants. `backlinks_detail_response_is_usable()` gates persistence
   (accepts `backlinks_response_is_successful_empty`).
4. **[x] Slice 4 — Live-run wiring.** `detail` variant fetched live in the same
   pass as `summary`/`dofollow`, gated behind the opt-in `--live-backlinks-detail`
   flag (requires `--live-backlinks`) so the extra per-URL API call stays
   explicit; `build_live_payload` iterates `BACKLINKS_VARIANT_PROVIDER_DATA_KEYS`
   generically. Regressions:
   `test_run_live_backlinks_detail_flag_fetches_and_persists_detail`,
   `test_run_live_backlinks_without_detail_flag_skips_detail`,
   `test_run_live_backlinks_detail_requires_live_backlinks`.
5. **[x] Slice 5 — Stored-run backfill** for `backlinks_detail`. New
   `_backlinks_variants_for_replay()` replays `detail` when the
   `--live-backlinks-detail` opt-in is set (`config.live_backlinks_detail`)
   OR when a `backlinks_detail` raw partition / `raw_provider_data` key already
   exists for that stored run. The opt-in path is what enables true legacy
   backfill: an older run that only ever fetched `summary`/`dofollow` gets
   `detail` fetched for all missing URLs on resume, without refetching the
   complete `summary`/`dofollow` variants. Regressions:
   `test_run_stored_run_backfills_legacy_backlinks_detail_via_opt_in` (legacy
   opt-in path) and
   `test_run_stored_run_backfills_only_missing_backlinks_detail_in_place`
   (in-place completion of an existing partition) in `test_cli_run.py`.
6. **[ ] Slice 6 — Curated builder** — `build_backlink_details_frame`: one row
   per `(run_id, target_keyword_id, canonical_url_hash, backlink_id)` with
   `domain_from_rank`, `page_from_rank`, `backlink_spam_score`, `anchor`,
   `dofollow`, `tld_from`, `domain_from_country`, `first_seen`.
7. **[ ] Slice 7 — Aggregation feature mart** — `backlink_quality_features`
   grouped back to URL grain: `avg_domain_from_rank`, `max_domain_from_rank`,
   `avg_backlink_spam_score`, `anchor_keyword_match_ratio` (lexical overlap
   between anchor text and `target_keyword`, no new NLP dependency),
   `referring_tld_diversity_count`, `referring_country_diversity_count`; null
   the whole row when zero backlinks returned (distinct from not-yet-fetched).
8. **[ ] Slice 8 — Family registry** — new kind `backlinks_quality`; add
   `backlinks_quality` and `backlinks_anchor_relevance` families, kept
   separate from the existing `backlinks_counts` family (Phase 6.2).
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.3 — Backlink velocity (`backlinks/timeseries_new_lost_summary/live`)

URL grain, one call per SERP URL, `group_range: month`, `date_from` 90 days
before the run's collection date.

##### Dev slices

**Progress:** 0 of 9 shipped.

1. **[ ] Slice 1 — Request/schema/fixture.**
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Fetch + persistence** — `fetch_backlink_velocity_for_urls`,
   `raw_responses/endpoint=backlinks_velocity`.
4. **[ ] Slice 4 — Live-run wiring.**
5. **[ ] Slice 5 — Stored-run backfill.**
6. **[ ] Slice 6 — Curated builder** — sum monthly buckets into
   `new_backlinks_90d`, `lost_backlinks_90d`,
   `net_backlink_velocity_90d = new - lost`.
7. **[ ] Slice 7 — Feature mart** — `backlink_velocity_features`, URL-grain join.
8. **[ ] Slice 8 — Family registry** — `backlinks_velocity` family, kind
   `backlinks_metric` (same shape as counts).
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.4 — Domain authority (`dataforseo_labs/google/domain_rank_overview/live`)

Domain grain, one call per **unique domain** in the run (dedupe the way
`domain_features` derives `domain` from SERP URLs).

##### Dev slices

**Progress:** 0 of 9 shipped.

1. **[ ] Slice 1 — Request/schema/fixture** — `target`, `location_code`,
   `language_code`, `limit: 1`.
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Fetch + persistence** — `fetch_domain_rank_overview_for_domains`,
   dedupe domains across the whole run before fetching, `raw_responses/endpoint=domain_rank_overview`.
4. **[ ] Slice 4 — Live-run wiring** — once per run after SERP collection.
5. **[ ] Slice 5 — Stored-run backfill**, keyed on domain not URL.
6. **[ ] Slice 6 — Curated builder** — `build_domain_rank_overview_frame`:
   `domain_rank`, `estimated_organic_traffic` (`etv`), `ranked_keywords_count`
   (`count`); one row per `(run_id, domain)`.
7. **[ ] Slice 7 — Feature mart** — `domain_authority_features`, joined via
   derived `domain` column the way `domain_features` joins.
8. **[ ] Slice 8 — Family registry** — new kind `domain_authority`; add
   `domain_authority` family.
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.5 — Domain technology & age (`domain_analytics/technologies/domain_technologies/live` + `domain_analytics/whois/overview/live`)

Domain grain, same dedupe-once-per-run approach as 7.4. Two endpoints in one
sub-phase since both are cheap per-domain lookups feeding the same mart.

##### Dev slices

**Progress:** 0 of 9 shipped.

1. **[ ] Slice 1 — Request/schema/fixture for both endpoints** —
   `build_domain_technologies_request`, `build_domain_whois_request` (whois
   uses `filters: [["domain","=",target]]`, not a bare `target` field).
2. **[ ] Slice 2 — Offline tests for both.**
3. **[ ] Slice 3 — Fetch + persistence for both** —
   `fetch_domain_technology_for_domains` + `fetch_domain_whois_for_domains`,
   `raw_responses/endpoint=domain_technologies` and `endpoint=domain_whois`.
4. **[ ] Slice 4 — Live-run wiring for both.**
5. **[ ] Slice 5 — Stored-run backfill for both partitions.**
6. **[ ] Slice 6 — Curated builder** — `domain_age_days` (today minus
   `created_datetime`, computed at normalize time so it stays current across
   re-normalizes); CMS/web-dev tech boolean flags (e.g. `uses_wordpress`,
   `uses_shopify`, `uses_react`); `tech_stack_count`.
7. **[ ] Slice 7 — Feature mart** — `domain_technology_features`, same
   domain-grain join as 7.4.
8. **[ ] Slice 8 — Family registry** — new kind `domain_technology`; add
   `domain_technology` family (age + tech flags).
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.6 — SERP feature presence (normalize-only, no new API calls)

Parses already-stored `raw_responses/endpoint=serp` payloads — no new
endpoint, no fetch/backfill wiring for the core slices.

##### Dev slices

**Progress:** 0 of 5 shipped.

1. **[ ] Slice 1 — Curated builder** — `build_serp_features_frame`: parse
   stored SERP `item_types` into `has_featured_snippet`,
   `has_people_also_ask`, `has_video`, `has_sitelinks`, `has_faq`, plus
   `same_domain_serp_position_count`; row grain matches `serp_items`.
2. **[ ] Slice 2 — Feature mart** — `serp_feature_presence`, URL-grain join,
   boolean validation rules.
3. **[ ] Slice 3 — Family registry** — new kind `serp_feature`; add
   `serp_features` family.
4. **[ ] Slice 4 — Artifacts, fixtures (including a no-rich-features SERP
   payload proving nulls/false render correctly), tests.**
5. **[ ] Slice 5 — Forward-looking pixel position (separate, no backfill)** —
   add `calculate_rectangles: true` to `build_serp_request()` behind a new
   opt-in `--serp-pixel-position` CLI flag (default off); nullable
   `serp_pixel_position_y` column; old runs stay null; explicitly no backfill
   since re-fetching the SERP would change ranks for existing runs.

| Acceptance item | Sub-phase | Status |
| --------------- | --------- | ------ |
| OnPage content/CWV/technical-check families land without an `analysis_mart` schema bump | 7.1 | Shipped (slices 8–9) |
| OnPage stored-run backfill without refetching unrelated partitions | 7.1 | Shipped (slice 5) |
| Backlink quality + anchor-relevance families are separate from the existing counts family | 7.2 | Open |
| Backlink velocity family lands at URL grain | 7.3 | Open |
| Domain authority family lands at domain grain, deduped once per run | 7.4 | Open |
| Domain technology/age family lands at domain grain | 7.5 | Open |
| SERP feature presence lands from stored SERP payloads with no new API calls | 7.6 | Open |
| `run --stored-run` backfills every new source's missing raw partition without refetching unrelated data | 7.2–7.5 | Open |

### Phase 8 — Non-DataForSEO API integrations

Add free-tier third-party signals DataForSEO doesn't cover: real-user Core
Web Vitals, content freshness, and brand/entity authority. Majestic, Ahrefs,
Moz, Similarweb, Google Search Console, and Google Natural Language are
**deferred** — paid or account-gated, marginal value over Phase 7. Each
source here is a brand-new client module (no existing endpoint to extend) but
follows the identical implementation pattern from Phase 7 — client module
with fixtures and offline tests, `SEO_RANK_ENABLE_<SOURCE>` env gate plus a
`validate_live_<source>_config`, fetch + `finally:`-block persistence with a
dedupe key, live-run wiring gated on that flag (these need their own
credentials, so unlike Phase 7's bundled DataForSEO calls they stay opt-in
like TextRazor), `--stored-run` backfill via the same reuse-check extension,
curated builder + feature mart + new family kind + spec entry, and golden
fixtures plus a stored-run regression. Missing/not-found data (e.g. a domain
with no CrUX data, a URL never archived) is a valid null outcome, never a
fetch error.

#### 8.1 — Google Chrome UX Report (CrUX) API — field Core Web Vitals

`POST https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=<GOOGLE_API_KEY>`.
URL grain with origin fallback: query `url` first; on 404 (no per-URL CrUX
data), retry once with `origin` and flag `crux_is_origin_fallback: true`.
Free, 150 req/min per GCP project.

##### Dev slices

**Progress:** 0 of 11 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/crux.py`:
   `CruxCredentials` (`api_key`), `build_crux_record_request(url_or_origin, form_factor=None)`,
   `CRUX_RESPONSE_SCHEMA`, `fixture_crux_response()`,
   `validate_crux_credentials(env)`.
2. **[ ] Slice 2 — Offline tests** — url vs origin body shape, schema-accept,
   schema-drift reject.
3. **[ ] Slice 3 — Execute + retry** — `execute_crux_request()` (copy the
   `execute_dataforseo_request` retry loop); treat HTTP 404 as "no data", not
   a retryable error.
4. **[ ] Slice 4 — Env gate** — `SEO_RANK_ENABLE_CRUX` +
   `validate_live_crux_config`; `GOOGLE_API_KEY` documented (shared with 8.3).
5. **[ ] Slice 5 — Fetch + persistence** — `fetch_crux_for_urls`: per unique
   URL, try `url` record, fall back to `origin` on 404, persist to
   `raw_responses/endpoint=crux`.
6. **[ ] Slice 6 — Live-run wiring**, gated on `SEO_RANK_ENABLE_CRUX`.
7. **[ ] Slice 7 — Stored-run backfill** for the `crux` partition.
8. **[ ] Slice 8 — Curated builder** — `build_crux_frame`: `crux_lcp_p75`,
   `crux_inp_p75`, `crux_cls_p75` (p75 from each histogram metric),
   `crux_is_origin_fallback`, `crux_has_data` (false when neither url nor
   origin returned a record — not a fetch error).
9. **[ ] Slice 9 — Feature mart** — `crux_features`, URL-grain join.
10. **[ ] Slice 10 — Family registry** — new kind `crux_field_data`; add
    `crux_core_web_vitals` family.
11. **[ ] Slice 11 — Fixtures (url-hit, origin-fallback, no-data), stored-run
    regression, tests.**

#### 8.2 — Wayback Machine CDX Server API — content freshness

`GET http://web.archive.org/cdx/search/cdx?url=<url>&output=json&limit=1&fl=timestamp&filter=statuscode:200`
for first capture, plus `output=json&fl=timestamp&collapse=timestamp:8` for a
distinct-capture count. No auth. URL grain.

##### Dev slices

**Progress:** 0 of 10 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/wayback.py`:
   `build_wayback_first_capture_request(url)`,
   `build_wayback_capture_count_request(url)`; validate the bare-JSON-array
   CDX response shape (header row + field count) instead of a
   path-based schema; `fixture_wayback_response()`. No credentials object
   (public API) — skip `validate_*_credentials`, but still add
   `SEO_RANK_ENABLE_WAYBACK` for gate consistency.
2. **[ ] Slice 2 — Offline tests** — request shape, response-shape
   validation, drift rejection (e.g. missing header row).
3. **[ ] Slice 3 — Execute + retry** — `execute_wayback_request()` (no auth,
   simplest client in this phase).
4. **[ ] Slice 4 — Fetch + persistence** — `fetch_wayback_for_urls`: two
   calls per unique URL, persisted to
   `raw_responses/endpoint=wayback_first_capture` and
   `endpoint=wayback_capture_count`.
5. **[ ] Slice 5 — Live-run wiring**, gated on `SEO_RANK_ENABLE_WAYBACK`.
6. **[ ] Slice 6 — Stored-run backfill** for both partitions.
7. **[ ] Slice 7 — Curated builder** — `first_capture_date`,
   `days_since_first_capture` (computed at normalize time), `capture_count`;
   null when never archived (a valid outcome, not an error).
8. **[ ] Slice 8 — Feature mart** — `wayback_features`, URL-grain join.
9. **[ ] Slice 9 — Family registry** — new kind `content_freshness`; add
   `content_freshness` family.
10. **[ ] Slice 10 — Fixtures (found / never-archived), stored-run
    regression, tests.**

#### 8.3 — Google Knowledge Graph Search API — brand entity confirmation

`GET https://kgsearch.googleapis.com/v1/entities:search?query=<brand>&key=<GOOGLE_API_KEY>&limit=1`.
Domain grain; brand name derived from the registrable domain label (reuse
whatever label extraction `domain_features` already does).

##### Dev slices

**Progress:** 0 of 11 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/knowledge_graph.py`:
   `KnowledgeGraphCredentials` (`api_key`, shared `GOOGLE_API_KEY`),
   `build_kg_search_request(query)`, response schema, `fixture_kg_response()`,
   `validate_knowledge_graph_credentials(env)`.
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Execute + retry** — `execute_kg_request()`.
4. **[ ] Slice 4 — Env gate** — `SEO_RANK_ENABLE_KNOWLEDGE_GRAPH` + validator.
5. **[ ] Slice 5 — Fetch + persistence** — `fetch_knowledge_graph_for_domains`,
   dedupe-by-domain, `raw_responses/endpoint=knowledge_graph`.
6. **[ ] Slice 6 — Live-run wiring**, gated on the flag.
7. **[ ] Slice 7 — Stored-run backfill**, keyed on domain.
8. **[ ] Slice 8 — Curated builder** — `kg_entity_found` (`itemListElement`
   non-empty), `kg_result_score` (top hit's `resultScore`, null when not found).
9. **[ ] Slice 9 — Feature mart** — `knowledge_graph_features`, domain-grain join.
10. **[ ] Slice 10 — Family registry** — new kind `entity_authority`; add
    `knowledge_graph_entity` family.
11. **[ ] Slice 11 — Fixtures (found / not-found), stored-run regression, tests.**

#### 8.4 — Wikidata entity search — supplementary brand notability

`GET https://www.wikidata.org/w/api.php?action=wbsearchentities&search=<brand>&language=en&format=json&limit=1`.
Domain grain, no auth. Kept deliberately thin (existence flag only) — overlaps
with 8.3 and is a lower-priority cross-check.

##### Dev slices

**Progress:** 0 of 10 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/wikidata.py`:
   `build_wikidata_search_request(query)`, response schema,
   `fixture_wikidata_response()`. No credentials needed; still add
   `SEO_RANK_ENABLE_WIKIDATA` for gate consistency.
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Execute + retry** — `execute_wikidata_request()`.
4. **[ ] Slice 4 — Fetch + persistence** — `fetch_wikidata_for_domains`,
   dedupe-by-domain, `raw_responses/endpoint=wikidata`.
5. **[ ] Slice 5 — Live-run wiring**, gated on `SEO_RANK_ENABLE_WIKIDATA`.
6. **[ ] Slice 6 — Stored-run backfill**, keyed on domain.
7. **[ ] Slice 7 — Curated builder** — `wikidata_entity_found`,
   `wikidata_label_match` (exact case-insensitive label match, a simple
   lexical check, not a new fuzzy-matching dependency).
8. **[ ] Slice 8 — Feature mart** — `wikidata_features`, domain-grain join.
9. **[ ] Slice 9 — Family registry** — add `wikidata_entity` signal columns
   to the existing `entity_authority` kind from 8.3 (same concept, one family,
   two extra columns) rather than inventing a new kind.
10. **[ ] Slice 10 — Fixtures, stored-run regression, tests.**

| Acceptance item | Sub-phase | Status |
| --------------- | --------- | ------ |
| CrUX field CWV family lands at URL grain with origin fallback | 8.1 | Open |
| Wayback freshness family lands at URL grain | 8.2 | Open |
| Knowledge Graph entity-authority family lands at domain grain | 8.3 | Open |
| Wikidata notability signal joins the same entity-authority family as 8.3 | 8.4 | Open |
| Every Phase 8 source stays opt-in behind its own `SEO_RANK_ENABLE_<SOURCE>` flag | 8.1–8.4 | Open |
| `run --stored-run` backfills every new source's missing raw partition without refetching unrelated data | 8.1–8.4 | Open |

## Deferred

- Entity-derived features beyond Phase 5.6 density bundle (keyword–entity overlap,
  type-weighted density, passage-level density)
- Direct page crawling outside DataForSEO
- CI, release packaging, coverage thresholds
- Production deployment, databases, cache
- Parquet `Variant` type for provider payloads
- Content Analysis API (citation-index brand mentions) — marginal value over
  TextRazor, doesn't fit a per-URL/per-domain grain cleanly (considered and
  cut from Phase 7/8 scope)
- Majestic, Ahrefs, Moz, Similarweb, Google Search Console, Google Natural
  Language API — paid/account-gated third-party signals (considered and cut
  from Phase 8 scope in favor of free-tier sources)

## History

- Repository scaffold: `pyproject.toml`, `src/seo_rank/`, `tests/`.
- **Phase 1 shipped:** offline CLI, DataForSEO/TextRazor fixtures, keyword/SERP/
  passage/similarity/entity normalization, `run.json` + `report.md`, unit tests,
  root product docs (`ARCHITECTURE.md`, `GOALS.md`, `ROADMAP.md`).
- SDLC wizard surface: hooks, manifest, `GOALS.md` active contract.
- **Phase 2 shipped:** provider request builders (DataForSEO keyword expansion,
  organic SERP, page-text parsing; TextRazor parsed-text entities), credential
  validation without secrets in errors, non-default CLI live-provider gate
  (`--live-providers` + `SEO_RANK_ENABLE_LIVE_PROVIDERS=1`), standard-library
  HTTP clients with injectable transports, env-gated live smoke integration test
  (`SEO_RANK_RUN_LIVE_INTEGRATION=1`), and Phase 2 documentation/test coverage.
- **Phase 2 deferred to later backlog:** broader live provider integration beyond
  the minimal smoke path.
- **GOALS retargeted to Phase 3:** full cluster orchestration for every capped
  keyword in offline and live paths.
- **Phase 3 shipped:** per-keyword cluster orchestration in offline and gated
  live paths.
  - `build_offline_keyword_result` / `build_live_keyword_result` loop every capped
    keyword (up to the configured keyword limit, default 1) with that keyword as
    `target_keyword`.
  - Per-keyword SERP, page text, passages, fixture similarity, TextRazor entities.
  - `keyword_results[]` in `run.json` / `report.md` with per-keyword raw provider
    payloads; top-level rollup preserved.
  - Flattened aggregate rows annotated with `target_keyword`.
  - `.env.example` documents live-provider and integration env gates.
  - Tests: 1-keyword default offline cluster + injected live cluster orchestration
    in `test_cli_run.py`.
- **GOALS retargeted to Phase 4:** live similarity backends and passage/page/domain
  scoring.
- **Phase 4 started:** fixture page-level scoring for **BGE**, **Gemini Doc
  Retrieval**, and **Gemini Semantic Similarity** wired through offline and
  gated live artifact generation, including JSON/Markdown exposure and unit
  coverage.
- **Env loading:** CLI and pytest auto-load project-root `.env` via
  `seo_rank.env` (`.env` overrides shell exports; no `source` required). Integration
  gate now requires `SEO_RANK_RUN_LIVE_INTEGRATION=1` explicitly (fixes `"0"` being
  treated as enabled).
- **Phase 4 shipped:** live page-level similarity backends behind opt-in CLI flags.
  - Fixture scorers in `similarity.py` for offline, `--dry-run`, and default live runs.
  - `gemini_embeddings.py` + `--live-gemini` for **Gemini Doc Retrieval** and
    **Gemini Semantic Similarity** via `gemini-embedding-2` / `google-genai`.
  - `bge_reranker.py` + `--live-bge` for local **BGE** via `FlagEmbedding`
    (`BAAI/bge-reranker-v2-m3`, CUDA, once per live run).
  - Optional `similarity` extra in `pyproject.toml`; env gates in `.env.example`.
  - Unit tests for prompt formatting, CLI path selection, and BGE batching; env-gated
    integration smoke with optional Gemini/BGE flags.
- **GOALS retargeted to Phase 4.5:** run-scoped Parquet lake storage.
- **Phase 4.5 scoped:** run-scoped Parquet architecture (`raw_responses`, curated
  tables, feature marts, `analysis_mart`), Polars LazyFrame data package
  (`src/seo_rank/data/`), CLI `normalize` / `build-features` / `analyze` /
  `replay`, and validation-before-sink contract.
- **Phase 4.5 Slice 1 shipped:** `seo-rank run` writes run-scoped `raw_responses`
  Parquet partitions plus `run.json` catalog metadata without duplicating raw
  payloads in JSON.
- **Phase 4.5 Slice 2 shipped:** stored `raw_responses` normalize into curated
  Parquet tables (`keywords`, `serp_items`, `pages`, `passages`, `entities`,
  `similarity_scores`) and refresh the run catalog from disk.
- **Phase 4.5 Slice 3 shipped:** `normalize_run()` scans `raw_responses`, filters
  by `endpoint`, and normalizes via lazy `map_batches` / `map_groups` UDFs with
  per-table streaming collect at sink. Package: `scans`, `normalize`, `features`,
  `marts`, `validate` under `src/seo_rank/data/`.
- **Phase 4.5 Slice 4 shipped:** feature marts (`keyword_serp`, `page_features`,
  `passage_features`, `domain_features`) materialized from curated tables via lazy
  Polars joins.
- **Phase 4.5 Slice 5 shipped:** `analysis_mart` materializes as a lazy panel
  joined from feature marts (one row per `target_keyword × SERP URL`);
  `raw_responses` excluded from analytical joins.
- **Phase 4.5 Slice 6 shipped:** CLI surfaces `normalize`, `build-features`,
  `analyze`, and `replay`; `run --stored-run` resumes partial runs in place from
  the saved raw lake and existing keyword results, then re-materializes marts
  from a stored run tree.
- **Phase 4.5 Slice 7 shipped:** `pyarrow` + `polars` declared; docs aligned;
  round-trip regression in `test_round_trip.py` and `test_sdlc_docs.py`.
- **Phase 4.5 Slice 8 shipped:** curated tables sink via Polars
  `sink_parquet(..., compression="zstd", statistics=True)` with sorted retrieval
  keys (replaces PyArrow `write_table` on curated path).
- **Phase 4.5 Slice 9 shipped:** feature marts and `analysis_mart` use lazy
  `sink_parquet` with statistics; catalog row counts from Parquet file metadata.
- **Phase 4.5 Slice 10 shipped:** `validate_frame_contract` stays schema-only and
  lazy; row-level uniqueness, null, and range checks at the sink edge only.
- **Phase 4.5 signed off (2026-06-29):** 10 dev slices shipped; 11 acceptance
  items complete. Run-scoped lake under `runs/{run_id}/` with authoritative
  `raw_responses`, six curated tables, four feature marts, `analysis_mart`, lazy
  Polars transforms, validation-before-sink, and storage CLI commands. Residual:
  batch Python UDFs for JSON parse and similarity grouping; post-sign-off polish
  tracked in `FIXUPS.md` § Phase 4.5.
- **Phase 4.77 shipped:** adapter schema validation at the DataForSEO boundary
  with endpoint-scoped parse errors and drift coverage for missing fields,
  type mismatches, and valid pass-through fixtures.
- **GOALS retargeted to Phase 5 (2026-07-01):** statistical analysis on
  `analysis_mart` — Spearman-first observational association, pooled OLS with
  keyword-clustered SEs, guardrails, BH policy, `analysis_spec.v1.yaml`, and
  `stats_*` artifacts wired through `seo-rank analyze`.
- **Phase 5 Slice 1 shipped:** `analysis_spec.v1.yaml` locks the v1 estimand
  (Spearman-first, pooled OLS secondary, BGE primary backend, BH per backend
  when K ≥ 10, guardrail thresholds, actionable-association rule, multivariate
  drop order, limitations); cross-linked in `ARCHITECTURE.md`,
  `PHASE5-STATS-PLAN-REVIEW.md`, and `ROADMAP.md`.
- **Phase 5 Slice 2 shipped:** `src/seo_rank/stats/` package scaffold with
  `spec.py` (`load_analysis_spec`), `artifacts.py` (`build_stats_output_metadata`),
  and placeholder modules for panel, Spearman, regression, BH, and diagnostics;
  `statsmodels`, `numpy`, `scipy`, and `PyYAML` declared in `pyproject.toml`;
  `tests/unit/test_stats_spec.py` covers spec load and estimand-version metadata.
- **Phase 5 Slice 5 shipped:** `regression.py` now fits pooled baseline and
  univariate backend models on `-log(serp_rank)` with keyword fixed effects,
  keyword-clustered SEs, effect-size translation, and a two-way-cluster
  sensitivity on repeated URLs; `run_phase5_stats()` writes regression summaries
  into `stats_summary.json` and `stats_report.md`, covered by
  `tests/unit/test_stats_regression.py`.
- **Phase 5 Slice 6 shipped:** `diagnostics.py` summarizes pooled OLS RESET,
  Breusch–Pagan (with HC3 recommendation when flagged), Cook's D, leverage,
  studentized residuals, DFFITS, and DFBETAs per backend; `run_phase5_stats()`
  writes `stats_diagnostics.json` and a Diagnostics section in `stats_report.md`
  on passing guardrails, covered by `tests/unit/test_stats_diagnostics.py`.
  `normalize` now materializes `similarity_scores` from `run.json`
  `page_similarity` instead of recomputing scores during curation.
- **Phase 5 Slice 7 shipped:** `diagnostics.py` fits the joint three-backend
  multivariate sensitivity model with spec-driven VIF threshold and backend drop
  order; `run_phase5_stats()` writes `rank_depths.top_20.multivariate_sensitivity`
  to `stats_diagnostics.json` and a `### Robustness` section in
  `stats_report.md`; `spec.py` exposes `multivariate_vif_threshold` and
  `backend_drop_order`; covered by `tests/unit/test_stats_diagnostics.py` and
  `tests/unit/test_stats_spec.py`.
- **Phase 5 Slices 16–20 shipped (2026-07-02):** parallel confirmatory rank-depth
  bundles at `top_20`, `top_10`, `top_5`, and `top_3` — `rank_depths` and
  `limitations_by_depth` in `analysis_spec.v1.yaml`, `rank_depth.py` panel
  filtering, per-depth Spearman/OLS/Plackett-Luce/diagnostics, nested
  `rank_depths` in `stats_summary.json` / `stats_diagnostics.json`, four
  `## Rank depth:` sections in `stats_report.md`,
  `actionable_association_by_rank_depth`, leave-one-out IIA on `top_20` only;
  covered by `tests/unit/test_stats_rank_depth.py`.
- **Phase 5 Slices 27–28 shipped (2026-07-02):** TextRazor signal-family registry
  in `analysis_spec.v1.yaml` and `families.py`; curated
  `textrazor_page_metrics_curated` plus feature mart `textrazor_page_metrics`
  at `target_keyword × SERP URL` grain; full page-metrics TextRazor extractors;
  similarity `analysis_mart` unchanged. Covered by `test_stats_families.py`,
  `test_textrazor_normalization.py`, and `test_feature_marts.py`.
- **Phase 5 Slices 29–30 shipped (2026-07-02):** family-aware Spearman, pooled
  OLS, diagnostics, and Plackett-Luce per registered signal family; combined
  `stats_*` artifact tree with nested `rank_depths.*.families` for similarity
  and TextRazor families; top-level similarity blocks kept for compatibility.
  Covered by `test_stats_family_dispatch.py` and `test_stats_family_artifacts.py`.
- **Phase 5 Slices 32–33 shipped (2026-07-02):** TextRazor page-metrics
  completeness (`textrazor_page_metrics_complete`, null-not-zero section
  counts) and small-K inference labeling (`keyword_count`, `inference_mode` in
  `stats_*`). Covered by `test_textrazor_normalization.py`,
  `test_feature_marts.py`, and `test_stats_family_artifacts.py`.
- **Phase 5 Slices 21–26 shipped (2026-07-02):** TextRazor-only ingestion path —
  `--live-textrazor-only` / `--refresh-textrazor` CLI flags and gates,
  `TEXTRAZOR_ENDPOINTS` registry, `fetch_textrazor_entities_for_pages()`,
  `merge_raw_response_records()` for `endpoint=entities`, stored-run backfill
  via `backfill_textrazor_run()`, and brand-new runs via
  `write_textrazor_only_artifacts()` (fixture DataForSEO structure + live
  TextRazor, zero `dataforseo.*` in `network_calls`). Cross-doc schema contract
  (slice 26) is shipped.
- **Phase 5.1 planned (2026-07-02):** live provider fail-fast on fatal DataForSEO
  task errors (`40207` IP whitelist, auth failures) — shared classifier, abort on
  all live endpoints, optional preflight, CLI flag override on stored-run replay,
  safer stale-SERP retention. Motivated by Columbus run continuing through 23
  denied SERPs before `raise_for_failed_dataforseo_tasks()` shipped.
- **Phase 5 Slices 8–10 shipped (2026-07-03):** influence refit appendix
  (`influence_sensitivity` block, `### Influence robustness` report sections,
  `influential_rows_rate` warn guardrail), similarity golden fixtures
  (`test_stats_golden_fixtures.py` schema/boundary contracts), and expanded
  ranking explainability (`textrazor_ranking_r2.py` similarity + TextRazor
  adjusted R², `ranking_r2.json`, curated-model PNG via
  `ranking_explainability_viz.py`, optional `matplotlib` dependency).
- **Backlinks two-call summary API (2026-07-04, Phase 5.91):** live runs issue
  two `POST /v3/backlinks/summary/live` calls per SERP URL (unfiltered summary
  plus dofollow-filtered summary, ~$0.04/target combined). Each variant
  persists immediately to `raw_responses/endpoint=backlinks_summary` or
  `endpoint=backlinks_dofollow_summary` via `persist_backlink_raw_responses()`
  (dedupe on `(target_keyword, url, variant)`). Normalization merges both into
  one curated row per `target_keyword × URL`; `dofollow_backlinks_count` is
  `null` and `backlinks_metrics_complete` is `false` when the dofollow variant
  is missing. Legacy `endpoint=backlinks` rows (pre-5.91 `/backlinks/backlinks/live`
  shape) remain read-compatible on normalize. Stored-run replay overlays
  `--live-providers` onto offline runs; `--skip-textrazor` stays sticky via
  `merge_stored_run_cli_overlay()`. Supersedes the 2026-07-03 single-partition
  summary migration.
- **Phase 6.2 shipped (2026-07-05):** `backlinks_analysis` feature mart
  (`analysis_mart` grain + curated `backlinks` counts), `backlinks_counts`
  signal family (`backlinks_metric` kind) in `analysis_spec.v1.yaml`, and
  family-aware stats/report blocks for `backlinks_count`,
  `referring_domains_count`, and `dofollow_backlinks_count`. `analysis_mart.v1`
  unchanged; `ensure_feature_marts_for_analysis` requires `backlinks_analysis`
  and `onpage_features`; `run_phase5_stats` invokes the same guard before loading
  family source frames.
- **Phase 7.1 slice 13 shipped (2026-07-07):** OnPage `htags` counts
  (`h1_count`/`h2_count`/`h3_count` from `meta.htags` array lengths via the
  Slice 12 `_optional_mapping_len` helper) and `social_media_tags` presence
  flags (`has_og_tags`/`has_twitter_tags` via new `_has_prefix_key` helper).
  5 new columns on `onpage_signals`; `onpage_features` bounded columns added
  for the three count fields. Fixture updated with representative
  `htags` + `social_media_tags`. Tests in `tests/unit/test_run_normalize.py`.
  Stats family wiring remains Slice 17.
- **Phase 7.1 slice 14 shipped (2026-07-07):** Within-keyword rank, percentile,
  and z-score columns added to `analysis_mart` (schema `v2`) for all three
  similarity backends (`bge`, `gemini_doc_retrieval`, `gemini_semantic_similarity`).
  `emit_keyword_analysis` JSON output includes rank/pct/z; `report.md` Page
  Similarity sorted by BGE rank with `[rank X/N, pct 0.00]` annotation.
  Tests in `test_data_marts.py`, `test_analysis_mart.py`, `test_cli_keyword_analysis.py`.
- **Phase 7.1 slices 1–14 shipped (2026-07-06):** OnPage `instant_pages` live
  path from request/fixture through raw `endpoint=onpage_instant_pages`,
  curated `onpage_signals` (46 `checks` booleans via Slice 11; 18 `meta` metrics
  via Slice 12),
  feature mart `onpage_features`, and three
  `onpage_metric` signal families (`onpage_content_quality`,
  `onpage_core_web_vitals`, `onpage_technical_checks`) with Spearman, pooled OLS,
  diagnostics, and family Plackett-Luce at all confirmatory rank depths.
  `ensure_feature_marts_for_analysis()` lives in `data/features.py` and rebuilds
  missing `onpage_features` on legacy run trees (when `run.json` exists) from
  both `seo-rank analyze` and `run_phase5_stats()`. Slice 18 stored-run
  end-to-end regression and full-layer CLI pipeline tests shipped (Jul 2026).
- **Phase 6.1 Slice 3 partial (2026-07-03):** `src/seo_rank/data/ranks.py`
  ships Polars-lazy `add_within_keyword_similarity_ranks()` with unit tests in
  `tests/unit/test_within_keyword_ranks.py`; mart wiring remains Slice 4.
- **Phase 5.6 planned (2026-07-03):** signal factor & proxy diagnostics —
  NDCG@k, incremental TextRazor-after-BGE regression ladder, partial
  correlation, leave-one-keyword-out stability, keyword holdout and optional
  time-split validation, negative controls, same-length / same-similarity subset
  analyses, and unified `signal_factor_report` artifact. Tracked as Phase 5
  slice 34; precursor `textrazor_ranking_r2.py` ships similarity + TextRazor
  adjusted R², curated multivariate model, and PNG charts.
- **Phase 5.6 entity density planned (2026-07-03):** Slice 0 materializes
  entity mention/unique counts and word-normalized densities in
  `textrazor_page_metrics`; dossier registry adds char-normalized density and
  proxy-test expectations for counts vs densities (six slices total in § 5.6).
- **Phase 5.2 planned (2026-07-02):** live Gemini/BGE fail-fast on empty scoring
  work — abort when a keyword yields zero `parsed_pages` or zero
  `page_similarity` with live scoring on; skip Gemini query embeds on empty
  pages; defer BGE GPU load; accurate `network_calls`; AI Studio billing clarity
  (not GCP console). Complements 5.1; depends on 5.1 slice 4 for stored-run
  CLI live-flag override.
- **GOALS retargeted to Phase 4.75 (2026-06-29):** page_text curation hardening
  after stored-run normalize failed on live nested `page_content` payloads.
- **Phase 4.75 Slice 1 shipped:** `parsed_page_text()` decodes nested DataForSEO
  `content_parsing` items; `build_pages_and_passages_frame()` uses the shared
  parser instead of flat `tasks[0].result[0]` indexing.
- **Phase 4.75 Slice 2 shipped:** `_extract_page_content_text()` now walks all
  relevant `page_content` regions, so `header` and other nested sections are
  included in normalized page `text` and passage splitting.
- **Phase 4.75 Slice 3 shipped:** `build_pages_and_passages_frame()` skips
  `page_text` responses with no URL or no text, automatically dropping empty
  bodies without any CLI flag and preventing blank curated rows or duplicate
  `page_id` warnings from crawl failures.
- **GOALS retargeted to Phase 4.76 (2026-07-01):** structured
  `content_parsing/live` capture — per-field curated storage, aggregate
  `pages.text`, raw HTML, and a fixed US English desktop request contract.
- **Phase 4.76 Slice 1 shipped:** `build_page_text_request()` always emits the
  fixed US English desktop contract (`ip_pool_for_scan=us`,
  `accept_language=en-US`, JS/rendering off, `store_raw_html=true`); the
  `--javascript-parsing` CLI knob was removed.
- **Phase 4.76 Slice 3 shipped:** curated `page_content_fields` now materialize
  one row per decoded `content_parsing/live` field with stable ids and JSON
  path metadata while leaving aggregate `pages.text` unchanged.
- **Phase 4.76 Slice 4 shipped:** normalization now preserves the aggregate
  `pages.text` path and writes raw HTML to a sibling `page_html` table keyed by
  `page_id` / `response_id`.
- **Phase 4.76 Slice 5 shipped:** unit tests and stored-run re-normalize smoke
  now cover multi-field content parsing fixtures, HTML retention, aggregate text
  parity, and structured-only round-trip payloads.
