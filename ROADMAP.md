# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract; keep deferred and historical items here.

---

> **Revision 2026-07-20 — feasibility-study update.** A 12-dimension research
> program (May 2024 Content Warehouse API leak; US v. Google trial record;
> academic and industry accuracy measurements.
>
> Everything marked **⌁** below is a revision driven by that study. One
> sourcing policy now applies to the whole roadmap: **DataForSEO is the only
> paid input** (pure pay-as-you-go, no monthly minimums since 2026-07-01); all
> other inputs are free — MozCast/Algoroo/SERPmetrics (volatility), Google
> Trends API alpha / Keyword Planner (brand demand), Common Crawl, CrUX,
> Wayback, Wikidata, GSC. No Semrush-class subscription is used anywhere.

## The acceptance contract — the measurable "95% system" ⌁

One public accuracy claim, pre-registered in `analysis_spec` before any model
is scored:

| Component | Contract |
| --------- | -------- |
| Primary metric | Out-of-time **end-to-end** NDCG@10 ≥ 0.95 — the composed GATE→RANK pipeline scored against the full graded relevance vector, per query, rolling-forward on held-out future snapshots (random splits forbidden — they leak query-level patterns). RANK-only (oracle-gate) NDCG is a diagnostic, never the acceptance figure |
| GATE metrics | Membership recall and precision against the realized top-10/20 labels, per segment, with a preregistered recall floor (≥ 0.90 top-10 recall on the filtered panel). Gate errors are pipeline errors, never invisible: a realized grade ≥ 1 URL that GATE rejects forfeits its gain in end-to-end NDCG (no predicted slot — ideal gain retained, predicted gain zero); a false admit consumes a slot in the emitted ranking and depresses both precision and DCG |
| Label | Median-of-N repeat-sampled rank, N ≥ 5 geo-pinned, de-personalized scrapes per keyword-snapshot; never a single-scrape rank (Phase 15) |
| Graded relevance | Fixed, reproducible mapping from the median-of-N rank to NDCG grades: rel 3 = ranks 1–3, rel 2 = ranks 4–10, rel 1 = ranks 11–20, rel 0 = not in top-20; gains $2^{rel}-1$, log₂ discount. Cut points are constants in `analysis_spec` — never tuned per run |
| Missing-URL rule | A valid repeat is a non-empty SERP. A URL absent from a valid repeat is coded rank 21 (depth + 1, censored), not dropped; the label is the median of all N coded values, so a URL absent from > N/2 repeats is grade 0. Whole-repeat scrape failures are re-sampled, never imputed; a keyword-snapshot is valid only with ≥ 4 of 5 valid repeats, otherwise excluded with a logged reason |
| Panel | Segmented (Phase 14), stability-filtered (Phase 15), top-20 rows per keyword |
| Abstention | Every score carries a prediction interval and a coverage decision; accuracy quoted at declared coverage as a coverage–accuracy frontier |
| Coverage / threshold policy | Preregistered before scoring: (a) abstain when the 80% prediction interval spans > 7 positions or when the Phase 15 regime label is "update window"; decisions are ex ante from model outputs only — never from realized error. (b) Primary operating point: NDCG@10 ≥ 0.95 at coverage ≥ 0.60 of the panel; claims are void below the 0.60 floor. (c) Frontier reported at fixed coverage points {1.00, 0.90, 0.75, 0.60}; per-segment claims additionally require ≥ 0.50 coverage within that segment |
| Reporting | Per-segment AND volume-weighted, with keyword-clustered effective n beside raw rows |

The label pipeline is fully determined by these rules: N repeat scrapes →
censor-aware coding (absent = 21) → median-of-N rank per URL → fixed grade
mapping → graded relevance vector per keyword → NDCG@10 against the model's
predicted ordering. Any two runs of the pipeline on the same raw scrapes
produce identical labels, and every constant (N, cut points, censor value,
interval-width threshold, coverage floor, frontier points) lives in
`analysis_spec`, preregistered before the acceptance evaluation runs.

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

### Phase 5.1 — Live provider failure handling

DataForSEO top-level and task-level failures are logged as warnings and the live
run continues. The failed response is retained in `parquet/raw_responses`; its
empty result is allowed to flow through normalization so the run can finish and
report the affected keyword.

**Root cause (Columbus run, 2026-07-02):** SERP schema allows `result: null`;
`normalize_serp_results()` returns `[]` without checking `status_code`. Runs
before `raise_for_failed_dataforseo_tasks()` (shipped in `74ea7c0`) looped all
keywords and persisted failed payloads. The current `--stored-run` path
resumes from the saved raw lake and existing keyword results, so completed work
survives replay; interrupting mid-run still loses in-RAM SERP + embedding
progress for in-flight refresh work.

**Implemented behavior**

- Log a warning for a failed top-level DataForSEO response.
- Log a warning for each failed task, including endpoint, task index, status,
  and keyword context when available.
- Preserve failed raw responses and continue the keyword loop; a failed SERP
  task produces no SERP rows for that keyword.
- `replay_stored_run` / `expand_stored_run`: CLI `--live-providers`,
  `--live-gemini`, `--live-bge` override stale `run.json` config for execution.

**CLI contract:** a failed DataForSEO task does not by itself change the exit
code. The warning includes `status_code`, endpoint, and `target_keyword` when
known; raw response persistence and the normal completion marker still occur.
Transport and configuration errors remain hard failures.

The preflight/fatal-classifier ideas in the remaining dev slices are deferred
hardening, not the current live-run contract. Related follow-ups are S5-11,
S6-10, and S6-12.

#### Dev slices

**Progress:** 0 of 5 shipped, 5 open.

1. **[ ] Slice 1 — Shared fatal task classifier**
   - Add `dataforseo_task_is_fatal()` / `dataforseo_task_is_success()` in
     `dataforseo.py` (fatal set: `40207`, `40101`, `40102`; extend from
     DataForSEO docs as needed).
   - Wire `raise_for_failed_dataforseo_tasks()` and
     `stored_serp_response_is_usable()` through the shared helper (S6-12).
   - Unit tests in `tests/unit/test_dataforseo_requests.py`.

2. **[ ] Slice 2 — Optional fatal-task policy hardening**
   - If a future policy distinguishes fatal auth/IP responses, keep the current
     warning-and-continue default explicit and add an opt-in abort contract.
   - Preserve the current behavior that failed SERP tasks are retained and the
     keyword loop continues.

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
| **Incremental regression after BGE** | Explicit proxy test | Pooled OLS ladder with keyword FE plus the three adjustment controls: baseline → `+ bge_normalized_score` → `+ candidate signal(s)`. Report coefficient, p-value, Δ adjusted R² at each step; shrinkage after BGE ⇒ likely proxy. |
| **Partial correlation** | Association net of similarity | Within-keyword or pooled partial ρ / partial regression of signal vs rank controlling for `bge_normalized_score`, referring domains, deprecated HTML tags, and meta-keyword consistency. |
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

> **Update (Phase 10):** the bi-encoder retrieval stage (Slice 2 below) is
> promoted into Phase 10 Slice 3 as the live dual-encoder write path for the
> `embeddings` mart — its vectors become the forward-looking source for
> centroid/radius/focus computation. This phase remains the scoring-pipeline
> context; Phase 10 owns vector persistence.

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
13), and surface relative ranks in CLI reports (Slice 14).

> **⌁ Revision — estimand inversion (CHANGE).** The strongest published public
> correlation with rank is a SERP-relative feature (text relevance ρ = 0.47,
> 16,298 keywords); direct absolute embedding cosine scores ~0.07 in the same
> study, and absolute link/authority metrics are weaker still (referring domains
> 0.255, Domain Rating 0.131, decaying). The evidence demands the reverse of the
> original posture: **within-keyword rank/pct/z transforms become the primary
> confirmatory estimand**; absolute `*_normalized_score` drops to the
> sensitivity path. This ships as `analysis_spec.v2.yaml` (v1 runs are never
> reinterpreted); Plackett-Luce is refit on relative predictors in v2; the
> limitation that relative ranks compare within observed top-20 rows only is
> retained. Slice 13's `robustness_only: true` posture is inverted accordingly.

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
`["run_id","target_keyword_id","canonical_url_hash"]`; domain sources
derive `domain` the way `domain_features` does), a new family `kind` in
`stats/families.py` (`VALID_SIGNAL_FAMILY_KINDS` + `SOURCE_MART_BY_KIND`),
and a family block appended (never reordered) to
`analysis_spec.v1.yaml` `signal_families.families`; (6) artifacts wiring
(spearman/regression/diagnostics/Plackett-Luce per new family) plus golden
fixtures and a stored-run regression proving only the missing source gets
(re)fetched.

#### 7.1 — OnPage page signals (`on_page/instant_pages`)

