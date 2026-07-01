# Small fixes backlog

Tracked hardening and polish items surfaced during Phase 4.5 Slice 3 (lazy
curated normalization), Slice 6 (CLI surfaces), Slice 9 (mart sink contract),
Phase 4.76 Slice 1 (content_parsing request contract) review, Slice 2
(item field decoder) review, and senior QA release-readiness review for
Slices 3–5. Each item names
the **phase/slice** where it should land. Nothing here blocks Slice 10 sign-off
unless marked **required**.

**Status key:** `open` | `done`

---

## Phase 4.76 — Slice 1 (request contract — post-ship polish)

Follow-ups from Slice 1 review. None block Slices 2–5.

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-01 | Document breaking CLI removal of `--javascript-parsing` in `README.md` (release note / changelog line) so scripts that still pass the flag know argparse will reject it | 4.76 Slice 1 | nice-to-have | open |
| S476-02 | Add transport-capture assertion in a live-provider CLI test: mock or spy the outgoing `content_parsing/live` request body at the integration boundary (unit test `test_build_page_text_request_uses_content_parsing_endpoint` already asserts the builder; live-path tests only mock responses today) | 4.76 Slice 1 | nice-to-have | open |
| S476-03 | Consider order-insensitive body comparison in `test_build_page_text_request_uses_content_parsing_endpoint` (subset / dict equality) so parameter reordering in `build_page_text_request()` does not break the test; current key order matches source and is consistent with other builder tests in the same file | 4.76 Slice 1 | nice-to-have | open |

---

## Phase 4.76 — Slice 2 (item field decoder — post-ship polish)

Follow-ups from Slice 2 review (`decode_content_parsing_items()`). None block
Slices 3–5 unless a row is marked **required**.

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-04 | Unify aggregate text extraction: derive merged `pages.text` from `decode_content_parsing_items()` (or a shared helper) instead of maintaining parallel logic in `parsed_page_text()` / `_extract_page_content_text()` — prevents drift between live CLI, normalize, and per-field decode | 4.76 Slice 4 | nice-to-have | open |
| S476-05 | Decide per-field Parquet row shape for container nodes: `decode_content_parsing_items()` emits parent object/array rows with full `structured_value` JSON plus child rows — confirm Slice 3 schema keeps both or leaf-only rows to avoid ~2× storage and repeated `json.dumps` on subtrees | 4.76 Slice 3 | nice-to-have | open |
| S476-06 | Add a one-line pointer in `ROADMAP.md` that Phase 4.75 is complete and canonical detail lives in `GOALS.md` § Completed (replaces the removed Phase 4.75 block) | 4.76 docs | nice-to-have | open |
| S476-07 | Document in Slice 3 curated schema that scalar numbers and booleans land in `structured_value` with empty `text` (e.g. `status_code: 200` → `structured_value` `"200"`, not `text`) so downstream consumers read the right column | 4.76 Slice 3 | nice-to-have | open |

---

## Phase 4.76 — Slice 5 (tests and QA — senior review)

Follow-ups from senior QA release-readiness review (Phase 4.76 slices 3–5).
**Required** rows are TDD gates or sign-off blockers; write failing tests before
implementing sinks. Unit baseline: `pytest tests/unit` (88 tests, all pass as of
review).

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-08 | Write failing `test_normalize_run_materializes_page_content_fields` before Slice 3 sink: per-field rows with `field_path`, `ordinal`, and stable ids (`run_id`, `response_id`, `page_id`) | 4.76 Slice 5 | required | open |
| S476-09 | Write failing `test_normalize_run_stores_raw_html_when_present` before Slice 4 HTML wiring: HTML linked by `page_id` / `response_id` when crawl payload includes raw HTML | 4.76 Slice 5 | required | open |
| S476-10 | Write failing `test_build_pages_and_passages_frame_preserves_aggregate_text_with_field_decode`: merged `pages.text` matches Phase 4.75 aggregate path when decoder is wired | 4.76 Slice 5 | required | open |
| S476-11 | Write failing `test_normalize_run_skips_empty_crawl_with_field_decode`: URL-only or empty-body crawls still omitted from `pages` / `passages` after field-decode path | 4.76 Slice 5 | required | open |
| S476-12 | Add stored-run re-normalize smoke fixture (multi-field `items[]` + HTML) and assert curated lake row counts; extend `test_round_trip.py` or `test_run_normalize.py` | 4.76 Slice 5 | required | open |
| S476-13 | Gate or fix live integration smoke: `test_live_provider_smoke_writes_artifacts` fails with Gemini `404 Not Found` when `SEO_RANK_ENABLE_GEMINI=1` — validate API key/model/endpoint or skip when credentials are unhealthy | QA / integration | required | open |
| S476-14 | Document default Phase 4.76 sign-off gate as `pytest tests/unit`; full suite (`pytest`) requires `SEO_RANK_RUN_LIVE_INTEGRATION=1` plus healthy provider env | QA / docs | nice-to-have | open |
| S476-15 | Add Phase 4.76 manual sign-off checklist to `TESTING.md` or `docs/qa/`: live crawl contract, `normalize --run` per-field + HTML, re-normalize on pre-4.76 run, locale note (`--language` does not change page crawl pool) | 4.76 docs | nice-to-have | open |
| S476-16 | Rollback criterion for slices 3–4: if per-field or HTML wiring changes `pages` / `passages` row counts or breaks existing normalize fixtures, revert and re-run `test_run_normalize.py` + `test_round_trip.py` before merge | 4.76 Slice 5 | nice-to-have | open |

