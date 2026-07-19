<!-- Part of the split roadmap. Index: ROADMAP.md -->

### Phase 5.75 — BGE Google-like scoring pipeline

Extend the live BGE path beyond single-shot `bge-reranker-v2-m3` on full page
text so similarity features better mirror hybrid search-engine retrieval
(lexical recall + neural rerank). Gemini backends stay separate.

- **Hybrid lexical signal** — add a BM25 or BGE-M3 sparse score per
  `(keyword, page)` and fuse it with the cross-encoder reranker output.
  Normalize lexical and neural scores before fusion (raw BM25 and cosine/rerank
  scales differ). Persist fused score alongside existing `bge` raw/normalized
  fields for Phase 5 OLS comparison.
- **Two-stage retrieve-then-rerank** — first stage: bi-encoder retrieval with
  `BAAI/bge-m3` or `BAAI/bge-large-en-v1.5` (query instruction on keyword
  only for v1.5; documents unmodified). Second stage: rerank the SERP candidate
  set with `BAAI/bge-reranker-v2-m3`. Expose retrieval score, rerank score, and
  optional combined rank for observational analysis against observed Google
  positions.

> **Update (Phase 10):** the bi-encoder retrieval stage (Slice 2 below) is
> promoted into Phase 10 Slice 3 as the live dual-encoder write path for the
> `embeddings` mart — its vectors become the forward-looking source for
> centroid/radius/focus computation. This phase remains the scoring-pipeline
> context; Phase 10 owns vector persistence.

#### Dev slices

1. **[ ] Slice 1 — Lexical / sparse feature**
   - Implement BM25 (Pyserini or equivalent) or BGE-M3 sparse weights per page.
   - Score normalization and fusion contract with existing `similarity_scores`.

2. **[ ] Slice 2 — Bi-encoder retrieval stage**
   - Embed keyword + page corpus with `bge-m3` or `bge-large-en-v1.5`.
   - Emit dense retrieval score per SERP URL before reranking.

3. **[ ] Slice 3 — Pipeline wiring and tests**
   - Wire retrieve → rerank in CLI live path (`--live-bge`) and curated
     `similarity_scores` schema.
   - Unit tests for score shaping; optional env-gated integration smoke.

### Phase 5.9 — Crash-Safe DataForSEO Persistence and Reuse

Persist validated DataForSEO responses immediately after each request returns,
so a crash leaves behind usable partial data instead of only end-of-run output.
When a new run matches a prior pull by effective request configuration, prompt
the user before reusing the existing DataForSEO data. Matching is based on the
effective config, not raw argv text: compare the seed plus every
request-affecting flag actually used in the run, treating omitted flags as
their effective defaults.

**Primary behavior**

- Save each validated DataForSEO response as soon as it is received.
- Update the run catalog incrementally so crash recovery reflects what is
  already on disk.
- Store provenance for the effective DataForSEO request config, including the
  seed and all request-affecting flags used in the run.
- Treat omitted flags as their effective defaults when comparing a new run to
  prior pulls.
- Prompt the user before reusing matching prior DataForSEO data.
- Fail explicitly in non-interactive mode if reuse would otherwise require a
  prompt.
- Record the reuse decision in run metadata so operators can tell whether a
  run reused prior data or performed fresh pulls.

**Test plan**

- Crash-safety test: simulate failure after the first DataForSEO response and
  verify that the first response is already on disk.
- Reuse-matching test: confirm the effective config is compared by seed plus
  the actual flag set in use.
- Prompt-path test: verify the CLI asks before reusing a matching prior
  DataForSEO pull.
- Non-interactive test: verify matching data does not get reused implicitly.
- Catalog/provenance test: confirm the saved metadata is sufficient to identify
  prior matching pulls.

### Phase 5.91 — Backlinks two-call dofollow correctness

The 2026-07-03 backlinks summary migration (`/v3/backlinks/summary/live`)
shipped `_dofollow_backlinks_count()` deriving "total dofollow backlinks" by
subtracting a fabricated `referring_links_attributes.nofollow` field that
does not exist in real DataForSEO summary responses — every live run
silently persisted `dofollow_backlinks_count = 0`. A true dofollow count
requires a **second, filtered** call to the same endpoint
(`backlinks_filters: ["dofollow", "=", true]`); it cannot be derived from one
unfiltered call. This phase replaces the one-call design with a two-call
design end-to-end: request building, separate raw partitions, curated
merge/null semantics, and an expanded curated schema capturing the fields
DataForSEO actually returns.

