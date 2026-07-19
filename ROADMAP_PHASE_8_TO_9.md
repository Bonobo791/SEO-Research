<!-- Part of the split roadmap. Index: ROADMAP.md -->

### Phase 8 — Non-DataForSEO API integrations

Add free-tier third-party signals DataForSEO doesn't cover: real-user Core
Web Vitals, content freshness, and brand/entity authority. Majestic, Ahrefs,
Moz, Similarweb, Google Search Console, and Google Natural Language are
**deferred** — paid or account-gated, marginal value over Phase 7. Each
source here is a brand-new client module (no existing endpoint to extend) but
follows the identical implementation pattern from Phase 7 — client module
with fixtures and offline tests, `SEO_RANK_ENABLE_<SOURCE>` env gate plus a
`validate_live_<source>_config`, fetch + `finally:`-block persistence with a
dedupe key, live-run wiring gated on that flag (these need their own
credentials, so unlike Phase 7's bundled DataForSEO calls they stay opt-in
like TextRazor), `--stored-run` backfill via the same reuse-check extension,
curated builder + feature mart + new family kind + spec entry, and golden
fixtures plus a stored-run regression. Missing/not-found data (e.g. a domain
with no CrUX data, a URL never archived) is a valid null outcome, never a
fetch error.

#### 8.1 — Google Chrome UX Report (CrUX) API — field Core Web Vitals

`POST https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=<GOOGLE_API_KEY>`.
URL grain with origin fallback: query `url` first; on 404 (no per-URL CrUX
data), retry once with `origin` and flag `crux_is_origin_fallback: true`.
Free, 150 req/min per GCP project.

##### Dev slices

**Progress:** 0 of 11 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/crux.py`:
   `CruxCredentials` (`api_key`), `build_crux_record_request(url_or_origin, form_factor=None)`,
   `CRUX_RESPONSE_SCHEMA`, `fixture_crux_response()`,
   `validate_crux_credentials(env)`.
2. **[ ] Slice 2 — Offline tests** — url vs origin body shape, schema-accept,
   schema-drift reject.
3. **[ ] Slice 3 — Execute + retry** — `execute_crux_request()` (copy the
   `execute_dataforseo_request` retry loop); treat HTTP 404 as "no data", not
   a retryable error.
4. **[ ] Slice 4 — Env gate** — `SEO_RANK_ENABLE_CRUX` +
   `validate_live_crux_config`; `GOOGLE_API_KEY` documented (shared with 8.3).
5. **[ ] Slice 5 — Fetch + persistence** — `fetch_crux_for_urls`: per unique
   URL, try `url` record, fall back to `origin` on 404, persist to
   `raw_responses/endpoint=crux`.
6. **[ ] Slice 6 — Live-run wiring**, gated on `SEO_RANK_ENABLE_CRUX`.
7. **[ ] Slice 7 — Stored-run backfill** for the `crux` partition.
8. **[ ] Slice 8 — Curated builder** — `build_crux_frame`: `crux_lcp_p75`,
   `crux_inp_p75`, `crux_cls_p75` (p75 from each histogram metric),
   `crux_is_origin_fallback`, `crux_has_data` (false when neither url nor
   origin returned a record — not a fetch error).
9. **[ ] Slice 9 — Feature mart** — `crux_features`, URL-grain join.
10. **[ ] Slice 10 — Family registry** — new kind `crux_field_data`; add
    `crux_core_web_vitals` family.
11. **[ ] Slice 11 — Fixtures (url-hit, origin-fallback, no-data), stored-run
    regression, tests.**

#### 8.2 — Wayback Machine CDX Server API — content freshness

`GET http://web.archive.org/cdx/search/cdx?url=<url>&output=json&limit=1&fl=timestamp&filter=statuscode:200`
for first capture, plus `output=json&fl=timestamp&collapse=timestamp:8` for a
distinct-capture count. No auth. URL grain.

##### Dev slices