URL grain (`target_keyword_id × canonical_url_hash` with the original `url`
retained), one synchronous live call per SERP URL with `enable_javascript`,
`enable_browser_rendering`, `load_resources`,
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
   `run_id`, `target_keyword_id`, `canonical_url_hash`); bounded
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

> **⌁ Revision — scope expansion (CHANGE).** Position is re-priced by what
> surrounds it: AI Overview presence cuts position-1 CTR by ~58% on
> informational queries (effect flips positive on branded). Item-type flags
> expand into a first-class **SERP-composition covariate family** — AI
> Overviews, local pack, featured snippet, People Also Ask, video, pixel depth
> where available — that Phase 14 uses to segment queries and Phase 13 uses to
> condition position targets on composition. Still normalize-only: all signals
> come from stored SERP payloads, no new API calls.

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

> **⌁ Revision — framing (KEEP + ADD).** 8.3/8.4 entity-authority signals are
> re-framed as **GATE-model inputs** (Phase 13): entity confirmation is an
> eligibility/authority prior, not a rank-order feature. The branded-demand
> half of this story moves to Phase 16 (free Google Trends API + Keyword
> Planner volumes + DA:BA-style ratio) — entity presence alone was shown to be
> the weaker half; brand *demand* is what discriminated HCU survivors (Brand
> Authority 50–52) from losers (37).

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

### Phase 9 — Manual content capture for blocklisted domains

Domains on the blocklist require manual browser scraping because automated
page-text retrieval is not sufficient. During live DataForSEO pulls, identify
SERP results whose exact returned URL belongs to a blocklisted domain and write
those rows to a separate Parquet handoff for manual completion. Preserve the
exact URL shown by DataForSEO; do not replace it with a canonicalized or
redirected URL.

#### Dev slices

1. **[ ] Slice 1 — Blocklist matching** — define the blocklist source and
   registrable-domain matching rule, while retaining the exact DataForSEO URL
   on each match.
2. **[ ] Slice 2 — Manual-scrape handoff Parquet** — write a separate Parquet
   dataset with `url`, `target_keyword`, `scraped_plain_text`, and
   `scraped_html` columns. The two scraped-content columns are nullable and
   blank when the row is first emitted for manual work; HTML is intended for
   browser source copy/paste.
3. **[ ] Slice 3 — Live-pull integration** — emit one handoff row for every
   blocklisted SERP result, deduplicated by exact `url × target_keyword`, and
   keep non-blocklisted retrieval unchanged.
4. **[ ] Slice 4 — Stored-run and validation coverage** — support rebuilding
   the handoff from stored DataForSEO responses, validate the schema and key
   columns before the Parquet write, and add fixtures/tests for blocked,
   unblocked, subdomain, duplicate, and URL-preservation cases.

| Acceptance item | Sub-phase | Status |
| --------------- | --------- | ------ |
| Exact DataForSEO SERP URL is retained for every blocklisted-domain match | 9.1–9.3 | Open |
| Separate manual-scrape Parquet contains `url`, `target_keyword`, nullable `scraped_plain_text`, and nullable `scraped_html` | 9.2 | Open |
| Initial handoff leaves both scraped-content columns blank | 9.2–9.3 | Open |
| Handoff rows are deduplicated by exact `url × target_keyword` and do not alter non-blocklisted retrieval | 9.3 | Open |
| Stored-run rebuild and schema/key validation are covered by tests | 9.4 | Open |

### Phase 10 — Embedding Store (keystone)

> **⌁ Revision — validated as planned (KEEP).** The May 2024 Content Warehouse
> leak confirms Google stores versioned site and page embeddings
> (`siteEmbeddings`, `versionId`) — this phase's model-pinning and versioned
> store design matches the disclosed machinery. Ships as specified; leaked
> attributes are used as feature-engineering priors revalidated against live
> SERPs, never as ground truth on weights (the leak contains none).

Persist the dense vectors that BGE and Gemini already compute and throw away,
so centroid/radius/focus math and the universe layer have something to compute
on. Today `bge_reranker.py` is a cross-encoder that returns a scalar logit per
(keyword, page) pair (no vector exists to store), and `gemini_embeddings.py`
writes the full `EmbedContentResponse` (with the 3072-d vector) into
`raw_responses/endpoint=gemini_embeddings` but nothing parses it into a usable
form. This phase adds a curated embeddings mart and a self-owned dual-encoder
path going forward.

**Primary decision (v1):** two write paths. (1) **Normalize-from-raw:** a
curated `embeddings` table materialized from the existing
`endpoint=gemini_embeddings` raw payloads (no re-fetch), unit-normalized, keyed
`(run_id, target_keyword_id, canonical_url_hash, role)` where
`role ∈ {query, page, passage}`. (2) **Live dual-encoder:** the deferred Phase
5.75 BGE-m3 bi-encoder becomes the forward-looking source of self-owned vectors
(query and page encoded separately → dot-product = retrieval score), persisted
to the same mart. Model name/version is pinned in `run.json` `config` and in
every `embeddings` row — scores are only comparable within one model.

**Mart columns (v1):** `run_id`, `target_keyword_id`, `canonical_url_hash`
(null for `role=query`), `role`, `model`, `dim`, `vector` (fixed-size list of
float32, L2-normalized), `source` (`gemini_embeddings_raw` | `bge_m3_live`).

**Guardrails:** a row whose `model` differs from the run's pinned model is
excluded from any pooled computation (never silently mix spaces); `dim` must
match the model registry entry; passage rows require a non-null
`page_id`/`passage_id` join key to `passages`.

**Out of scope for 10:** centroid/radius/focus computation (Phase 11), any
stats wiring (Phase 11 registers these as families), passage MaxSim scoring
(Phase 11.5).

#### Dev slices

**Progress:** 0 of 6 shipped.

1. **[ ] Slice 1 — Gemini raw → curated embeddings**
   - `build_embeddings_frame()` in `data/normalize.py`: parse
     `endpoint=gemini_embeddings` payloads, extract the float vector per
     (role, keyword, URL), L2-normalize, emit the mart schema above.
   - Null/excluded when payload missing, malformed, or model mismatch.
   - Tests: `test_run_normalize.py` with real-shaped `EmbedContentResponse`
     fixtures; unit-norm assertion; dedupe on latest `timestamp`.

2. **[ ] Slice 2 — Embeddings feature mart + validation**
   - `data/features.py` entry; fixed-size-list validation (`dim` consistent
     per model); `vector` excluded from `ANALYSIS_REQUIRED_COLUMNS` (it is a
     store, not a predictor column).
   - Tests: `test_feature_marts.py` schema + bounds.

3. **[ ] Slice 3 — BGE-m3 dual-encoder live path (promote Phase 5.75 Slice 2)**
   - Query and page encoded separately with `BAAI/bge-m3`; dot-product
     retrieval score; vectors persisted to the same mart with
     `source=bge_m3_live`.
   - `--live-bge` wiring; defer model load until first scorable keyword
     (consistent with Phase 5.2 Slice 3).
   - Tests: score shaping; dot-product == persisted retrieval score.

4. **[ ] Slice 4 — Query + passage embeddings**
   - Extend both write paths to `role=query` (keyword text) and
     `role=passage` (from `passages`); passage rows carry join keys.
   - Tests: passage grain round-trip; query rows have null URL hash.

5. **[ ] Slice 5 — Model registry + pinning**
   - `EMBEDDING_MODEL_REGISTRY` (name → dim, normalize rule); `run.json`
     records the pinned model; cross-model exclusion guard.
   - Tests: mixed-model panel → foreign-model rows dropped with a logged reason.

6. **[ ] Slice 6 — Golden fixture + stored-run regression**
   - Synthetic `endpoint=gemini_embeddings` payloads with known vectors;
     assert the curated mart reproduces them (values, norms, keys) without
     re-fetching.
   - Stored-run: re-normalize an old run materializes `embeddings` from raw
     with zero live calls.

#### Phase 10 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `embeddings` mart materialized from Gemini raw payloads, no re-fetch | 1, 6 | Open |
| Unit-normalized fixed-size vectors with model pinned per row | 1, 2, 5 | Open |
| BGE-m3 dual-encoder path writes self-owned query/page vectors | 3 | Open |
| Query and passage roles populated with correct join keys | 4 | Open |
| Cross-model rows excluded from pooled computation | 5 | Open |
| Golden fixture + stored-run regression green | 6 | Open |

### Phase 11 — Site/Topic Layer (centroids, radii, focus)