---

## Phase 4.75 — page_text normalization polish

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S475-01 | Skip empty `page_text` rows in `build_pages_and_passages_frame`: `continue` when `parsed_page_text()` yields no URL and no text (mirrors CLI `if page_text` filter); avoids empty `pages` rows and duplicate `page_id` warnings from crawl failures (e.g. `crawl_status: "Page content is empty"`) | 4.75 | nice-to-have | done |
| S475-02 | Add `secondary_content` and `table_content` fixtures to `test_parsed_page_text_extracts_nested_page_content` (or a sibling test) so Slice 2 regression coverage includes the section keys the pre-recursive extractor walked explicitly | 4.75 | nice-to-have | open |
| S475-03 | Add a second top-level `page_content` region fixture (e.g. `footer`) in `test_dataforseo_requests.py` / `test_run_normalize.py` when a live DataForSEO sample is available — confirms recursive extraction beyond `header` + `main_topic` | 4.75 | nice-to-have | open |
| S475-04 | Assert merged page-level `text` in `test_build_pages_and_passages_frame_parses_nested_page_content` (full `header` + `main_topic` string on the page row where `passage_id` is null), not only individual passage rows | 4.75 | nice-to-have | open |
| S475-05 | Re-normalize stored runs that were created before the empty-text guard tightened, so URL-only empty bodies disappear from existing curated `pages` / `passages` rows; automatic at normalize time, no CLI flag | 4.75 | nice-to-have | open |

---

## Phase 4.5 — Slice 3 (post-ship hardening)

Polish on the shipped lazy normalize path. Safe to batch after Slice 7 starts
if none of these block deps/docs/round-trip work.

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S3-01 | Return explicit Polars schemas from empty `build_*_frame` UDFs (`keywords`, `serp_items`, `pages_and_passages`, `entities`), matching each `map_batches(..., schema=...)` contract — same pattern as `build_similarity_scores_frame` | 4.5 Slice 3 | nice-to-have | open |
| S3-02 | Filter null `target_keyword` on serp / page_text / entities lazy branches (`.filter(pl.col("target_keyword").is_not_null())`) to restore pre-refactor skip behavior | 4.5 Slice 3 | nice-to-have | open |
| S3-03 | Document or relocate `load_raw_response_rows` so it is clearly replay/debug-only, not the normalize read path | 4.5 Slice 3 | nice-to-have | open |
| S3-04 | Strengthen lazy-path test: assert raw scan is not fully collected before transforms (e.g. guard `collect` on `scan_raw_responses`, not only `load_raw_response_rows`) | 4.5 Slice 3 | nice-to-have | open |
| S3-05 | Extend `test_build_similarity_scores_frame_handles_empty_group` to assert column names and dtypes match `CURATED_VALIDATION_RULES["similarity_scores"]["expected_schema"]`, not only `is_empty()` | 4.5 Slice 3 | nice-to-have | open |
| S3-06 | Deprecate or remove unused `build_curated_lazyframes` helper once no tests or callers need the list-in → lazy-out shim | 4.5 Slice 3 | nice-to-have | open |

---

