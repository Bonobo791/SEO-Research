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

**Slices:** 0 of 10 shipped, 10 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Estimand & analysis spec | Stats | Open | `analysis_spec.v1.yaml` |
| 2 | Stats module & dependencies | Stats | Open | `src/seo_rank/stats/` + `statsmodels` |
| 3 | Guardrails & panel prep | Stats | Open | Hard-fail / warn gates on `analysis_mart` |
| 4 | Spearman primary path | Stats | Open | Per-keyword ρ + BH per backend |
| 5 | Pooled regression (secondary) | Stats | Open | Keyword FE + clustered SEs |
| 6 | Pooled OLS diagnostics | Stats | Open | RESET, BP, Cook's D, influence flags |
| 7 | Multivariate sensitivity | Stats | Open | Joint model + VIF drop order |
| 8 | Robustness appendix (influence) | Stats | Open | Refit excluding influential rows |
| 9 | Stats artifacts & CLI | Stats | Open | `stats_summary.json`, `analyze` wiring |
| 10 | Golden fixtures & tests | Stats | Open | Synthetic mart + schema contracts |

**Remaining to close Phase 5:** slices 1–10 (see `ROADMAP.md`).

#### Dev slices

**Progress:** 0 of 10 shipped, 10 open.

1. **[ ] Slice 1 — Estimand & analysis spec**
   - Add `analysis_spec.v1.yaml`: outcome (`-log(serp_rank)`), predictors,
     keyword FE, length adjustment, clustering rule, BH family, success
     thresholds, backend drop order for multivariate sensitivity.
   - Lock primary decision (A + B), BGE-first order, warn vs hard-fail table,
     BH-when-K ≥ 10, actionable-association rule, spec versioning vs 5.75.
   - Cross-link `ARCHITECTURE.md`, `ROADMAP.md`, `PHASE5-STATS-PLAN-REVIEW.md`.

2. **[ ] Slice 2 — Stats module & dependencies**
   - Add `src/seo_rank/stats/` (`spec.py`, `panel.py`, `spearman.py`,
     `regression.py`, `diagnostics.py`, `bh.py`, `artifacts.py`).
   - Declare `statsmodels` (+ existing `scipy`/`numpy`) in `pyproject.toml`.
   - Load `analysis_spec.v1.yaml` at runtime; expose estimand version in outputs.

3. **[ ] Slice 3 — Guardrails & panel prep**
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

4. **[ ] Slice 4 — Spearman primary path**
   - Per `target_keyword_id`, two-sided Spearman ρ(normalized similarity,
     `serp_rank`) for each backend.
   - Summarize ρ across keywords (median, IQR, fraction same-sign).
   - BH at q = 0.05 within each backend family when K ≥ 10; else raw p-values +
     `bh_skipped_reason: underpowered`.
   - Do not BH-adjust diagnostics or regression coefficients.

5. **[ ] Slice 5 — Pooled regression (secondary)**
   - Baseline: `-log(serp_rank) ~ log(page_text_length + 1) + C(target_keyword_id)`.
   - Feature: + one `*_normalized_score` at a time (univariate + keyword FE +
     length); separate model per backend.
   - Keyword-clustered robust SEs; never emit naive IID SEs in primary output.
   - **Effect size:** translate coefficient to approximate Δ rank per 1 SD
     similarity (document formula in spec).
   - Descriptive Δ adjusted R² or AIC vs baseline (not BH-adjusted).
   - **Sensitivity (robustness appendix):** refit with two-way cluster
     (keyword × `canonical_url_hash`) when URL repeats exist.

6. **[ ] Slice 6 — Pooled OLS diagnostics**
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

**Status:** 0 of 10 slices shipped, 10 open.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `analysis_spec.v1.yaml` loaded; estimand version in outputs | 1, 2 | Open |
| Guardrail hard-fail skips inference; warn surfaces in JSON | 3, 9 | Open |
| Spearman + BH per backend when K ≥ 10 | 4 | Open |
| Pooled regression with keyword-clustered SEs only in primary output | 5 | Open |
| Effect-size translation + `actionable_association` rule | 5, 9 | Open |
| Pooled diagnostics + influence % in diagnostics JSON | 6, 8 | Open |
| Multivariate sensitivity with VIF drop order | 7 | Open |
| Limitations in JSON and Markdown | 9 | Open |
| `seo-rank analyze` exit code + dry-run skip | 9 | Open |
| Golden fixture ρ/slope within tolerance | 10 | Open |

---

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
