<!-- Part of the split roadmap. Index: ROADMAP.md. Continues ROADMAP_PHASE_7_1.md -->

#### 7.2 — Backlink quality & anchor relevance (`backlinks/backlinks/live`)

URL grain. One call per SERP URL, `mode: one_per_domain`, `limit: 100`,
`order_by` on `rank` descending. Anchor-text relevance is derived from the
`anchor` field already on this response — the dedicated
`backlinks/anchors/live` endpoint is skipped as redundant, cutting an entire
API source.

##### Dev slices

**Progress:** 5 of 9 shipped.

1. **[x] Slice 1 — Request/schema/fixture** — `build_backlinks_detail_request()`,
   `BACKLINKS_QUERY_DETAIL` variant, `DATAFORSEO_RESPONSE_SCHEMAS["backlinks_detail"]`,
   `fixture_backlinks_detail_response()` in `dataforseo.py`. Offline request/schema
   tests in `tests/unit/test_dataforseo_requests.py`.
2. **[x] Slice 2 — Offline tests.** Covered alongside Slice 1
   (`test_dataforseo_requests.py`) and Slices 4/5 (`test_cli_run.py`).
3. **[x] Slice 3 — Fetch + persistence.** Folded into the existing
   `fetch_dataforseo_backlinks_for_urls` variant loop rather than a standalone
   function — `BACKLINKS_QUERY_DETAIL` added to `BACKLINKS_VARIANT_ENDPOINTS` /
   `BACKLINKS_VARIANT_PROVIDER_DATA_KEYS`, persisted to
   `raw_responses/endpoint=backlinks_detail` alongside the summary/dofollow
   variants. `backlinks_detail_response_is_usable()` gates persistence
   (accepts `backlinks_response_is_successful_empty`).
4. **[x] Slice 4 — Live-run wiring.** `detail` variant fetched live in the same
   pass as `summary`/`dofollow`, gated behind the opt-in `--live-backlinks-detail`
   flag (requires `--live-backlinks`) so the extra per-URL API call stays
   explicit; `build_live_payload` iterates `BACKLINKS_VARIANT_PROVIDER_DATA_KEYS`
   generically. Regressions:
   `test_run_live_backlinks_detail_flag_fetches_and_persists_detail`,
   `test_run_live_backlinks_without_detail_flag_skips_detail`,
   `test_run_live_backlinks_detail_requires_live_backlinks`.
5. **[x] Slice 5 — Stored-run backfill** for `backlinks_detail`. New
   `_backlinks_variants_for_replay()` replays `detail` when the
   `--live-backlinks-detail` opt-in is set (`config.live_backlinks_detail`)
   OR when a `backlinks_detail` raw partition / `raw_provider_data` key already
   exists for that stored run. The opt-in path is what enables true legacy
   backfill: an older run that only ever fetched `summary`/`dofollow` gets
   `detail` fetched for all missing URLs on resume, without refetching the
   complete `summary`/`dofollow` variants. Regressions:
   `test_run_stored_run_backfills_legacy_backlinks_detail_via_opt_in` (legacy
   opt-in path) and
   `test_run_stored_run_backfills_only_missing_backlinks_detail_in_place`
   (in-place completion of an existing partition) in `test_cli_run.py`.
6. **[ ] Slice 6 — Curated builder** — `build_backlink_details_frame`: one row
   per `(run_id, target_keyword_id, canonical_url_hash, backlink_id)` with
   `domain_from_rank`, `page_from_rank`, `backlink_spam_score`, `anchor`,
   `dofollow`, `tld_from`, `domain_from_country`, `first_seen`.
7. **[ ] Slice 7 — Aggregation feature mart** — `backlink_quality_features`
   grouped back to URL grain: `avg_domain_from_rank`, `max_domain_from_rank`,
   `avg_backlink_spam_score`, `anchor_keyword_match_ratio` (lexical overlap
   between anchor text and `target_keyword`, no new NLP dependency),
   `referring_tld_diversity_count`, `referring_country_diversity_count`; null
   the whole row when zero backlinks returned (distinct from not-yet-fetched).
8. **[ ] Slice 8 — Family registry** — new kind `backlinks_quality`; add
   `backlinks_quality` and `backlinks_anchor_relevance` families, kept
   separate from the existing `backlinks_counts` family (Phase 6.2).
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.3 — Backlink velocity (`backlinks/timeseries_new_lost_summary/live`)

URL grain, one call per SERP URL, `group_range: month`, `date_from` 90 days
before the run's collection date.

##### Dev slices

**Progress:** 0 of 9 shipped.

1. **[ ] Slice 1 — Request/schema/fixture.**
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Fetch + persistence** — `fetch_backlink_velocity_for_urls`,
   `raw_responses/endpoint=backlinks_velocity`.
4. **[ ] Slice 4 — Live-run wiring.**
5. **[ ] Slice 5 — Stored-run backfill.**
6. **[ ] Slice 6 — Curated builder** — sum monthly buckets into
   `new_backlinks_90d`, `lost_backlinks_90d`,
   `net_backlink_velocity_90d = new - lost`.