> **⌁ Revision — validated as planned, two additions (KEEP + ADD).** Centroid,
> radius, and focus are literal external analogs of the leaked `siteEmbeddings`
> / `siteRadius` / `siteFocusScore` attributes. Two research-driven
> refinements: **(a)** topical authority behaves as a **threshold/gate**, not a
> linear scale — these features register as GATE-model inputs in Phase 13
> (eligibility), and MaxSim as a RANK-model relevance feature; **(b)** your
> geometry is computed over *your crawl*, Google's over its full indexed
> representation of the domain (thin tag/parameter/legacy URLs included) — so
> every domain carries an **indexation-coverage covariate**
> (`pages_embedded / pages_indexed`), and focus/radius metrics are
> down-weighted or abstained on low-coverage domains (self-crawled geometry
> systematically overstates focus).

Compute the site-level topical metrics — domain centroid (`siteEmbedding`
analog), per-page radius (`siteRadius` analog), site focus (`siteFocusScore`
analog), and domain↔query topic fit — and register them as **new signal
families** so the entire existing Phase 5 engine (Spearman + BH, pooled OLS,
diagnostics, Plackett-Luce at all four rank depths) runs on them for free via
`stats/families.py`. This is the first direct test of "does the centroid
distance even matter" at the associational level, using machinery already
built and tested.

**Primary decision (v1):** centroid = **robust** (component-wise median
direction, then L2-normalized) over a domain's page vectors, not the mean —
a single off-topic page must not drag the core. Radius = `1 − cos(page_vec,
centroid)`. Focus = `1 − mean(radius over the domain's pages)`. Topic fit =
`cos(centroid, query_vec)`. All computed per `run_id` from the Phase 10
`embeddings` mart, joined back to the `analysis_mart` panel grain via the
derived `domain` column (same derivation as `domain_features`).

**Family registration:** new kind `site_topic` mapped to a
`site_topic_features` mart in `SOURCE_MART_BY_KIND`; families appended (never
reordered) to `analysis_spec.v1.yaml`: `site_topic_fit`
(`domain_query_cosine`), `site_focus` (`site_focus_score`), `page_radius`
(`page_site_radius`, sign-flipped so higher = more central). No
`analysis_mart` schema bump — mirrors the Phase 6.2/7.x pattern.

**Guardrails:** a domain with < 3 embedded pages yields `null` centroid/focus
(not a fabricated value); if the run's `embeddings` mart is empty or the
model is unpinned, the family registers as `skipped` with a reason rather than
hard-failing the whole stats run (consistent with family hard-fail semantics
in Slice 30).

**Out of scope for 11:** temporal change tracking (Phase 12), using these as
model features for prediction (Phase 13), passage MaxSim (Phase 11.5).

#### Dev slices

**Progress:** 0 of 7 shipped.

1. **[ ] Slice 1 — Centroid/radius/focus computation**
   - `data/site_topic.py`: group `embeddings` by domain → robust centroid;
     per-page radius; per-domain focus. Pure functions on the mart.
   - Tests: synthetic domain with a planted off-topic page → median centroid
     isolates it, mean does not (known-answer fixture).

2. **[ ] Slice 2 — `site_topic_features` mart + domain join**
   - Join page radius + domain focus onto the panel grain via derived
     `domain`; `domain_query_cosine` via query vectors.
   - Bounded validation: radius/focus/fit ∈ [−1, 1] (fit) / [0, 2] (radius).
   - Tests: `test_feature_marts.py`.

3. **[ ] Slice 3 — Family registry + spec**
   - `site_topic` kind in `VALID_SIGNAL_FAMILY_KINDS` +
     `SOURCE_MART_BY_KIND`; three families appended to `analysis_spec.v1.yaml`.
   - Tests: `test_stats_families.py`, `test_stats_spec.py`.

4. **[ ] Slice 4 — Stats wiring**
   - Family-aware Spearman/OLS/diagnostics/PL consume `site_topic_features`;
     `#### Family: site_topic_*` blocks in `stats_*`.
   - Tests: `test_stats_family_artifacts.py` with a synthetic panel where
     topic fit has a known rank relationship.

5. **[ ] Slice 5 — Small-domain null semantics**
   - Domains under the page threshold → nulls; completeness flag
     `site_topic_complete`.
   - Tests: under-threshold domain rows null, over-threshold rows populated.

6. **[ ] Slice 6 — Golden fixtures**
   - Known-focus synthetic sites; assert focus ordering and that the stats
     engine recovers a planted topic-fit ↔ rank association.
   - Complements Phase 5 Slice 31 (unblocks its similarity+TextRazor fixture
     pattern for site-topic families).

7. **[ ] Slice 7 — Docs**
   - `ARCHITECTURE.md` (mart + family), `TESTING.md`, limitations text:
     centroid metrics are associational, model-dependent, and not Google's
     literal `siteFocusScore`.

#### Phase 11 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Robust domain centroids resist planted off-topic pages | 1 | Open |
| Radius/focus/fit join onto panel grain with bounds validation | 2 | Open |
| `site_topic` families registered without `analysis_mart` schema bump | 3 | Open |
| Full Phase 5 stats run on site-topic families at all rank depths | 4 | Open |
| Under-threshold domains yield nulls, not fabricated values | 5 | Open |
| Golden fixtures prove known focus/fit relationships | 6 | Open |

### Phase 11.5 — Passage MaxSim scoring

Add passage-level relevance: split pages into passages (already have
`passages` / `passage_features`), embed them (Phase 10 Slice 4), and score a
page's relevance to a query as `max over passages cos(query, passage)` — the
ColBERT late-interaction pattern and the closest analog to Google's passage
ranking. Registers as a similarity-adjacent signal family.

**Primary decision (v1):** `page_maxsim_score = max_p cos(query_vec,
passage_vec)` per (keyword, page); also persist `best_passage_id` for
explainability. Family `passage_maxsim` (kind `site_topic` reused or a new
`passage_sim` kind) at the panel grain.

#### Dev slices

**Progress:** 0 of 3 shipped.

1. **[ ] Slice 1 — MaxSim computation + mart columns**
   - `data/site_topic.py` (or `similarity.py`): join passage embeddings to
     query vectors, reduce to per-page max; persist `page_maxsim_score`,
     `best_passage_id`.
   - Tests: multi-passage page where one passage matches the query → max
     selects it.

2. **[ ] Slice 2 — Family registration + stats wiring**
   - Append `passage_maxsim` family; family-aware stats consume it.
   - Tests: `test_stats_family_artifacts.py`.

3. **[ ] Slice 3 — Golden fixture**
   - Synthetic page with a planted best-matching passage; assert MaxSim
     outranks a page whose relevance is diffuse.

### Phase 11.6 — Pre-Publication Delta Simulator ⌁ (new)

Score a *draft* content piece against the site's vector geometry **before
publishing**: does introducing this page move the site toward or away from a
target topic? Three separable deltas, all computed pre-publication from the
Phase 10 store and Phase 11 geometry:

**Set and centroid definitions (explicit):** let $S$ be the domain's embedded
page vectors — the exact set Phase 11 used to compute $\mu_S$ — and $v_{new}$
the draft's vector. The **post-publication set is $S' = S \cup \{v_{new}\}$**:
exactly the pre set plus the draft, no pages removed, $|S'| = |S| + 1$. The
**post-publication centroid $\mu'_S$ is recomputed from scratch over $S'$ by
the same Phase 11 estimator** (component-wise median direction, then
L2-normalized) — a full recomputation via the same code path, never an
incremental tweak of $\mu_S$. **All existing pages are then re-scored against
$\mu'_S$**: $r'_i = 1 - \cos(v_i, \mu'_S)$ for every $v_i \in S'$, draft
included — stored radii against the old centroid are never reused inside the
post-publication quantities.

- **Δfit (centroid shift):** $\cos(\mu'_S, \mu_T) - \cos(\mu_S, \mu_T)$ —
  does the site centroid move toward the target-topic centroid when the
  draft's vector is included? Positive = stronger topical alignment.
- **ΔF (focus change):** $F' - F$ where $F = 1 - \mathrm{mean}_{v_i \in S}\, r_i$
  (radii against $\mu_S$) and $F' = 1 - \mathrm{mean}_{v_i \in S'}\, r'_i$
  (radii re-scored against $\mu'_S$, **draft included in the mean**,
  denominator $|S| + 1$). ΔF deliberately captures both effects — the
  centroid moving and the set changing; a page can improve Δfit while
  reducing focus (tangential to everything else), so the two are reported
  separately.
- **r_new (page radius):** $1 - \cos(v_{new}, \mu_S)$ — the `siteRadius`
  analog against the *current* centroid; a high-radius draft is a
  dilution-risk flag regardless of direction. Its post-publication radius
  $r'_{new}$ (against $\mu'_S$) is reported as a diagnostic only.

**Acceptance-test invariants** (verified in Slice 2):

- **I1 (pre/post sets):** $S' = S \cup \{v_{new}\}$ exactly — $|S'| = |S|+1$,
  every $v_i \in S$ present in $S'$ unchanged, no other members.
