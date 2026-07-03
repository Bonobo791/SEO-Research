# Phase 5 Statistical Analysis — Plan Review

Review of the planned per-run observational ranking analysis described in
`ARCHITECTURE.md` (Planned Per-Run Statistical Analysis, OLS Pre-Analysis
Preparation) and `ROADMAP.md` (Phase 5). Written for product and implementation
review before Phase 5 ships.

**Status:** Draft for review  
**Scope:** Observational association between similarity scores and SERP rank on
the `analysis_mart` panel (`target_keyword × SERP URL`, top 20 per keyword).

---

## Executive summary

The current plan is **strong on regression diagnostics** (linearity, VIF,
heteroskedasticity, influence, cautious exogeneity language) and **honest about
observational limits**. It is **weak on the decision the analysis supports**,
the **default estimand and model**, **dependence across rows**, **multiplicity
(BH) family definition**, and **effect-size reporting**.

Recommendation: add a short pre-registered **estimand + default model spec**
before expanding the diagnostic workflow. Keep the diagnostic loop, but run it
primarily on a **pooled** specification with keyword structure handled explicitly,
not on twenty-row per-keyword OLS fits.

---

## What decision should Phase 5 inform?

Every run's stats should answer one primary question. Pick one (or rank them) and
make the rest secondary or sensitivity-only.

| Decision | Example action if positive | Implied analysis |
| -------- | -------------------------- | ---------------- |
| **A. Association exists** | Continue investing in similarity stack | Pooled within-keyword association; report effect size + CI |
| **B. Backend comparison** | Prefer one scorer in product/docs | Pre-specified primary backend; pairwise or separate univariate models |
| **C. Keyword heterogeneity** | Deep-dive high-signal keywords | Per-keyword slopes with explicit multiplicity family |
| **D. Run quality gate** | Flag run as "low signal" for human review | Guardrail metrics only; no BH on a single run |

**Proposed primary (v1):** **A + B** — pooled within-keyword association per
similarity backend, with **BGE as primary backend** and Gemini backends as
secondary comparisons (order fixed in spec, not data-driven).

**Guardrails (fail or warn, do not interpret coefficients):**

- Minimum number of keywords with complete similarity scores (suggest ≥ 10).
- Minimum fraction of SERP rows with non-null scores per backend (suggest ≥ 90%).
- Minimum variance in `serp_rank` and in each similarity column within keyword.

---

## Current plan — strengths

1. **Diagnostic-first OLS workflow** — detect problems before interpreting
   coefficients or applying Benjamini–Hochberg (BH).
2. **"Fix only when flagged"** — avoids automatic data deletion and blind
   transformation fishing (in intent).
3. **Exogeneity section** — correctly refuses to claim causality from residual
   plots; points to DAG / timing / domain review.
4. **Observational framing** — top-20 truncation acknowledged in Decisions.
5. **Single stats stack** — `statsmodels` (+ optional `linearmodels`) avoids
   parallel implementations.
6. **Fair feature surface** — three backends land in `analysis_mart` for
   comparable downstream work.

---

## Gaps and missing pieces

### 1. Outcome variable

`serp_rank` is **ordinal, bounded (1–20), discrete**. OLS on raw rank is a
convenience, not a defensible default.

**Choose one primary outcome transform and document it:**

| Transform | Pros | Cons |
| --------- | ---- | ---- |
| `-log(serp_rank)` | Monotonic, dampens top-heavy curvature | Still not truly continuous |
| `21 - serp_rank` | "Higher is better" for intuition | Same |
| Within-keyword z-score of rank | Removes keyword difficulty | Loses cross-keyword scale |
| Spearman ρ per keyword | Robust, rank-native | Not a regression coefficient; pool via meta |
| Ordered logit / count GLM | Matches outcome type | Heavier; harder to automate every run |

**Recommendation:** primary = **within-keyword Spearman ρ** between normalized
similarity and `serp_rank` per backend; secondary = pooled regression on
`-log(serp_rank)` with keyword fixed effects.

### 2. Dependence / clustering

Rows nest under `target_keyword_id` (~20 URLs each). The same URL can appear
under multiple keywords. **IID OLS standard errors are invalid.**

**Missing today:**

- Cluster-robust SEs (cluster = `target_keyword_id` at minimum).
- Explicit rule: never report naive OLS SEs on the full panel without clustering.
- Optional two-way clustering (keyword × URL) as sensitivity.

**Recommendation:** default inference = **keyword-clustered robust SEs** on pooled
models; per-keyword OLS only for exploratory plots, not primary inference.

### 3. Top-20 selection bias

Only URLs Google already placed in the top 20 are observed. This is **incidental
truncation**, not just "censoring" in the survival sense.

**Missing today:**

