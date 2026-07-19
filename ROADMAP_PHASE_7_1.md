<!-- Part of the split roadmap. Index: ROADMAP.md -->

### Phase 7 — DataForSEO datapoint expansion

Widen the factor set with DataForSEO data already paid for but unused:
on-page content/CWV/structured-data signals, backlink quality and
anchor-relevance (not just counts), backlink velocity, domain authority,
domain technology/age, and SERP feature presence. Every new source is
**additive** — new signal families and feature marts, no `analysis_mart`
schema bump — raw-persisted to disk immediately per call (DataForSEO Live
endpoints are not retained provider-side), backfillable onto existing runs
via `run --stored-run` without refetching unrelated data, and covered by
offline fixtures before any live wiring. Partial/missing per-source data is
represented as null (mirrors `dofollow_backlinks_count` /
`backlinks_metrics_complete`), never as a fetch failure — a run missing one
new source must still produce full stats for every other family.

**Depends on Phase 6.2:** reuses the `backlinks_metric` family kind and
`backlinks_analysis` mart pattern established there.

**Shared implementation pattern per source** (apply once per sub-phase, not
restated per slice): (1) client module — request builder(s), a response
schema table (new `DATAFORSEO_RESPONSE_SCHEMAS` entries for DataForSEO
endpoints in `dataforseo.py`), one `fixture_*_response()`, offline
request/schema tests, no live wiring yet; (2) fetch + partial-durability
persistence — a `fetch_<source>_for_*` function building raw records via
`build_raw_response_record(..., endpoint="<partition>")`, persisted in a
`finally:` block so a mid-batch crash keeps prior progress (copy
`fetch_dataforseo_backlinks_for_urls` / `persist_backlink_raw_responses` in
`cli.py`, including the dedupe key and `refresh_run_json_raw_response_catalog`);
(3) live-run wiring alongside the existing backlinks fetch so new runs
collect the source automatically; (4) `--stored-run` backfill — extend
`expand_stored_run` / `build_resumed_keyword_result`'s reuse-check (mirrors
`_register_usable_backlink_response`) so only missing URLs/domains are
(re)fetched; this is the **one** general backfill mechanism for every source
in this phase, not a per-source CLI flag; (5) curated builder in
`data/normalize.py`, feature mart entry in `data/features.py` joined on the
correct grain (URL sources join like `backlinks_analysis` on
`["run_id","target_keyword_id","canonical_url_hash"]`; domain sources
derive `domain` the way `domain_features` does), a new family `kind` in
`stats/families.py` (`VALID_SIGNAL_FAMILY_KINDS` + `SOURCE_MART_BY_KIND`),
and a family block appended (never reordered) to
`analysis_spec.v1.yaml` `signal_families.families`; (6) artifacts wiring
(spearman/regression/diagnostics/Plackett-Luce per new family) plus golden
fixtures and a stored-run regression proving only the missing source gets
(re)fetched.

#### 7.1 — OnPage page signals (`on_page/instant_pages`)

URL grain (`target_keyword_id × canonical_url_hash` with the original `url`
retained), one synchronous live call per SERP URL with `enable_javascript`,
`enable_browser_rendering`, `load_resources`,
and `validate_micromarkup: true` all set on the same request — structured-data
validation rides along in one call, no separate `on_page/microdata` endpoint
or task id needed, and no `task_post` crawl/poll flow.

##### Dev slices

**Progress:** 18 of 18 shipped.

1. **[x] Slice 1 — Request/schema/fixture** — `build_onpage_instant_pages_request()`,
   `DATAFORSEO_RESPONSE_SCHEMAS["onpage_instant_pages"]`,
   `fixture_onpage_instant_pages_response()` in `dataforseo.py`.
2. **[x] Slice 2 — Offline tests** — request shape, schema-accept, schema-drift
   rejection, null/missing optional sections, required-leaf parity cases in
   `tests/unit/test_dataforseo_requests.py`.
3. **[x] Slice 3 — Fetch + persistence** — `fetch_onpage_signals_for_urls` in
   `cli.py`, one call per unique `(target_keyword, url)`, persisted to
   `raw_responses/endpoint=onpage_instant_pages`. Copy
   `fetch_dataforseo_backlinks_for_urls` / `persist_backlink_raw_responses`:
   `execute_validated_dataforseo_request("onpage_instant_pages", …)` with
   `build_onpage_instant_pages_request(url)`, dedupe key `(target_keyword, url)`,
   `build_raw_response_record(..., endpoint="onpage_instant_pages")`, partial
   batch persistence in a `finally:` block, request metadata
   (`target_keyword`, `url`, rendering/micromarkup flags). Tests in
   `tests/unit/test_cli_run.py` and `tests/unit/test_raw_response_merge.py`.
4. **[x] Slice 4 — Live-run wiring** — call alongside the existing backlinks
   fetch in the live keyword-result build path. Filter to missing
   ``(target_keyword, url)`` pairs before calling
   ``fetch_onpage_signals_for_urls``; the fetch helper does not dedupe its
   ``urls`` input, so the call site must guarantee uniqueness to avoid duplicate
   live API calls (mirrors backlinks missing-url filtering ~1166–1174).
   Wired into `build_live_keyword_result`, `build_resumed_keyword_result`
   (missing-URL overlay), `build_keyword_result_from_responses`,
   `build_live_payload`, `expand_stored_run`, and `build_raw_response_records`.
   Tests in `tests/unit/test_cli_run.py`.