- **I2 (centroid update):** $\mu'_S$ equals the Phase 11 robust-centroid
  function applied to $S'$ bit-for-bit (same estimator, same code path);
  adding a duplicate of an existing page leaves the centroid invariant up to
  numerical tolerance.
- **I3 (similarity recalculation):** every $r'_i$ entering $F'$ is computed
  against $\mu'_S$; a fixture where $\mu'_S \neq \mu_S$ must show at least
  one existing page whose $r'_i \neq r_i$ — reusing stale radii fails the
  test.
- **I4 (focus calculation):** the $F'$ mean has denominator $|S| + 1$ and
  includes $r'_{new}$; dropping the draft from the mean changes the value
  and fails the test.
- **I5 (null contract preserved):** below-threshold domains or topic sets
  return `insufficient_data`/null deltas — invariants I1–I4 are evaluated
  only above both thresholds.

**Primary decision (v1):** the **topic centroid $\mu_T$ is built from SERP
winners**, not from abstract topic labels — embed the pages currently ranking
top-20 for a representative query set for the target topic. The evidence is
blunt: absolute embedding cosine correlates ~0.07 with rank while SERP-relative
constructs reach 0.47; anchoring $\mu_T$ to realized SERPs makes the delta a
SERP-relative measurement and auto-updates as SERPs shift. Threshold
semantics: Δfit is interpreted as movement toward/through a qualification
boundary (gate model), not as continuous rank payoff — once inside the
qualified region, more focus does not linearly help.

