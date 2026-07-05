# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

## What works today

Offline `seo-rank run` expands a seed keyword from fixtures, loops over every
capped cluster keyword, normalizes SERP rows and passages, computes fixture
page-level **BGE**, **Gemini Doc Retrieval**, and **Gemini Semantic Similarity**
scores, and writes JSON and Markdown artifacts with **no network calls**. Provider
request builders and credential validators are available for offline
verification. The CLI also has a non-default `--live-providers` gate,
standard-library HTTP clients, env-gated live DataForSEO and TextRazor paths,
and env-gated live Gemini (`gemini-embedding-2`) and BGE (FlagEmbedding on CUDA)
page scoring.

Long runs print **progress to stderr** (`[seo-rank]` prefix): run phase, per-keyword
steps (SERP, page text, similarity, optional TextRazor/Gemini/BGE), a keyword
progress bar, and artifact writes. Stdout stays clean for piping.

### Recommended workflows

Use these commands in order. Each step reads or extends the same run tree under
`runs/{run_id}/` (or `--output-dir`).

| Goal | Command |
|------|---------|
| **Fast local smoke** (default: 1 keyword, fixtures, no network) | `seo-rank run --seed "technical seo" --dry-run` |
| **Full offline cluster** (25 keywords from fixtures) | `seo-rank run --seed "technical seo" --dry-run --keyword-limit 25` |
| **Materialize curated Parquet tables** | `seo-rank normalize --run runs/RUN_ID` |
| **Build feature marts** | `seo-rank build-features --run runs/RUN_ID` |
| **Analysis mart + stats** | `seo-rank analyze --run runs/RUN_ID` |
| **Re-run stats only** (after mart exists) | `seo-rank analyze --run runs/RUN_ID` (exit `1` on guardrail hard-fail) |
| **Inspect one keyword row** | `seo-rank analyze --run runs/RUN_ID --keyword "technical seo"` |
| **Resume stored run in place** | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID` |
| **Backfill live TextRazor on stored run** | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only` |
| **Backfill DataForSEO backlinks on stored run** | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-providers` |
| **Brand-new run with live TextRazor only** | `seo-rank run --seed "technical seo" --live-textrazor-only --output-dir runs/demo` |
| **Expand existing run in place** | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --keyword-limit 25` |
| **Audit one raw HTTP response** | `seo-rank replay --run runs/RUN_ID --response-id RESPONSE_ID` |
| **Live provider smoke** (DataForSEO; optional Gemini/BGE/TextRazor) | See [Live providers](#live-providers) below |

**Fresh data**

```bash
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts
```

**Resume stored run in place**

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID
```

This resumes stored runs in place, reuses existing raw responses and completed
measurements, and only backfills missing keywords or backend scores before the
downstream chain is re-materialized. When the stored run already contains more
keywords than the current `--keyword-limit`, the CLI expands the limit to match
the stored keyword count. Pair it with a higher `--keyword-limit` to extend the
original seed in place.

**Expand existing run**

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --keyword-limit 25
```

**Backfill live TextRazor on a stored run** (no DataForSEO network; requires
`SEO_RANK_ENABLE_TEXTRAZOR=1` and `TEXTRAZOR_API_KEY` in `.env`):

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only
```

Pass `--refresh-textrazor` to replace existing `endpoint=entities` rows for the
same `(target_keyword, url)` keys. If the stored run already had TextRazor
enabled, `--skip-textrazor` still wins during replay and keeps TextRazor off
for that invocation.

**Backfill DataForSEO backlinks on a stored run** (requires
`SEO_RANK_ENABLE_LIVE_PROVIDERS=1` and DataForSEO credentials in `.env`):

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-providers
```

Pass `--live-providers` on replay even when the stored run was created offline:
the CLI overlays live-provider flags onto the saved config for this invocation
(`merge_stored_run_cli_overlay`); `--skip-textrazor` stays sticky and suppresses
TextRazor even when the stored run had it enabled. Only missing SERP URL
backlink summaries are fetched via DataForSEO `backlinks/summary/live` (two
calls per URL: unfiltered summary plus dofollow-filtered summary); existing raw
rows are kept. Each keyword batch persists to
`parquet/raw_responses/endpoint=backlinks_summary/` and
`endpoint=backlinks_dofollow_summary/` (dedupe on `(target_keyword, url, variant)`),
including partial progress when a later URL in the same batch fails; survives
later provider failures before `run.json` is written. Curated rows materialize in
`parquet/backlinks/` on normalize (`dofollow_backlinks_count` is null when the
dofollow variant is missing; `backlinks_metrics_complete` flags paired rows).
`build-features` materializes `parquet/backlinks_analysis/` (panel grain plus
backlinks count columns) for the `backlinks_counts` signal family in analyze.

TextRazor responses are stored under `raw_responses/endpoint=entities`, use
`provider=textrazor`, and share the same `RAW_RESPONSE_SCHEMA` as the other
raw-response rows. Normalization also materializes `parquet/entities/` (entity
mentions) and `parquet/textrazor_page_metrics_curated/` (one aggregated row per
`target_keyword × SERP URL`). The feature mart
`parquet/textrazor_page_metrics/` feeds Phase 5 TextRazor signal families; the
similarity `analysis_mart` stays similarity-only. Curated and feature marts
include `textrazor_page_metrics_complete` when upstream extractor sections were
fully present.

**Brand-new run with live TextRazor only** uses offline DataForSEO fixtures for
keyword expansion, SERP, and page text, then calls live TextRazor for entities.
No DataForSEO HTTP and no `dataforseo.*` entries in `network_calls`:

```bash
seo-rank run --seed "technical seo" --live-textrazor-only --output-dir runs/demo
```

**Typical offline research path:**

```bash
seo-rank run --seed "technical seo" --dry-run --keyword-limit 25
seo-rank normalize --run runs/RUN_ID
seo-rank build-features --run runs/RUN_ID
seo-rank analyze --run runs/RUN_ID
```

`analyze` backfills missing feature marts automatically. On non–dry-run runs it
also writes `runs/{run_id}/stats/` (`stats_summary.json`, `stats_diagnostics.json`,
`stats_report.md`) and exits `1` when guardrails hard-fail (stderr message only;
no traceback). `--dry-run` runs skip Phase 5 stats via `run_manifest_is_dry_run()`.
The same stats path runs from `seo-rank run` after `materialize_run_tree()`.
When the post-run materialization chain finishes, the CLI syncs TextRazor entity
confidence and relevance from `textrazor_page_metrics` into `run.json`
`page_similarity` and refreshes `report.md` so page-level reports show TextRazor
scores alongside the three similarity backends.

### What `seo-rank run` executes

On every `run` (offline or live), per expanded cluster keyword:

1. SERP normalization (top *N* organic rows, default 20)
2. DataForSEO `backlinks/summary/live` — **two calls per SERP URL** when live
   providers are on (unfiltered summary plus dofollow-filtered summary; ~$0.04
   per target for both calls combined); incremental raw-lake persistence to
   `endpoint=backlinks_summary` and `endpoint=backlinks_dofollow_summary`;
   curated `backlinks` on normalize
3. Page text from fixtures or DataForSEO `content_parsing/live`
4. Passage splitting
5. **Passage-level similarity features** — max/mean cosine per URL from deterministic
   fixture embeddings (`compute_page_similarity_features`)
6. **Page-level similarity scores** — three backends per URL (`compute_page_similarity_scores`
   or live overrides below)
7. TextRazor page metrics (fixture unless `--live-providers --live-textrazor`):
   one call per parsed SERP URL with extractors
   `entities,topics,categories,entailments,words,relations,properties,nounPhrases`
8. Artifacts: `run.json`, `report.md`, `parquet/raw_responses/`, curated tables,
   feature marts, `analysis_mart`, and Phase 5 stats unless `--dry-run` is set

`seo-rank run` now performs the full postprocessing chain after writing raw
artifacts. Use `--stored-run runs/RUN_ID` to resume stored runs in place,
reusing existing raw responses and completed measurements while backfilling
missing keywords or backend scores before the downstream chain is
re-materialized. `--dry-run` still skips Phase 5 stats.

By default, keyword expansion keeps **one** cluster keyword (the seed). Pass
`--keyword-limit 25` for the full fixture expansion set used in lake round-trip
tests.

### Similarity backends (fixture vs live)

All three page-level backends are always emitted in JSON/Markdown. Default and
live runs without optional flags use **deterministic fixture scorers** in
`similarity.py` (hash-style embeddings and a stand-in BGE formula). They are
for pipeline shape and tests, not production-grade retrieval.

| Backend | JSON key | Default `run` | Live override |
|---------|----------|---------------|---------------|
| BGE cross-encoder rerank | `bge` | Fixture formula | `--live-providers --live-bge` loads `BAAI/bge-reranker-v2-m3` (CUDA) |
| Gemini Doc Retrieval | `gemini_doc_retrieval` | Fixture cosine | `--live-providers --live-gemini` (`gemini-embedding-2`, asymmetric query/doc) |
| Gemini Semantic Similarity | `gemini_semantic_similarity` | Fixture cosine | same `--live-gemini` flag (symmetric sentence-similarity task) |

With `--live-providers` only, DataForSEO is live but similarity stays on fixtures
until `--live-bge` and/or `--live-gemini` are set. Live BGE **merges** real rerank
scores over the base page-similarity rows; it does not replace Gemini columns.

Retrieve-then-rerank (BM25 + bi-encoder recall, then BGE) is **not** implemented;
see `ROADMAP.md` (BGE hybrid / retrieve-then-rerank backlog).

### `seo-rank analyze` today

`analyze` writes `parquet/analysis_mart/` (SERP rank plus the three similarity
columns and page text length). TextRazor page metrics live in separate marts
(`textrazor_page_metrics_curated`, `textrazor_page_metrics`) at the same URL
grain; they are not columns on `analysis_mart` today. The curated and feature
marts include `textrazor_page_metrics_complete` so incomplete upstream
extractor coverage is visible instead of silent zeros. If feature marts are
missing, it materializes them first from the curated tables. It does **not**
re-fetch pages or re-run embeddings. The stats path runs guardrails, Spearman
summaries, pooled regression summaries, and page-level Plackett-Luce summaries
at four confirmatory rank depths (`top_20`, `top_10`, `top_5`, `top_3`) for
every registered signal family (similarity backends, TextRazor page-signal
families, and the `backlinks_counts` family on `backlinks_analysis`) into `runs/{run_id}/stats/`, including nested `rank_depths` and
`rank_depths.*.families` in `stats_summary.json` and
`stats_diagnostics.json`, four `## Rank depth:` sections with `### Families`
subsections, and `actionable_association_by_rank_depth`.

**Robustness appendix (slices 7–8, primary depth `top_20` only):**

- **Multivariate sensitivity (slice 7):** joint pooled OLS with all three
  `*_normalized_score` predictors plus `log(page_text_length + 1)` and keyword
  fixed effects. Computes VIF; when any VIF exceeds the spec threshold (default
  5), drops backends in pre-registered order (Gemini Semantic Similarity → Gemini
  Doc Retrieval → keep BGE). Writes coefficients, VIF table, and drop log to
  `rank_depths.top_20.multivariate_sensitivity` in `stats_diagnostics.json` and
  a `### Robustness` section in `stats_report.md`. Not used for BH or
  `actionable_association`.
- **Influence robustness (slice 8):** for each backend pooled feature model,
  refits excluding rows with Cook's D > 4/n and compares confirmatory vs
  sensitivity coefficients in `rank_depths.*.regression.<backend>.influence_sensitivity`.
  Surfaces `### Influence robustness` in `stats_report.md`. Warn guardrail
  `influential_rows_rate` fires when the primary backend exceeds 5% influential
  rows (threshold from `analysis_spec.v1.yaml`).

Each depth and backend reports `keyword_count` and `inference_mode`
(`confirmatory` when K ≥ 10, `exploratory` when 2 ≤ K < 10, `underpowered`
when K = 1). Top-level summary fields mirror `rank_depths.top_20` for
compatibility. Golden fixture and schema contracts for the stats JSON tree live
in `tests/unit/test_stats_golden_fixtures.py` (slice 10). Passage-level
Plackett-Luce remains deferred backlog work and is not wired into `analyze`
today.

### Standalone scripts

`analysis/gemini_nwh_similarity.py` is a one-off experiment for a fixed keyword
and hand-picked realtor homepage text blocks. It can call live Gemini and BGE when
configured, and optionally requests extended TextRazor analysis (entities, topics,
categories, relations, entailments, and more) per block. It is not part of the
default CLI `run` flow.

`analysis/textrazor_ranking_r2.py` measures how much similarity backends and
TextRazor page metrics explain SERP rank on a completed run using pooled OLS
adjusted R² (univariate per metric plus joint multivariate models). Requires
`parquet/analysis_mart` and `parquet/textrazor_page_metrics` from a prior
`seo-rank analyze` pass:

```bash
python analysis/textrazor_ranking_r2.py --run runs/RUN_ID
python analysis/textrazor_ranking_r2.py --run runs/RUN_ID --depth top_10
python analysis/textrazor_ranking_r2.py --run runs/RUN_ID --no-show
```

By default the script opens the curated final-model chart: it uses a matplotlib
window when Tk/Qt is available, otherwise it opens the saved PNG in your default
image viewer. Pass `--no-show` to skip display and only write the PNG.

Writes `runs/{run_id}/stats/ranking_r2.json` with `similarity`, `textrazor`, a
top-level `multivariate` block (all similarity + TextRazor predictors), and
`multivariate_curated` (relation count, property count, entity relevance, Gemini
semantic similarity). Also writes `stats/ranking_r2_curated_model.png` and
`stats/ranking_r2_entity_relevance.png` — coefficient/fit charts for the curated
model and the entity-relevance-only model.

```bash
python -m pytest
seo-rank run --seed "technical seo" --dry-run
seo-rank run --seed "technical seo" --dry-run --keyword-limit 25 --output-dir artifacts
```

### Live providers

For live provider smoke tests, copy `.env.example` to `.env` in the project root
and fill in real credentials. The CLI and pytest **load `.env` automatically**
(project root is detected via `pyproject.toml`); you do not need to `source` it in
the shell. Values in `.env` override conflicting shell exports.

Live-provider contract:

- `--live-providers` always uses live DataForSEO.
- `--live-bge` additionally enables live local BGE reranking and requires
  `SEO_RANK_ENABLE_BGE=1` plus a CUDA GPU.
- `--live-gemini` additionally enables Gemini live scoring and requires
  `SEO_RANK_ENABLE_GEMINI=1` plus `GEMINI_API_KEY`.
- `--live-textrazor` additionally enables live TextRazor entity extraction and
  requires `SEO_RANK_ENABLE_TEXTRAZOR=1` plus `TEXTRAZOR_API_KEY`.
- If an optional live flag is not passed, that provider is skipped.
- `page_text` crawls always use the fixed US English desktop contract
  (`ip_pool_for_scan: us`, `accept_language: en-US`, JS and browser rendering
  off, `store_raw_html: true`). They do **not** follow `--location` /
  `--language`. Keyword expansion and SERP still use those flags, so
  `--language fr --location France` returns French SERPs but US-fetched page
  HTML. Aligning page-crawl locale with SERP locale is **not supported** today.

Example live smoke (DataForSEO only, fixture similarity):

```bash
# .env: SEO_RANK_ENABLE_LIVE_PROVIDERS=1, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
seo-rank run --seed "technical seo" --live-providers --output-dir artifacts
```

Example with live Gemini:

```bash
# .env: also SEO_RANK_ENABLE_GEMINI=1, GEMINI_API_KEY
seo-rank run --seed "technical seo" --live-providers --live-gemini --output-dir artifacts
```

**Removed flags:** `--javascript-parsing` was dropped; argparse rejects it if
scripts still pass it.

### Storage layout 

`seo-rank run` writes this layout under `runs/{run_id}/` when `--output-dir` is
omitted. The command now chains raw artifact generation, normalization, feature
materialization, `analysis_mart`, and Phase 5 stats. CLI subcommands still
materialize layers in place on an existing run tree.

```text
runs/{run_id}/
  run.json
  report.md
  parquet/
    raw_responses/endpoint={keyword_expansion|serp|page_text|entities|backlinks_summary|backlinks_dofollow_summary}/part-*.parquet
    keywords/part-*.parquet
    serp_items/part-*.parquet
    pages/part-*.parquet
    passages/part-*.parquet
    entities/part-*.parquet
    backlinks/part-*.parquet
    textrazor_page_metrics_curated/part-*.parquet
    similarity_scores/part-*.parquet
    keyword_serp/part-*.parquet
    page_features/part-*.parquet
    passage_features/part-*.parquet
    domain_features/part-*.parquet
    textrazor_page_metrics/part-*.parquet
    analysis_mart/part-*.parquet
  stats/
    stats_summary.json       # confirmatory summaries + nested rank_depths
    stats_diagnostics.json   # pooled diagnostics, multivariate_sensitivity, influence_sensitivity
    stats_report.md          # human-readable report (four rank-depth sections)
```

### CLI reference

All subcommands. Prefer the [recommended workflows](#recommended-workflows) above
for day-to-day use.

#### `seo-rank run`

Fetch or fixture provider data, score pages, write `run.json`, `report.md`, and
`parquet/raw_responses/`. Progress logs go to **stderr**.

| Flag | Default | Purpose |
|------|---------|---------|
| `--seed` | *(required)* | Seed keyword for expansion |
| `--location` | `United States` | DataForSEO location (name or numeric code) |
| `--language` | `en` | Language code for expansion/SERP |
| `--device` | `desktop` | `desktop` or `mobile` SERP |
| `--depth` | `20` | Max organic SERP rows per keyword |
| `--keyword-limit` | `1` | Max cluster keywords after expansion |
| `--output-dir` | `runs/{run_id}` | Run root (content-addressed id when omitted) |
| `--model-name` | `fixture-similarity-v1` | Recorded in `run.json` |
| `--dry-run` | off | Mark run as fixture/offline in config |
| `--skip-textrazor` | off | Skip TextRazor entities (offline and live); on stored-run replay, this stays sticky and suppresses TextRazor even if the saved run had it enabled |
| `--stored-run` | — | Resume or expand the chain on an existing run tree in place |
| `--live-providers` | off | Live DataForSEO (requires env gate) |
| `--live-bge` | off | Live BGE reranking (requires `--live-providers`) |
| `--live-gemini` | off | Live Gemini embeddings (requires `--live-providers`) |
| `--live-textrazor` | off | Live TextRazor (requires `--live-providers`) |
| `--live-textrazor-only` | off | Live TextRazor without DataForSEO HTTP: brand-new runs use fixture expansion/SERP/page_text; with `--stored-run`, backfills entities from stored `page_text`. Requires `SEO_RANK_ENABLE_TEXTRAZOR=1`; mutually exclusive with `--live-providers` and `--skip-textrazor` |
| `--refresh-textrazor` | off | Replace existing `endpoint=entities` rows when backfilling TextRazor |

```bash
# Offline defaults (1 keyword, progress on stderr)
seo-rank run --seed "technical seo" --dry-run

# Full fixture cluster
seo-rank run --seed "technical seo" --dry-run --keyword-limit 25 --depth 3 --skip-textrazor

# Explicit output directory
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts

# Re-process stored lake and finish downstream layers (no network)
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID
```

#### Lake pipeline commands

Materialize downstream layers on an existing run directory:

```bash
seo-rank normalize --run runs/RUN_ID      # raw_responses → curated tables
seo-rank build-features --run runs/RUN_ID   # curated → feature marts
seo-rank analyze --run runs/RUN_ID            # feature marts → analysis_mart (+ stats)
seo-rank analyze --run runs/RUN_ID --keyword "technical seo"   # JSON rows for one keyword
```

`analyze` exit codes: `0` on success (or dry-run manifest with optional
`--keyword` emit); `1` when Phase 5 guardrails hard-fail on a non–dry-run run;
`2` on missing run data or unknown `--keyword`.

#### `seo-rank replay`

Re-parse one stored raw response body (audit / debugging):

```bash
seo-rank replay --run runs/RUN_ID --response-id RESPONSE_ID
```

Storage commands exit `2` on missing run data or unknown `--keyword` / `--response-id`
values (message on stderr, no traceback).

All transforms use `pl.scan_parquet()` and return `pl.LazyFrame` until a command
boundary calls `collect(engine="streaming")` or `sink_parquet(..., compression="zstd")`.
`raw_responses` is not joined in normal analysis; use `replay` to re-parse one
response.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/seo_rank/` | CLI, provider boundaries, `progress.py` (stderr run logging) |
| `src/seo_rank/data/` | Polars lake transforms: `scans`, `normalize`, `ranks`, `features`, `marts`, `validate` |
| `src/seo_rank/stats/` | Phase 5 observational analysis (`spec`, `families`, `panel`, `rank_depth`, `spearman`, `regression`, `plackett_luce`, `diagnostics`, `scale`, `textrazor_explainability`, `ranking_explainability_viz`, `artifacts`) |
| `tests/unit/` | pytest unit tests |
| `ARCHITECTURE.md` | Product architecture, data flow, planned pipeline |
| `GOALS.md` | Active-scope contract |
| `FIXUPS.md` | Slice-scoped small fixes backlog |
| `ROADMAP.md` | Backlog and history |
| `analysis/gemini_nwh_similarity.py` | Standalone Gemini/BGE/TextRazor block-scoring experiment |
| `analysis/textrazor_ranking_r2.py` | Standalone similarity + TextRazor adjusted R² ranking explainability script (writes `stats/ranking_r2.json` and PNG charts) |
| `TESTING.md` | Verification contract |

## Documentation

- Architecture and planned pipeline: `ARCHITECTURE.md`
- Active scope: `GOALS.md`
- Backlog: `ROADMAP.md`
- Testing: `TESTING.md`
- Process: `AGENTS.md`, `SDLC.md`

Verification: `python -m pytest`
