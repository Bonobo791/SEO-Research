# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 4.5 **run-scoped Parquet lake** storage for SEO ranking similarity
research outputs.

### Current capability

**Phase 4 shipped:** offline and gated live runs loop every capped cluster keyword,
group outputs under `keyword_results`, and annotate flattened rows with
`target_keyword`. Page-level **BGE**, **Gemini Doc Retrieval**, and **Gemini Semantic
Similarity** scores land in `run.json` and `report.md` for every organic SERP row.

- **Offline / default live:** deterministic fixture scorers in `similarity.py`.
- **`--live-gemini`:** real `gemini-embedding-2` embeddings via `google-genai`.
- **`--live-bge`:** real `BAAI/bge-reranker-v2-m3` cross-encoder via `FlagEmbedding`
  on CUDA (loaded once per live run).
- **`--live-textrazor`:** opt-in live entity extraction; default live runs skip it.
- **Provider gates:** `--live-providers` plus per-provider env flags; hard failures
  when flags or credentials are missing.

### Phase 4.5 objective

Persist provider and similarity outputs from completed runs as a **run-scoped
Parquet lake** under `runs/{run_id}/`, process it with **Polars LazyFrames
end-to-end** (`pl.scan_parquet()` for every dataset; functions accept and return
`pl.LazyFrame`), and add CLI commands that materialize curated tables, feature
marts, and analysis marts without re-fetching DataForSEO or TextRazor payloads.

File-based storage only (no server database). Raw HTTP payloads and generated run
trees stay out of source control.

#### Progress (2026-06-29)

**Slices:** 5 of 7 shipped, 2 open. Phase 4.5 is not signed off.

| Slice | Status | Notes |
| ----- | ------ | ----- |
| 1 Raw lake | Shipped | `seo-rank run` writes `parquet/raw_responses/` + `run.json` catalog via `--output-dir` |
| 2 Curated normalize | Shipped | `normalize_run()` → six curated tables; library + `test_run_normalize.py` |
| 3 Polars data package | Shipped | `scans`, `validate`, `features`, `marts`, and lazy `normalize` (`scan_raw_responses` → endpoint filters → `map_batches` / `map_groups`); per-table `collect(engine="streaming")` at curated sink only |
| 4 Feature marts | Shipped | `build_feature_marts()` with lazy joins; `test_feature_marts.py` |
| 5 Analysis mart | Shipped | `build_analysis_mart()` + `marts.build_analysis_lazyframe`; `test_analysis_mart.py` |
| 6 CLI surfaces | Shipped | `seo-rank normalize`, `build-features`, `analyze`, `replay`, and `run --stored-run` replay the stored run tree without refetching provider payloads |
| 7 Deps + docs + round-trip | Partial | `pyarrow` and `polars` declared; curated sinks still use PyArrow not Polars `sink_parquet`; chained round-trip in `test_analysis_mart.py` only |

**Library API (callable, with CLI surfaces):** `normalize_run`,
`build_feature_marts`, `build_analysis_mart` under `src/seo_rank/data/`.

**Remaining to close Phase 4.5:** dedicated round-trip test, curated
`sink_parquet` alignment, final doc alignment pass.

**Residual risk:** curated normalization stays lazy through the Polars plan, but
batch-level Python UDFs still parse JSON (`response_body_bytes`), split passages,
normalize entities, and compute per-keyword similarity groups. Each curated table
also collects once at the write boundary (PyArrow sink today).

**Next useful slice:** deps/docs/round-trip (Slice 7).

#### Polars data layer

```text
src/seo_rank/data/
  scans.py        # run-scoped scan functions (pl.scan_parquet per table)
  normalize.py    # raw_responses → typed curated tables
  features.py     # page, passage, domain, similarity feature marts
  marts.py        # analysis-ready joins (Phase 5 prep)
  validate.py     # schema/key/null/range checks before every write
```

#### Storage layout

