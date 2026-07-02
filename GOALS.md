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

Prior shipped work (Phase 4.77 adapter schema validation, Phase 4.76 structured
`content_parsing/live` capture, the run-scoped Parquet lake, page-level
similarity) is documented in `ROADMAP.md` § History.
Completed: Phase 4.77 is recorded there as shipped work.

### Phase 5 objective

Measure observational association between normalized similarity scores and SERP
rank on the page-level panel (`target_keyword × SERP URL`, top 20 per keyword).
**Primary inference:** keyword-level Spearman ρ per backend with Benjamini–Hochberg
within each backend family when K ≥ 10 keywords. **Secondary inference:** pooled
OLS with keyword fixed effects, length adjustment, and keyword-clustered robust
standard errors. **Pre-registered primary backend:** BGE; Gemini backends are
secondary comparisons in fixed order.

#### Progress

**Slices:** 6 of 14 shipped, 8 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Estimand & analysis spec | Stats | Shipped | `analysis_spec.v1.yaml` |
| 2 | Stats module & dependencies | Stats | Shipped | `src/seo_rank/stats/` + `statsmodels` |
| 3 | Guardrails & panel prep | Stats | Shipped | Hard-fail / warn gates on `analysis_mart` |
| 4 | Spearman primary path | Stats | Shipped | Per-keyword ρ + BH per backend |
| 5 | Pooled regression (secondary) | Stats | Shipped | Keyword FE + clustered SEs |
| 6 | Pooled OLS diagnostics | Stats | Shipped | RESET, BP, Cook's D, influence flags |
| 7 | Multivariate sensitivity | Stats | Open | Joint model + VIF drop order |
| 8 | Robustness appendix (influence) | Stats | Open | Refit excluding influential rows |
| 9 | Stats artifacts & CLI | Stats | Open | `stats_summary.json`, `analyze` wiring |
| 10 | Golden fixtures & tests | Stats | Open | Synthetic mart + schema contracts |
| 11 | Within-keyword rank transform | Data | Open | `data/ranks.py` rank + pct + z |
| 12 | Analysis mart v2 columns | Data | Open | `analysis_mart.v2` + validation |
| 13 | Relative similarity sensitivity | Stats | Open | Robustness appendix on rank/pct/z |
| 14 | Relative ranks in CLI & fixtures | CLI | Open | Keyword report + golden invariants |

**Remaining to close Phase 5:** slices 7–14 (see `ROADMAP.md`).

#### Dev slices

**Progress:** 6 of 14 shipped, 8 open.

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
     drop rows with null `bge_normalized_score` for primary path (per-backend
     null checks for secondary backends).
   - Evaluate guardrail table; emit `guardrails: {name, status, value, threshold}`
     in `stats_summary.json`.
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
   - Report % influential rows; warn when > 5% (guardrail table).

9. **[ ] Slice 9 — Stats artifacts & CLI**
   - `stats_summary.json`: estimand version, guardrails, per-backend ρ, BH
     q-values, pooled coefficients + clustered CIs, effect-size translation,
     `actionable_association`, **`limitations` object** (observational, top-20
     truncation, no causal claims, measurement-error conservatism).
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
- **Limitations in JSON** — observational, top-20 truncation, measurement-error
  conservatism, no causal claims in `stats_summary.json` and `stats_report.md`.
- **Tests** — golden `analysis_mart`, schema contracts, guardrail skip path,
  BH boundaries, influence refit per `TESTING.md`.
- **Relative similarity (slices 11–14)** — within-keyword rank, percentile, and
  z-score per backend in `analysis_mart.v2`; robustness-only stats path; CLI
  surfaces ranks alongside absolute scores. Primary confirmatory estimand stays
  on absolute `*_normalized_score`.

## In Scope (current and near-term)

- `analysis_spec.v1.yaml` and runtime spec loader.
- `src/seo_rank/stats/` package (`spec`, `panel`, `spearman`, `regression`,
  `diagnostics`, `bh`, `artifacts`).
- `statsmodels` dependency in `pyproject.toml` (plus existing `scipy` / `numpy`).
- Guardrail evaluation on `runs/{run_id}/parquet/analysis_mart/`.
- Spearman + BH, pooled OLS, diagnostics, multivariate sensitivity, influence
  robustness appendix.
- `stats_summary.json`, `stats_diagnostics.json`, `stats_report.md` under
  `runs/{run_id}/stats/`.
- `seo-rank analyze --run RUN_ID` materialization and exit-code contract.
- Unit tests and golden fixtures in `tests/unit/`.
- Within-keyword relative similarity: `*_similarity_rank`, `*_similarity_pct`,
  `*_similarity_z` in `analysis_mart.v2` (`src/seo_rank/data/ranks.py`).
- Stats robustness appendix for relative predictors (Slice 13).

## Out Of Scope

- Passage-level similarity scoring (Phase 5.5).
- Domain-level URL inventory scoring (Phase 5.5).
- Phase 5.75 BGE hybrid / retrieve-then-rerank pipeline (separate spec v2).
- Phase 5.1 exploratory extensions (rank-decile segments, keyword holdout).
- Expanded report sections beyond stats artifacts (Phase 6).
- Entity-derived ranking features.
- Direct page fetching outside DataForSEO.
- Causal claims about ranking factors.
- IV / `PanelOLS`, URL fixed effects, per-keyword OLS as primary inference.
- CI, deployment, production hosting.
- Parquet `Variant` type for semi-structured provider payloads.

## Phase 5 acceptance criteria

**Status:** 5 of 14 slices shipped, 9 open.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `analysis_spec.v1.yaml` loaded; estimand version in outputs | 1, 2 | Shipped |
| Guardrail hard-fail skips inference; warn surfaces in JSON | 3, 9 | Open |
| Spearman + BH per backend when K ≥ 10 | 4 | Open |
| Pooled regression with keyword-clustered SEs only in primary output | 5 | Shipped |
| Effect-size translation + `actionable_association` rule | 5, 9 | Open |
| Pooled diagnostics + influence % in diagnostics JSON | 6, 8 | Open |
| Multivariate sensitivity with VIF drop order | 7 | Open |
| Limitations in JSON and Markdown | 9 | Open |
| `seo-rank analyze` exit code + dry-run skip | 9 | Open |
| Golden fixture ρ/slope within tolerance | 10 | Open |
| Within-keyword rank/pct/z columns in `analysis_mart.v2` | 11, 12 | Open |
| Relative similarity robustness in `stats_diagnostics.json` | 13 | Open |
| CLI keyword report surfaces relative ranks | 14 | Open |

---

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