- Language in every stats output: *associations within observed top 20 only*.
- Sensitivity note that similarity for rank 20 ≠ similarity for unranked URLs.
- Phase 6 defers observational-limit narrative — stats may ship before users see
  this context.

**Recommendation:** embed a **limitations block** in Phase 5 JSON/Markdown output
now (stub is fine); expand in Phase 6. **Shipped (slices 16–20):** limitations
are depth-specific (`top_20_truncation`, `top_10_truncation`, etc.) under
`stats_summary.json` → `rank_depths.*.limitations`, with four matching
`## Rank depth:` sections in `stats_report.md`.

### 4. Benjamini–Hochberg family

"Keyword- and feature-level comparisons" does not define the **hypothesis
family**. BH is only meaningful if the family is fixed before looking.

**Must specify:**

- What counts as one hypothesis (slope test? correlation test? ΔR²?).
- Whether family is global per run, per backend, or per keyword.
- Whether exploratory diagnostics create new hypotheses post hoc.

**Recommendation (v1):**

- **Family per backend:** all keyword-level Spearman tests for that backend
  (K = number of keywords).
- Apply BH at q = 0.05 **within each backend family**.
- Do **not** BH-adjust diagnostic p-values (RESET, Breusch–Pagan, etc.).

### 5. Baseline and adjustment set

ROADMAP mentions "baseline vs similarity-feature models" but ARCHITECTURE does not
define the baseline.

`analysis_mart` already includes `page_text_length`. Length correlates with both
content quality signals and rank. Ignoring it **confounds similarity coefficients**.

**Recommendation — default adjustment set:**

- `page_text_length` (or `log(page_text_length + 1)`).
- **Keyword fixed effects** in pooled regression (absorbs keyword difficulty).
- Do **not** include URL fixed effects in v1 (collapses variation within keyword).

**Baseline model:** keyword FE only (no similarity).  
**Feature model:** keyword FE + one similarity backend at a time (primary path).

### 6. Three correlated predictors

`bge_normalized_score`, `gemini_doc_retrieval_normalized_score`, and
`gemini_semantic_similarity_normalized_score` will be highly correlated.

**Pre-specify:**

1. **Primary:** separate model per backend (univariate + keyword FE + length).
2. **Sensitivity:** one multivariate model; if VIF > 5, drop lowest-priority
   backend per pre-registered order (e.g. semantic similarity first).

Do not treat joint OLS coefficients as primary evidence without this hierarchy.

### 7. Primary metrics and effect sizes

Diagnostics and FDR are specified; **decision metrics** are not.

