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

**Outputs:** `runs/{run_id}/stats/stats_summary.json` (includes `limitations`
object), `stats_diagnostics.json`, `stats_report.md`. Link from existing
`report.md` to `stats/stats_report.md` when stats run. Limitations also belong
in JSON, not Markdown-only.

**CLI:** `seo-rank analyze --run RUN_ID` materializes `analysis_mart`, runs
Phase 5 stats when guardrails allow, writes `stats_*`. Exit **1** on guardrail
hard-fail (optional `--no-fail-on-guardrails` for CI/fixtures). Skip full stats
on explicit `--dry-run` and documented offline fixture modes only.

**Analysis spec versioning:** ship `analysis_spec.v1.yaml` for page-level
three-backend panel. Phase 5.75 adds features → `analysis_spec.v2.yaml`; do not
reinterpret v1 runs with v2 spec.

**Not in v1:** per-keyword OLS as primary inference, IV / `PanelOLS`, URL fixed
effects, rank-decile segments, keyword-heterogeneity deep-dives (Phase 5.1),
confirmatory keyword holdout (Phase 5.1).

#### Dev slices

**Progress:** 5 of 14 shipped, 9 open.

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

### Phase 5.1 — Exploratory extensions (deferred)

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
  `analyze`, and `replay`; `run --stored-run` re-materializes marts from a stored
  run tree without provider calls.
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