```text
runs/{run_id}/
  run.json                         # manifest, schema versions, counts, checksums
  report.md                        # human-readable summary (existing reporter)
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

#### Three processing layers

1. **Curated** — parse stored `raw_responses` once into typed keyword, SERP, page,
   passage, entity, and score tables (`normalize.py`).
2. **Feature marts** — `keyword_serp`, `page_features`, `passage_features`,
   `domain_features` (`features.py`).
3. **Analysis mart** — one row per `target_keyword × SERP URL`, joined only when
   required for Phase 5 (`marts.py`).

#### Design rules

1. **`raw_responses` is authoritative** — one row per DataForSEO HTTP response:
   `response_id`, endpoint, task ID, timestamp, request metadata, exact
   `response_body_bytes`, content type, status, and SHA-256. Preserves every
   downloaded payload without relying on DataForSEO retention (Live results are
   not stored by DataForSEO; Standard and HTML retention is limited).
2. **Keep `raw_responses` out of normal analytical joins** — use it only for
   explicit replay/re-normalization (`seo-rank replay`).
3. **Curated tables are normalized for analysis** — every row carries `run_id`,
   `target_keyword_id`, `response_id`, stable IDs (`canonical_url_hash`,
   `passage_id`, etc.), and `schema_version`. Full page text lives in `pages`;
   passages, entities, and scores are separate tables.
4. **LazyFrames end-to-end** — `pl.scan_parquet()` at read boundaries; filter
   and select **before** joins; join by stable IDs only: `run_id`,
   `target_keyword_id`, `canonical_url_hash`, `response_id`, `passage_id`.
5. **Materialize reusable marts only** — `sink_parquet(..., compression="zstd")`
   with statistics enabled; use `collect(engine="streaming")` only at CLI/report
   boundaries or when a DataFrame is actually needed.
6. **Validate before every write** — `validate.py` refuses to sink invalid marts.
   Curated, feature, and analysis writes all run schema/key/null/range checks
   before sink.
7. **No nested provider schemas** — keep the raw body as bytes/JSON plus extracted
   typed columns. Do not use the Parquet `Variant` type (interoperability risk).
8. **Partition only `raw_responses` by low-cardinality `endpoint`** — do not
   partition by keyword, URL, task ID, or rank; the run directory already scopes
   by run.
9. **Sort curated and mart tables** by primary retrieval keys (e.g.
   `target_keyword_id`, `canonical_url_hash`, `serp_rank`) before sink.
10. **`run.json` is a lightweight catalog only** — no duplicate raw payloads;
    include table schemas, row counts, source response IDs, and file checksums.

#### CLI commands (Phase 4.5)

```text
seo-rank normalize --run RUN_ID
seo-rank build-features --run RUN_ID
seo-rank analyze --run RUN_ID --keyword "..."
seo-rank replay --run RUN_ID --response-id ...
```

`seo-rank run` continues to orchestrate provider calls and write `raw_responses`
first. Downstream commands scan lazily and sink only the marts they own.

### Dev slices

1. **[x] Slice 1 — Raw lake foundation** — persist completed runs under
   `runs/{run_id}/`, write authoritative `raw_responses` Parquet partitioned only
   by `endpoint`, and extend `run.json` into a lightweight catalog with schema
   version, row counts, source `response_id`s, and file checksums. Keep this slice
   limited to the write path for fetched provider HTTP responses plus offline tests
   that prove deterministic layout and metadata. *(Shipped: write path + catalog for
   `raw_responses`; CLI uses `--output-dir` rather than enforcing `runs/{run_id}/`
   path.)*
2. **[x] Slice 2 — Curated normalization from storage** — parse stored
   `raw_responses` into typed Parquet tables for `keywords`, `serp_items`,
   `pages`, `passages`, `entities`, and `similarity_scores`, preserving
   `run_id`, `target_keyword_id`, `response_id`, `schema_version`, and stable row
   IDs.
3. **[x] Slice 3 — Polars data package** — add `src/seo_rank/data/` with `scans`,
   `normalize`, `features`, `marts`, and `validate`; every transform accepts/returns
   `pl.LazyFrame`, every read boundary uses `pl.scan_parquet()`, and validation runs
   before each sink. *(Shipped: package layout complete; feature/analysis paths are
   lazy; curated normalization scans `raw_responses` lazily and builds typed tables
   via endpoint filters plus batch UDFs; per-table streaming collect at sink only;
   residual: JSON/similarity UDFs and PyArrow curated writes.)*
4. **[x] Slice 4 — Feature marts** — build and persist `keyword_serp`,
   `page_features`, `passage_features`, and `domain_features` from curated tables
   with stable-ID joins, filter/select before joins, Zstandard compression, and
   sorted retrieval keys.
5. **[x] Slice 5 — Analysis mart** — build `analysis_mart` lazily as one row per
   `target_keyword × SERP URL`, excluding `raw_responses` from analytical joins.
6. **[x] Slice 6 — CLI and stored-run surfaces** — `normalize`,
   `build-features`, `analyze`, and `replay` subcommands, plus explicit
   `seo-rank run --stored-run runs/{run_id}` reload behavior.
7. **[ ] Slice 7 — Dependencies, docs, and round-trip verification** — align
   `ARCHITECTURE.md`, `TESTING.md`, `ROADMAP.md`, `README.md`, and `.env.example`
   as needed, and prove the offline write → normalize → build-features → analyze
   round-trip plus single-response replay. *(Partial: `pyarrow` and `polars`
   declared; `test_analysis_mart.py` chains run → normalize → feature marts →
   analysis mart; `test_cli_surfaces.py` covers CLI dispatch; no dedicated
   round-trip test file.)*

See `ROADMAP.md` for Phase 5 (OLS) and Phase 5.5 (passage/domain scoring).

## In Scope (current and near-term)

- Python CLI under `src/seo_rank/`.
- Polars data package under `src/seo_rank/data/` (LazyFrame transforms).
- Pytest under `tests/unit/` and `tests/integration/`.
- Run-scoped Parquet lake (`raw_responses`, curated tables, feature marts,
  analysis mart) with lazy `pl.scan_parquet()` read path.
- CLI: `normalize`, `build-features`, `analyze`, `replay`, and `--stored-run`.

## Out Of Scope

- Passage-level similarity scoring (Phase 5.5).
- Domain-level URL inventory scoring (Phase 5.5).
- `statsmodels` OLS, OLS pre-analysis, Benjamini-Hochberg (Phase 5).
- Expanded report sections and observational-limit narrative (Phase 6).
- Entity-derived ranking features.
- Direct page fetching outside DataForSEO.
- Causal claims about ranking factors.
- CI, deployment, production hosting.
- Parquet `Variant` type for semi-structured provider payloads.

## Phase 4.5 acceptance criteria

**Status (2026-06-29):** 6 acceptance items complete, 5 partial, 0 not started
(CLI). Dev slices: 6 shipped, 1 open (Slice 7). Phase 4.5 is not signed off
until Slice 7 closes.

- [ ] `runs/{run_id}/` layout written for each completed run with `run.json`
  catalog (schemas, row counts, source response IDs, file checksums; no duplicate
  raw payloads). *(Partial: lake layout + catalog ship under `--output-dir`; canonical
  `runs/{run_id}/` path not enforced; full multi-layer catalog requires library
  calls after `run`.)*
- [x] `raw_responses` stores one row per DataForSEO HTTP response with
  `response_body_bytes`, metadata, status, and SHA-256; partitioned only by
  `endpoint`.
- [x] Curated Parquet tables (`keywords`, `serp_items`, `pages`, `passages`,
  `entities`, `similarity_scores`) with `run_id`, `target_keyword_id`,
  `response_id`, `schema_version`, and stable row IDs; page text in `pages` only.
- [x] Feature marts (`keyword_serp`, `page_features`, `passage_features`,
  `domain_features`) and `analysis_mart` (one row per `target_keyword × SERP URL`).
- [x] `src/seo_rank/data/` implements `scans`, `normalize`, `features`, `marts`,
  and `validate`; every transform accepts/returns `pl.LazyFrame`. *(Shipped: all
  five modules exist; transforms build lazy plans from `pl.scan_parquet()`; curated
  normalization uses batch UDFs for JSON parse and similarity grouping; collect
  only at per-table sink.)*
- [ ] Parquet sinks use Zstandard compression and statistics; tables sorted by
  primary retrieval keys; `collect(engine="streaming")` only at CLI/report edges.
  *(Partial: Zstd + sorted keys on curated and mart writes; feature marts use
  streaming collect; curated writes use PyArrow not Polars `sink_parquet`;
  statistics not explicitly enabled.)*
- [x] `validate.py` runs schema/key/null/range checks before every mart write.
  *(Shipped for curated, feature, and analysis writes.)*
- [x] `raw_responses` excluded from normal analytical joins; `replay` path only.
  *(Shipped: analytical joins use curated/feature scans only; `replay` reads the
  stored raw lake.)*
- [x] CLI: `normalize`, `build-features`, `analyze`, `replay`; `--stored-run`
  reloads stored data when explicitly requested.
- [ ] Offline unit tests cover write → normalize → build-features → analyze
  round-trip without network calls. *(Partial: `test_analysis_mart.py` chains the
  full pipeline after `seo-rank run --dry-run`; per-layer tests in `test_cli_run`,
  `test_run_normalize`, and `test_feature_marts`; no dedicated round-trip test
  module.)*
- [ ] `polars` + `pyarrow` declared in `pyproject.toml`; docs updated. *(Partial:
  both declared; Slice 6 CLI docs updated in `README.md` and `ARCHITECTURE.md`;
  Slice 7 round-trip test module remains.)*

## Phase 4 acceptance criteria (complete)

- [x] Page-level fixture scores for **BGE**, **Gemini Doc Retrieval**, and
  **Gemini Semantic Similarity** exposed per SERP row in artifacts.
- [x] Scores land in `keyword_results` with `target_keyword` preserved.
- [x] Offline fixture tests cover `bge`, `gemini_doc_retrieval`, and
  `gemini_semantic_similarity` at page scope.
- [x] Optional live provider flags (`--live-gemini`, `--live-bge`,
  `--live-textrazor`) with env gates and hard failures when misconfigured.
- [x] Live TextRazor is opt-in only; default live runs skip entity extraction.
- [x] Documentation and `.env.example` aligned with `ARCHITECTURE.md`,
  `TESTING.md`, `ROADMAP.md`.
- [x] Live **Gemini Doc Retrieval** and **Gemini Semantic Similarity** via
  Gen AI SDK (`gemini-embedding-2`) when `--live-gemini` is enabled.
- [x] Live **BGE** cross-encoder via FlagEmbedding (`BAAI/bge-reranker-v2-m3`)
  with documented score calibration notes.
- [x] `pyproject.toml` `similarity` optional extra for `google-genai` and
  `FlagEmbedding`.
- [x] Opt-in integration smoke coverage for live Gemini and BGE flags.

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
