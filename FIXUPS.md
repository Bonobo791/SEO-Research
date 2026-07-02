# Small fixes backlog

Tracked hardening and polish items surfaced during Phase 4.5 Slice 3 (lazy
curated normalization), Slice 6 (CLI surfaces), Slice 9 (mart sink contract),
Phase 4.76 Slice 1 (content_parsing request contract) review, Slice 2
(item field decoder) review, Slice 3 (per-field storage) code review,
Slice 4 (aggregate + HTML wiring) code review, senior QA release-readiness
review for Slices 3–5, the Jul 2026 senior QA pass
(default sign-off gate, hook/manifest alignment, live-smoke health), the Jul 2026
release-readiness verdict, the Jul 2026 senior QA follow-up (Slice 5
in-progress diff, fields-vs-pages policy, default gate), and the Jul 2026
senior QA diff review (orphan invariant, policy matrix docs, baseline sync),
and the Jul 2026 code review of the Slice 5 test diff (code / tests only —
doc follow-ups stay in S476-38, S476-47, S476-14, etc.), the Jul 2026
second senior QA diff review (code / tests only), and Phase 4.77 Slice 1
(DataForSEO schema contracts in `dataforseo.py`), and the Jul 2026 Phase 5
Slices 3–4 code review (guardrails, Spearman/BH, `analyze` wiring). Each item names
the **phase/slice** where it should land. Nothing here blocks Slice 10 sign-off
unless marked **required**.

**Status key:** `open` | `done` | `blocked` | `cancelled`

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

## Phase 4.76 — Slice 3 (per-field storage — post-ship polish)

Follow-ups from Slice 3 code review (`page_content_fields` curated sink).
None block Slice 4 HTML wiring unless marked **required**.

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-17 | ~~Align `build_page_content_fields_frame` skip logic with `build_pages_and_passages_frame`~~ — **superseded:** `page_content_fields` may exist without a matching `pages` row when URL + structured payload exist but aggregate text and `raw_html` are both empty (parity with S476-31 for `page_html`). Downstream joins use `page_id` from `page_content_fields` / `page_html` directly; do not assume every field row has a `pages` row. Frame coverage: `test_build_page_content_fields_frame_keeps_structured_fields_without_aggregate_text`, `…_without_page_text`. `normalize_run` orphan invariant: S476-46 (not `test_normalize_run_materializes_structured_fields_and_html_from_stored_run`, which includes `raw_html`) | 4.76 Slice 5 | required | done |
| S476-18 | Remove redundant `page_content_field_rows = page_content_fields` alias in `build_curated_lazyframes_from_raw_responses` return dict | 4.76 Slice 3 | nice-to-have | open |
| S476-19 | Consider a single `page_text` `map_batches` UDF that emits both page/passage rows and field rows to avoid double `json.loads` + `parsed_page_text` / `decode_content_parsing_items` per response | 4.76 Slice 3 | nice-to-have | open |
| S476-20 | Assert `field_row_id` uniqueness and stability (`stable_id(page_id, response_id, field_path, ordinal)`) in `test_build_page_content_fields_frame_decodes_structured_fields` and `test_normalize_run_materializes_page_content_fields` | 4.76 Slice 5 | nice-to-have | open |
| S476-21 | Assert scalar sink contract in normalize tests: e.g. `status_code` row has `structured_value == "200"` and empty `text` (decoder covered in `test_dataforseo_requests.py`; sink path in `test_normalize_run_stores_raw_html_when_present`) | 4.76 Slice 5 | nice-to-have | done |
| S476-22 | Keep `FIXUPS.md` unit baseline count in sync when the suite changes (was 88 at senior QA review; 91 after Slice 3 ship; 92 after Slice 4 HTML frame tests; 95 after Jul 2026 Slice 5 test additions; 96 after raw-HTML page shell test; **125** after Phase 4.77 Slice 3 drift tests — sync `TESTING.md` / `ARCHITECTURE.md` when the count moves again) | 4.76 docs | nice-to-have | done |

---

## Phase 4.76 — Slice 4 (aggregate + HTML wiring — post-ship polish)