**Progress:** 0 of 10 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/wayback.py`:
   `build_wayback_first_capture_request(url)`,
   `build_wayback_capture_count_request(url)`; validate the bare-JSON-array
   CDX response shape (header row + field count) instead of a
   path-based schema; `fixture_wayback_response()`. No credentials object
   (public API) — skip `validate_*_credentials`, but still add
   `SEO_RANK_ENABLE_WAYBACK` for gate consistency.
2. **[ ] Slice 2 — Offline tests** — request shape, response-shape
   validation, drift rejection (e.g. missing header row).
3. **[ ] Slice 3 — Execute + retry** — `execute_wayback_request()` (no auth,
   simplest client in this phase).
4. **[ ] Slice 4 — Fetch + persistence** — `fetch_wayback_for_urls`: two
   calls per unique URL, persisted to
   `raw_responses/endpoint=wayback_first_capture` and
   `endpoint=wayback_capture_count`.
5. **[ ] Slice 5 — Live-run wiring**, gated on `SEO_RANK_ENABLE_WAYBACK`.
6. **[ ] Slice 6 — Stored-run backfill** for both partitions.
7. **[ ] Slice 7 — Curated builder** — `first_capture_date`,
   `days_since_first_capture` (computed at normalize time), `capture_count`;
   null when never archived (a valid outcome, not an error).
8. **[ ] Slice 8 — Feature mart** — `wayback_features`, URL-grain join.
9. **[ ] Slice 9 — Family registry** — new kind `content_freshness`; add
   `content_freshness` family.
10. **[ ] Slice 10 — Fixtures (found / never-archived), stored-run
    regression, tests.**

#### 8.3 — Google Knowledge Graph Search API — brand entity confirmation

`GET https://kgsearch.googleapis.com/v1/entities:search?query=<brand>&key=<GOOGLE_API_KEY>&limit=1`.
Domain grain; brand name derived from the registrable domain label (reuse
whatever label extraction `domain_features` already does).

##### Dev slices

**Progress:** 0 of 11 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/knowledge_graph.py`:
   `KnowledgeGraphCredentials` (`api_key`, shared `GOOGLE_API_KEY`),
   `build_kg_search_request(query)`, response schema, `fixture_kg_response()`,
   `validate_knowledge_graph_credentials(env)`.
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Execute + retry** — `execute_kg_request()`.
4. **[ ] Slice 4 — Env gate** — `SEO_RANK_ENABLE_KNOWLEDGE_GRAPH` + validator.
5. **[ ] Slice 5 — Fetch + persistence** — `fetch_knowledge_graph_for_domains`,
   dedupe-by-domain, `raw_responses/endpoint=knowledge_graph`.
6. **[ ] Slice 6 — Live-run wiring**, gated on the flag.
7. **[ ] Slice 7 — Stored-run backfill**, keyed on domain.
8. **[ ] Slice 8 — Curated builder** — `kg_entity_found` (`itemListElement`
   non-empty), `kg_result_score` (top hit's `resultScore`, null when not found).
9. **[ ] Slice 9 — Feature mart** — `knowledge_graph_features`, domain-grain join.
10. **[ ] Slice 10 — Family registry** — new kind `entity_authority`; add
    `knowledge_graph_entity` family.
11. **[ ] Slice 11 — Fixtures (found / not-found), stored-run regression, tests.**

#### 8.4 — Wikidata entity search — supplementary brand notability

`GET https://www.wikidata.org/w/api.php?action=wbsearchentities&search=<brand>&language=en&format=json&limit=1`.
Domain grain, no auth. Kept deliberately thin (existence flag only) — overlaps
with 8.3 and is a lower-priority cross-check.

##### Dev slices

**Progress:** 0 of 10 shipped.

1. **[ ] Slice 1 — Client module** — new `src/seo_rank/wikidata.py`:
   `build_wikidata_search_request(query)`, response schema,
   `fixture_wikidata_response()`. No credentials needed; still add
   `SEO_RANK_ENABLE_WIKIDATA` for gate consistency.