## Phase 4.5 — Slice 6 (CLI surfaces — post-ship polish)

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S6-02 | Remove redundant `except CliCommandError` in `main()` — `CliCommandError` subclasses `ValueError`, already caught by `STORAGE_COMMAND_EXCEPTIONS` | 4.5 Slice 6 | nice-to-have | open |
| S6-03 | Simplify `replay_stored_run`: drop unused `config` parameter (or use config fields if replay should respect run settings later) | 4.5 Slice 6 | nice-to-have | open |
| S6-04 | Make `--seed` optional when `--stored-run` is set (replay ignores seed today but argparse still requires it) | 4.5 Slice 6 | nice-to-have | open |
| S6-05 | Emit stderr warning when both `--stored-run` and `--live-providers` are passed (`--stored-run` wins silently today) | 4.5 Slice 6 | nice-to-have | open |
| S6-06 | `replay`: error or warn when multiple rows match `--response-id` (currently uses `rows[0]` only) | 4.5 Slice 6 | nice-to-have | open |
| S6-07 | Test `run --stored-run` failure path (e.g. missing `run.json`) → exit code `2` without traceback | 4.5 Slice 6 | nice-to-have | open |
| S6-08 | Replace private `parser._actions` introspection in `test_cli_surfaces.py` with public argv round-trips only | 4.5 Slice 6 | nice-to-have | open |
| S6-09 | Optional: `replay` re-normalize path — derive curated rows from one `response_id` (beyond printing raw `response_body_bytes`) | 4.5 Slice 6 | planned | open |

---

## Phase 4.5 — Slice 7 (deps, docs, round-trip)

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S7-01 | Update `ARCHITECTURE.md` test count when the suite changes (was 53; now 66) | 4.5 Slice 7 | nice-to-have | done |
| S7-02 | Migrate curated table writes from PyArrow `write_table` to Polars `sink_parquet(..., compression="zstd")` for parity with feature/analysis marts | 4.5 Slice 8 | planned | done |
| S7-03 | Add dedicated round-trip test module: `run --dry-run` → `normalize_run` → `build_feature_marts` → `build_analysis_mart` in one test file (beyond `test_analysis_mart.py` chain) | 4.5 Slice 7 | planned | open |
| S7-04 | Declare `polars` in `pyproject.toml` | 4.5 Slice 7 | required | done |
| S7-05 | Optional empty-endpoint integration test (e.g. run missing `entities` partition) to exercise empty `map_batches` paths end-to-end | 4.5 Slice 7 | nice-to-have | open |

---

## Phase 4.5 — Slice 9 (mart sink — post-ship polish)

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S9-01 | Assert written feature/analysis Parquet files expose column statistics in file metadata (integration path in `test_build_feature_marts_materializes_lazy_joins_from_curated_tables`, not only mocked `sink_parquet` kwargs) | 4.5 Slice 9 | nice-to-have | open |
| S9-02 | Add empty-dataset test for `write_feature_dataset`: lazy empty frame sinks and catalog `row_count` is `0` via Parquet metadata | 4.5 Slice 9 | nice-to-have | open |
| S9-03 | Keep slice-specific doc regression sweeps in `test_sdlc_docs.py` (slice 7 round-trip wording, slice 9 mart sink counters) instead of pinning moving acceptance-item totals on older slice tests | 4.5 Slice 9 | nice-to-have | done |

---

## Phase 4.5 — Slice 3 (already done)

| ID | Fix | Phase | Status |
| --- | --- | --- | --- |
| S3-DONE-01 | Empty `build_similarity_scores_frame`: use `CURATED_VALIDATION_RULES` Polars schema instead of PyArrow `CURATED_SCHEMAS` | 4.5 Slice 3 | done |
| S3-DONE-02 | Lazy curated normalize: `scan_raw_responses` + `map_batches` / `map_groups` instead of `load_raw_response_rows` loop | 4.5 Slice 3 | done |
| S3-DONE-03 | Align `GOALS.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `README.md`, `TESTING.md` with lazy normalize + residual UDF risk | 4.5 Slice 3 | done |

---

## Phase 4.5 — Slice 6 (already done)

| ID | Fix | Phase | Status |
| --- | --- | --- | --- |
| S6-DONE-01 | Wire `seo-rank replay` to read one `response_id` from `raw_responses` via `scan_raw_responses` (successor to eager `load_raw_response_rows`) | 4.5 Slice 6 | done |
| S6-DONE-02 | Align Slice 6 docs: `README.md`, `ARCHITECTURE.md`, `GOALS.md`, `ROADMAP.md`, `TESTING.md` with shipped CLI surfaces | 4.5 Slice 6 | done |

---

## How to use this file

- Pick items by **Phase** column when planning slice work in `GOALS.md`.
- Mark **Status** `done` and move rows to the “already done” section when merged.
- Do not treat `nice-to-have` items as sign-off gates; `required` / `planned`
  items belong in slice acceptance or `GOALS.md` remaining work.