5. **[x] Slice 5 — Stored-run backfill** — reuse-check parity for the
   `onpage_instant_pages` partition inside `build_resumed_keyword_result`
   (`_usable_onpage_by_url_from_records`, `_missing_serp_urls`); backfill only
   missing SERP URLs when `--stored-run --live-providers`. Empty schema-valid
   rows (`result: null`, no page items) are **not** reusable (unlike backlinks
   empty summaries). CLI regressions in `tests/unit/test_cli_run.py`.
6. **[x] Slice 6 — Curated builder** — `build_onpage_signals_frame` in
   `normalize.py`: URL-grain `parquet/onpage_signals` with `onpage_score`, 12
   check booleans, content/readability metrics, CWV timing, `total_transfer_size`,
   and microdata summary (`micromarkup_*` counts when nested object present,
   `has_valid_structured_data` derived from `has_micromarkup*` flags). Skips
   unusable empty raw rows; dedupes by `(target_keyword, url)` on latest
   `timestamp` with `response_id` tie-break. Tests in
   `tests/unit/test_run_normalize.py`.
7. **[x] Slice 7 — Feature mart** — `onpage_features`, URL-grain join of
   curated `onpage_signals` onto the `analysis_mart` panel
   (`build_feature_lazyframes` left join on
   `run_id`, `target_keyword_id`, `canonical_url_hash`); bounded
   validation (`onpage_score` 0–100, non-negative counts/timing). Tests in
   `tests/unit/test_feature_marts.py`.
8. **[x] Slice 8 — Family registry + stats source wiring** — new kind `onpage_metric` mapped to
   `onpage_features` in `stats/families.py`; three families appended to
   `analysis_spec.v1.yaml`: `onpage_content_quality` (score + readability),
   `onpage_core_web_vitals` (TTFB, LCP, CLS, transfer size),
   `onpage_technical_checks` (12 SEO/tech booleans + structured-data summary).
   `build_family_source_frames()` loads `onpage_features` when the mart partition
   exists; boolean predictors are coerced to 0/1 before pooled OLS. Registry/spec
   tests in `test_stats_families.py` and `test_stats_spec.py`; integration in
   `test_stats_family_artifacts.py`.
9. **[x] Slice 9 — Artifacts follow-ups** — family Plackett-Luce enabled for
   `onpage_metric` with shared-prep perf refactor (`FAMILY_PLACKETT_LUCE_OPTIMIZER_OPTIONS`,
   zero-variance fast skip), `ensure_feature_marts_for_analysis()` in
   `data/features.py` (requires `onpage_features`; rebuilds when `run.json`
   exists), same guard from `run_phase5_stats()` for legacy upgrade paths,
   golden contract + hard-fail OnPage assertions.
10. **[x] Slice 10 — Fix `meta.content`/CLS nesting bug + schema/fixture
    correction.** Fix `_onpage_signals_row` to read `item["meta"]["content"]`
    and `item["meta"]["cumulative_layout_shift"]` (keep the existing
    item-top-level fallback for backward compatibility with any
    already-persisted raw rows that used the flat shape, but prefer nested).
    Correct `fixture_onpage_instant_pages_response` to nest `content` and
    `cumulative_layout_shift` under `meta`, matching the real payload. Update
    `DATAFORSEO_RESPONSE_SCHEMAS["onpage_instant_pages"]` field-schema entries
    in `normalize.py:117-156` accordingly. Regression test asserting the
    readability/CLS fields populate from a fixture shaped like the real
    response (nested), not just the old flat shape.
11. **[x] Slice 11 — Expand `checks` coverage.** Grow
    `ONPAGE_CURATED_CHECK_FIELDS` (`normalize.py:52-65`) from 12 to the full
    46-field set: `deprecated_html_tags`, `duplicate_title_tag`, `flash`,
    `frame`, `from_sitemap`, `has_html_doctype`, `has_meta_refresh_redirect`,
    `has_micromarkup`, `has_micromarkup_errors`, `high_character_count`,
    `high_content_rate`, `high_loading_time`, `high_waiting_time`,
    `https_to_http_links`, `irrelevant_meta_keywords`, `irrelevant_title`,
    `is_4xx_code`, `is_5xx_code`, `is_broken`, `is_redirect`, `is_www`,
    `large_page_size`, `lorem_ipsum`, `low_content_rate`,
    `meta_charset_consistency`, `no_content_encoding`, `no_doctype`,
    `no_encoding_meta_tag`, `no_favicon`, `no_image_alt`, `no_image_title`,
    `seo_friendly_url`, `size_greater_than_3mb`, `small_page_size`. Extend
    `CURATED_SCHEMAS["onpage_signals"]` and `CURATED_VALIDATION_RULES` with the
    new boolean columns. `_optional_onpage_check_bool()` reads `checks` first
    and falls back to item-level flags for `has_micromarkup`,
    `has_micromarkup_errors`, and `from_sitemap`. Tests in
    `tests/unit/test_run_normalize.py`.