2. **[ ] Slice 2 — Offline tests.**
3. **[ ] Slice 3 — Execute + retry** — `execute_wikidata_request()`.
4. **[ ] Slice 4 — Fetch + persistence** — `fetch_wikidata_for_domains`,
   dedupe-by-domain, `raw_responses/endpoint=wikidata`.
5. **[ ] Slice 5 — Live-run wiring**, gated on `SEO_RANK_ENABLE_WIKIDATA`.
6. **[ ] Slice 6 — Stored-run backfill**, keyed on domain.
7. **[ ] Slice 7 — Curated builder** — `wikidata_entity_found`,
   `wikidata_label_match` (exact case-insensitive label match, a simple
   lexical check, not a new fuzzy-matching dependency).
8. **[ ] Slice 8 — Feature mart** — `wikidata_features`, domain-grain join.
9. **[ ] Slice 9 — Family registry** — add `wikidata_entity` signal columns
   to the existing `entity_authority` kind from 8.3 (same concept, one family,
   two extra columns) rather than inventing a new kind.
10. **[ ] Slice 10 — Fixtures, stored-run regression, tests.**

| Acceptance item | Sub-phase | Status |
| --------------- | --------- | ------ |
| CrUX field CWV family lands at URL grain with origin fallback | 8.1 | Open |
| Wayback freshness family lands at URL grain | 8.2 | Open |
| Knowledge Graph entity-authority family lands at domain grain | 8.3 | Open |
| Wikidata notability signal joins the same entity-authority family as 8.3 | 8.4 | Open |
| Every Phase 8 source stays opt-in behind its own `SEO_RANK_ENABLE_<SOURCE>` flag | 8.1–8.4 | Open |
| `run --stored-run` backfills every new source's missing raw partition without refetching unrelated data | 8.1–8.4 | Open |

### Phase 9 — Manual content capture for blocklisted domains

Domains on the blocklist require manual browser scraping because automated
page-text retrieval is not sufficient. During live DataForSEO pulls, identify
SERP results whose exact returned URL belongs to a blocklisted domain and write
those rows to a separate Parquet handoff for manual completion. Preserve the
exact URL shown by DataForSEO; do not replace it with a canonicalized or
redirected URL.

#### Dev slices

1. **[ ] Slice 1 — Blocklist matching** — define the blocklist source and
   registrable-domain matching rule, while retaining the exact DataForSEO URL
   on each match.
2. **[ ] Slice 2 — Manual-scrape handoff Parquet** — write a separate Parquet
   dataset with `url`, `target_keyword`, `scraped_plain_text`, and
   `scraped_html` columns. The two scraped-content columns are nullable and
   blank when the row is first emitted for manual work; HTML is intended for
   browser source copy/paste.
3. **[ ] Slice 3 — Live-pull integration** — emit one handoff row for every
   blocklisted SERP result, deduplicated by exact `url × target_keyword`, and
   keep non-blocklisted retrieval unchanged.
4. **[ ] Slice 4 — Stored-run and validation coverage** — support rebuilding
   the handoff from stored DataForSEO responses, validate the schema and key
   columns before the Parquet write, and add fixtures/tests for blocked,
   unblocked, subdomain, duplicate, and URL-preservation cases.

| Acceptance item | Sub-phase | Status |
| --------------- | --------- | ------ |
| Exact DataForSEO SERP URL is retained for every blocklisted-domain match | 9.1–9.3 | Open |
| Separate manual-scrape Parquet contains `url`, `target_keyword`, nullable `scraped_plain_text`, and nullable `scraped_html` | 9.2 | Open |
| Initial handoff leaves both scraped-content columns blank | 9.2–9.3 | Open |
| Handoff rows are deduplicated by exact `url × target_keyword` and do not alter non-blocklisted retrieval | 9.3 | Open |
| Stored-run rebuild and schema/key validation are covered by tests | 9.4 | Open |
