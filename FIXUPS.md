# Small fixes backlog

Tracked hardening and polish items surfaced during Phase 4.5 Slice 3 (lazy
curated normalization) and Slice 6 (CLI surfaces) review. Each item names the
**phase/slice** where it should land. Nothing here blocks Slice 7 sign-off
unless marked **required**.

**Status key:** `open` | `done`

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
| S7-02 | Migrate curated table writes from PyArrow `write_table` to Polars `sink_parquet(..., compression="zstd")` for parity with feature/analysis marts | 4.5 Slice 7 | planned | open |
| S7-03 | Add dedicated round-trip test module: `run --dry-run` → `normalize_run` → `build_feature_marts` → `build_analysis_mart` in one test file (beyond `test_analysis_mart.py` chain) | 4.5 Slice 7 | planned | open |
| S7-04 | Declare `polars` in `pyproject.toml` | 4.5 Slice 7 | required | done |
| S7-05 | Optional empty-endpoint integration test (e.g. run missing `entities` partition) to exercise empty `map_batches` paths end-to-end | 4.5 Slice 7 | nice-to-have | open |

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
