# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract; keep deferred and historical items here.

## Current Backlog

Active scope contract: `GOALS.md` (Phase 4.75).

### Phase 4.75 — page_text curation hardening

Active contract: `GOALS.md` § Phase 4.75 objective and dev slices. Related
polish: `FIXUPS.md` § Phase 4.75.

- **Shared decoder** — `parsed_page_text()` is the single extractor for live and
  stored `page_text` payloads; normalization must not re-index raw JSON ad hoc.
- **Multi-region text** — merge `header` and other `page_content` keys into page
  `text`, not only `main_topic` sections.
- **Empty crawl filter** — skip responses with no URL and no text before writing
  `pages` / `passages` (align with CLI `if page_text`).
- **Tests** — `test_dataforseo_requests.py`, `test_run_normalize.py`; re-normalize
  smoke on stored live runs.

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
- **GOALS retargeted to Phase 4.75 (2026-06-29):** page_text curation hardening
  after stored-run normalize failed on live nested `page_content` payloads.
- **Phase 4.75 Slice 1 shipped:** `parsed_page_text()` decodes nested DataForSEO
  `content_parsing` items; `build_pages_and_passages_frame()` uses the shared
  parser instead of flat `tasks[0].result[0]` indexing.