Follow-ups from Slice 4 code review (`page_html` curated sink, `_extract_raw_html`,
`build_page_html_frame`). Slice 4 behavior is shipped; none of these block Slice 5
sign-off unless marked **required**.

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-34 | Fix `GOALS.md` progress line: change *"Remaining to close Phase 4.76: slices 4–5"* to **slice 5 only** now that Slice 4 is marked shipped | 4.76 docs | nice-to-have | open |
| S476-35 | Replace `_extract_raw_html()` whole-tree first-match with item-aligned extraction: read `items[].raw_html` from the same first item / URL path as `parsed_page_text()` so URL and HTML cannot diverge on multi-item payloads; drop broad `html` / `page_html` key aliases unless a fixture proves DataForSEO emits them | 4.76 Slice 4 | nice-to-have | open |
| S476-36 | Document intentional duplicate storage: `decode_content_parsing_items()` already emits a `raw_html` row in `page_content_fields`; sibling `page_html` is a query-optimized full-HTML table — add a one-line comment in `build_page_html_frame()` and/or `ARCHITECTURE.md` so downstream consumers know which table to read | 4.76 Slice 4 | nice-to-have | open |
| S476-37 | Document or align `page_html` `unique_columns` (`page_id`, `response_id`) vs `pages` (`page_id` only): state when multiple `page_html` rows per `page_id` are valid (e.g. distinct `response_id` replays) or narrow uniqueness to `page_id` if one row per URL per run is invariant | 4.76 Slice 4 | nice-to-have | open |
| S476-38 | Close out S476-31 / S476-17 resolution in docs/tests: publish the crawl sink policy matrix in `ARCHITECTURE.md` (one-line pointer in `GOALS.md`): `page_content_fields` → URL only; `page_html` → URL + `raw_html`; `pages` → URL + (aggregate text **or** `raw_html`); `passages` → aggregate text only. Document that `page_content_fields` / `page_html` may exist without a matching `pages` row when URL + structured payload exist but aggregate text and `raw_html` are both empty. **Partial:** frame tests cover fields/HTML without text; `test_build_pages_and_passages_frame_keeps_page_rows_for_raw_html_without_text` covers raw-HTML page shells; orphan `normalize_run` test still missing (S476-46); policy table not yet in `ARCHITECTURE.md` | 4.76 Slice 5 | required | open |
| S476-39 | Fold triple `json.loads` per `page_text` response (`pages_and_passages`, `page_content_fields`, `page_html`) into one `map_batches` UDF (extends S476-19) to cut CPU on large runs | 4.76 Slice 4 | nice-to-have | open |
| S476-40 | Import order in `normalize.py`: keep stdlib imports grouped (`collections.abc`, `pathlib`, `typing`) per project style | 4.76 Slice 4 | nice-to-have | open |

---

## Phase 4.76 — Slice 5 (tests and QA — senior review)

Follow-ups from senior QA release-readiness review (Phase 4.76 slices 3–5).
**Required** rows are TDD gates or sign-off blockers; write failing tests before
implementing sinks. Unit baseline: `pytest tests/unit` (**125** tests, all pass as of
Phase 4.77 Slice 3 diff; bare `pytest` may run integration when live gates are on).

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-08 | Write failing `test_normalize_run_materializes_page_content_fields` before Slice 3 sink: per-field rows with `field_path`, `ordinal`, and stable ids (`run_id`, `response_id`, `page_id`) | 4.76 Slice 5 | required | done |
| S476-09 | Write failing `test_normalize_run_stores_raw_html_when_present` before Slice 4 HTML wiring: HTML linked by `page_id` / `response_id` when crawl payload includes raw HTML | 4.76 Slice 5 | required | done |
| S476-10 | Write failing `test_build_pages_and_passages_frame_preserves_aggregate_text_with_field_decode`: merged `pages.text` matches Phase 4.75 aggregate path when decoder is wired | 4.76 Slice 5 | required | done |
| S476-11 | ~~Write failing `test_normalize_run_skips_empty_crawl_with_field_decode`~~ — **superseded by S476-17:** structured-only crawls intentionally emit `page_content_fields` (and `page_html` when present) while omitting `pages` / `passages` when aggregate text is empty. True no-URL crawls are already skipped by all three sinks | 4.76 Slice 5 | required | done |
| S476-12 | Add stored-run re-normalize smoke fixture (multi-field `items[]` + HTML) and assert curated lake row counts; extend `test_round_trip.py` or `test_run_normalize.py`. **Partial:** `test_normalize_run_materializes_structured_fields_and_html_from_stored_run` + `test_cli_round_trip_materializes_structured_only_page_text_payload` cover normalize and CLI `normalize` paths; close when S476-46 + S476-51 + S476-56 land | 4.76 Slice 5 | required | open |
| S476-13 | Gate or fix live integration smoke: `test_live_provider_smoke_writes_artifacts` fails with Gemini `404 Not Found` when `SEO_RANK_ENABLE_GEMINI=1` (reproduced Jul 2026: bare `pytest` → unit pass + 1 integration fail) — validate API key/model/endpoint or skip when embed health check fails | QA / integration | required | open |
| S476-14 | Document default Phase 4.76 sign-off gate as `pytest tests/unit`; full suite (`pytest`) runs integration when `SEO_RANK_RUN_LIVE_INTEGRATION=1` in `.env` and needs healthy provider credentials | QA / docs | required | open |
| S476-15 | Add Phase 4.76 manual sign-off checklist to `TESTING.md` only (no separate QA doc): live crawl contract, `normalize --run` per-field + HTML, re-normalize on pre-4.76 run, locale note (`--language` does not change page crawl pool), rollback criterion (S476-16) | 4.76 docs | nice-to-have | open |
| S476-16 | Rollback criterion for slices 3–4: if per-field or HTML wiring changes `pages` / `passages` row counts or breaks existing normalize fixtures, revert and re-run `test_run_normalize.py` + `test_round_trip.py` before merge | 4.76 Slice 5 | nice-to-have | open |

