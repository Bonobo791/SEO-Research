<!-- Part of the split roadmap. Index: ROADMAP.md -->

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