| Role | Proposed metric |
| ---- | ---------------- |
| Primary | Keyword-level Spearman ρ between normalized similarity and rank; report median ρ and IQR across keywords |
| Effect size (regression path) | Coefficient on similarity with 95% CI (clustered SE); translate to approximate rank change per 1 SD similarity |
| Guardrails | n_keywords, % missing scores, % influential rows (Cook's D), diagnostic pass/fail flags |
| Segments (exploratory) | Rank decile (1–3 vs 4–10 vs 11–20), keyword order, score backend |

**Success threshold example (tune before ship):** report "actionable association"
only if median |ρ| ≥ 0.25 **and** ≥ 60% of keywords have same-sign ρ **and**
primary pooled regression CI excludes 0.

### 8. Researcher degrees of freedom

The diagnostic loop allows polynomials, logs, predictor drops, WLS, GLM, RLM on
the **same run** used for BH. That inflates false discoveries.

**Mitigations:**

- **Pre-register** `analysis_spec.v1.yaml` (outcome, predictors, FE, clustering,
  BH family).
- Treat diagnostic-driven spec changes as **robustness appendix**, not the
  confirmatory estimand.
- Optional: hold out a random 20% of keywords for confirmatory pass (Phase 5.1).

### 9. Measurement error

Similarity scores are noisy model outputs → coefficients biased toward zero
(attenuation). Plan should state coefficients are **likely conservative** and
prefer CIs over p-values alone.

### 10. Testing and artifacts

`TESTING.md` lists future OLS + BH tests but not:

- Golden fixture: synthetic `analysis_mart` with known slope/ρ.
- Deterministic stats JSON schema for `seo-rank analyze`.
- Minimum gates that skip or downgrade stats when guardrails fail.

### 11. Relative similarity predictors (Phase 6.1 — `ROADMAP.md`)

Absolute `*_normalized_score` values answer "how similar is this page to the
keyword?" Relative columns answer "how similar is this page **compared to the
other top-20 SERP pages for this keyword**?"

**Shipped scaling baseline (Jul 2026):** pooled OLS and page-level Plackett-Luce
both report per-1-SD effects using `within_keyword_sd_rms()` in
`src/seo_rank/stats/scale.py` (RMS of per-keyword SDs). Models still fit on raw
scores; remaining polish and mart v2 work is Phase 6.1.

**Planned mart columns (`analysis_mart.v2`):** per backend,
`*_similarity_rank` (1 = highest), `*_similarity_pct` (`(rank - 1) / (n - 1)`),
`*_similarity_z` (within-keyword z-score). BGE ranks on `bge_raw_score`; Gemini
on `*_normalized_score`. Derived at mart build time; absolute columns unchanged.

**Primary estimand unchanged:** Spearman ρ and pooled OLS on absolute
`*_normalized_score` remain confirmatory.

**Robustness appendix (Phase 6.1 Slice 5):**

1. Spearman ρ on `*_similarity_rank` — sanity check (should align with absolute
   path up to ties).
2. Pooled OLS refits with `*_similarity_z` and `*_similarity_pct` per backend
   (keyword FE + length + clustered SEs).

**Limitation:** relative ranks are within the observed top-20 only, not vs the
full index. Not used for actionable flag or BH.

### 12. Rank-depth confirmatory paths (Phase 5 slices 16–20, shipped)

The confirmatory estimand now runs at four SERP depth caps: ranks 1–20, 1–10,
1–5, and 1–3. Each depth is an independent bundle with its own guardrails,
Spearman, pooled OLS, page-level Plackett-Luce, pooled diagnostics,
limitations, and `actionable_association`. `primary_rank_depth` stays
`top_20`; top-level `stats_summary.json` fields mirror `rank_depths.top_20`
for backward compatibility. `actionable_association_by_rank_depth` exposes the
BGE rule outcome per depth.

**Spec:** `analysis_spec.v1.yaml` → `rank_depths` (confirmatory order, limits,
primary) and `limitations_by_depth`.

**Code:** `src/seo_rank/stats/rank_depth.py` (`filter_panel_by_max_rank`),
`panel.prepare_rank_depth_panel()`, `artifacts.build_rank_depth_bundles()` /
`run_phase5_stats()`.

**IIA:** leave-one-out-top-rank sensitivity runs on `top_20` only; the retired
`top_20_vs_top_10` subset refit is no longer reported.

---

## Drawbacks of the current approach

| Drawback | Impact |
| -------- | ------ |
| Full textbook diagnostics on n ≈ 20 per keyword | Low power; Shapiro/RESET mostly noise at keyword level |
| OLS-first on ordinal rank | Misspecified curvature; patch with polynomials adds DF |
| BH on every single run | Encourages p-hunting in low-N client runs |
| Phase 5 before Phase 5.75 (BM25 / bi-encoder) | Early backend conclusions may not survive new features |
| Optional IV / PanelOLS paths | Implies causal tooling without clear triggers; misuse risk |

---

## Risks

| Risk | Severity | Notes |
| ---- | -------- | ----- |
| False confidence | **High** | Significant q-values read as "ranking factors" despite GOALS forbidding causal claims |
| Invalid BH | **High** | Undefined family → "FDR-controlled" label may be wrong |
| Overfitting via diagnostic loop | **Medium** | Same data selects and tests model |
| Collinearity instability | **Medium** | Joint three-backend model: sign flips |
| Confounding by page length | **Medium** | Length in mart but not in default spec today |
| Underpowered per-keyword fits | **Medium** | Wide CIs; cherry-pick keywords that "work" |
| Stats without limitations text | **Medium** | Phase 6 defers narrative users need in Phase 5 |
| Bad runs still get full stats | **Low–Med** | No quality gate before fit |

---

## Proposed default analysis spec (v1 draft)

For implementation review. Adjust thresholds after golden fixtures.

### Data

- Source: `runs/{run_id}/parquet/analysis_mart/part-*.parquet`
- Grain: one row per `target_keyword_id × canonical_url_hash`
- Filter: `serp_rank` between 1 and 20; drop rows with null primary backend score

### Primary path (per backend)

1. For each `target_keyword_id`, compute Spearman ρ(normalized similarity,
   `serp_rank`).
2. Summarize distribution of ρ across keywords (median, IQR, fraction positive).
3. Apply BH across keywords **within backend** on two-sided correlation tests.
4. Pooled regression (secondary):  
   `-log(serp_rank) ~ normalized_similarity + log(page_text_length + 1) + C(target_keyword_id)`  
   with **cluster-robust SE** at `target_keyword_id`.

### Baseline

- Pooled: `-log(serp_rank) ~ log(page_text_length + 1) + C(target_keyword_id)`  
  Compare adjusted R² or AIC to feature model (descriptive, not BH-adjusted).

### Diagnostics (pooled model only)

Run ARCHITECTURE diagnostic loop on the **pooled** feature model per backend:

- Linearity: residuals vs fitted + RESET
- Heteroskedasticity: Breusch–Pagan → default to **HC3** SEs if flagged
- Influence: flag Cook's D > 4/n; report sensitivity with flagged rows downweighted or excluded in appendix
- VIF: only in multivariate sensitivity model
- Skip per-keyword normality tests as primary gates

### Outputs (`runs/{run_id}/stats/`)

| Artifact | Contents |
| -------- | -------- |
| `stats_summary.json` | Estimand version, `primary_rank_depth`, nested `rank_depths` (guardrails, limitations, per-backend ρ summary, BH q-values, pooled coefficients + CIs, `actionable_association` per depth), `actionable_association_by_rank_depth`, top-20 compat shim |
| `stats_diagnostics.json` | Nested `rank_depths` with diagnostic flags, influential row counts, VIF (if multivariate), Plackett-Luce optimizer / leave-one-out IIA on `top_20` |
| `stats_report.md` | Human summary + four `## Rank depth:` sections with depth-specific **Limitations** (observational, truncation at that depth, no causal claims) |

### CLI contract

```text
seo-rank analyze --run RUN_ID
  → materialize analysis_mart (existing)
  → run Phase 5 stats if guardrails pass
  → write stats_* under runs/{run_id}/
  → exit non-zero on guardrail hard-fail (optional)
```

---

## Open questions for review

Resolved in `ROADMAP.md` Phase 5 (v1 defaults; tune thresholds after golden
fixtures):

| # | Question | v1 resolution |
| - | -------- | ------------- |
| 1 | Primary decision A vs B | **Both** — A headline, B via separate per-backend models + BGE primary |
| 2 | Primary backend | **BGE** pre-registered; Gemini backends secondary, fixed order |
| 3 | BH strictness | BH **only when K ≥ 10**; raw p-values + `bh_skipped_reason` below |
| 4 | Outcome headline | **Spearman-first**; pooled regression secondary |
| 5 | Phase 5.75 spec | **`analysis_spec.v1.yaml`** frozen for page-level three-backend panel; v2 after 5.75 |
| 6 | IV / PanelOLS | **Deferred** — not in Phase 5 or 5.1 backlog |

---

## Suggested edits to existing docs (after approval)

| Doc | Change | Status |
| --- | ------ | ------ |
| `ARCHITECTURE.md` | Add "Phase 5 estimand" before OLS Pre-Analysis; link to this file | Done |
| `ROADMAP.md` | Phase 5 slices 1–10 + acceptance criteria + Phase 5.1 deferrals | Done |
| `TESTING.md` | Golden `analysis_mart` + expected ρ/slope tolerance | Done |
| `GOALS.md` | When Phase 5 becomes active scope, move stats items from Out Of Scope | Done |
| Phase 5 slices 1–2 | `analysis_spec.v1.yaml` + `src/seo_rank/stats/` scaffold | Done (2026-07-01) |
| Phase 5 slices 16–20 | Rank-depth confirmatory paths (`rank_depths`, nested JSON, report sections) | Done (2026-07-02) |
| Phase 5 slices 27–28 | TextRazor `signal_families` registry + `textrazor_page_metrics` mart at URL grain | Done (2026-07-02) |
| Phase 5 slice 29 | Family-aware Spearman dispatch (`summarize_spearman_families`); OLS/PL/artifacts open | Partial (2026-07-02) |

---

## TextRazor signal families (slices 27–29)

Phase 5 adds TextRazor-derived predictors **without widening** the similarity
`analysis_mart`. Each SERP URL gets one TextRazor page-metrics response during
`seo-rank run`; normalization aggregates scalar and structural summaries into
`textrazor_page_metrics_curated` and the `textrazor_page_metrics` feature mart at
`target_keyword_id × canonical_url_hash` grain.

`analysis_spec.v1.yaml` registers nine signal families: three similarity backends
(BGE, Gemini Doc Retrieval, Gemini Semantic Similarity) plus six TextRazor families
(entity confidence/relevance, topic score, category/classifier, entailment
score/prior/context, word/grammar/sense/spelling counts, relation/property/noun-phrase
counts). `src/seo_rank/stats/families.py` loads the registry; `spec.py` derives
similarity `backend_order` from it.

**Stats status (2026-07-02):** `summarize_spearman_families()` runs keyword-level
Spearman + BH per family with BH boundaries scoped per family (not globally across
all signals). Confirmatory pooled OLS, diagnostics, Plackett-Luce, rank-depth
bundles, and `stats_*` artifact wiring for TextRazor families remain open (slices
29–30). `seo-rank analyze` today still runs similarity-only confirmatory paths on
`analysis_mart`.

---

## References

- `ARCHITECTURE.md` — Planned Per-Run Statistical Analysis, OLS Pre-Analysis
  Preparation, Decisions
- `ROADMAP.md` — Phase 5, Phase 5.75, Phase 6
- `src/seo_rank/data/marts.py` — `analysis_mart` columns and grain
- `GOALS.md` — explicit non-goal: causal claims about ranking factors