12. **[x] Slice 12 — `meta` block metrics.** Add columns to
    `onpage_signals`/curated schema for: `description_length`,
    `title_length`, `external_links_count`, `internal_links_count`,
    `images_count`, `images_size`, `scripts_count`, `scripts_size`,
    `stylesheets_count`, `stylesheets_size`,
    `render_blocking_scripts_count`, `render_blocking_stylesheets_count`,
    `follow` (bool), `inbound_links_count`, `duplicate_meta_tags_count`
    (array length), and the 3 consistency scores from `meta.content`
    (`description_to_content_consistency`, `title_to_content_consistency`,
    `meta_keywords_to_content_consistency`). New helper
    `_optional_mapping_len` for array-length counts (`duplicate_meta_tags`,
    `htags.h1/h2/h3`, reused by Slice 13). Tests in
    `tests/unit/test_run_normalize.py`.
13. **[x] Slice 13 — `htags` counts + `social_media_tags` presence flags.**
    Add `h1_count`/`h2_count`/`h3_count` (derived from `meta.htags` array
    lengths; heading text itself stays out of scope) and
    `has_og_tags`/`has_twitter_tags` (boolean presence of any `og:*`/
    `twitter:*` key in `meta.social_media_tags`; tag values are not stored,
    since title/description/canonical are already captured elsewhere).
    Tests in `tests/unit/test_run_normalize.py`.
14. **[x] Slice 14 — Resource/cache/DOM/size metrics.** Add columns for
    `cache_control.cachable`, `cache_control.ttl`, `resource_errors_count`
    and `resource_warnings_count` (lengths of the `errors`/`warnings`
    arrays), `broken_links`, `broken_resources`, `duplicate_content`,
    `duplicate_description`, `duplicate_title`, `click_depth`,
    `encoded_size`, `total_dom_size`. Tests in
    `tests/unit/test_run_normalize.py`.
15. **[x] Slice 15 — Full `page_timing` expansion.** Add the remaining
    timing columns beyond the existing TTFB/LCP/CLS:
    `connection_time`, `time_to_secure_connection`, `request_sent_time`,
    `download_time`, `duration_time`, `fetch_end`, `dom_complete`,
    `time_to_interactive`, `first_input_delay`. Tests in
    `tests/unit/test_run_normalize.py`.
16. **[x] Slice 16 — Feature mart + bounded validation.** Extend
    `ONPAGE_FEATURES_EXTRA_COLUMNS`/`ONPAGE_FEATURES_EXPECTED_SCHEMA`/
    `ONPAGE_FEATURES_BOUNDED_COLUMNS` (`features.py:444-487`) to carry all
    new columns (Slices 11-15) into `onpage_features` (non-negative bounds
    on new numeric/count/size/timing columns; new booleans unbounded).
    Tests in `tests/unit/test_feature_marts.py`.
17. **[x] Slice 17 — Analysis family wiring for new fields.** Extend the
    three existing `onpage_metric` families in `analysis_spec.v1.yaml` (or
    add a 4th, e.g. `onpage_resource_profile`, if the existing three don't
    fit thematically): link/image/script/DOM/size metrics and new technical
    booleans into a technical/structural family, timing extensions into
    `onpage_core_web_vitals`, consistency scores into
    `onpage_content_quality`. No `analysis_mart` schema bump, mirroring
    Slice 8. Tests in `test_stats_families.py`/`test_stats_spec.py`.
18. **[x] Slice 18 — Fixtures and regressions** — stored-run end-to-end
    regression, full-layer CLI pipeline tests beyond analyze/mart guards,
    now covering the full expanded field set including the corrected nested
    `meta.content`/CLS shape.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| OnPage instant_pages request/schema/fixture | 1 | Shipped |
| Offline request/schema tests | 2 | Shipped |
| Fetch + raw partition persistence | 3 | Shipped |
| Live-run wiring | 4 | Shipped |
| Stored-run backfill (OnPage partition only) | 5 | Shipped |
| Curated `onpage_signals` | 6 | Shipped |
| Feature mart `onpage_features` | 7 | Shipped |
| Three `onpage_metric` families; no `analysis_mart` schema bump | 8 | Shipped |
| Full family stats + legacy `onpage_features` rebuild on analyze | 9 | Shipped |
| Fix `meta.content`/CLS nesting bug + fixture correction | 10 | Shipped |
| Full `checks` coverage (46 booleans) | 11 | Shipped |
| `meta` block metrics (links/images/scripts/stylesheets/consistency) | 12 | Shipped |
| `htags` counts + `social_media_tags` presence flags | 13 | Shipped |
| Resource/cache/DOM/size metrics | 14 | Shipped |
| Full `page_timing` expansion | 15 | Shipped |
| Feature mart + bounded validation for new columns | 16 | Shipped |
| Analysis family wiring for new fields | 17 | Shipped |
| Stored-run regression + full-layer CLI tests | 18 | Shipped |
