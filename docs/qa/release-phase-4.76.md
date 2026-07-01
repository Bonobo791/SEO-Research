# Release test plan — Phase 4.76

Structured `content_parsing/live` capture: per-field rows, aggregate `pages.text`, and `page_html`.

## Scope

- **In scope:** `build_page_text_request()`, `decode_content_parsing_items()`, curated sinks (`page_content_fields`, `page_html`), `normalize_run` / `seo-rank normalize --run`, dry-run fixtures.
- **Out of scope:** Phase 4.77 adapter schema validation, OLS (Phase 5), passage/domain scoring (Phase 5.5), non-US page crawl pools.

## Risks (highest first)

| Risk | Why it hurts | Layer |
| ---- | ------------ | ----- |
| Orphan `page_content_fields` rows | URL-only empty crawls join-break downstream marts | Unit + normalize integration |
| Aggregate `pages.text` drift | Passage split and similarity features regress | Unit (`test_run_normalize`, `test_dataforseo_requests`) |
| Missing / unlinked `raw_html` | Audit and replay path broken | Unit + stored-run smoke |
| Live integration flakiness | Bare `pytest` red when Gemini gate on | Integration gate / skip policy |
| Paid API misuse | Accidental live runs in CI or hooks | Env gates + manifest `test_command` |

## Must-pass automated (sign-off gate)

**Default gate — do not use bare `pytest` until S476-13 / S476-23 are closed.**

```bash
python -m pytest tests/unit -q
python -m pytest tests/unit/test_run_normalize.py tests/unit/test_round_trip.py -q
```

Expected today: **92 unit tests, all green** (Jul 2026).

### Targeted unit coverage (Slice 5)

| Test | Status | FIXUPS |
| ---- | ------ | ------ |
| `test_build_page_content_fields_frame_decodes_structured_fields` | Green | S476-08 (partial) |
| `test_normalize_run_materializes_page_content_fields` | Green | S476-08 |
| `test_build_page_html_frame_persists_raw_html_without_page_text` | Green | S476-09 (partial) |
| `test_normalize_run_stores_raw_html_when_present` | **Missing** | S476-09 |
| `test_build_pages_and_passages_frame_preserves_aggregate_text_with_field_decode` | **Missing** | S476-10 |
| `test_normalize_run_skips_empty_crawl_with_field_decode` | **Missing** | S476-11, S476-17 |
| Stored-run re-normalize multi-field + HTML fixture | **Missing** | S476-12 |

### Optional live integration

Only when credentials and gates are intentional:

```bash
# .env: SEO_RANK_RUN_LIVE_INTEGRATION=1, SEO_RANK_ENABLE_LIVE_PROVIDERS=1, DATAFORSEO_*
python -m pytest -m integration -q
```

**Known failure (Jul 2026):** `test_live_provider_smoke_writes_artifacts` → Gemini `404 Not Found` when `SEO_RANK_ENABLE_GEMINI=1`. Treat as **required** fix (S476-13) or skip embed health before calling live Gemini.

## Manual checklist

- [ ] **Request contract:** dry-run or captured request shows `content_parsing/live`, `store_raw_html: true`, `ip_pool_for_scan: us`, `accept_language: en-US`, JS/rendering off.
- [ ] **Per-field lake:** after `normalize --run <id>`, `parquet/page_content_fields/` has rows with `field_path`, `field_name`, `structured_value` for scalars (e.g. `status_code`).
- [ ] **HTML lake:** `parquet/page_html/` has `raw_html` linked by `page_id` / `response_id` when crawl payload includes HTML.
- [ ] **Aggregate unchanged:** `pages` / `passages` row counts match pre–Slice 4 baseline on the same stored run; merged `pages.text` still drives passages only.
- [ ] **Empty crawl:** URL-only / empty-body responses appear in neither `pages` nor `page_content_fields` nor `page_html`.
- [ ] **Re-normalize:** pre–4.76 stored run re-normalizes without schema errors; catalog lists new datasets.
- [ ] **Locale note:** `--language fr` still uses US English desktop page crawl (documented in `GOALS.md`).

## Acceptance / sign-off

| Criterion | Met? |
| --------- | ---- |
| All Slice 5 required tests green (S476-09–S476-12, S476-17) | No |
| `pytest tests/unit` green | Yes |
| `GOALS.md` Slice 5 checked off | No |
| Live integration optional and documented | Partial (`TESTING.md` stale vs full `pytest`) |

## Rollback criteria

If per-field or HTML wiring changes `pages` / `passages` row counts or breaks existing normalize fixtures:

1. Revert slice 3–4 sink changes.
2. Re-run `pytest tests/unit/test_run_normalize.py` and `tests/unit/test_round_trip.py`.
3. Do not merge until unit gate is green.

## Follow-up (from `FIXUPS.md`)

- **S476-23:** Pin SDLC manifest `test_command` to `pytest tests/unit`.
- **S476-24:** `addopts = "-m 'not integration'"` in `pyproject.toml`.
- **S476-14 / S476-26:** Align `TESTING.md` with unit vs full suite behavior.
