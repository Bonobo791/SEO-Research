# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract; keep deferred and historical items here.

## Current Backlog

Active scope contract: `GOALS.md` (Phase 4.5).

### Phase 4.5 — Run-scoped Parquet lake (Polars)

Active contract: `GOALS.md` § Phase 4.5 objective, Polars data layer, storage
layout, and dev slices.

- **Run-scoped layout** under `runs/{run_id}/`: authoritative `raw_responses`
  (one row per DataForSEO HTTP response, partitioned by `endpoint` only), curated
  tables, feature marts, and `analysis_mart`.
- **`src/seo_rank/data/`** — `scans.py`, `normalize.py`, `features.py`,
  `marts.py`, `validate.py`; LazyFrames end-to-end (`pl.scan_parquet()` in,
  `pl.LazyFrame` between transforms, `sink_parquet` out).
- **Three processing layers** — curated (`normalize`) → feature marts
  (`keyword_serp`, `page_features`, `passage_features`, `domain_features`) →
  analysis mart (one row per `target_keyword × SERP URL`).
- **Join contract** — filter/select before joins; stable IDs only (`run_id`,
  `target_keyword_id`, `canonical_url_hash`, `response_id`, `passage_id`);
  `raw_responses` excluded from normal analytical joins.
- **Write contract** — `validate.py` before every sink; Zstandard compression,
  Parquet statistics, sorted retrieval keys; `collect(engine="streaming")` only at
  CLI/report boundaries.
- **CLI** — `normalize`, `build-features`, `analyze`, `replay`; `--stored-run`
  on `run` for stored-input replay.
- **`run.json` catalog** — schemas, row counts, source response IDs, file
  checksums; no duplicate raw payloads.
- **Schema policy** — raw body as `response_body_bytes` + extracted typed
  columns; `schema_version` on every output; no nested provider objects; no
  Parquet `Variant` type.
- File-based storage; no server database.

### Phase 5 — Statistical analysis

- OLS pre-analysis preparation (root `ARCHITECTURE.md`)
- `statsmodels` OLS baseline vs similarity-feature models
- Benjamini-Hochberg correction every run

### Phase 5.5 - Analysis Expansion

- Per keyword: top-20 SERP; passage and domain URL scoring vs target
  keyword; domain URL cap 1000; skip domains over 1000 URLs

### Phase 6 — Reporting

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
    keyword (up to 25) with that keyword as `target_keyword`.
  - Per-keyword SERP, page text, passages, fixture similarity, TextRazor entities.
  - `keyword_results[]` in `run.json` / `report.md` with per-keyword raw provider
    payloads; top-level rollup preserved.
  - Flattened aggregate rows annotated with `target_keyword`.
  - `.env.example` documents live-provider and integration env gates.
  - Tests: 25-keyword offline cluster + injected live cluster orchestration in
    `test_cli_run.py`.
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
- **Phase 4.5 scoped:** `GOALS.md` expanded with run-scoped Parquet architecture
  (`raw_responses`, curated tables, feature marts, `analysis_mart`), Polars
  LazyFrame data package (`src/seo_rank/data/`), CLI `normalize` / `build-features`
  / `analyze` / `replay`, and validation-before-sink contract. Backlog § Phase 4.5
  aligned to the same contract.
- **Phase 4.5 Slice 1 shipped:** `seo-rank run` now writes run-scoped
  `raw_responses` Parquet partitions plus `run.json` catalog metadata without
  duplicating raw payloads in JSON.
- **Phase 4.5 Slice 2 shipped:** stored `raw_responses` normalize into curated
  Parquet tables (`keywords`, `serp_items`, `pages`, `passages`, `entities`,
  `similarity_scores`) and refresh the run catalog from disk.
- **Phase 4.5 Slice 3 started:** `src/seo_rank/data/` gained lazy raw-response
  scan helpers and column validation helpers as the Polars data-layer
  foundation.
- **Phase 4.5 Slice 3 advanced:** stored-run curated normalization now builds
  LazyFrames before the write boundary and reads raw responses through the lazy
  scan helper.