7. **[ ] Slice 7 — Feature mart** — `backlink_velocity_features`, URL-grain join.
8. **[ ] Slice 8 — Family registry** — `backlinks_velocity` family, kind
   `backlinks_metric` (same shape as counts).
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.4 — Domain authority (`dataforseo_labs/google/domain_rank_overview/live`)

Domain grain, one call per **unique domain** in the run (dedupe the way
`domain_features` derives `domain` from SERP URLs).

##### Dev slices

**Progress:** 0 of 9 shipped.

1. **[ ] Slice 1 — Request/schema/fixture** — `target`, `location_code`,
   `language_code`, `limit: 1`.
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Fetch + persistence** — `fetch_domain_rank_overview_for_domains`,
   dedupe domains across the whole run before fetching, `raw_responses/endpoint=domain_rank_overview`.
4. **[ ] Slice 4 — Live-run wiring** — once per run after SERP collection.
5. **[ ] Slice 5 — Stored-run backfill**, keyed on domain not URL.
6. **[ ] Slice 6 — Curated builder** — `build_domain_rank_overview_frame`:
   `domain_rank`, `estimated_organic_traffic` (`etv`), `ranked_keywords_count`
   (`count`); one row per `(run_id, domain)`.
7. **[ ] Slice 7 — Feature mart** — `domain_authority_features`, joined via
   derived `domain` column the way `domain_features` joins.
8. **[ ] Slice 8 — Family registry** — new kind `domain_authority`; add
   `domain_authority` family.
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.5 — Domain technology & age (`domain_analytics/technologies/domain_technologies/live` + `domain_analytics/whois/overview/live`)

Domain grain, same dedupe-once-per-run approach as 7.4. Two endpoints in one
sub-phase since both are cheap per-domain lookups feeding the same mart.

##### Dev slices

**Progress:** 0 of 9 shipped.

1. **[ ] Slice 1 — Request/schema/fixture for both endpoints** —
   `build_domain_technologies_request`, `build_domain_whois_request` (whois
   uses `filters: [["domain","=",target]]`, not a bare `target` field).
2. **[ ] Slice 2 — Offline tests for both.**
3. **[ ] Slice 3 — Fetch + persistence for both** —
   `fetch_domain_technology_for_domains` + `fetch_domain_whois_for_domains`,
   `raw_responses/endpoint=domain_technologies` and `endpoint=domain_whois`.
4. **[ ] Slice 4 — Live-run wiring for both.**
5. **[ ] Slice 5 — Stored-run backfill for both partitions.**
6. **[ ] Slice 6 — Curated builder** — `domain_age_days` (today minus
   `created_datetime`, computed at normalize time so it stays current across
   re-normalizes); CMS/web-dev tech boolean flags (e.g. `uses_wordpress`,
   `uses_shopify`, `uses_react`); `tech_stack_count`.
7. **[ ] Slice 7 — Feature mart** — `domain_technology_features`, same
   domain-grain join as 7.4.
8. **[ ] Slice 8 — Family registry** — new kind `domain_technology`; add
   `domain_technology` family (age + tech flags).
9. **[ ] Slice 9 — Artifacts, fixtures, stored-run regression, tests.**

#### 7.6 — SERP feature presence (normalize-only, no new API calls)

Parses already-stored `raw_responses/endpoint=serp` payloads — no new
endpoint, no fetch/backfill wiring for the core slices.

##### Dev slices

**Progress:** 0 of 5 shipped.

1. **[ ] Slice 1 — Curated builder** — `build_serp_features_frame`: parse
   stored SERP `item_types` into `has_featured_snippet`,
   `has_people_also_ask`, `has_video`, `has_sitelinks`, `has_faq`, plus
   `same_domain_serp_position_count`; row grain matches `serp_items`.
2. **[ ] Slice 2 — Feature mart** — `serp_feature_presence`, URL-grain join,
   boolean validation rules.
3. **[ ] Slice 3 — Family registry** — new kind `serp_feature`; add
   `serp_features` family.
4. **[ ] Slice 4 — Artifacts, fixtures (including a no-rich-features SERP
   payload proving nulls/false render correctly), tests.**
5. **[ ] Slice 5 — Forward-looking pixel position (separate, no backfill)** —
   add `calculate_rectangles: true` to `build_serp_request()` behind a new
   opt-in `--serp-pixel-position` CLI flag (default off); nullable
   `serp_pixel_position_y` column; old runs stay null; explicitly no backfill
   since re-fetching the SERP would change ranks for existing runs.

| Acceptance item | Sub-phase | Status |
| --------------- | --------- | ------ |
| OnPage content/CWV/technical-check families land without an `analysis_mart` schema bump | 7.1 | Shipped (slices 8–9) |
| OnPage stored-run backfill without refetching unrelated partitions | 7.1 | Shipped (slice 5) |
| Backlink quality + anchor-relevance families are separate from the existing counts family | 7.2 | Open |
| Backlink velocity family lands at URL grain | 7.3 | Open |
| Domain authority family lands at domain grain, deduped once per run | 7.4 | Open |
| Domain technology/age family lands at domain grain | 7.5 | Open |
| SERP feature presence lands from stored SERP payloads with no new API calls | 7.6 | Open |
| `run --stored-run` backfills every new source's missing raw partition without refetching unrelated data | 7.2–7.5 | Open |