**Non-negotiables:** missing dofollow data is `null` (never defaulted to
`0`), the two call variants persist to **separate** raw partitions
(`endpoint=backlinks_summary`, `endpoint=backlinks_dofollow_summary`, not one
partition distinguished only by a metadata tag), and the curated schema is
expanded now rather than deferred.

**Out of scope:** root-domain backlink rollups (this stays page-level, one
row per SERP URL); changing `backlinks_status_type` off `"live"` or
`include_subdomains` off `true`; concurrency changes to DataForSEO request
execution.

**Unblocks:** Phase 6.2 (Backlinks count family and analysis surfacing) —
shipped against the expanded schema and separate
`endpoint=backlinks_summary` / `endpoint=backlinks_dofollow_summary`
partitions.

#### Dev slices

**Progress:** 6 of 6 shipped.

1. **[x] Slice 1 — Request builders, fixtures, and schema (`dataforseo.py`)**
   - `format_backlinks_target()` target-format helper (domain strip vs.
     absolute page URL passthrough); shared `_build_backlinks_base_body()`
     (`target`, `include_subdomains: true`, `backlinks_status_type: "live"`,
     `internal_list_limit: 1000`).
   - `build_backlinks_summary_request()` (renamed from
     `build_backlinks_request`) and `build_backlinks_dofollow_summary_request()`
     both build off the shared base body; the latter layers
     `BACKLINKS_DOFOLLOW_FILTERS`.
   - `fixture_backlinks_response(url, *, dofollow_only=False)` drops the
     fabricated `referring_links_attributes.nofollow` derivation; dofollow
     fixture returns `backlinks=35` directly. New
     `fixture_backlinks_response_for_request_body()` picks the fixture
     variant from a request body's `backlinks_filters`.
   - Restored per-variant `DATAFORSEO_RESPONSE_SCHEMAS["backlinks_summary"]`
     (`target`, `backlinks`, `referring_domains`) and
     `["backlinks_dofollow_summary"]` (`target`, `backlinks`); malformed/missing
     aggregates now hard-fail validation instead of silently coercing to zero.
   - Top-level `response.status_code == 20000` check added to
     `raise_for_failed_dataforseo_tasks()` (shared across all DataForSEO
     endpoints); per-task `cost` logging; exponential-backoff retry in
     `execute_dataforseo_request()` on 429/5xx only, bounded attempts,
     injectable `sleep`.

2. **[x] Slice 2 — Two-call fetch, separate partitions, dedupe key (`cli.py`)**
   - `fetch_dataforseo_backlinks_for_urls()` takes a `variants` sequence
     (default: both) and issues one request per `(url, variant)`, tagging
     full request metadata (`target`, `variant`, `include_subdomains`,
     `backlinks_status_type`, `internal_list_limit`, `backlinks_filters`
     when present).
   - `backlink_raw_response_key()` is now a `(target_keyword, url, variant)`
     3-tuple (previously 2-tuple) — the critical fix preventing one variant
     from silently overwriting the other in
     `merge_backlink_raw_response_rows()` / `rewrite_backlink_endpoint_partition()`;
     missing `variant` defaults to `"summary"` for legacy rows.
   - `persist_backlink_raw_responses()` splits records by endpoint and writes
     each to its own partition directory
     (`endpoint=backlinks_summary`, `endpoint=backlinks_dofollow_summary`).
   - Resume/backfill (`build_resumed_keyword_result`) now tracks existing
     `(url, variant)` pairs and fetches only the missing variant(s) per URL,
     not always both.
   - `raw_provider_data["dataforseo"]` carries two collections
     (`backlinks_summary`, `backlinks_dofollow_summary`) everywhere a
     keyword result's provider data is built, merged, or replayed
     (`build_keyword_result_from_responses`, `build_raw_response_records`,
     `merge_stored_run_cli_overlay`, textrazor-only/offline payload builders).

