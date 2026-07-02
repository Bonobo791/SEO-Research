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

### What `seo-rank run` executes

On every `run` (offline or live), per expanded cluster keyword:

1. SERP normalization (top *N* organic rows, default 20)
2. Page text from fixtures or DataForSEO `content_parsing/live`
3. Passage splitting
4. **Passage-level similarity features** — max/mean cosine per URL from deterministic
   fixture embeddings (`compute_page_similarity_features`)
5. **Page-level similarity scores** — three backends per URL (`compute_page_similarity_scores`
   or live overrides below)
6. TextRazor entities (fixture unless `--live-providers --live-textrazor`)
7. Artifacts: `run.json`, `report.md`, and `parquet/raw_responses/`

A plain `run` does **not** call `normalize`, `build-features`, or `analyze`. Use
`--stored-run runs/RUN_ID` to re-materialize curated tables and marts from an
existing run tree without provider calls.

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
columns and page text length). If feature marts are missing, it materializes
them first from the curated tables. It does **not** re-fetch pages or re-run
embeddings. The current stats path runs guardrails, Spearman summaries, and
pooled regression summaries into `runs/{run_id}/stats/`, including
`stats_summary.json`, `stats_diagnostics.json`, and `stats_report.md`; later
slices expand CLI reporting.

### Standalone script

`analysis/gemini_nwh_similarity.py` is a one-off experiment for a fixed keyword
and hand-picked text blocks. It can call live Gemini and BGE when configured; it
is not part of the default CLI `run` flow.

```bash
python -m pytest
seo-rank run --seed "technical seo" --dry-run
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts
```

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

### Storage layout 

`seo-rank run` writes this layout under `runs/{run_id}/` when `--output-dir` is
omitted. CLI subcommands materialize layers in place on an existing run tree.

```text
runs/{run_id}/
  run.json
  report.md
  parquet/
    raw_responses/endpoint={keyword_expansion|serp|page_text}/part-*.parquet
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

### CLI 

```bash
seo-rank normalize --run RUN_ID
seo-rank build-features --run RUN_ID
seo-rank analyze --run RUN_ID --keyword "technical seo"
seo-rank replay --run RUN_ID --response-id RESPONSE_ID
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID   # re-materialize marts
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
| `src/seo_rank/` | CLI and provider boundaries |
| `src/seo_rank/data/` | Polars lake transforms: `scans`, `normalize`, `features`, `marts`, `validate` |
| `tests/unit/` | pytest unit tests |
| `ARCHITECTURE.md` | Product architecture, data flow, planned pipeline |
| `GOALS.md` | Active-scope contract |
| `FIXUPS.md` | Slice-scoped small fixes backlog |
| `ROADMAP.md` | Backlog and history |
| `analysis/gemini_nwh_similarity.py` | Standalone Gemini/BGE block-scoring experiment |
| `TESTING.md` | Verification contract |

## Documentation

- Architecture and planned pipeline: `ARCHITECTURE.md`
- Active scope: `GOALS.md`
- Backlog: `ROADMAP.md`
- Testing: `TESTING.md`
- Process: `AGENTS.md`, `SDLC.md`

Verification: `python -m pytest`
