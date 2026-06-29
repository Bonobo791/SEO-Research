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
Later phases add `statsmodels` OLS with Benjamini-Hochberg after OLS pre-analysis
diagnostics.

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
  `build-features`, `analyze`, and `replay`
- **Tests:** 53 tests under `tests/`; gate: `python -m pytest`
- **Product docs:** `ARCHITECTURE.md`, `GOALS.md`, `ROADMAP.md`, `README.md`,
  `TESTING.md`
- **Not yet:** `statsmodels` analysis; CLI stored-run surfaces and the remaining
  lazy Polars CLI surfaces (Phase 4.5 in progress)

Module and artifact details are in [Application Surface](#application-surface)
and [Key Product Components](#key-product-components) below. Planned live
similarity and statistical analysis sections in this file are **not implemented**
in code yet.

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
- **Analysis engine (planned):** OLS pre-analysis, `statsmodels` OLS,
  Benjamini-Hochberg — see [Planned Per-Run Statistical Analysis](#planned-per-run-statistical-analysis).
- **Reporters (shipped):** JSON + Markdown under `--output-dir`; Phase 4.5 adds
  `runs/{run_id}/` Parquet lake + `run.json` catalog; Phase 6 expands report
  narrative sections.
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
`build-features`, and `analyze` materialize only the marts they own. `raw_responses`
stays out of normal analytical joins (replay/re-normalization only). Live
DataForSEO payloads are not retained by the provider long-term.

**Planned full pipeline (Phase 5+):** lazy Polars joins on `analysis_mart` →
OLS pre-analysis → `statsmodels` OLS → Benjamini-Hochberg → report generation.

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
| **Curated** | `keywords`, `serp_items`, `pages`, `passages`, `entities`, `similarity_scores` | `normalize.py` | Parse `raw_responses` once into typed tables |
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

Normalized tables derived from `raw_responses` via `normalize.py`. Every row
includes join keys: `run_id`, `target_keyword_id`, `response_id`, `schema_version`,
plus stable entity IDs (`canonical_url_hash`, `passage_id`, etc.).

| Table | Contents |
|-------|----------|
| `keywords` | Expanded cluster keywords with caps and dedup metadata |
| `serp_items` | Organic SERP rows (top 20), ranks, URLs, titles |
| `pages` | Full parsed page text and page-level metadata (text lives here only) |
| `passages` | Passage splits with offsets; no duplicate full page bodies |
| `entities` | TextRazor entity rows when present |
| `similarity_scores` | Page-level `bge`, `gemini_doc_retrieval`, `gemini_semantic_similarity` |

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
  refuse to sink invalid output.

### Read contract

- **LazyFrames end-to-end:** `pl.scan_parquet()` for every dataset; functions
  accept and return `pl.LazyFrame`.
- Apply filters and column projection **before** joins.
- Join only on stable IDs: `run_id`, `target_keyword_id`, `canonical_url_hash`,
  `response_id`, `passage_id`.
- Materialize reusable marts with `sink_parquet`; use
  `collect(engine="streaming")` only at CLI/report boundaries or when a
  DataFrame is actually needed.
- CLI: `seo-rank run --stored-run runs/{run_id}` selects a prior run tree for
  orchestration replay. Explicit opt-in; missing slices fall back to fixtures
  (offline) or gated live API calls.

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
```

| Module | Responsibility |
|--------|----------------|
| `scans.py` | `scan_raw_responses(run_id)`, `scan_keywords(run_id)`, etc.; stable paths under `runs/{run_id}/parquet/` |
| `normalize.py` | Parse `response_body_bytes` once; emit curated LazyFrames; no analytical reads of `raw_responses` elsewhere |
| `features.py` | Build `keyword_serp`, `page_features`, `passage_features`, `domain_features` from curated scans |
| `marts.py` | Join feature marts into `analysis_mart` at `target_keyword × SERP URL` grain |
| `validate.py` | Schema contracts, primary/foreign keys, null and range checks; called before every `sink_parquet` |

**Execution model:** scan lazily, filter/select early, join on IDs only, validate,
then sink. Collect to eager DataFrames only at CLI boundaries, report generation,
or tests that need in-memory assertions.

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
| Scores | Relative rank within SERP (~0.6–1.0 typical); not calibrated vs Gemini |
| Compute | Local CUDA GPU required; fp16 enabled; batch per keyword |

### Analysis use

**BGE** — local cross-encoder rerank signal. **Gemini Doc Retrieval** — asymmetric
search-result embedding cosine. **Gemini Semantic Similarity** — symmetric
sentence-similarity embedding cosine. Do not use sentence similarity for retrieval.
All three land in every live page-similarity path for comparability in downstream
OLS work (Phase 5).

## Planned Per-Run Statistical Analysis

Every completed run must include observational ranking analysis, not only
similarity feature generation. **Before interpreting results or applying
Benjamini-Hochberg correction**, complete [OLS Pre-Analysis
Preparation](#ols-pre-analysis-preparation) on the run dataset.

1. Fit baseline and similarity-feature models with **`statsmodels` OLS**
   residual/variance modeling over the observed top-20 rankings, following the
   diagnostic workflow below.
2. Apply **Benjamini-Hochberg** multiple-testing correction across keyword- and
   feature-level comparisons produced by that run.
3. Emit similarity-backend outputs, diagnostic artifacts, and statistical
   analysis into the run outputs (JSON plus Markdown report sections).

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
- Use `statsmodels` for OLS residual/variance models and Benjamini-Hochberg FDR
  correction on every run; complete [OLS Pre-Analysis
  Preparation](#ols-pre-analysis-preparation) before interpreting results; do not
  introduce a parallel stats stack for the same work.
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
