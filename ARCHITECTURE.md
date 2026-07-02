# Architecture

## Stack

- Language: Python
- Runtime: CLI
- Source directory: `src/seo_rank/`
- Test directory: `tests/`
- Package manifest: `pyproject.toml`
- Analysis library: `polars` (lazy Parquet lake, Phase 4.5); `statsmodels` for
  observational ranking models (planned; not yet a runtime dependency); `numpy`,
  `scipy`, `patsy`, and `linearmodels` for OLS diagnostics, IV/panel extensions,
  and supporting tests (planned)
- Similarity backends: deterministic fixture passage aggregation plus
  offline-testable page-level fixtures for **BGE**, **Gemini Doc Retrieval**, and
  **Gemini Semantic Similarity**. **Live Gemini execution is wired** for the CLI
  live path via Gen AI SDK embeddings (`google-genai`, `gemini-embedding-2`).
  **Live BGE execution is wired** for the CLI live path via `FlagEmbedding`
  (local BGE cross-encoder, pinned `BAAI/bge-reranker-v2-m3`) as an optional
  runtime dependency — see [Live similarity backends (Phase 4)](#live-similarity-backends-phase-4).
- Deployment: none
- Databases: none (file-based Parquet lake in Phase 4.5)
- Cache layer: none (`--stored-run` reloads prior runs; not a live API cache)
- CI: none configured

## Overview

SEO-Research is a Python CLI for research-grade SEO ranking similarity analysis.

**Shipped today (Phase 1):** offline `seo-rank run` expands a seed keyword from
fixtures, normalizes SERP rows, passages, page-level similarity features, and
optional TextRazor entities, then writes `run.json` and `report.md` with no
network calls.

**Phase 3 shipped:** DataForSEO and TextRazor provider boundaries include
offline-verifiable request construction, credential validation, and a
non-default CLI live-provider gate. Standard-library HTTP clients and an
env-gated live smoke test are available. Offline and explicitly gated live runs
now loop over every capped cluster keyword, group provider outputs under
`keyword_results`, and annotate flattened normalized rows with
`target_keyword`.

**Phase 4 shipped:** page-level similarity emits **BGE**, **Gemini Doc Retrieval**,
and **Gemini Semantic Similarity** per SERP row in JSON and Markdown artifacts.
Live Gemini embeddings replace the live-path Gemini fixtures when
`--live-gemini` is enabled. Live BGE reranking replaces the live-path BGE
fixture when `--live-bge` is enabled — see
[Live similarity backends (Phase 4)](#live-similarity-backends-phase-4).
Later phases add keyword-level Spearman inference with BH per backend, pooled
OLS with clustered SEs, and OLS pre-analysis diagnostics on pooled models.

TextRazor entities are captured in offline runs for schema validation; entity-derived
model features remain out of scope.

Product architecture, scope, and phased backlog live in root markdown:
`ARCHITECTURE.md` (this file), `GOALS.md`, and `ROADMAP.md`.

## Current Components

- `AGENTS.md`: repo process contract. It requires strict TDD for code-shaped
  changes and all configured tests passing before commit.
- `SDLC-LOOP.md`: operating loop for planning, red/green proof, review, and
  escalation.
- `START-SDLC.md`: session-start prompt for working in SDLC mode.
- `PROVE-IT.md`: pre-commit proof checklist and proof-stamp instructions.
- `.agents/skills/sdlc/SKILL.md`: repo-local SDLC skill entrypoint. Use `$sdlc`
  for implementation work.
- `.codex/config.toml`: repo-local Codex model and hook settings.
- `.codex/hooks.json`: portable hook wiring using Node entrypoints.
- `.codex/hooks/*.cjs`: active hook implementations for session, git, and
  compaction guards.
- `.codex-sdlc/manifest.json`: setup scan results and confirmed preferences.
- `GOALS.md`: active-scope contract and Phase status.
- `ROADMAP.md`: phased backlog and history.

## Application Surface

The repository contains an **offline-verifiable CLI scaffold** (Phase 1 shipped):

- **Package:** `src/seo_rank/` — `cli.py`, `dataforseo.py`, `text.py`,
  `similarity.py`, `gemini_embeddings.py`, `bge_reranker.py`, `textrazor.py`;
  Phase 4.5 adds `src/seo_rank/data/` (`scans`, `normalize`, `features`,
  `marts`, `validate`)
- **CLI:** `seo-rank run` writes `run.json` and `report.md` from fixtures (no
  network calls) or gated live providers; Phase 4.5 adds `normalize`,
  `build-features`, `analyze`, `replay`, and `run --stored-run` (Slice 6 shipped)
- **Tests:** 169 tests under `tests/`; gate: `python -m pytest`; Phase 4.5 Slice 7
  shipped the round-trip regression sweep in `test_sdlc_docs.py`
- **Product docs:** `ARCHITECTURE.md`, `GOALS.md`, `ROADMAP.md`, `README.md`,
  `TESTING.md`
- **Not yet:** multivariate sensitivity, influence robustness, and final CLI
  stats expansion (Phase 5 slices 7–10)

Module and artifact details are in [Application Surface](#application-surface)
and [Key Product Components](#key-product-components) below. Phase 5 slices 1–6
ship the estimand spec, stats package scaffold, guardrails, Spearman/BH primary
path, pooled regression, and pooled diagnostics; confirmatory inference and
CLI wiring continue in slices 7–10.

## Key Product Components

- **CLI (shipped):** `seo-rank run` — seed keyword, location, language, device,
  depth, output directory, model name, JavaScript parsing, `--dry-run`,
  `--skip-textrazor`.
- **Provider fixtures + normalizers (shipped):** DataForSEO-shaped keyword/SERP/
  page-text fixtures; TextRazor entity fixtures (`dataforseo.py`, `textrazor.py`).
- **Provider request boundaries (shipped):** DataForSEO keyword expansion,
  organic SERP, and page-text request specs; TextRazor parsed-text entity
  request specs; credential validation without secret values in errors.
- **Live-provider gate (shipped):** `--live-providers` requires
  `SEO_RANK_ENABLE_LIVE_PROVIDERS=1` in `.env` (loaded automatically) and provider
  credentials before executing the minimal live provider smoke path.
- **Provider HTTP clients (shipped):** standard-library DataForSEO and TextRazor
  request execution with injectable transports for offline tests.
- **Text pipeline (shipped, offline):** passage split (`text.py`); passage
  aggregation and page-level fixture similarity for BGE, Gemini Doc Retrieval,
  and Gemini Semantic Similarity (`similarity.py`).
- **Broader provider integration (planned):** live coverage beyond the smoke
  path.
- **Live similarity (Phase 4 shipped):** **Gemini Doc Retrieval** +
  **Gemini Semantic Similarity** via Gen AI SDK (`gemini-embedding-2`) behind
  `--live-gemini`; local **BGE** (`BAAI/bge-reranker-v2-m3`) behind
  `--live-bge` — see [Live similarity backends (Phase 4)](#live-similarity-backends-phase-4)
  and [Planned Page Similarity Run](#planned-page-similarity-run).
- **Analysis engine (in progress, Phase 5):** slices 1–6 shipped —
  `analysis_spec.v1.yaml`, `src/seo_rank/stats/` scaffold, guardrails/panel
  prep, Spearman + BH, pooled OLS with clustered regression summaries, and
  pooled OLS diagnostics. Multivariate sensitivity, robustness appendices, and
  final CLI stats expansion remain in slices 7–10 — see [Planned Per-Run
  Statistical Analysis](#planned-per-run-statistical-analysis).
- **Reporters (shipped):** JSON + Markdown under the selected run root;
  `seo-rank run` defaults to `runs/{run_id}/` when `--output-dir` is omitted
  and still supports explicit overrides. Phase 6 expands report narrative
  sections.
- **Storage (planned, Phase 4.5):** run-scoped Parquet lake with three processing
  layers — see [Run-scoped Parquet lake](#run-scoped-parquet-lake-phase-45) and
  [Polars data layer](#polars-data-layer-phase-45).

## Data Flow

**Offline run today:** seed keyword → fixture keyword expansion → capped keyword
cluster → per-keyword SERP fixtures → page-text fixtures → passage normalize →
fixture passage aggregation plus page-level **BGE**, **Gemini Doc Retrieval**, and
**Gemini Semantic Similarity** against the target keyword → optional TextRazor
entities → grouped `keyword_results` plus `target_keyword`-annotated aggregate
fields in `run.json` + `report.md`.

**Live run today (Phase 4):** seed keyword → keyword expansion → per-keyword
top-20 SERP → page text → optional TextRazor entities → page similarity (fixture
by default; Gemini live under `--live-gemini`; BGE live under `--live-bge`) →
grouped `keyword_results` in `run.json` + `report.md`.

**Stored run (Phase 4.5):** completed runs persist under `runs/{run_id}/` with
authoritative `raw_responses`, curated tables, feature marts, and `analysis_mart`.
Downstream work scans lazily via `pl.scan_parquet()`; `seo-rank normalize`,
`build-features`, and `analyze` materialize downstream marts in place.
`analyze` backfills missing feature marts before writing `analysis_mart`.
`raw_responses`
  stays out of normal analytical joins (replay/re-normalization only). Live
  DataForSEO payloads are not retained by the provider long-term.

**Planned full pipeline (Phase 5+):** lazy Polars joins on `analysis_mart` →
guardrails → keyword-level Spearman ρ with BH per backend → pooled OLS with
clustered SEs and diagnostics → `runs/{run_id}/stats/` artifacts.

Raw provider responses and generated run trees should stay out of source
control.

## Run-scoped Parquet lake (Phase 4.5)

Phase 4.5 introduces a **run-scoped Parquet lake** with three processing layers.
Each completed run writes a self-contained directory. The run directory scopes all
data; only `raw_responses` adds a second partition dimension (`endpoint`).

### Directory layout

```text
runs/{run_id}/
  run.json                         # manifest, schema versions, counts, checksums
  report.md                        # human-readable summary
  parquet/
    raw_responses/
      endpoint=keyword_expansion/part-*.parquet
      endpoint=serp/part-*.parquet
      endpoint=page_text/part-*.parquet
    keywords/part-*.parquet
    serp_items/part-*.parquet
    pages/part-*.parquet
    page_content_fields/part-*.parquet
    passages/part-*.parquet
    entities/part-*.parquet
    similarity_scores/part-*.parquet
    keyword_serp/part-*.parquet
    page_features/part-*.parquet
    passage_features/part-*.parquet
    domain_features/part-*.parquet
    analysis_mart/part-*.parquet
```

### Three processing layers

| Layer | Tables | Producer | Purpose |
|-------|--------|----------|---------|
| **Curated** | `keywords`, `serp_items`, `pages`, `page_content_fields`, `passages`, `entities`, `similarity_scores` | `normalize.py` | Parse `raw_responses` once into typed tables |
| **Feature marts** | `keyword_serp`, `page_features`, `passage_features`, `domain_features` | `features.py` | Reusable similarity and ranking features |
| **Analysis mart** | `analysis_mart` | `marts.py` | One row per `target_keyword × SERP URL` for Phase 5 |

### Layer 1 — `raw_responses` (authoritative)

One row per DataForSEO HTTP response. This layer is the system of record for
every downloaded payload.

| Column (conceptual) | Role |
|---------------------|------|
| `response_id` | Stable UUID for this HTTP response within the run |
| `endpoint` | Low-cardinality partition key: `keyword_expansion`, `serp`, `page_text` |
| `task_id` | DataForSEO task identifier when present |
| `timestamp` | Response receipt time (UTC) |
| Request metadata | Method, URL, headers/body hash as needed for audit |
| `response_body_bytes` | Exact response body (bytes or UTF-8 JSON bytes) |
| `content_type` | MIME type from the response |
| `status` | HTTP status code |
| `sha256` | SHA-256 of `response_body_bytes` |

**Why authoritative:** DataForSEO does not retain Live endpoint results.
Standard and HTML task results have limited retention. Storing the raw body at
write time makes runs reproducible without provider replay.

**Partitioning:** partition `raw_responses` **only** by `endpoint`. Do not
partition by keyword, URL, task ID, or SERP rank.

**Analytical isolation:** keep `raw_responses` out of normal joins. Use it only
for `seo-rank replay` and explicit re-normalization paths.

### Layer 2 — curated tables (typed, analysis-ready)

Normalized tables derived from `raw_responses` via `normalize.py`. The write path
scans lazily, filters by `endpoint`, and applies batch UDFs for JSON parsing,
passage splitting, entity normalization, and per-keyword similarity scoring;
each table collects once at sink. Every row includes join keys: `run_id`,
`target_keyword_id`, `response_id`, `schema_version`, plus stable entity IDs
(`canonical_url_hash`, `passage_id`, etc.).

| Table | Contents |
|-------|----------|
| `keywords` | Expanded cluster keywords with caps and dedup metadata |
| `serp_items` | Organic SERP rows (top 20), ranks, URLs, titles |
| `pages` | Full parsed page text and page-level metadata (text lives here only) |
| `page_content_fields` | One row per decoded `content_parsing/live` field with path metadata and stable ids |
| `passages` | Passage splits with offsets; no duplicate full page bodies |
| `entities` | TextRazor entity rows when present |
| `similarity_scores` | Page-level `bge`, `gemini_doc_retrieval`, `gemini_semantic_similarity` |

Planned follow-on: raw HTML persistence still needs a dedicated sink path, and
the aggregate page row remains the source for passage splitting.

Curated tables are **not** partitioned beyond the run directory. Sort rows at
write time by primary retrieval keys, e.g. `target_keyword_id`, `canonical_url_hash`,
`serp_rank`, so scans with filters on those columns benefit from row-group
statistics.

### Layer 3 — feature marts

Derived from curated tables via `features.py`. Filter and select **before** joins.

| Mart | Contents |
|------|----------|
| `keyword_serp` | Keyword × SERP grain with ranks and URL keys |
| `page_features` | Page-level similarity and text features |
| `passage_features` | Passage-level features (Phase 5.5 expands scoring scope) |
| `domain_features` | Domain-level aggregates (Phase 5.5 expands URL inventory) |

### Layer 4 — analysis mart

Built by `marts.py` when Phase 5 analysis needs a single panel. One row per
`target_keyword × SERP URL`. Join curated and feature marts only on stable IDs:
`run_id`, `target_keyword_id`, `canonical_url_hash`, `response_id`, `passage_id`.

### Schema policy

- **Do not** model dynamic provider objects as nested Parquet structs. Persist
  `response_body_bytes` and extract typed scalar/list columns at write time.
- **Do not** use the Parquet `Variant` type for semi-structured payloads
  (interoperability risk across readers).
- **Preserve lineage** — every output row carries source IDs and `schema_version`.
- **`run.json` is catalog-only** — table schemas, row counts per table, mapping
  from curated rows to source `response_id`s, and per-file checksums. No
  duplicate raw payloads in JSON.

### Write contract

- Compression: **Zstandard** (`zstd`) via `sink_parquet(..., compression="zstd")`.
- Enable **Parquet statistics** on write (column min/max/null counts for predicate
  pushdown).
- Sort curated and mart tables by primary retrieval keys before sink.
- Write `raw_responses` first, then derive curated tables so `response_id`
  lineage is consistent.
- Run `validate.py` schema/key/null/range checks **before** every mart write;
  row-level audits happen at the sink edge for materialized datasets.

### Read contract

- **LazyFrames end-to-end:** `pl.scan_parquet()` for every dataset; functions
  accept and return `pl.LazyFrame`.
- Apply filters and column projection **before** joins.
- Join only on stable IDs: `run_id`, `target_keyword_id`, `canonical_url_hash`,
  `response_id`, `passage_id`.
- Materialize reusable marts with `sink_parquet`; use
  `collect(engine="streaming")` only at CLI/report boundaries or when a
  DataFrame is actually needed.
- CLI: `seo-rank run --stored-run runs/{run_id}` re-materializes curated tables,
  feature marts, and `analysis_mart` from the stored lake without provider calls.
  `--seed` is still required by argparse but ignored on this path.

### CLI commands (Phase 4.5)

```text
seo-rank normalize --run RUN_ID
seo-rank build-features --run RUN_ID
seo-rank analyze --run RUN_ID --keyword "..."
seo-rank replay --run RUN_ID --response-id ...
```

| Command | Action |
|---------|--------|
| `normalize` | `raw_responses` → curated tables |
| `build-features` | curated → feature marts |
| `analyze` | feature marts → `analysis_mart` (+ Phase 5 stats when shipped) |
| `replay` | re-parse one `response_id` from `raw_responses` (audit/re-normalize) |

## Polars data layer (Phase 4.5)

All lake transforms live under `src/seo_rank/data/`. Every public function accepts
and returns `pl.LazyFrame` so predicate and projection pushdown stay enabled
through the pipeline.

```text
src/seo_rank/data/
  scans.py        # run-scoped scan functions (one pl.scan_parquet per table)
  normalize.py    # raw_responses → typed curated tables
  features.py     # page, passage, domain, similarity feature marts
  marts.py        # analysis-ready joins (Phase 5 prep)
  validate.py     # schemas, keys, null/range checks before every sink

src/seo_rank/stats/   # Phase 5 observational analysis (see ROADMAP.md)
  spec.py         # load analysis_spec.v1.yaml
  panel.py        # mart load, filter, guardrails
  spearman.py     # per-keyword ρ + BH
  regression.py   # pooled OLS, clustered SEs, effect size
  diagnostics.py  # RESET, BP, influence, multivariate VIF
  bh.py           # Benjamini–Hochberg within backend family
  artifacts.py    # stats_summary.json, stats_diagnostics.json, stats_report.md
```

| Module | Responsibility |
|--------|----------------|
| `scans.py` | `scan_raw_responses(run_id)`, `scan_keywords(run_id)`, etc.; stable paths under `runs/{run_id}/parquet/` |
| `normalize.py` | Scan `raw_responses`, filter by `endpoint`, parse `response_body_bytes` via batch UDFs (`map_batches` / `map_groups`); emit curated LazyFrames; no analytical reads of `raw_responses` elsewhere |
| `features.py` | Build `keyword_serp`, `page_features`, `passage_features`, `domain_features` from curated scans |
| `marts.py` | Join feature marts into `analysis_mart` at `target_keyword × SERP URL` grain |
| `validate.py` | Schema contracts plus row-level uniqueness, null, and range audits; used before every mart write or at the sink edge |

**Phase 5 stats package** (`src/seo_rank/stats/`): **slices 1–6 shipped** —
`spec.py` loads `analysis_spec.v1.yaml`; `artifacts.py` exposes estimand-version
metadata for future `stats_*` outputs. Placeholder modules (`panel.py`,
`spearman.py`, `regression.py`, `diagnostics.py`, `bh.py`) now include
guardrails, the Spearman/BH primary path, pooled regression summaries with
keyword-clustered SEs plus two-way-cluster sensitivity, and pooled OLS
diagnostics; later slices add multivariate sensitivity and the remaining
robustness paths.
Dependencies: `statsmodels`, `numpy`, `scipy`, `PyYAML` in `pyproject.toml`.
Spec: `analysis_spec.v1.yaml`.

**Execution model:** scan lazily, filter/select early, join on IDs only, validate
schema contracts, then sink; materialized row audits run at the sink edge.
Curated normalization keeps JSON parsing and similarity grouping in batch-level
Python UDFs inside the lazy plan; each table collects once at write
(`collect(engine="streaming")`). Further eager collection only at CLI
boundaries, report generation, or tests that need in-memory assertions.

## Planned Page Similarity Run

Live similarity evaluation runs once per keyword in the expanded keyword
cluster. For each cluster keyword:

1. Collect the organic **top-20 SERP** for that keyword. That keyword is the
   **target keyword** for every similarity score derived from that SERP. Passage,
   page, and domain scores always use the keyword that generated the SERP, not
   other keywords in the cluster.
2. For **each organic result** in that top 20 (Phase 4 **page scope** shipped):
   - Score the full parsed page with **BGE** (`bge`).
   - Score with **Gemini Doc Retrieval** (`gemini_doc_retrieval`) — asymmetric
     **search result** (query vs `title|text` document).
   - Score with **Gemini Semantic Similarity** (`gemini_semantic_similarity`) —
     symmetric **sentence similarity** on keyword and page.
3. **Later (Phase 5.5):** passage and domain scopes for the same three signals.

Each measurement produces page-level scores for the same top-20 SERP rows so
results stay comparable run to run.

## Live similarity backends (Phase 4)

Fixture scorers in `similarity.py` implement the artifact shape for offline
runs. Live paths swap in backend-specific scorers only when the matching flags
and env gates are enabled. Offline tests and `--dry-run` keep fixtures.

### Gemini Doc Retrieval & Gemini Semantic Similarity (Gen AI SDK)

| Item | Requirement |
|------|-------------|
| Auth | `GEMINI_API_KEY` (Google AI Studio; local research runs) |
| SDK | `google-genai` — `genai.Client(api_key=...)`, `models.embed_content` |
| Model | `gemini-embedding-2` (8192 tokens; up to 3072 dims; MRL; task via prompt prefix, not `task_type`) |
| Gemini Doc Retrieval | Asymmetric **search result**: `task: search result \| query: {keyword}` vs `title: {title\|none} \| text: {body}` → `gemini_doc_retrieval` |
| Gemini Semantic Similarity | Symmetric **sentence similarity**: `task: sentence similarity \| query: {text}` on keyword and page → `gemini_semantic_similarity` |
| Vectors | Cosine on API embeddings; optional `output_dimensionality`; truncation handled by Gemini |

### BGE (local cross-encoder)

| Item | Requirement |
|------|-------------|
| JSON key | `bge` |
| Library | `FlagEmbedding` |
| Model | BGE **reranker** (cross-encoder), pinned `BAAI/bge-reranker-v2-m3` |
| Query | Target keyword; prepend model-card instruction when required |
| Scores | Per-page sigmoid(raw logit) → `bge_normalized_score`; within-keyword rank/pct/z planned in Phase 5 slices 11–12 (`analysis_mart.v2`) |
| Compute | Local CUDA GPU required; fp16 enabled; batch per keyword |

### Analysis use

**BGE** — local cross-encoder rerank signal. **Gemini Doc Retrieval** — asymmetric
search-result embedding cosine. **Gemini Semantic Similarity** — symmetric
sentence-similarity embedding cosine. Do not use sentence similarity for retrieval.
All three land in every live page-similarity path for comparability in downstream
OLS work (Phase 5).

## Planned Per-Run Statistical Analysis

Every completed run must include observational ranking analysis, not only
similarity feature generation. Product review and open questions:
`PHASE5-STATS-PLAN-REVIEW.md`. Implementation slices: `ROADMAP.md` Phase 5.

### Phase 5 estimand (v1)

**Grain:** one row per `target_keyword_id × canonical_url_hash` from
`analysis_mart`; filter `serp_rank` 1–20; drop rows with null
`bge_normalized_score` for the primary path (per-backend null rules for
secondary backends).

**Mart columns (absolute):** `bge_normalized_score`, `gemini_doc_retrieval_normalized_score`,
`gemini_semantic_similarity_normalized_score`, `serp_rank`, `page_text_length`,
`target_keyword_id`, `canonical_url_hash`.

**Mart columns (relative, `analysis_mart.v2`, slices 11–12):** per backend,
`*_similarity_rank`, `*_similarity_pct`, `*_similarity_z` — derived within each
`target_keyword_id` from absolute scores (BGE ranks on `bge_raw_score`). Used in
robustness appendix only (Slice 13); primary estimand stays on absolute scores.

**Dependence:** cluster inference at `target_keyword_id`. The same URL may appear
under multiple keywords; do not dedupe the panel in v1. Optional robustness:
two-way cluster (keyword × `canonical_url_hash`).

**Primary decision:** (A) association exists and (B) backend comparison — pooled
within-keyword association per similarity backend. **BGE** is the pre-registered
primary backend; Gemini Doc Retrieval and Gemini Semantic Similarity are
secondary (fixed order, not data-driven).

**Headline metric:** keyword-level Spearman ρ (primary). Pooled regression with
clustered CIs (secondary). Prefer CIs over p-values; coefficients are likely
conservative under similarity measurement error (attenuation).

**Primary estimand:** keyword-level Spearman ρ between each backend's
`*_normalized_score` and `serp_rank`. Summarize median ρ, IQR, and fraction of
keywords with same-sign ρ. **BH:** one two-sided correlation test per keyword per
backend; family = all keywords for that backend (size K). Apply BH at q = 0.05
**within each backend family** when **K ≥ 10**; otherwise report raw p-values
with `bh_skipped_reason`. Do not BH-adjust diagnostic p-values.

**Secondary estimand:** pooled regression on `-log(serp_rank)`:

```text
-log(serp_rank) ~ normalized_similarity + log(page_text_length + 1) + C(target_keyword_id)
```

One univariate feature model per backend (not joint three-predictor as primary).
Keyword-clustered robust SEs only in primary output; never naive IID SEs.

**Effect size:** report approximate Δ rank per 1 SD increase in normalized
similarity (derived from pooled coefficient and within-panel SD).

**Actionable association (BGE only, v1):** `actionable_association: true` when
median |ρ| ≥ 0.25, ≥ 60% same-sign ρ, and BGE pooled 95% CI excludes 0 (thresholds
in `analysis_spec.v1.yaml`, tune after golden fixtures).

**Baseline (descriptive):** keyword FE + `log(page_text_length + 1)` only.
Compare adjusted R² or AIC to feature model; not BH-adjusted.

**Multivariate sensitivity (not confirmatory):** joint three-backend model; if
VIF > 5, drop backends in order semantic similarity → doc retrieval → keep BGE.

**Robustness appendix:** refit pooled models excluding Cook's D > 4/n rows;
optional two-way-cluster CIs; diagnostic-driven spec changes never replace the
confirmatory estimand.

**Guardrails** — hard-fail skips BH and coefficient interpretation; warn still
runs full stats:

| Guardrail | Default | Severity |
| --------- | ------- | -------- |
| Within-keyword `serp_rank` variance | > 0 | hard-fail |
| Within-keyword similarity variance | > 0 | warn |
| Influential rows (Cook's D > 4/n) | report %; warn if > 5% | warn |

**Limitations** (required in `stats_summary.json` `limitations` object **and**
`stats_report.md`): observational only; associations within observed top 20 only
(incidental truncation; rank-20 ≠ unranked); no causal ranking-factor claims;
measurement error on similarity scores.

**Diagnostics (pooled feature model per backend):** RESET, Breusch–Pagan (→ HC3
when flagged), Cook's D plus leverage / studentized residuals / DFFITS /
DFBETAs in diagnostics JSON. Skip per-keyword normality as primary gates; skip
LOWESS/CCPR file artifacts in v1 unless debug.

**Module layout:** `src/seo_rank/stats/`; spec in `analysis_spec.v1.yaml`.
Phase 5.75 features → `analysis_spec.v2.yaml`.

**Outputs:** `runs/{run_id}/stats/stats_summary.json`, `stats_diagnostics.json`,
`stats_report.md`; link from `report.md`. CLI: `seo-rank analyze`; exit 1 on
guardrail hard-fail (overridable); skip stats on `--dry-run` and documented
fixture modes only.

**Deferred (Phase 5.1):** rank-decile segments, keyword heterogeneity deep-dives,
confirmatory keyword holdout, IV / `PanelOLS`, URL fixed effects.

### Pipeline steps

1. Load `analysis_spec.v1.yaml`; materialize panel; evaluate guardrails.
2. On hard-fail: write guardrails + limitations; skip confirmatory inference.
3. Compute keyword-level Spearman ρ; BH within each backend family when K ≥ 10.
4. Fit baseline and univariate pooled models with keyword-clustered SEs; effect
   size translation; optional two-way-cluster sensitivity.
5. Run pooled diagnostics; multivariate VIF sensitivity; influence refit appendix.
6. Emit `stats_*` artifacts; link from `report.md`; set `actionable_association`
   per BGE rule.

Do not skip any page-level scorer or the statistical analysis step on individual
runs unless the run is an explicit offline fixture or dry-run test mode
documented in the CLI contract.

## OLS Pre-Analysis Preparation

Before running ranking-variation analysis on a prepared run dataset, fit and
validate the OLS specification. Detect problems first; **fix only when a check
flags an issue or theory supports a revision**. After every correction, refit
the model and rerun all diagnostics on the revised specification.

### Fit a preliminary OLS model first

Use `statsmodels.OLS` or `statsmodels.formula.api.ols`. Retain fitted values,
residuals, and the design matrix for all downstream diagnostics.

### Linearity — detect

- Plot residuals versus fitted values with a LOWESS smoother using
  `statsmodels.nonparametric.smoothers_lowess.lowess`.
- Run `statsmodels.stats.diagnostic.linear_reset`.
- Inspect component-plus-residual plots with
  `statsmodels.graphics.regressionplots.plot_ccpr_grid`.

**Fix only if curved patterns or RESET indicate misspecification:** add
theory-supported polynomial terms, interactions, `np.log(x)` for positive
predictors, or spline terms with `patsy.bs`; refit and repeat the checks.

### Multicollinearity — detect only when there is more than one predictor

- Calculate VIF for each non-intercept predictor with
  `statsmodels.stats.outliers_influence.variance_inflation_factor`.
- Calculate a condition number with `numpy.linalg.cond`.

**Flag for review:** VIF above about 5, condition number above about 30, exact
duplicate columns, or near-perfect correlations.

**Fix only if flagged:** drop one redundant predictor, combine conceptually
overlapping predictors into an index, or mean-center continuous predictors
before creating polynomial and interaction terms. Use PCA or ridge only when
prediction—not standard OLS coefficient interpretation—is the goal.

### Exogeneity — assess

Do not use residual plots or a generic Python test to claim exogeneity. Require a
causal DAG, variable timing, and domain review to identify omitted confounders,
reverse causality, colliders, and measurement problems.

**Test only in a valid identification setup:** where a credible instrument
exists, fit `linearmodels.iv.IV2SLS` and run `wu_hausman()`; assess instrument
relevance through first-stage diagnostics.

**Fix only if an issue is plausible:** add justified **pre-treatment**
confounders, use panel fixed effects with `linearmodels.panel.PanelOLS` when
appropriate, or use IV/2SLS with a defensible instrument. Do not treat
transformations as an exogeneity fix.

### Homoscedasticity — detect

- Plot residuals versus fitted values.
- Run `statsmodels.stats.diagnostic.het_breuschpagan` and optionally `het_white`.

**Fix only if variance is nonconstant:** refit inference using HC3 robust
standard errors (`cov_type="HC3"`). Use `statsmodels.WLS` only when justified
inverse-variance weights are available. Consider a substantively justified
outcome transformation, then recheck residuals.

### Normality of errors — detect

- Create a Q-Q plot with `statsmodels.graphics.gofplots.qqplot`.
- Use `scipy.stats.shapiro` for small samples or `scipy.stats.normaltest` for
  larger samples. Treat large-sample test rejections cautiously.

**Fix only if non-normality materially affects small-sample inference:** first
address outliers, nonlinearity, and heteroscedasticity. Then use bootstrap
confidence intervals, a justified outcome transformation, or a more suitable
model family such as `statsmodels.GLM` for binary, count, or strongly skewed
outcomes.

### Influential observations — detect

Use `results.get_influence()` and extract leverage (`hat_matrix_diag`),
externally studentized residuals (`resid_studentized_external`), Cook's distance
(`cooks_distance`), DFFITS, and DFBETAs.

**Flag for review** (where `p` includes the intercept, `n` is sample size):

- Leverage > `2p/n`
- Absolute studentized residual > 3
- Cook's distance > `4/n`
- DFFITS > `2 * sqrt(p/n)`
- Absolute DFBETA > `2/sqrt(n)`

**Fix only if necessary:** correct verified data errors. Do not automatically
delete valid observations. Refit the model with and without flagged valid cases
as a sensitivity analysis; use `statsmodels.RLM` as an additional robustness
check when conclusions are highly sensitive.

### After every correction

Refit the model and rerun **all** diagnostics on the revised specification
before proceeding to Benjamini-Hochberg correction and run reporting.

## Decisions

- Build as a CLI-first Python application.
- Use DataForSEO as the canonical SERP and page-text source.
- Send DataForSEO parsed page text to TextRazor; do not send original URLs for
  entity extraction.
- Keep direct page fetching out of v1.
- Treat analysis as observational and censored to observed top-20 rankings.
- Phase 5 estimand: Spearman ρ per keyword as primary inference; pooled OLS with
  keyword-clustered SEs as secondary; BH within each backend family only;
  complete [OLS Pre-Analysis Preparation](#ols-pre-analysis-preparation) on
  pooled models before interpreting regression coefficients; see
  [Phase 5 estimand (v1)](#phase-5-estimand-v1) and `PHASE5-STATS-PLAN-REVIEW.md`;
  do not introduce a parallel stats stack for the same work.
- Keep deterministic fixture embeddings for offline tests. Live runs follow
  [Planned Page Similarity Run](#planned-page-similarity-run): per cluster keyword,
  top-20 SERP, then BGE, Gemini Doc Retrieval, and Gemini Semantic Similarity at
  page scope (passage and domain in Phase 5.5).
- Phase 4.5 storage: run-scoped Parquet lake under `runs/{run_id}/` with
  authoritative `raw_responses`, curated tables, feature marts, and
  `analysis_mart`; Polars LazyFrame pipeline in `src/seo_rank/data/`; Zstd sinks
  with validation before write; `collect(engine="streaming")` only at CLI/report
  edges; CLI `normalize`, `build-features`, `analyze`, `replay`, and
  `--stored-run`. No Parquet `Variant`; no nested provider schemas in curated
  tables; `raw_responses` excluded from normal analytical joins.
- Capture TextRazor entities for future work but exclude entity-derived features
  from the first ranking-variation model.
- Continue filling in the real package under `src/seo_rank/` and add
  discoverable tests under `tests/`.
- Record significant architecture decisions in this file's [Decisions](#decisions)
  section and `ROADMAP.md` History.

## Codex And SDLC Flow

The canonical implementation entrypoint is `$sdlc`. Codex does not have a
native `/sdlc` command in this repo, and repo docs should not imply one exists.

Execution lane guidance:

- Use CLI for repository edits, tests, docs, hooks, commits, and ordinary
  verification.
- Use Desktop/computer-use first for browser sign-in, Microsoft tenant flows,
  MFA, Office UI, admin portals, screenshots, or desktop-only state. Start it
  from the repo root with `codex app .` on macOS or Windows.
- Keep credentials, MFA, tenant consent, sends, deletes, license/admin changes,
  and policy publishing as explicit human actions.