3. **[x] Slice 3 — Curated merge, expanded schema, null semantics (`normalize.py`)**
   - `build_backlinks_frame()` groups raw records from both partitions (plus
     legacy `endpoint=backlinks` rows, read-compatibly as the summary
     variant) by `(target_keyword, url)` and emits one curated row per URL.
   - `backlinks_count` / `referring_domains_count` come from the summary
     variant; `dofollow_backlinks_count` comes directly from the dofollow
     variant's `backlinks` field (no subtraction). When the dofollow variant
     is absent: `dofollow_backlinks_count = null`,
     `backlinks_metrics_complete = false`.
   - Curated schema gains: `rank`, `backlinks_spam_score`,
     `target_spam_score`, `new_backlinks`, `lost_backlinks`,
     `new_referring_domains`, `lost_referring_domains`, `referring_pages`,
     `referring_main_domains`, `referring_ips`, `referring_subnets`,
     `broken_backlinks`, `broken_pages`, `referring_domains_nofollow`,
     `crawled_pages`, `internal_links_count`, `external_links_count`,
     `first_seen`, `lost_date`, `dofollow_referring_domains_count`,
     distribution maps as JSON-string columns (`referring_links_types_json`,
     `referring_links_tld_json`, `referring_links_platform_types_json`,
     `referring_links_semantic_locations_json`,
     `referring_links_attributes_json`, `referring_links_countries_json`),
     and traceability (`summary_response_id`, `dofollow_summary_response_id`,
     `backlinks_metrics_complete`).
   - Drops `_dofollow_backlinks_count()`'s items-loop and
     `referring_links_attributes` subtraction path entirely.

4. **[x] Slice 4 — Tests (TDD)**
   - Request builders: exact unfiltered/dofollow bodies; target-format rules.
   - Response handling: top-level and task-level failure surfacing; cost
     logging; retry fires only on retryable errors, succeeds on 2nd attempt.
   - Raw persistence: separate partitions; dedupe key includes `variant`
     (fix `test_raw_response_merge.py`); resume fetches only missing
     variants; mid-loop failure preserves completed rows (3 URLs, failure on
     URL 3 → 4 rows persisted).
   - Normalization: paired responses → one curated row with all three counts
     plus expanded columns; missing dofollow → `null` +
     `backlinks_metrics_complete = false` (remove any test asserting `0`);
     malformed aggregates hard-fail; distribution maps serialize to JSON.
   - Update stale `test_validate_dataforseo_response_accepts_backlinks_live_shape`
     and siblings in `test_dataforseo_requests.py` to real new-shape fields.
   - CLI: exactly 2 summary calls per SERP URL (3 URLs → 6 calls, 6 raw rows
     split across two partitions); zero calls to `/v3/backlinks/backlinks/live`.

5. **[x] Slice 5 — Docs**
   - Updated `README.md`, `ROADMAP.md` backlog/history, `ARCHITECTURE.md`, and
     `TESTING.md`: two-call pattern (`2 calls × N` SERP URLs), separate
     `endpoint=backlinks_summary` / `endpoint=backlinks_dofollow_summary`
     partitions, ~$0.04/target, null dofollow semantics.

6. **[x] Slice 6 — Verification**
   - Targeted backlinks test run, then full `tests/unit` suite (offline; green).
   - Manual `--live-providers` trace with real DataForSEO credentials (operator
     step; not CI-runnable): confirm 2 raw records per URL across the two
     partitions and 1 correct curated row per URL. Offline `--dry-run` path is
     covered by the unit suite.

**Implementation order:** Slice 1 → Slice 2 → Slice 3 (each depends on the
previous). Slice 4 can start once Slice 1 lands and grows alongside Slices
2–3. Slice 5 after Slice 3. Slice 6 last.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Dofollow count sourced from a real filtered call, never fabricated | 1, 3 | Shipped |
| Raw variants land in separate `endpoint=` partitions | 1, 2 | Shipped |
| Dedupe key prevents one variant overwriting the other | 2 | Shipped |
| Resume fetches only missing variant(s) per URL | 2 | Shipped |
| Curated row has expanded columns + null/`backlinks_metrics_complete` semantics | 3 | Shipped |
| Tests cover request bodies, persistence, normalization, and CLI call counts | 4 | Shipped |
| Docs describe the two-call pattern and cost | 5 | Shipped |
| Full unit suite green | 6 | Shipped |