---

## Senior QA — release infrastructure (Jul 2026)

Follow-ups from the Jul 2026 senior QA pass. Priority order: S476-14 + S476-23
(default gate), then S476-13 (live smoke health), then Slice 5 TDD rows
(S476-09–S476-12).

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-23 | Pin `.codex-sdlc/manifest.json` `test_command` (and git-hook proof) to `pytest tests/unit` or `pytest -m "not integration"` so SDLC hooks do not invoke live smoke when `.env` sets `SEO_RANK_RUN_LIVE_INTEGRATION=1` | QA / SDLC | required | open |
| S476-24 | Add `addopts = "-m 'not integration'"` to `[tool.pytest.ini_options]` in `pyproject.toml` so bare `pytest` matches unit-only sign-off; live smoke runs only with `pytest -m integration` | QA / pytest | nice-to-have | open |
| S476-25 | ~~Scaffold `docs/qa/release-phase-4.76.md`~~ — **superseded:** sign-off checklist and must-pass commands live in `TESTING.md` (S476-15) and this file's Slice 5 / release-infrastructure sections; do not add a separate QA doc | 4.76 docs | nice-to-have | cancelled |
| S476-26 | Fix `TESTING.md` verification status: state unit baseline (`pytest tests/unit` → **125 pass**) separately from full `pytest` when live gates are on (integration runs and may fail) | QA / docs | nice-to-have | done |
| S476-27 | TDD gate for Slice 4–5: S476-46 → S476-54 → close S476-12 (S476-09, S476-10, S476-44 **done** in Jul 2026 diff). S476-11 and S476-17 closed as superseded. **Partial:** Slice 4 `page_html` sink shipped; S476-42 / S476-43 done; orphan `normalize_run` test (S476-46), raw-HTML `normalize_run` test (S476-54), and test hardening (S476-49–S476-57) still open | 4.76 Slices 4–5 | required | open |
| S476-28 | Slice 4–5 merge sign-off must-pass: `pytest tests/unit -q` plus targeted `test_run_normalize.py` + `test_round_trip.py`; do not treat bare `pytest` as green until S476-13 and S476-23/24 are closed | 4.76 Slice 5 | required | open |

---

## Senior QA — Jul 2026 release verdict (Phase 4.76)

Follow-ups from the Jul 2026 release-readiness review and Jul 2026 senior QA
follow-up. **Verdict:** Phase 4.76 Slice 5 is **not** release-ready; Slices 1–4
code is largely shipped, unit baseline is green (`pytest tests/unit` → 125 pass),
but required TDD gates (S476-12 remainder, **S476-46** orphan invariant) and
integration gate policy (S476-13, S476-23) remain open. S476-09, S476-10, and
S476-44 closed in Jul 2026 diff. Fields-vs-pages policy resolved in code (S476-17, S476-11 superseded; docs
close-out tracked in S476-38 / S476-47).

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-29 | Inline Phase 4.76 sign-off in `TESTING.md` (must-pass commands from S476-28, manual checklist from S476-15, default gate is `pytest tests/unit` not bare `pytest`) — completes S476-15; no external QA doc | QA / docs | nice-to-have | open |
| S476-30 | Extend `test_normalize_run_materializes_curated_tables_from_raw_responses` (dry-run path) to assert `page_content_fields` and `page_html` catalog datasets and row counts — today only keywords/pages/passages are checked on the default dry-run fixture | 4.76 Slice 5 | nice-to-have | open |
| S476-31 | ~~Align `build_page_html_frame` skip logic with pages/fields when aggregate text is empty~~ — **resolved:** Slice 4 intentionally persists `page_html` when URL + `raw_html` exist but aggregate text is empty (`test_build_page_html_frame_persists_raw_html_without_page_text`); close out in S476-38 | 4.76 Slice 5 | required | done |
| S476-32 | After Slice 5 required tests green, check off `GOALS.md` Slice 5 dev slice, acceptance row 5, and progress table (5 of 5 shipped) | 4.76 docs | required | open |
| S476-33 | Treat flakiness as product bug: root-cause Gemini `404` in live smoke (model name, API version, or pre-flight skip) before re-enabling full `pytest` as a hook gate — do not paper over with unconditional `skip` without documenting why | QA / integration | required | open |

