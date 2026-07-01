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
  HTML. Aligning page-crawl locale with SERP locale is not supported in Phase
  4.76.

## Product direction

**Phase 4 shipped.** Full cluster orchestration plus three page-level measurements
on each top-20 organic SERP row:

| Name | JSON key | Live flag |
|------|----------|-----------|
| BGE | `bge` | `--live-bge` |
| Gemini Doc Retrieval | `gemini_doc_retrieval` | `--live-gemini` |
| Gemini Semantic Similarity | `gemini_semantic_similarity` | `--live-gemini` |

Offline and default live runs use deterministic fixtures. Opt-in flags swap in
real backends when env gates and credentials are set.

**Phase 4.5 (shipped):** run-scoped Parquet lake (`runs/{run_id}/` by default
when `--output-dir` is omitted, or an explicit override path when supplied) with
authoritative `raw_responses`, curated tables, feature marts, and `analysis_mart`
plus a Polars LazyFrame library in `src/seo_rank/data/` (`normalize_run`,
`build_feature_marts`, `build_analysis_mart`). CLI commands `normalize`,
`build-features`, `analyze`, and `replay` are wired; `run --stored-run` re-materializes
marts from a stored run tree without provider calls.
**Slice 7 shipped:** docs alignment and the round-trip regression sweep are in
place. **Next:** curated sink parity/statistics hardening in the Phase 4.5 write
path. Later: passage/domain scopes (Phase 5.5), `statsmodels` OLS with
Benjamini-Hochberg (Phase 5), and expanded report sections (Phase 6).

Details: `GOALS.md` and `ARCHITECTURE.md` (see **Run-scoped Parquet lake** and
**Polars data layer**).

### Storage layout (Phase 4.5)

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

### CLI (Phase 4.5)

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
| `src/seo_rank/data/` | Polars lake transforms (Phase 4.5): `scans`, `normalize`, `features`, `marts`, `validate` |
| `tests/unit/` | pytest unit tests |
| `ARCHITECTURE.md` | Product architecture, data flow, planned pipeline |
| `GOALS.md` | Active-scope contract |
| `FIXUPS.md` | Slice-scoped small fixes backlog (phase-tagged hardening) |
| `ROADMAP.md` | Phased backlog and history |
| `TESTING.md` | Verification contract |

## Documentation

- Architecture and planned pipeline: `ARCHITECTURE.md`
- Active scope: `GOALS.md`
- Backlog: `ROADMAP.md`
- Testing: `TESTING.md`
- Process: `AGENTS.md`, `SDLC.md`

Verification: `python -m pytest`
