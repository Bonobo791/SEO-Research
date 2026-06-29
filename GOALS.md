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

**Slices:** 8 of 10 shipped, 2 open. Phase 4.5 is not signed off pending mart
sink and validation-edge hardening (slices 9–10).

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Raw lake foundation | Write | Shipped | Default `runs/{run_id}/` layout; authoritative `raw_responses` partitioned by `endpoint`; lightweight `run.json` catalog |
| 2 | Curated normalization | Curated | Shipped | `normalize_run()` → six typed Parquet tables with stable IDs and `schema_version` |
| 3 | Polars data package | Infra | Shipped | `src/seo_rank/data/` (`scans`, `validate`, `features`, `marts`, lazy `normalize`); LazyFrame in/out at transform boundaries |
| 4 | Feature marts | Feature | Shipped | `keyword_serp`, `page_features`, `passage_features`, `domain_features` via stable-ID lazy joins |
| 5 | Analysis mart | Analysis | Shipped | One row per `target_keyword × SERP URL`; `raw_responses` excluded from joins |
| 6 | CLI and stored-run surfaces | CLI | Shipped | `normalize`, `build-features`, `analyze`, `replay`; `run --stored-run` reload path |
| 7 | Dependencies, docs, round-trip | Verify | Shipped | `pyarrow` + `polars` declared; docs aligned; `test_round_trip.py` CLI sweep |
| 8 | Curated sink contract | Write | Shipped | Curated tables sink via Polars `sink_parquet(..., compression="zstd", statistics=True)` with sorted retrieval keys |
| 9 | Mart sink contract | Write | Open | Feature marts and `analysis_mart` use lazy `sink_parquet` with statistics; drop eager `collect` + `write_parquet` in `write_feature_dataset` |
| 10 | Validation lazy edge | Infra | Open | Row-level checks in `validate.py` without mid-plan `collect()`; validation stays lazy until sink boundary |

**Library API (callable, with CLI surfaces):** `normalize_run`,
`build_feature_marts`, `build_analysis_mart` under `src/seo_rank/data/`.

**Remaining to close Phase 4.5:** slices 9–10 (mart sink contract + validation
lazy edge).

**Residual risk:** curated normalization stays lazy through the Polars plan, but
batch-level Python UDFs still parse JSON (`response_body_bytes`), split passages,
normalize entities, and compute per-keyword similarity groups. Feature and
analysis marts still `collect(engine="streaming")` before `write_parquet`
(slice 9). Validation still collects selected columns before row-level checks
(slice 10).

**Post-sign-off polish:** optional hardening tracked in `FIXUPS.md` (empty-endpoint
paths, CLI replay polish, normalize UDF schema guards). Not sign-off gates.

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

Delivery slices (1–7) shipped the end-to-end lake. Hardening slices (8–10) close
the write contract. Each slice is one reviewable unit with its own tests.

#### Delivery (shipped)

1. **[x] Slice 1 — Raw lake foundation**
   - Default output: `runs/{run_id}/` when `--output-dir` is omitted; explicit
     override still supported.
   - Authoritative `raw_responses`: one row per HTTP response, `endpoint` partition
     only, `response_body_bytes` + SHA-256 + metadata.
   - `run.json` catalog: schema version, row counts, source `response_id`s, file
     checksums (no duplicate raw payloads).
   - Tests: deterministic layout and catalog metadata on the provider write path.

2. **[x] Slice 2 — Curated normalization from storage**
   - Parse stored `raw_responses` into six typed tables: `keywords`, `serp_items`,
     `pages`, `passages`, `entities`, `similarity_scores`.
   - Every row carries `run_id`, `target_keyword_id`, `response_id`,
     `schema_version`, and stable row IDs; full page text lives in `pages` only.
   - Tests: `test_run_normalize.py`.

3. **[x] Slice 3 — Polars data package**
   - Package layout: `scans`, `normalize`, `features`, `marts`, `validate` under
     `src/seo_rank/data/`.
   - Read boundary: `pl.scan_parquet()`; transform boundary: `pl.LazyFrame` in/out.
   - Curated path: lazy `scan_raw_responses` → endpoint filters → `map_batches` /
     `map_groups` UDFs (JSON parse, passage split, entity normalize, similarity
     grouping).
   - Validation hook before every sink (schema/key/null/range contract).
   - Residual: batch UDFs are Python-side; not a streaming-native transform.

4. **[x] Slice 4 — Feature marts**
   - Build and persist `keyword_serp`, `page_features`, `passage_features`,
     `domain_features` from curated scans.
   - Filter/select before joins; stable-ID join keys only; sorted retrieval keys.
   - Tests: `test_feature_marts.py`.

5. **[x] Slice 5 — Analysis mart**
   - `build_analysis_lazyframe` + `build_analysis_mart`: one row per
     `target_keyword × SERP URL`.
   - Analytical joins use curated/feature scans only; `raw_responses` excluded.
   - Tests: `test_analysis_mart.py`.

6. **[x] Slice 6 — CLI and stored-run surfaces**
   - Subcommands: `normalize`, `build-features`, `analyze`, `replay`.
   - `seo-rank run --stored-run runs/{run_id}` reloads stored input without
     refetching provider payloads.
   - Tests: `test_cli_surfaces.py`.

