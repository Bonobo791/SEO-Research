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

**Mart columns (relative, v2 — slices 11–12):** per backend, `*_similarity_rank`,
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
| Influential rows (Cook's D > 4/n on pooled BGE model) | report %; warn if > 5% | warn (deferred — counts in `stats_diagnostics.json` today; guardrail evaluation in Slice 8) |

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
confirmatory keyword holdout (Phase 5.4), passage-level Plackett-Luce analysis.

#### Dev slices

**Progress:** 11 of 31 shipped, 20 open.

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
   - **Remaining (live run):** `FIXUPS.md` **S5-11** — `page_text` schema
     rejects `tasks[].result: null` from DataForSEO; blocks
     `--live-providers` E2E sign-off.

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

9. **[ ] Slice 9 — Stats artifacts & CLI**
   - `stats_summary.json`: estimand version, guardrails, per-backend ρ, BH
     q-values, pooled coefficients + clustered CIs, effect-size translation,
     `actionable_association`, **`limitations` per rank depth** (observational,
     depth-specific truncation, no causal claims, measurement-error
     conservatism), nested under `rank_depths` with top-20 compat shim.
   - `stats_diagnostics.json`: diagnostic flags, influence counts, multivariate
     VIF, influence_sensitivity, optional two-way-cluster CIs.
   - `stats_report.md`: human summary mirroring JSON limitations.
   - Wire `seo-rank analyze`; link from `report.md`; exit 1 on hard-fail;
     `--no-fail-on-guardrails`; respect dry-run / fixture skip contract.

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

15. **[ ] Slice 15 — Plackett-Luce estimand runtime wiring**
    - Load `analysis_spec.estimand.plackett_luce` at runtime and thread the
      top-20 limit, IIA cutoffs, and convergence thresholds from the spec
      instead of hardcoding them in `plackett_luce.py`.
    - Keep page-level PL behavior aligned with the committed estimand block so
      future spec edits do not silently diverge from code.
    - Tests: spec-driven threshold loader and regression coverage for the
      runtime-plumbed estimator settings.

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

21. **[ ] Slice 21 — TextRazor-only flags and gates**
    - Add `--live-textrazor-only`, `--refresh-textrazor` to `seo-rank run`.
    - Validation: mutual exclusion with `--live-providers` and `--skip-textrazor`;
      requires `SEO_RANK_ENABLE_TEXTRAZOR=1` + `TEXTRAZOR_API_KEY` only.
    - `prepare_textrazor_only_context(env)` — no DataForSEO credential check.
    - Persist flags in `run.json` `config`.
    - Tests: flag combos, env gate, rejection messages.

22. **[ ] Slice 22 — TextRazor ingest core**
    - `TEXTRAZOR_ENDPOINTS` registry in `textrazor.py` (`entities` ships first).
    - `fetch_textrazor_entities_for_pages()`, `pages_missing_textrazor()`.
    - Unit tests with injected transport.

23. **[ ] Slice 23 — Raw lake merge for entities**
    - `merge_raw_response_records()` + `rewrite_endpoint_partition()`.
    - Dedupe `(target_keyword, url)` on `endpoint=entities`; refresh replaces
      latest-wins (align with Phase 5.1 stale-SERP retention).
    - Other endpoint partitions unchanged.

24. **[ ] Slice 24 — Stored-run TextRazor backfill**
    - `load_pages_for_textrazor()` from `raw_responses` `page_text` (authoritative).
    - `backfill_textrazor_run()` — no `build_live_keyword_result` / no DFS HTTP.
    - Update `run.json` entity summaries; `materialize_run_tree` refresh.

25. **[ ] Slice 25 — Brand-new TextRazor-only run**
    - `write_textrazor_only_artifacts()`: fixture expansion/SERP/page_text,
      live TextRazor, fixture similarity scoring.
    - Zero `dataforseo.*` in `network_calls`.

26. **[ ] Slice 26 — TextRazor-only tests and docs**
    - CLI tests: new run, stored backfill, `--live-providers --live-textrazor`
      regression.
    - `README.md`, `TESTING.md`, `ARCHITECTURE.md` schema contract.
    - Optional TextRazor connectivity probe in `test_provider_connectivity.py`.

**Example usage (after ship):**

```bash
# Brand-new: fixture structure + live TextRazor
seo-rank run --seed "technical seo" --live-textrazor-only --output-dir runs/demo

# Backfill entities on an existing run
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only

# Force re-fetch
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only --refresh-textrazor
```

#### TextRazor signal expansion (stats plane — depends on slices 21–26)

27. **[ ] Slice 27 — TextRazor signal registry and family contract**
    - Define a signal-family registry at the same `target_keyword × SERP URL`
      grain as `analysis_mart`.
    - Cover similarity backends plus TextRazor scalar families: entity
      confidence/relevance, topic score, category/classifier score, and
      entailment score/prior/context.
    - Cover TextRazor structural families with derived numeric summaries for
      word/grammar/sense/spelling and relation/property/noun-phrase counts or
      densities.
    - Keep the existing similarity rules intact; TextRazor families are
      additive, not a replacement.

28. **[ ] Slice 28 — Materialize TextRazor page metrics**
    - Extend TextRazor normalization so the raw response can emit the required
      extractors beyond entities.
    - Add a separate TextRazor page-metrics mart at the same page grain as
      `analysis_mart`, with one row per `target_keyword × SERP URL`.
    - Derive stable page-level numeric summaries from the curated TextRazor
      tables so downstream stats can consume them without widening the current
      similarity mart.

29. **[ ] Slice 29 — Generalize the Phase 5 stats engine**
    - Replace hard-coded backend lists in the stats modules with a
      signal-family registry.
    - Run the same Spearman/BH, pooled OLS, diagnostics, optional
      Plackett-Luce, and rank-depth bundles per signal family.
    - Keep Benjamini–Hochberg family boundaries per signal family rather than
      globally across all signals.

30. **[ ] Slice 30 — Fold families into CLI output and artifacts**
    - Extend `stats_summary.json`, `stats_diagnostics.json`, and
      `stats_report.md` so they show similarity and TextRazor families in one
      combined Phase 5 report tree.
    - Preserve the current hard-fail path: skip confirmatory inference but
      still write the minimal summary and report artifacts.
    - Update `seo-rank analyze` and keyword inspection output so the TextRazor
      features appear alongside the existing similarity output.

31. **[ ] Slice 31 — Golden fixtures and tests**
    - Add synthetic fixtures that include both similarity rows and TextRazor
      rows with known rank relationships.
    - Add tests for family registry loading, TextRazor page-metric aggregation,
      BH gating at `K >= 10`, pooled regression and diagnostics on the new
      families, artifact serialization, and CLI output.
    - Keep one end-to-end fixture that proves the same Phase 5 stack works on a
      similarity family and the new TextRazor families without changing the
      current similarity results.

#### Phase 5 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `analysis_spec.v1.yaml` loaded; estimand version in outputs | 1, 2 | Shipped |
| Guardrail hard-fail skips inference; warn surfaces in JSON | 3, 9 | Open |
| Spearman + BH per backend when K ≥ 10 | 4 | Shipped |
| Pooled regression with keyword-clustered SEs only in primary output | 5 | Shipped |
| Effect-size translation + actionable_association rule | 5, 9 | Open |
| Pooled diagnostics + influence % in diagnostics JSON | 6, 8 | Open |
| Multivariate sensitivity with VIF drop order | 7 | Open |
| Limitations in JSON and Markdown | 9 | Open |
| `seo-rank analyze` exit code + dry-run skip | 9 | Open |
| Golden fixture ρ/slope within tolerance | 10 | Open |
| Within-keyword rank/pct/z columns in `analysis_mart.v2` | 11, 12 | Open |
| Relative similarity robustness in `stats_diagnostics.json` | 13 | Open |
| CLI keyword report surfaces relative ranks | 14 | Open |
| Parallel confirmatory rank depths (20/10/5/3) | 16–20 | Shipped |
| `actionable_association_by_rank_depth` in summary JSON | 19 | Shipped |
| `rank_depths` nested JSON + four `## Rank depth:` report sections | 19 | Shipped |
| `--live-textrazor-only` without DataForSEO network | 21, 25 | Open |
| Stored-run entity backfill merges `endpoint=entities` only | 23, 24 | Open |
| `parquet/entities/` after textrazor-only ingest + normalize | 24–26 | Open |
| TextRazor signal registry and page-metrics mart | 27, 28 | Open |
| Family-aware stats registry and combined artifacts | 29, 30 | Open |
| Similarity + TextRazor golden fixtures and CLI tests | 31 | Open |

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
- Random 20% keyword holdout for confirmatory pass.
- LOWESS / CCPR diagnostic plots as optional artifacts.

### Phase 5.5 - Analysis Expansion

- Per keyword: top-20 SERP; passage and domain URL scoring vs target
  keyword; domain URL cap 1000; skip domains over 1000 URLs

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

### Phase 6.1 — Reporting

- Expanded `report.md` sections for observational limits and top-20 censoring
- Generated `runs/{run_id}/` trees out of source control (layout ships in Phase 4.5)

## Deferred

- Entity-derived ranking features
- Direct page crawling outside DataForSEO
- CI, release packaging, coverage thresholds
- Production deployment, databases, cache
- Parquet `Variant` type for provider payloads

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
- **Phase 5 Slices 16–20 shipped (2026-07-02):** parallel confirmatory rank-depth
  bundles at `top_20`, `top_10`, `top_5`, and `top_3` — `rank_depths` and
  `limitations_by_depth` in `analysis_spec.v1.yaml`, `rank_depth.py` panel
  filtering, per-depth Spearman/OLS/Plackett-Luce/diagnostics, nested
  `rank_depths` in `stats_summary.json` / `stats_diagnostics.json`, four
  `## Rank depth:` sections in `stats_report.md`,
  `actionable_association_by_rank_depth`, leave-one-out IIA on `top_20` only;
  covered by `tests/unit/test_stats_rank_depth.py`.
- **Phase 5.1 planned (2026-07-02):** live provider fail-fast on fatal DataForSEO
  task errors (`40207` IP whitelist, auth failures) — shared classifier, abort on
  all live endpoints, optional preflight, CLI flag override on stored-run replay,
  safer stale-SERP retention. Motivated by Columbus run continuing through 23
  denied SERPs before `raise_for_failed_dataforseo_tasks()` shipped.
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