**Recommended work order:** S476-23 + S476-26 (default gate docs) → S476-13 +
S476-33 (live smoke health) → **code:** S476-46 → S476-49–S476-53 → S476-48 /
S476-35 / S476-04 → **docs:** S476-47 + S476-38 (policy matrix) → close S476-12 →
S476-34 (GOALS progress line) → S476-32 (GOALS sign-off).

---

## Senior QA — Jul 2026 follow-up (Slice 5 in progress)

Second senior QA pass on uncommitted Slice 5 work, plus a third pass (diff review)
with recommendations folded into S476-46–S476-57 below. **Verdict unchanged:**
Slice 5 is **conditionally merge-ready at the unit layer** (`pytest tests/unit`
→ 125 pass) but **not** release-ready until required TDD gates and S476-38 docs
close. Default merge gate (S476-28):

```bash
pytest tests/unit -q
pytest tests/unit/test_run_normalize.py tests/unit/test_dataforseo_requests.py tests/unit/test_round_trip.py -q
```

Do not treat bare `pytest` as green until S476-13 and S476-23/24 close.

### Risky journeys (confidence per effort)

| Journey | Risk | Notes |
| --- | --- | --- |
| Stored-run `normalize` → curated Parquet | High | Core Phase 4.76 deliverable |
| `page_content_fields` without matching `pages` | High | Intentional (S476-17 done); frame test exists; `normalize_run` orphan test missing (S476-46); doc in S476-38 / S476-47 |
| Raw-HTML-only page shells in `pages` | Medium | Frame gate: `test_build_pages_and_passages_frame_keeps_page_rows_for_raw_html_without_text`; `normalize_run` E2E still missing (S476-54); docs in S476-47 |
| Aggregate `pages.text` vs decoder output | Medium | S476-10 frame regression **done**; long-term drift still tracked in S476-04 |
| Parser split between sinks | Low | `page_content_fields` uses `parsed_page_text`; pages/html use `parsed_page_text_details` — shared URL today; watch S476-48 |
| Empty-frame schema in lazy `map_batches` | Medium | Partial fix in uncommitted `normalize.py` (S476-43) |
| Live integration smoke | Low for Slice 5 | Gemini 404 when gates on; gate away from hooks |

### Manual sign-off (real stored run — fold into S476-15 in `TESTING.md`)

- [ ] `seo-rank normalize --run <pre-4.76-artifacts>` — no schema validation errors
- [ ] Curated lake has `page_content_fields` with expected `field_path` / `ordinal`
- [ ] `page_html.raw_html` present where crawl succeeded
- [ ] `pages` / `passages` row counts unchanged on runs that had aggregate text
- [ ] Locale: `--language fr` does not change page crawl pool (US / en-US contract)

### Follow-up fixups from this pass

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-42 | Ship structured-only frame tests (uncommitted): `test_build_page_content_fields_frame_keeps_structured_fields_without_aggregate_text`, `…_without_page_text`; decoder asserts for telephones + comment `relative_rating` in `test_dataforseo_requests.py` | 4.76 Slice 5 | required | done |
| S476-43 | Close S3-01 partial for `build_keywords_frame` + `build_pages_and_passages_frame`: typed empty frames and explicit null `passage_id` / `source` / `word_count` on page rows (uncommitted `normalize.py`) | 4.5 Slice 3 / 4.76 Slice 5 | nice-to-have | done |
| S476-44 | Extend `test_round_trip.py` with structured-only `page_text` payload (ratings/offers/comments + HTML, zero aggregate text) — remainder of S476-12 | 4.76 Slice 5 | required | done |
| S476-45 | Add unit test asserting empty `build_keywords_frame` returns `CURATED_VALIDATION_RULES["keywords"]["expected_schema"]` (lazy `map_batches` contract) | 4.76 Slice 5 | nice-to-have | open |
| S476-47 | Publish crawl sink policy matrix in `ARCHITECTURE.md` (+ one-line in `GOALS.md`): `page_content_fields` → URL only; `page_html` → URL + `raw_html`; `pages` → URL + (aggregate text or `raw_html`); `passages` → aggregate text only. Fixes S476-DONE-05 doc drift (pages no longer require aggregate text when `raw_html` is present) | 4.76 Slice 5 | required | open |