7. **[x] Slice 7 — Dependencies, docs, and round-trip verification**
   - Declare `pyarrow` and `polars` in `pyproject.toml`.
   - Align `ARCHITECTURE.md`, `TESTING.md`, `ROADMAP.md`, `README.md`, and
     `.env.example`.
   - Round-trip regression: `test_round_trip.py` (CLI write → normalize →
     build-features → analyze); `test_analysis_mart.py` library chain;
     `test_sdlc_docs.py` guards slice-state wording.
   - Slice 7 shipped.

#### Hardening (open)

8. **[x] Slice 8 — Curated sink contract**
   - Curated tables sink via Polars `sink_parquet(..., compression="zstd",
     statistics=True)` with rows sorted by primary retrieval keys before write.
   - Replaces direct PyArrow `write_table` on the curated path (`FIXUPS.md`
     S7-02).

9. **[ ] Slice 9 — Mart sink contract**
   - `write_feature_dataset` (feature marts + `analysis_mart`) uses lazy
     `sink_parquet(..., compression="zstd", statistics=True)` instead of
     `collect(engine="streaming")` + `DataFrame.write_parquet`.
   - Preserve sorted retrieval keys and post-sink catalog row counts.
   - Tests: assert Parquet file metadata / statistics where feasible; extend
     round-trip sweep if needed.

10. **[ ] Slice 10 — Validation lazy edge**
    - Refactor `validate_frame_contract` so uniqueness, null, and range checks do
      not call mid-plan `collect()` on selected columns.
    - Acceptable outcomes: lazy-native checks, minimal streaming collect only at
      the documented sink edge, or row-count-free schema-only validation before
      sink with post-sink audit for row rules.
    - Tests: guard against new non-edge `collect()` calls in `validate.py`.

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

**Status (2026-06-29):** 7 acceptance items complete, 4 partial, 0 not started.
Dev slices: 8 shipped, 2 open (slices 9–10). Phase 4.5 is not signed off pending
mart sink and validation-edge hardening.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `runs/{run_id}/` default layout + `run.json` catalog | 1 | Complete |
| `raw_responses` authoritative store | 1 | Complete |
| Six curated Parquet tables with stable IDs | 2, 8 | Complete |
| Feature marts + `analysis_mart` | 4, 5 | Complete |
| `src/seo_rank/data/` LazyFrame transforms | 3 | Complete |
| Parquet sinks: zstd, statistics, sorted keys; collect only at edges | 8, 9, 10 | Partial |
| `validate.py` before every mart write | 3, 10 | Partial |
| `raw_responses` excluded from analytical joins | 5, 6 | Complete |
| CLI storage commands + `--stored-run` | 6 | Complete |
| Offline round-trip tests (no network) | 7 | Complete |
| `polars` + `pyarrow` declared; docs updated | 7 | Complete |

- [x] `runs/{run_id}/` layout written for each completed run by default when
  `--output-dir` is omitted, with `run.json` catalog (schemas, row counts, source
  response IDs, file checksums; no duplicate raw payloads). Explicit
  `--output-dir` overrides remain supported. *(Slice 1; partial only for the full
  multi-layer catalog, which still requires library calls after `run`.)*
- [x] `raw_responses` stores one row per DataForSEO HTTP response with
  `response_body_bytes`, metadata, status, and SHA-256; partitioned only by
  `endpoint`. *(Slice 1.)*
- [x] Curated Parquet tables (`keywords`, `serp_items`, `pages`, `passages`,
  `entities`, `similarity_scores`) with `run_id`, `target_keyword_id`,
  `response_id`, `schema_version`, and stable row IDs; page text in `pages` only.
  *(Slices 2, 8.)*
- [x] Feature marts (`keyword_serp`, `page_features`, `passage_features`,
  `domain_features`) and `analysis_mart` (one row per `target_keyword × SERP URL`).
  *(Slices 4, 5.)*
- [x] `src/seo_rank/data/` implements `scans`, `normalize`, `features`, `marts`,
  and `validate`; every transform accepts/returns `pl.LazyFrame`. *(Slice 3;
  curated normalization uses batch UDFs for JSON parse and similarity grouping.)*
- [ ] Parquet sinks use Zstandard compression and statistics; tables sorted by
  primary retrieval keys; `collect(engine="streaming")` only at CLI/report edges.
  *(Partial: slice 8 shipped for curated tables; slice 9 open for feature/analysis
  marts; slice 10 open for validation `collect()`.)*
- [x] `validate.py` runs schema/key/null/range checks before every mart write.
  *(Slice 3 shipped the hook; slice 10 open for lazy-edge row checks.)*
- [x] `raw_responses` excluded from normal analytical joins; `replay` path only.
  *(Slices 5, 6.)*
- [x] CLI: `normalize`, `build-features`, `analyze`, `replay`; `--stored-run`
  reloads stored data when explicitly requested. *(Slice 6.)*
- [x] Offline unit tests cover write → normalize → build-features → analyze
  round-trip without network calls. *(Slice 7: `test_round_trip.py`,
  `test_analysis_mart.py`, per-layer tests in `test_cli_run`, `test_run_normalize`,
  `test_feature_marts`.)*
- [x] `polars` + `pyarrow` declared in `pyproject.toml`; docs updated. *(Slice 7.)*

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