**Guardrails:** same model-pinning rules as Phase 10 (a centroid is only
comparable within one embedding model). **Centroid contract (resolved — one
rule everywhere):** below the Phase 11 small-domain threshold (< 3 embedded
pages) the simulator returns an `insufficient_data` verdict with all three
deltas `null` — never a shrunk, partial, or imputed estimate. There is one
shared threshold and one shared flag (Phase 11's `site_topic_complete`);
11.6 adds no estimator of its own, and a shrinkage estimator is explicitly
deferred (it would need its own threshold, spec, and tests — not v1). A draft
never *creates* a centroid: the simulated μ′_S is computed only by adding the
draft vector to an existing, non-null Phase 11 centroid; likewise the topic
centroid μ_T requires ≥ 5 embedded winner pages, otherwise Δfit/ΔF are
`null`. Simulated outputs therefore cannot fabricate centroid or focus values
— every emitted delta traces to real stored embeddings above both thresholds.
Indexation-coverage covariate attached to every delta (low coverage ⇒ delta
is an upper bound); every simulated "publish" decision is logged into the
Phase 12 `treatment_log` with its predicted deltas, so realized outcomes
retrospectively validate the simulator (DiD with 1–5-month effect latency).

**Out of scope for 11.6:** using deltas as direct rank predictions (they are
gate inputs); multi-draft portfolio optimization (13b universe territory).

#### Dev slices

**Progress:** 0 of 4 shipped.

1. **[ ] Slice 1 — Topic-centroid builder**
   - From a query set, pull stored top-20 page vectors → robust $\mu_T$
     per topic, versioned by snapshot date.
   - Tests: synthetic SERP set → centroid recovers planted topic direction.
2. **[ ] Slice 2 — Delta computation**
   - Given a draft vector + domain: Δfit, ΔF, r_new with coverage covariate;
     pure functions on the Phase 10/11 marts.
   - Tests: known-answer fixtures (in-topic draft raises Δfit; off-topic
     draft flagged by radius); below-threshold domain (< 3 embedded pages)
     returns `insufficient_data` with all deltas null and emits no centroid
     or focus value; under-populated topic set (< 5 winner pages) nulls
     Δfit/ΔF only; invariants I1–I5 hold on every fixture (pre/post set
     membership, from-scratch robust-centroid recomputation via the Phase 11
     code path, radii re-scored against μ′_S, draft included in the F′ mean,
     nulls below threshold).
3. **[ ] Slice 3 — CLI + report surfacing**
   - `simulate-draft` command: input text/URL → three deltas + verdict;
     results in `report.md`.
   - Tests: end-to-end on the golden fixture domain.
4. **[ ] Slice 4 — Treatment-log integration + validation harness**
   - Publish decisions logged with predicted deltas; Phase 12 DiD scores
     realized vs predicted after the effect window.
   - Tests: logged prediction joins the panel; prospective accuracy computed.

### Phase 11.75 — Vector-Space Visualization (UMAP projection)

Render the embedding space so queries, pages, site centroids, and their
similarity relationships are inspectable as a picture — the 3D-universe
intuition made concrete as a per-run artifact. Vocabulary, fixed: **nodes**
are the embedded entities (`role ∈ {query, page, site_centroid}`), **edges**
are similarity relationships from a k-nearest-neighbor graph weighted by
cosine, and centroids render as first-class nodes with their mean page
radius drawn as a halo (the `siteRadius` analog made visible). Depends on
Phase 10 (embeddings mart) and Phase 11 (centroids/radii/focus); becomes the
visual front-end for the Phase 13 universe.

**Primary decision (v1):** two outputs. (1) **Static report artifact** —
`runs/{run_id}/viz/vector_space.png` (+ `.svg`) linked from `report.md`:
UMAP projection (`umap-learn`, `metric="cosine"`, pinned `random_state`)
with t-SNE (`sklearn`) as a diagnostics-only comparison render.
(2) **Interactive HTML explorer** (optional slice) — one self-contained
Plotly file (no server, no build step) with hover tooltips: URL, role,
radius, focus, per-backend similarity scores. Edges come from a **kNN graph**
(default k = 10) — never the full N² pairwise matrix, which is unreadable at
SERP scale; page→centroid membership edges are a distinct edge type from
similarity edges.

**Visual encoding:** node shape by role (query = diamond, page = circle,
centroid = star); centroid node size ∝ site focus; centroid halo disc radius
= mean page radius; edge width/alpha ∝ cosine weight; a planted off-topic
page must appear visibly separated from its own site's centroid.

**Guardrails**

- **Projection is display-only.** UMAP/t-SNE distort distances; every metric
  (radius, focus, fit, MaxSim) is computed in full dimensionality and only
  *plotted* in 2D. Projection coordinates are never registered as features,
  never join a mart, never enter stats.
- **Determinism:** pinned `random_state`; identical input → identical
  coordinates (test).
- **Cross-run comparability (Phase 12 hook):** fit UMAP on the union of
  snapshots, or fit once and `transform()` new points, so the same entity
  keeps stable coordinates across time; independent per-snapshot refits
  produce incomparable maps and are valid for single-run inspection only.
- **Model purity:** same cross-model exclusion as Phase 10 — one embedding
  space per plot.
- **Degenerate panels:** fewer than ~15 embedded entities → skip projection
  with a logged reason (`n_neighbors` clamped to point count; below that
  scale the picture is meaningless anyway).

**Out of scope for 11.75:** 3D rendering or served webapp (the interactive
slice ships one static HTML file); animation (Phase 12 adds cross-snapshot
frames); using the plot to select model features; real-time updates.

#### Dev slices

**Progress:** 0 of 6 shipped.

1. **[ ] Slice 1 — kNN similarity graph builder**
   - `viz/graph.py`: read the `embeddings` mart → nodes frame (id, role,
     vector) + edge frame (src, dst, weight, `edge_type ∈ {similarity,
     membership}`). Cosine kNN (k configurable, default 10); membership
     edges page→centroid from Phase 11.
   - Tests: synthetic space with known neighbors → correct edges/weights;
     thresholding; cross-model rows excluded.

2. **[ ] Slice 2 — UMAP projection module**
   - `viz/project.py`: UMAP on full-dim vectors (`metric="cosine"`, pinned
     seed, `n_neighbors` clamped); t-SNE comparison render behind a flag.
   - Determinism test: identical input → identical coordinates.
   - Optional dependency extra (`umap-learn`); graceful skip with a logged
     reason when not installed (consistent with the optional `matplotlib`
     handling in `ranking_explainability_viz.py`).

3. **[ ] Slice 3 — Static per-run artifact + report wiring**
   - Render `runs/{run_id}/viz/vector_space.png` (+ `.svg`) with the visual
     encoding above; link from `report.md`.
   - Tests: artifact exists after analyze; roles/edge types present in the
     render data; off-topic fixture page separated from its centroid.

4. **[ ] Slice 4 — Interactive HTML explorer (optional)**
   - Self-contained Plotly HTML (`runs/{run_id}/viz/vector_space.html`);
     hover shows URL, role, radius, focus, per-backend similarity.
   - Tests: HTML payload contains all node ids; snapshot the data payload,
     not the rendering.

5. **[ ] Slice 5 — Cross-snapshot alignment (Phase 12 hook)**
   - Fit-once-then-transform (or union-fit) mode so the same entity keeps
     stable coordinates across snapshots; emits per-snapshot frames for
     future animation.
   - Tests: same page across two synthetic snapshots keeps nearby
     coordinates under transform mode.

6. **[ ] Slice 6 — Golden fixture + docs**
   - Synthetic universe: two focused sites + one planted off-topic page →
     assertions on the full-dim data behind the plot (off-topic page's
     distance-to-own-centroid > every core page's) and on the 2D render
     (cluster separation above a silhouette threshold).
   - `ARCHITECTURE.md` + `TESTING.md`; limitations text: 2D projection is
     illustrative, distances are distorted, never evidence in stats.

#### Phase 11.75 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| kNN graph + membership edges built from the embeddings mart | 1 | Open |
| Deterministic UMAP projection with cosine metric | 2 | Open |
| Static PNG/SVG per run linked from `report.md` | 3 | Open |
| Optional self-contained interactive HTML explorer | 4 | Open |
| Cross-snapshot coordinate stability mode | 5 | Open |
| Golden fixture: off-topic page separable; projection never used as a feature | 6 | Open |

### Phase 12 — Temporal Panel (the bottleneck: a clock, not code)

Runs today are isolated snapshots; nothing connects the same
`(keyword, URL)` across time. This phase turns repeated runs into a
longitudinal panel and adds the lead-lag and difference-in-differences
machinery that separates a *live* signal from a static artifact. **Start the
recurring collection immediately** — the validation timeline is bounded by
data accumulation (content updates take ~1 month to show rank effects, new
pages 3–5 months), not by engineering.

**Primary decision (v1):** a `panel` mart keyed `(target_keyword_id,
canonical_url_hash, snapshot_date)`, materialized by joining across run trees
on overlapping keywords. Each row carries the full Phase 5 feature set plus
the Phase 10–11 vector-derived metrics, versioned by `snapshot_date`. The
`--stored-run` replay machinery already makes re-collection idempotent; a
scheduler (cron / CI schedule) triggers a fresh run on a fixed keyword set on
a fixed cadence (weekly SERP + embeddings; monthly full re-embed).

**Lead-lag:** `panel_leadlag` table pairs `Δmetric(t → t+1)` with
`Δrank(t+1 → t+2)` per page-keyword, with lag windows matched to the
documented effect latencies (4–6 weeks for refreshes, 12+ weeks for new
pages). **DiD:** a `treatment_log` (you record your own content changes:
publish / refresh / consolidate / prune, with date and target pages) drives a
difference-in-differences estimate — treated pages' rank change minus matched
unchanged pages' change over the same window — expressible in the existing
pooled-OLS-with-FE machinery.

**Guardrails:** metrics are only comparable within a pinned embedding model —
a model upgrade forces a full re-embed of the archive and a `model_version`
break in the panel (never bridge across it silently); SERP rows are
geo-pinned and de-personalized so Δrank reflects the algorithm, not
measurement noise.

**Out of scope for 12:** predictive modeling on the panel (Phase 13),
behavioral/GSC feed (deferred — account-gated).

> **⌁ Revision — two additions (KEEP + ADD).**
> **(a) Regime + segment labels on every snapshot:** each panel row persists
> the Phase 14 query-segment label and the Phase 15 volatility-regime
> covariates (free trackers: MozCast, Algoroo, SERPmetrics), so evaluation
> windows are reproducible and update-adjacent folds can be embargoed.
> **(b) Median-of-N labels:** the stored rank label switches from
> single-scrape rank to median-of-N (N ≥ 5) repeat-sampled rank per
> keyword-snapshot (geo-pinned, fixed device, minute-level timestamps), plus
> top-10/20 membership and ±1/±3 bucket labels — trackers reproduce exact
> positions only 71–78% of the time but 96–97% within ±3, so the label
> schema is built to the instrument's real resolution. Labels are median
> rank, membership, and buckets — never a single-scrape integer.
>
> **Absent-URL semantics (deterministic, matches the acceptance contract):**
> the **candidate URL universe** for a keyword-snapshot is the union of all
> URLs observed in any valid repeat's top-20 — never just the first scrape's
> rows. Every union member receives a coded rank per repeat: its observed
> rank when present, or **21 with `censored = true`** when absent from a
> valid repeat (21 = depth + 1; the flag distinguishes "not observed in
> top-20" from any real position — a stored 21 without the flag is a schema
> error). The URL's label is the median of its N coded values. **Membership:**
> top-10 member ⇔ median coded rank ≤ 10 (equivalently: in the top-10 in
> > N/2 valid repeats); top-20 member ⇔ median ≤ 20; otherwise non-member
> for that snapshot. **Training targets:** the median coded rank is the
> RANK-model ordering target only for rows whose median is ≤ 20; rows with
> median 21 are excluded from RANK training (their position is censored, not
> ordinal) and instead serve as membership-negative (label 0) examples for
> the GATE model — the censor share (fraction of repeats absent) is stored
> per row as a reliability field. **NDCG evaluation:** grades come from the
> fixed contract mapping (rel 3 = median 1–3, rel 2 = 4–10, rel 1 = 11–20,
> rel 0 = 21/censored); only grade ≥ 1 URLs enter the gain vectors —
> censored rows contribute neither gain nor a slot in the ideal ordering.

#### Dev slices

**Progress:** 0 of 8 shipped.

1. **[ ] Slice 1 — Panel schema + cross-run join**
   - `data/panel.py`: scan multiple run trees, join on
     `(target_keyword_id, canonical_url_hash)`, emit `snapshot_date` rows.
   - Tests: two synthetic runs with overlapping keywords → one panel row per
     page per date.

2. **[ ] Slice 2 — Recurring-run scheduler contract**
   - Fixed keyword set config; idempotent re-collection via `--stored-run`;
     `run.json` records `schedule_id` and `snapshot_date`.
   - Tests: replay of a scheduled run produces the same panel keys.

3. **[ ] Slice 3 — Δmetric / Δrank computation**
   - Per page-keyword, diff consecutive snapshots for every registered
     feature + vector metric.
   - Tests: planted metric change appears with correct sign and timing.

4. **[ ] Slice 4 — Lead-lag tables**
   - `panel_leadlag` with configurable lag windows (default 4–6 / 12+ weeks).
   - Tests: lag-window assignment correctness.

5. **[ ] Slice 5 — Treatment log data model**
   - `treatment_log` schema (date, action, target pages/keywords, optional
     predicted delta); manual-entry interface (CLI or YAML).
   - Tests: schema validation; join to panel.

6. **[ ] Slice 6 — Difference-in-differences estimation**
   - Treated vs matched-control rank change; OLS-with-FE implementation;
     clustered SEs.
   - Tests: synthetic treated group with a known effect recovers it.

7. **[ ] Slice 7 — Model-version break guard**
   - `model_version` on the panel; cross-version bridging raises/splits.
   - Tests: mixed-model panel refuses pooled Δ computation.

8. **[ ] Slice 8 — Golden fixture + regression**
   - A 3-snapshot synthetic panel with a planted treatment effect; assert
     lead-lag and DiD recover it.

#### Phase 12 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `panel` mart joins the same page-keyword across run trees | 1 | Open |
| Recurring runs are idempotent and produce stable panel keys | 2 | Open |
| Δmetric/Δrank computed per page-keyword across snapshots | 3 | Open |
| Lead-lag tables respect effect-latency windows | 4 | Open |
| Treatment log validated and joined to the panel | 5 | Open |
| DiD recovers a planted treatment effect | 6, 8 | Open |
| Model-version breaks prevent silent cross-model comparison | 7 | Open |

### Phase 13 — Predictive & Universe Layer

> **⌁ Revision — structural change (CHANGE + ADD).** The single predictor
> splits into **two models**, mirroring Google's disclosed pipeline
> (retrieval gates → neural re-rank → click re-order):
>
> - **GATE ("who can rank"):** top-10/20 membership classifier over domain
>   authority (7.4), topical centroid fit (11), brand demand (16), and
>   technical qualification (7.1, 8.1). Carries the high-accuracy claims —
>   the candidate set is stable (72.9% of top-10 pages are >3 years old;
>   only 1.74% of new pages reach top-10 within a year).
> - **RANK ("in what order"):** orders GATE-admitted candidates using
>   SERP-relative features (Phase 6.1 inversion), emitting predicted rank
>   **with prediction intervals — never point ranks**; abstains when the
>   interval exceeds the Phase 15 per-segment threshold. Expectation cap:
>   the ~60–80% exact-order band from the evidence synthesis.
>
> Every 13a candidate is trained twice — as gate and as ranker. Evaluation
> is **end-to-end**: the pipeline output (GATE admit/reject decisions plus
> the RANK ordering of admitted candidates) is scored against the full
> realized universe — the Phase 12 union-of-repeats label set, including its
> censored rows — not only RANK quality on GATE-admitted candidates. GATE is
> additionally scored on its own: membership **recall** (fraction of realized
> top-10/20 members admitted) and **precision** (fraction of admits that are
> realized members), per segment. A **gate miss** (realized grade ≥ 1 URL
> rejected by GATE) is represented in the acceptance metrics as forfeited
> gain: it keeps its grade in the ideal DCG but has no predicted slot, so
> end-to-end NDCG drops accordingly; a false admit consumes an emitted slot.
> Model selection runs on the acceptance contract (out-of-time end-to-end
> NDCG@10 at declared coverage, per segment, with the GATE recall floor);
> exact-position MAE and RANK-only (oracle-gate) NDCG survive as diagnostics
> only.
> The `w_beh` term is formalized as a pluggable **`behavioral_signal` family
> interface**, zero-default today: GSC own-site data is the immediate opt-in
> ingest; DOJ-remedy interaction data ingests only if the stayed sharing
> order ever takes effect (Phase 15 Slice 5 carries the docket-monitoring
> hook).

Turn the (now temporal) feature set into a validated predictor and a
controllable simulation. Two halves: **(13a) the bake-off** that answers
"what's the correct model" under out-of-time validation with formal ablation,
and **(13b) the universe** — a shared embedding space of queries, pages, and
site centroids that you perturb to simulate ranking changes. 13a is the
validation gate; 13b is only trustworthy once 13a passes — and 13b ships only
after GATE/RANK passes the acceptance contract, since it would otherwise emit
confident trajectories on exactly the queries where prediction is unreliable.

**Primary decision (13a):** candidate models evaluated on **out-of-time
NDCG@10** — train on earlier snapshots, score held-out *future* SERPs, per
query, averaged (the production LTR evaluation standard; your Phase 5.6
time-split slice is the seed). Candidates, in increasing complexity: (a) a
**linear force model** (`w_sem·cos(q,p) + w_auth·authority + w_site·site_fit
+ w_beh·ctr_delta`, weights fitted); (b) a **gradient-boosted classifier**
(top-10 probability, HistGradientBoosting/LightGBM); (c) **LambdaMART**
(lambdarank objective — statistically adjacent to your Plackett-Luce work);
(d) a **feature-free cosine baseline** (raw query·page cosine only) as the
null every other model must beat. **Ablation:** retrain the winner minus
`site_fit`, minus `radius`; the NDCG cost (paired bootstrap over queries) is
the definitive answer to "do the centroid terms even matter." Selection rule:
adopt the simplest model that beats the baseline out-of-time **on end-to-end
pipeline NDCG (GATE composed with RANK — gate misses count as forfeited
gain, per the acceptance contract), while clearing the GATE recall floor**,
passes ablation
for the features you intend to intervene on, and is calibrated (predicted
top-10 probabilities match realized frequencies in deciles). RANK-only
oracle-gate NDCG is reported alongside as a diagnostic to separate gate
error from ordering error, but it is never the selection figure.

**Primary decision (13b):** a `universe` module — nodes
(query/page/site-centroid) in one shared space; typed forces (semantic,
site-membership, link authority via PageRank, behavioral proxy); a SERP as a
computed readout `sorted(score(q,p))`; and `simulate(query, intervention)`
that runs a SERP, applies a change (publish / refresh / consolidate / add a
link), re-runs, and returns rank diffs. Force weights come from the 13a
winner. **Honest ceiling (documented in limitations):** the behavioral term
for competitors defaults to zero (you can only observe your own CTR), so the
universe predicts *direction and relative magnitude* for the topical/authority
components — never exact positions.

**Guardrails:** rolling-forward validation only (never random splits — they
leak query-level patterns); a model whose out-of-time NDCG collapses in the
fold after a core update flags a regime change and is not trusted for
prediction until refit; every universe prediction is logged with its
assumptions and date so it can be scored against realized outcomes.

**Out of scope for 13:** real-time serving, the behavioral/GSC feed
(deferred — account-gated; when added it becomes the `w_beh` term for your
own pages), any claim of exact-position prediction.

#### Dev slices

**Progress:** 0 of 10 shipped.

1. **[ ] Slice 1 — Out-of-time evaluation harness**
   - `stats/evaluate.py`: rolling-forward splits on the Phase 12 panel;
     NDCG@k per query; top-10 AUC; paired keyword bootstrap CIs.
   - Tests: synthetic panel with known ordering → correct NDCG; bootstrap CI
     coverage.

2. **[ ] Slice 2 — Feature-free cosine baseline**
   - The null model every candidate must beat.
   - Tests: baseline NDCG computed and recorded.

3. **[ ] Slice 3 — Linear force model**
   - Fit `w_sem…w_beh` by regression on the panel.
   - Tests: weights recovered from a synthetic panel with known ground truth.

4. **[ ] Slice 4 — Gradient-boosted classifier**
   - Top-10 probability; same features + controls.
   - Tests: out-of-time AUC reported per fold.

5. **[ ] Slice 5 — LambdaMART ranker**
   - Lambdarank objective; per-query grouping.
   - Tests: NDCG@10 on held-out queries.

6. **[ ] Slice 6 — Ablation studies**
   - Retrain the winner minus `site_fit`, minus `radius`; paired bootstrap on
     the NDCG difference.
   - Tests: ablation cost with CI; `adds_value` verdict.

7. **[ ] Slice 7 — Calibration + model selection**
   - Decile calibration of predicted probabilities; selection rule applied;
     chosen model persisted with its feature list and weights.
   - Tests: calibration table; selection respects the rule.

8. **[ ] Slice 8 — Universe module**
   - `universe/`: nodes, typed forces, PageRank authority, `simulate()`.
   - Tests: golden synthetic universe — planted off-topic page ranks last;
     in-topic draft strengthens focus; refresh flips a near-tied pair.

9. **[ ] Slice 9 — Prediction logging + prospective scoring**
   - Every intervention prediction logged with date/assumptions; scored
     against realized SERPs after the effect window.
   - Tests: log schema; prospective accuracy computed.

10. **[ ] Slice 10 — Golden fixtures + docs**
    - End-to-end synthetic universe with known interventions; limitations
      text (mechanism model, behavioral ceiling, not Google's literal scores).

#### Phase 13 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Rolling-forward NDCG@10 harness with keyword bootstrap CIs | 1 | Open |
| Feature-free baseline recorded as the null to beat | 2 | Open |
| All four candidates evaluated out-of-time on the panel | 3–5 | Open |
| Ablation proves (or disproves) centroid-feature value with NDCG cost | 6 | Open |
| Model selected by the simplest-calibrated rule and persisted | 7 | Open |
| Universe reproduces known interventions in a golden fixture | 8, 10 | Open |
| Predictions logged and scored prospectively | 9 | Open |
| GATE membership classifier evaluated per segment with calibrated probabilities, recall, and precision (recall floor ≥ 0.90 top-10) ⌁ | 4 | Open |
| End-to-end pipeline NDCG (GATE composed with RANK) meets the contract; gate misses represented as forfeited gain; RANK-only oracle-gate NDCG reported as diagnostic ⌁ | 1, 4–7 | Open |
| RANK model emits prediction intervals; abstention at Phase 15 thresholds; accuracy quoted at declared coverage ⌁ | 4–7 | Open |
| Acceptance contract (out-of-time NDCG@10 ≥ 0.95, segmented, stability-filtered, median-of-N labels) pre-registered before scoring ⌁ | 1 | Open |

### Phase 14 — Query Segmentation ⌁ (new)

Google states verbatim that "the weight applied to each factor varies
depending on the nature of your query," and the industry abandoned universal
factor lists a decade ago (Searchmetrics: "ranking factors that apply equally
to all industries have ceased to exist"). One global model is not merely
inaccurate — it is structurally inconsistent: keyword fixed effects absorb
intercepts, not slope heterogeneity, and pooled correlations demonstrably
reverse segment-level effects.

**Primary decision (v1):** a segment classifier labels every keyword at
collection time into five mandatory segments, each getting its own model head
or explicit interaction structure in Phase 13:

1. **Local** — separate algorithm (proximity/business-profile/review-driven);
   a page-rank model does not apply; segment out and handle separately.
2. **News / QDF** — freshness weight flips per class; exclude from
   stability-filtered panels by default.
3. **Navigational / branded** — near-deterministic; supports the strictest
   accuracy claims but must not inflate pooled metrics.
4. **AIO / featured-snippet-bearing informational** — rank and citation are
   separate labels (AIO presence re-priced position-1 CTR by ~−58%);
   position targets conditioned on Phase 7.6 composition covariates.
5. **YMYL** — distinct authority bar; evaluate separately.

**Overlap resolution (deterministic, exclusive):** real queries trigger
several rules at once, so every keyword carries **two** persisted values:

- `segment_flags` — the full multi-label set of triggered rules (e.g.
  `{YMYL, AIO}`); used as covariates and for overlap auditing.
- `segment_primary` — exactly one label, chosen by fixed precedence:
  **Local > News/QDF > Navigational/branded > YMYL > AIO-informational**.
  Rationale: Local and News/QDF run different ranking regimes entirely and
  must be isolated first; navigational queries are near-deterministic and
  would silently inflate any segment they land in; YMYL outranks AIO
  because the authority bar changes gate behavior fundamentally, while AIO
  composition is already preserved as Phase 7.6 covariates regardless of
  the primary label, so less information is lost that way.

**Fallback:** a keyword with no triggered flag is `unknown` — excluded from
all per-segment accuracy claims, included in volume-weighted totals only as
its own reported line. There is no `mixed` primary: mixedness lives in
`segment_flags`, never in `segment_primary`. Missing/unparseable SERP
payload ⇒ `unknown`, never a guessed label.

**Reproducibility:** the v1 classifier is pure deterministic rules over
stored SERP payloads — same payload + same rules ⇒ same labels. A
`segment_rules_version` is persisted on every Phase 12 snapshot row; a rules
change forces a version break with re-labeling (same discipline as Phase 10
model pinning — never bridge across it silently). Train/holdout folds
stratify by `segment_primary`; per-segment metrics are computed on
`segment_primary` alone; overlap rates (`flags` vs `primary`) are reported
per segment so the precedence rule's impact is auditable.

**Reporting contract:** per-segment AND volume-weighted metrics only; a single
pooled headline accuracy is an invalid claim.

#### Dev slices

**Progress:** 0 of 3 shipped.

1. **[ ] Slice 1 — Segment classifier** — deterministic rule-based v1 from
   stored SERP payloads (local pack present, news boxes, AIO flag,
   brand/entity match, YMYL lexicon), emitting both `segment_flags` and
   `segment_primary` via the fixed precedence (Local > News/QDF >
   Navigational/branded > YMYL > AIO-informational) with `unknown` fallback;
   upgradeable to a learned classifier later (a model swap is a rules-version
   break). Tests: overlapping-flag fixtures resolve to the correct primary;
   no-payload keyword labels `unknown`; identical payload ⇒ identical labels.
2. **[ ] Slice 2 — Label persistence** — `segment_flags`, `segment_primary`,
   and `segment_rules_version` on every Phase 12
   snapshot row; reproducible evaluation windows.
3. **[ ] Slice 3 — Segmented reporting** — per-segment + volume-weighted
   metrics in `report.md` and the Phase 13 evaluation harness.

### Phase 15 — Volatility Regime, Measurement Protocol & Abstention ⌁ (new)

The measurement layer every accuracy claim stands on. Google ships ~5,000
changes/year with 1,000+ live experiments daily; trackers reproduce a manual
SERP exactly only 71–78% of the time (96–97% within ±3); only 16.5% of top-10
positions kept the same URL over two quiet weeks. All inputs in this phase
are **free** — no paid API.

**Primary decision (v1):** three components.

- **Regime covariates (free):** MozCast, Algoroo, and SERPmetrics ingested
  daily as regime labels on every snapshot; confirmed-update exclusion
  windows; regime-change flags that suspend trust in post-update folds until
  refit. **Embargo boundaries (deterministic):** a spike = a tracker value
  above its own preregistered high-volatility threshold (constants in
  `analysis_spec`, one per tracker); a tracker with a missing value on a date
  is ignored for that date — the ≥3-tracker rule is evaluated only over
  reporting trackers, so with any tracker down the rule cannot fire and
  embargo relies on official confirmation alone. **Start** = the earlier of
  (a) Google's official update confirmation date, (b) the first date with
  ≥3 reporting trackers spiking. **End** = max(start + 28 days, the official
  rollout-complete date) when a completion notice exists, else start + 42
  days — the 4–6 week settling rule, with no discretion. Snapshots inside
  [start, end] are excluded from acceptance evaluation folds and flagged
  `regime = update_window`; the first fold after `end` is quarantined until
  the model is refit on post-settling data.
- **Measurement protocol:** geo-pinned coordinates (city-level geo moves
  18–34% of local results), one fixed device class (mobile/desktop diverge
  on ~76% of queries), median-of-N (N ≥ 5) repeat samples with minute-level
  timestamps. Labels: median rank, top-10/20 membership, ±1/±3 buckets.
- **Abstention layer:** per-segment confidence thresholds on the Phase 13
  RANK model's prediction-interval width; below threshold the system declines
  to score. Accuracy is only ever reported jointly with coverage — the
  coverage–accuracy frontier is the deliverable. **Calibration is
  leakage-safe (deterministic):** for each rolling-forward fold, the
  interval-width threshold τ_s for segment s is selected **only on that
  fold's training window** (data strictly before the evaluation window) or on
  a dedicated calibration split that ends before the evaluation window minus
  the embargo/settling gap; τ_s is then frozen before the fold is scored.
  No future-fold labels, realized errors, or future interval distributions
  may influence τ_s — the frontier for a fold is computed with its frozen
  τ_s, and every (τ_s, calibration window) pair is persisted in
  `analysis_spec` so the decision path is replayable. If a segment's
  training window contains fewer than `N_min` scored queries (constant in
  `analysis_spec`), τ_s falls back to the all-segment threshold; if that is
  also uncalibratable, coverage defaults to 1.0 (no abstention) rather than
  a tuned-on-the-fly threshold.

#### Dev slices

**Progress:** 0 of 5 shipped.

1. **[ ] Slice 1 — Free-tracker ingest** — MozCast/Algoroo/SERPmetrics daily
   pulls; regime label per snapshot date.
2. **[ ] Slice 2 — Update-window detection** — ≥3-tracker spike rule over
   reporting trackers only; deterministic embargo [start, end] per the
   Primary-decision rules (earlier of official confirmation or first ≥3-spike
   date; end = max(start + 28d, official completion) else start + 42d).
   Tests: synthetic tracker series with a missing-tracker day → rule cannot
   fire; confirmation-first and spike-first orderings both yield the
   specified window; snapshots inside the window carry `update_window` and
   are excluded from evaluation folds.
3. **[ ] Slice 3 — Median-of-N collection mode** — repeat-sample collection
   on a subset panel; median-rank/membership/bucket labels materialized.
4. **[ ] Slice 4 — Abstention calibration** — interval-width thresholds per
   segment, calibrated per fold on training-window or isolated calibration
   data only (frozen before scoring; no future-fold inputs); coverage–accuracy
   frontier computation and plotting with frozen thresholds; (τ_s, window)
   pairs persisted to `analysis_spec`. Tests: a fixture where the optimal
   threshold differs between training and evaluation windows must still use
   the training-derived value; leakage probe — any code path reading
   evaluation-window labels or intervals during calibration fails the test.
5. **[ ] Slice 5 — Docket-monitoring hook** — watch the DOJ data-sharing
   remedy (stayed pending appeal); if it takes effect, activate the Phase 13
   `behavioral_signal` seam.

### Phase 16 — Brand-Demand Signals ⌁ (new)

The best-validated discriminator of domain-level outcomes is brand demand,
not links: in Moz's controlled 1.9M-keyword study of the September 2023
Helpful Content Update, losers averaged Brand Authority 37 versus 50–52 for
survivors (DA:BA 2:1 vs 1.4:1), and branded search volume correlates with
rankings nearly as strongly as Domain Authority, more strongly than raw link
counts. All inputs **free**.

**Primary decision (v1):** branded-query-volume proxies from the official
Google Trends API (v1alpha, free with a Google Cloud account; pytrends as
unofficial fallback) and Keyword Planner volumes (free with any Google Ads
account); a DA:BA-style authority-to-brand ratio (Phase 7.4 authority ÷
branded volume); branded-anchor share from Phase 7.2 link data. All three
register as GATE-model features alongside the Phase 8.3/8.4 entity-authority
family.

#### Dev slices

**Progress:** 0 of 3 shipped.

1. **[ ] Slice 1 — Trends ingest** — normalized branded-interest series per
   panel domain; snapshot-versioned.
2. **[ ] Slice 2 — Authority:brand ratio + branded-anchor share** — feature
   computation from existing 7.2/7.4 data.
3. **[ ] Slice 3 — GATE integration** — family registration; Phase 13 gate
   features; ablation against Phase 8 entity authority.

## Sequencing, cost, and the clock ⌁

The bottleneck remains a clock, not code: panel depth bounds everything
downstream, and documented effect latencies (~1 month for content updates,
3–5 months for new pages) set the minimum evaluation horizon.

| Window | Work |
| ------ | ---- |
| Months 1–2 | Start the weekly panel immediately (MVP: 10k keywords × top-20). Land the Phase 6.1 estimand inversion (`analysis_spec.v2.yaml`) and the Phase 7.6 composition expansion. |
| Months 3–4 | Phase 15 regime covariates + label protocol; Phase 16 brand-demand features; GATE model v1 on accumulated snapshots. |
| Months 5–8 | Phase 10 embedding store live; Phase 11 centroid/radius/focus as GATE features; Phase 11.6 delta simulator; Phase 14 segment heads; abstention calibration. |
| Months 9–12 | Phase 13 bake-off on the acceptance contract (out-of-time NDCG@10 ≥ 0.95 at declared coverage); acceptance evaluation; prospective prediction logging; 13b universe ships only after acceptance passes. |

**Cost:** DataForSEO is the only paid input (all APIs pay-as-you-go, no
monthly minimums since 2026-07-01). MVP ≈ $60–100/month all-in — SERP pulls
≈ $52 per 10k keywords weekly, page text ≈ $15–30, embeddings $1–8 (local
BGE), sampled backlinks $24–60 (rotating 5–10k domain sample; exhaustive
collection is the one prohibitive line item). A $500/month tier buys 50k
keywords and per-niche segment models. Everything else is $0: MozCast,
Algoroo, SERPmetrics, Google Trends API, Keyword Planner, Common Crawl, CrUX,
Wayback, Wikidata, GSC.

## Deferred

- Entity-derived features beyond Phase 5.6 density bundle (keyword–entity overlap,
  type-weighted density, passage-level density)
- CI, release packaging, coverage thresholds
- Production deployment, databases, cache
- Parquet `Variant` type for provider payloads
- Content Analysis API (citation-index brand mentions) — marginal value over
  TextRazor, doesn't fit a per-URL/per-domain grain cleanly (considered and
  cut from Phase 7/8 scope)
- Majestic, Ahrefs, Moz, Similarweb, Google Search Console, Google Natural
  Language API — paid/account-gated third-party signals (considered and cut
  from Phase 8 scope in favor of free-tier sources). GSC resurfaces in
  Phases 12–13 as the optional behavioral (`w_beh`) feed for your own pages.

## History

- **Feasibility-study revision (2026-07-20):** 12-dimension research program
  (leak + DOJ trial + academic/industry accuracy measurements) applied
  in-file. Top matter: acceptance contract (out-of-time NDCG@10 ≥ 0.95,
  segmented, stability-filtered, median-of-N labels, abstention coverage) and
  free/cheap sourcing policy (DataForSEO-only paid input). CHANGED: Phase 6.1
  (SERP-relative estimand inversion), Phase 7.6 (composition family),
  Phase 13 (GATE/RANK split, abstention, `behavioral_signal` seam).
  ADDED: Phase 11.6 (pre-publication delta simulator), Phase 14 (query
  segmentation), Phase 15 (regime/measurement/abstention), Phase 16
  (brand demand). KEPT with validation notes: Phases 1–12 architecture
  (embedding store, centroids, temporal panel confirmed by leak/trial
  record). DELETED: nothing; exact-position prediction demoted to diagnostic.
  Revision blocks marked ⌁ throughout.
- **Embargo + calibration determinism (2026-07-20):** Phase 15 now pins
  confirmed-update embargo boundaries (start = earlier of official
  confirmation or first ≥3-reporting-tracker spike; end = max(start+28d,
  official completion) else start+42d; missing trackers ignored; post-end
  fold quarantined) and leakage-safe abstention calibration (per-fold
  training-window or isolated calibration split only; τ frozen before
  scoring, persisted to analysis_spec; N_min fallback chain).
- **Segment-precedence determinism (2026-07-20):** Phase 14 now defines dual
  labels (`segment_flags` multi-label set + single `segment_primary`), fixed
  precedence Local > News/QDF > Navigational/branded > YMYL > AIO-info,
  `unknown` fallback (no `mixed` primary), `segment_rules_version` breaks,
  and fold stratification by primary — collection, folds, and per-segment
  metrics are reproducible.
- **End-to-end GATE/RANK evaluation (2026-07-20):** acceptance contract and
  Phase 13 now score the composed pipeline, not RANK-on-admitted-only:
  primary metric is end-to-end NDCG@10 (gate miss = forfeited gain, false
  admit = consumed slot); new GATE metrics row (recall/precision per segment,
  ≥ 0.90 top-10 recall floor); 13a selection rule and acceptance criteria
  table updated to match; RANK-only oracle-gate NDCG kept as diagnostic.
- **Median-of-N absent-URL semantics (2026-07-20):** Phase 12 (b) block
  extended — candidate universe = union over valid repeats; absent URLs
  coded 21 with explicit `censored` flag; membership via median thresholds
  (≤10 / ≤20); censored rows excluded from RANK ordering targets, used as
  GATE label-0 examples, and excluded from NDCG gain vectors. Consistent
  with the acceptance-contract Missing-URL rule; geo/device/timestamp
  requirements unchanged.
- **Simulator-semantics formalization (2026-07-20):** Phase 11.6 deltas now
  rest on explicit definitions — post set S′ = S ∪ {draft} (|S′| = |S|+1),
  μ′_S recomputed from scratch via the Phase 11 robust estimator (never
  incremental), all existing pages re-scored against μ′_S, draft included in
  the F′ mean; acceptance-test invariants I1–I5 added and wired into Slice 2.
- **Centroid-contract resolution (2026-07-20):** Phase 11.6 guardrails
  replaced "robust/shrunk centroids" with the single Phase 11 rule — below
  < 3 embedded pages the simulator returns `insufficient_data` with null
  deltas (no shrunk/partial estimates; shrinkage estimator deferred); topic
  centroid requires ≥ 5 winner pages; Slice 2 tests extended for both null
  cases. Simulated outputs cannot fabricate centroid/focus values.
- **Acceptance-contract hardening (2026-07-20):** added reproducible graded
  relevance mapping (median-of-N → fixed rel 0–3 cut points for NDCG),
  censor-aware missing-URL labeling (absent = rank 21; ≥4/5 valid repeats per
  snapshot), and preregistered abstention policy (interval-width > 7 or
  update-window abstention; primary operating point NDCG@10 ≥ 0.95 at
  coverage ≥ 0.60; frontier at {1.00, 0.90, 0.75, 0.60}; ≥ 0.50 per-segment
  coverage floor).
- **Page-text staged retrieval shipped (2026-07):** `PAGE_TEXT_RETRIEVAL_PLAN.md`
  slices 1–4 — `classify_page_text_response()`, staged
  `fetch_page_text_for_urls()` (baseline → JavaScript → browser), `50402`
  timeout retry + `switch_pool` recovery, and automatic non-usable
  `page_text` re-fetch on `run --stored-run --live-providers` with similarity /
  TextRazor invalidation for refreshed URLs. No new CLI flag.
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
- **Phase 5.1 updated (2026-07-16):** DataForSEO top-level and task-level
  failures now log warnings, retain raw responses, and let live runs continue;
  failed SERP tasks produce empty SERP rows for the affected keyword. Fatal-task
  classification and preflight remain deferred hardening.
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
  `accept_language=en-US`, baseline JS/rendering off, `store_raw_html=true`); the
  `--javascript-parsing` CLI knob was removed. Later staged retrieval (2026-07)
  escalates rendering on empty / JavaScript-disabled outcomes without changing
  that baseline contract or restoring a CLI toggle.
- **Phase 4.76 Slice 3 shipped:** curated `page_content_fields` now materialize
  one row per decoded `content_parsing/live` field with stable ids and JSON
  path metadata while leaving aggregate `pages.text` unchanged.
- **Phase 4.76 Slice 4 shipped:** normalization now preserves the aggregate
  `pages.text` path and writes raw HTML to a sibling `page_html` table keyed by
  `page_id` / `response_id`.
- **Phase 4.76 Slice 5 shipped:** unit tests and stored-run re-normalize smoke
  now cover multi-field content parsing fixtures, HTML retention, aggregate text
  parity, and structured-only round-trip payloads.
- **Vision phases planned (2026-07-19):** Phases 10–13 added — embedding store
  (keystone: curated `embeddings` mart from Gemini raw payloads + BGE-m3
  dual-encoder live path), site/topic layer (robust domain centroids, page
  radius, site focus, topic fit as registered signal families), passage MaxSim,
  temporal panel (cross-run joins, lead-lag, difference-in-differences with a
  treatment log), and the predictive/universe layer (out-of-time NDCG@10
  bake-off across four candidate models, centroid-feature ablation, calibrated
  model selection, intervention simulation with prospective prediction
  logging).