Code / test follow-ups from the same pass: **S476-46–S476-57** in
[Code review — Jul 2026 diff](#code-review--jul-2026-diff-code--tests-only) below.

### Code review — Jul 2026 diff (code / tests only)

Recommendations from the Slice 5 test diff review. **No doc rows here** — policy
matrix and sign-off wording stay in S476-38, S476-47, S476-14, S476-26, etc.
Existing open **implementation** rows elsewhere in this file that the review
re-prioritized: S476-04, S476-13, S476-18, S476-23, S476-24, S476-30, S476-35,
S476-39, S476-40, S476-45, S476-48 (refocus S476-48 on `normalize.py` helper
extraction, not comments/docs).

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S476-46 | Add `normalize_run` test for orphan structured-only crawl: fixture from `test_build_page_content_fields_frame_keeps_structured_fields_without_aggregate_text` (URL + `status_code`, empty `page_content`, **no** `raw_html`) — assert `page_content_fields` row count > 0, `pages` / `passages` / `page_html` row counts == 0. Locks the cross-table invariant S476-17 describes; frame-level tests alone are insufficient | 4.76 Slice 5 | required | open |
| S476-49 | Add test docstrings (or rename) on `test_normalize_run_materializes_structured_fields_and_html_from_stored_run` and `test_cli_round_trip_materializes_structured_only_page_text_payload`: both fixtures include `raw_html`, so `pages row_count > 0` is expected — they prove HTML + structured-field materialization, **not** the orphan fields-without-pages case (S476-46) | 4.76 Slice 5 | nice-to-have | open |
| S476-50 | Extract shared structured `page_text` response builder (ratings/offers/comments + optional `raw_html`) into `tests/conftest.py` or `tests/fixtures/page_text.py`; dedupe JSON between `test_normalize_run_stores_raw_html_when_present` and `test_cli_round_trip_materializes_structured_only_page_text_payload` | 4.76 Slice 5 | nice-to-have | open |
| S476-51 | Assert `passages` catalog `row_count == 0` in `test_cli_round_trip_materializes_structured_only_page_text_payload` (parity with `test_normalize_run_materializes_structured_fields_and_html_from_stored_run`) | 4.76 Slice 5 | nice-to-have | open |
| S476-52 | Extend `test_build_pages_and_passages_frame_preserves_aggregate_text_with_field_decode` with ratings/offers/comments in the same payload as `page_content` text blocks so the test exercises decoder + aggregate merge together; **or** rename to `test_build_pages_and_passages_frame_preserves_aggregate_text_from_page_content` if scope stays text-only | 4.76 Slice 5 | nice-to-have | open |
| S476-53 | Rename `test_cli_round_trip_materializes_structured_only_page_text_payload` → `test_cli_round_trip_materializes_structured_fields_and_html_without_aggregate_text` — current name implies the S476-46 orphan case but fixture ships `raw_html` | 4.76 Slice 5 | nice-to-have | open |
| S476-48 | Unify page identity resolution in `src/seo_rank/data/normalize.py`: extract a shared helper used by `build_page_content_fields_frame` (`parsed_page_text`) and `build_pages_and_passages_frame` / `build_page_html_frame` (`parsed_page_text_details`) so URL / `raw_html` extraction cannot drift on multi-item payloads (extends S476-35) | 4.76 Slice 4 | nice-to-have | open |
| S476-54 | Add `normalize_run` test for raw-HTML-only crawl: fixture from `test_build_pages_and_passages_frame_keeps_page_rows_for_raw_html_without_text` (URL + `raw_html`, no aggregate text) — assert catalog `pages` and `page_html` row counts > 0, `passages` == 0. Frame test alone does not prove lazy sink wiring at the `normalize_run` boundary | 4.76 Slice 5 | nice-to-have | open |
| S476-55 | Assert `catalog["datasets"]["passages"]["row_count"] == 0` in `test_normalize_run_stores_raw_html_when_present` — parity with `test_normalize_run_materializes_structured_fields_and_html_from_stored_run` and S476-51 | 4.76 Slice 5 | nice-to-have | open |
| S476-56 | Extend structured `page_text` coverage through `build-features` and `analyze`, not only `normalize`: run the injected fixture in `test_round_trip.py` (or a sibling test) through the full storage CLI chain so `page_content_fields` / `page_html` survive mart builds; closes S476-12 remainder (relates to S7-03) | 4.76 Slice 5 | nice-to-have | open |
| S476-57 | Strengthen S476-46 orphan test: assert field-row `page_id` values do not appear in `pages` Parquet (cross-table negative join), not only catalog row counts == 0 | 4.76 Slice 5 | nice-to-have | open |

**Recommended code order:** S476-46 (orphan `normalize_run` invariant) → S476-54
(raw-HTML-only `normalize_run`) → S476-55 + S476-51 + S476-53 + S476-49 (passages
+ naming clarity) → S476-57 (orphan cross-table join) → S476-50 (fixture dedupe) →
S476-52 (aggregate + decoder interaction) → S476-56 (full CLI chain) → S476-48 /
S476-35 / S476-04 (`normalize.py` hardening) → S476-23 / S476-24 / S476-13
(integration gate in `pyproject.toml` + `tests/integration/`).

### Senior QA diff review — release test plan (Jul 2026)

**Must-pass (default sign-off gate):**

```bash
pytest tests/unit -q
```

Expected: **125 passed** (`pytest tests/unit`; verified Phase 4.77 Slice 3 diff).

**Targeted before Slice 5 sign-off:**

```bash
pytest tests/unit/test_run_normalize.py tests/unit/test_dataforseo_requests.py tests/unit/test_round_trip.py -q
```

**Should-add before Phase 4.76 sign-off (code):** S476-46 → S476-54 → S476-55 /
S476-51 / S476-53 / S476-49 (test clarity) → S476-57 → S476-50 / S476-52 →
S476-56. **Docs (not code):** S476-47 / S476-38 (policy matrix) → close S476-12.

**Integration (when live gates on):** bare `pytest` → unit pass + 1 integration fail until
S476-13 closes; do not use as hook gate until S476-23 / S476-24.

**Approve implementation direction** for Slice 5 fields-vs-pages policy; **do
not** treat Phase 4.76 signed off until S476-38, S476-46, and S476-13 close
(S476-09, S476-10, S476-44 already shipped in diff).

---

## Phase 4.76 — Slice 4 (already done)

| ID | Fix | Phase | Status |
| --- | --- | --- | --- |
| S476-DONE-04 | Ship curated `page_html` PyArrow schema, Polars validation rules, `build_page_html_frame()` + `_extract_raw_html()`, lazy sink wiring, `GOALS.md` / `ROADMAP.md` Slice 4 sign-off, and unit tests (`test_build_page_html_frame_persists_raw_html_without_page_text`, HTML asserts in `test_normalize_run_materializes_page_content_fields`) | 4.76 Slice 4 | done |

---

## Phase 4.76 — Slice 3 (already done)

| ID | Fix | Phase | Status |
| --- | --- | --- | --- |
| S476-DONE-01 | Ship curated `page_content_fields` PyArrow schema, Polars validation rules, lazy `map_batches` sink, catalog wiring, and doc updates (`GOALS.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `TESTING.md`) | 4.76 Slice 3 | done |
| S476-DONE-02 | Fix `decode_content_parsing_items()` to set `structured_value = json.dumps(value)` for string scalars so `page_content_fields` `non_null_columns` validation passes on sink | 4.76 Slice 3 | done |
| S476-DONE-03 | Add `test_build_page_content_fields_frame_decodes_structured_fields` and `test_normalize_run_materializes_page_content_fields` (partial S476-08; `field_row_id` stability assertions deferred to S476-20) | 4.76 Slice 3 | done |
| S476-DONE-05 | Resolve fields-vs-pages policy (S476-17, S476-11): emit `page_content_fields` when URL + structured payload exist but aggregate text is empty; emit `pages` (no passages) when URL + `raw_html` exist but aggregate text is empty; omit `pages` / `passages` when URL exists but aggregate text and `raw_html` are both empty (orphan fields only — `normalize_run` test tracked in S476-46). Tests: `test_build_page_content_fields_frame_keeps_structured_fields_without_aggregate_text`, `…_without_page_text`, `test_build_pages_and_passages_frame_keeps_page_rows_for_raw_html_without_text`, `test_normalize_run_materializes_structured_fields_and_html_from_stored_run` (HTML path, not orphan). Policy matrix docs: S476-47 | 4.76 Slice 5 | done |

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
| S3-01 | Return explicit Polars schemas from empty `build_*_frame` UDFs (`keywords`, `serp_items`, `pages_and_passages`, `entities`), matching each `map_batches(..., schema=...)` contract — same pattern as `build_similarity_scores_frame`. **Partial:** uncommitted Slice 5 diff covers `keywords` + `pages_and_passages` (S476-43); `serp_items` + `entities` still open | 4.5 Slice 3 | nice-to-have | open |
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
``
## Phase 4.77 — Slice 1 (schema contracts — already done)

Shipped in Jul 2026 diff: `DATAFORSEO_RESPONSE_SCHEMAS`, `DataForSeoParseError`,
`validate_dataforseo_response()`, strict leaf type checks (`_matches_expected_type`),
missing-field `expected: "present"` errors, content-parsing item validation, and unit
tests in `test_dataforseo_requests.py` / `test_serp_normalization.py`. Validator is
standalone — boundary wiring is Slice 2 (S477-04–S477-09).

| ID | Fix | Phase | Status |
| --- | --- | --- | --- |
| S477-DONE-01 | Explicit schemas + `validate_dataforseo_response()` for `keyword_expansion`, `serp`, and `page_text`; parametrized pass-through tests on fixture responses | 4.77 Slice 1 | done |
| S477-DONE-02 | Reject `bool` where schema expects `int` (`rank_group`) via `type(value) is expected_type` in `_matches_expected_type`; tests `test_validate_dataforseo_response_rejects_bool_rank_group_as_int`, `test_normalize_serp_results_rejects_bool_rank_group` | 4.77 Slice 1 | done |
| S477-DONE-03 | Missing-field `DataForSeoParseError` with `expected: "present"` and `got field absent`; test `test_validate_dataforseo_response_reports_missing_field_as_absent` | 4.77 Slice 1 | done |
| S477-DONE-04 | Unknown endpoint raises at `<endpoint>`; test `test_validate_dataforseo_response_rejects_unknown_endpoint` | 4.77 Slice 1 | done |
| S477-DONE-05 | Nested `items[].page_content` passes validation; test `test_validate_dataforseo_response_accepts_nested_page_content_fixture` | 4.77 Slice 1 | done |
| S477-DONE-06 | Empty-page response (`items: None`, `items_count: 0`) passes validation; test `test_validate_dataforseo_response_accepts_empty_page_response` | 4.77 Slice 1 | done |
| S477-DONE-07 | `page_text` item missing all content keys raises with content-key expectation message; test `test_validate_dataforseo_response_rejects_content_item_without_body` | 4.77 Slice 1 | done |
| S477-DONE-08 | SERP top-level type drift raises typed error; test `test_validate_dataforseo_response_rejects_schema_drift_with_typed_error` | 4.77 Slice 1 | done |
| S477-DONE-09 | `page_content` wrong-type drift raises typed error; test `test_validate_dataforseo_response_checks_content_parsing_item_shape` | 4.77 Slice 1 | done |
| S477-DONE-10 | Parametrized missing required leaf fields (`keyword`, `rank_group`, `url`, `title`) now fail loud in `test_validate_dataforseo_response_rejects_missing_required_leaf_fields`; explicit `page_text` extra-field pass-through is pinned in `test_validate_dataforseo_response_accepts_page_text_with_extra_fields_unchanged` | 4.77 Slice 3 | done |
| S477-DONE-11 | Non-dict root input raises at `<root>`; test `test_validate_dataforseo_response_rejects_non_dict_root_input` | 4.77 Slice 3 | done |

---``

## Phase 4.77 — Slice 1 (post-ship polish)

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S477-03 | Remove unreachable `isinstance` branch after `_raise_unless_type(items, list, ...)` in `_validate_content_parsing_result` and redundant `results` list `continue` in `_validate_content_parsing_response` | 4.77 Slice 1 | nice-to-have | open |

---

## Phase 4.77 — Slice 2 (boundary enforcement — open)

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S477-04 | Add `request.path` → endpoint schema key mapping helper and unit tests for all three DataForSEO paths plus unknown path | 4.77 Slice 2 | required | open |
| S477-05 | Call `validate_dataforseo_response` from `execute_dataforseo_request` (or shared adapter wrapper) using path mapping | 4.77 Slice 2 | required | open |
| S477-06 | Unit test: mock transport returns schema-invalid SERP; live CLI keyword path raises `DataForSeoParseError` before `normalize_serp_results` | 4.77 Slice 2 | required | open |
| S477-07 | Validate stored-run `raw_responses` bodies at normalize entry before curated Parquet writes | 4.77 Slice 2 | required | open |
| S477-08 | Unit test in `test_run_normalize.py`: drift `page_text` Parquet row fails normalize with `DataForSeoParseError` and does not materialize curated tables | 4.77 Slice 2 | required | open |
| S477-09 | Extend round-trip or normalize regression to assert schema-valid fixtures still pass after boundary wiring (guard against accidental break of `test_round_trip` / stored-run paths) | 4.77 Slice 2 | required | open |

---

## Phase 4.77 — Slice 3 (drift coverage — open)

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |

---

## Phase 5 — Slices 3–4 (guardrails + Spearman — post-ship polish)

Follow-ups from the Jul 2026 code review of uncommitted Phase 5 panel prep,
Spearman/BH, artifact writers, and `seo-rank analyze` wiring. None block Slice 5
(pooled regression) unless marked **required**.

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S5-01 | Update `test_phase_45_slice_9_regression_sweep_marks_mart_sink_docs_as_shipped` (and keep `ARCHITECTURE.md` / `TESTING.md` in sync) when the unit suite grows — currently asserts **145** tests while docs say **153** collected / **152** passing / **1** skipped; full `pytest tests/unit` fails until reconciled (extends S476-22) | 5 docs | required | open |
| S5-02 | Secondary-backend Spearman: `prepare_analysis_panel()` filters one BGE-complete panel for all backends; `GOALS.md` Slice 3 calls for per-backend null checks on secondary paths — filter from `prepared_mart` per backend in `summarize_backend_spearman()` (or document that v1 intentionally shares the BGE-complete panel) | 5 Slice 4 | required | open |
| S5-03 | Read guardrail thresholds and relations from `analysis_spec.v1.yaml` (`guardrails.hard_fail` / `guardrails.warn`) in `_evaluate_guardrails()` instead of hardcoding `10`, `0.90`, and variance thresholds | 5 Slice 3 | nice-to-have | open |
| S5-04 | `influential_rows_rate` warn guardrail deferred to Slice 8 — Slice 6 reports Cook's D / influence counts in `stats_diagnostics.json`; panel guardrail evaluation still pending | 5 Slice 8 | nice-to-have | open |
| S5-05 | Trim `stats_summary.json` payload: move per-keyword `keyword_tests` arrays to `stats_diagnostics.json` (or a sibling artifact) and keep summary aggregates only (median ρ, IQR, fraction same-sign, BH q-values) per `PHASE5-STATS-PLAN-REVIEW.md` | 5 Slice 9 | nice-to-have | open |
| S5-06 | Deduplicate backend→column maps: `SIMILARITY_RATE_COLUMNS` (`panel.py`) and `BACKEND_SCORE_COLUMNS` (`spearman.py`) are identical — single shared constant in `stats/` | 5 Slice 4 | nice-to-have | open |
| S5-07 | Fix stale `ARCHITECTURE.md` wording that still calls `panel.py` / `spearman.py` “placeholder modules” after Slices 3–4 shipped; update `README.md` § `seo-rank analyze` (still says stats are not implemented in the CLI) | 5 docs | nice-to-have | open |
| S5-08 | Add CLI test: `run_manifest_is_dry_run()` causes `analyze` to skip `run_phase5_stats` and exit `0` without writing `stats/` (dry-run fixture contract in `TESTING.md`) | 5 Slice 9 | nice-to-have | open |
| S5-09 | Add Spearman/BH edge-case tests: empty panel, keywords skipped when paired `n < 2` (silent K reduction vs guardrail keyword count), single-keyword panel BH skip | 5 Slice 4 | nice-to-have | open |
| S5-10 | Read `bh_when_keyword_count_gte` and `bh_q` from `AnalysisSpec` instead of literal `10` / implicit q in `summarize_backend_spearman()` | 5 Slice 4 | nice-to-have | open |

---

## Phase 5 — Slice 6 (live-run blocker)

Blocks end-to-end `seo-rank run --live-providers` validation of pooled OLS
diagnostics on real DataForSEO crawls. Relates to Phase 4.77 schema contracts
(`dataforseo.py`); top-level `tasks[].result` type check runs before
`_validate_content_parsing_response` can skip non-list results.

| ID | Fix | Phase | Priority | Status |
| --- | --- | --- | --- | --- |
| S5-11 | Accept `page_text` responses where `tasks[].result` is `null` (task-level crawl failure) instead of raising `DataForSEO page_text response schema drift at tasks[0].result: expected list, got NoneType`. Align `DATAFORSEO_RESPONSE_SCHEMAS` `tasks[].result` with `_validate_content_parsing_response` (already `continue`s when `result` is not a list); CLI live path should skip the URL and continue the run. Repro: `seo-rank run --seed "seo company columbus" --live-providers --live-gemini --live-bge`. Add unit test for `result: null` pass-through and CLI regression that run does not abort on one failed page_text task | 5 Slice 6 | required | open |

---

## How to use this file

- Pick items by **Phase** column when planning slice work in `GOALS.md`.
- Mark **Status** `done` and move rows to the “already done” section when merged.
- Do not treat `nice-to-have` items as sign-off gates; `required` / `planned`
  items belong in slice acceptance or `GOALS.md` remaining work.
