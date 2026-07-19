# Phase 6 — Backlinks integration

DataForSEO Backlinks API: fetch referring domains, backlinks, and domain/page
rank for each SERP URL. Register as new signal families at the panel grain.

**Primary decision (v1):** two families — `backlinks_counts`
(`backlinks_count`, `referring_domains_count`, `rank`) and
`backlinks_domain_authority` (`domain_rank`); both at
`target_keyword_id × canonical_url_hash` grain; joined via `raw_responses`
`endpoint=backlinks_*` partitions.

#### Dev slices

**Progress:** 0 of 6 shipped, 6 open.

1. **[ ] Slice 1 — Backlinks fetch + raw lake**
   - `dataforseo_backlinks.py`: `fetch_backlinks_summary()`,
     `fetch_referring_domains()` per SERP URL; partitions under
     `raw_responses/endpoint=backlinks_summary|referring_domains`.
   - Tests: injected transport; raw schema round-trip.

2. **[ ] Slice 2 — Curated + feature marts**
   - `build_backlinks_frame()` → `backlinks_summary_curated` +
     `backlinks_features` mart; validation bounds on counts.
   - Tests: `test_feature_marts.py`.

3. **[ ] Slice 3 — Family registration + stats wiring**
   - `backlinks` kind in `VALID_SIGNAL_FAMILY_KINDS`; families appended to
     spec; stats engine consumes.
   - Tests: `test_stats_families.py`, `test_stats_family_artifacts.py`.

4. **[ ] Slice 4 — CLI + artifacts**
   - `--live-backlinks` flag; `#### Family: backlinks_*` blocks in stats
     artifacts.
   - Tests: `test_cli_run.py`.

5. **[ ] Slice 5 — Golden fixtures**
   - Synthetic panel with known backlinks ↔ rank relationship.
   - Tests: `test_stats_golden_fixtures.py` extension.

6. **[ ] Slice 6 — Docs**
   - `ARCHITECTURE.md` (mart + family), `TESTING.md`, cost notes (Backlinks
     API pricing per task).

#### Phase 6 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Backlinks raw lake partitions with schema round-trip | 1 | Open |
| Feature mart with bounded validation | 2 | Open |
| Families registered and stats consume them | 3 | Open |
| CLI flag + artifact blocks | 4 | Open |
| Golden fixtures prove known relationship | 5 | Open |

---

# Phase 6.1 — Within-keyword relative similarity (partially shipped)

Moves the per-backend rank/pct/z columns into `analysis_mart.v2` and adds the
relative-similarity robustness path. Slices 11–14 in the Phase 5 table.

**Progress:** 2 of 4 slices shipped (ranks module + unit tests done; mart
wiring, stats sensitivity, CLI surface open).

See Phase 5 slice table rows 11–14 for specification and status.

---

# Phase 6.2 — OnPage integration

DataForSEO OnPage API: crawl each SERP URL for technical SEO metrics (page
speed, mobile usability, structured data, hreflang, canonical, meta tags).
Register as new signal families.

**Primary decision (v1):** `onpage_technical` family
(`page_speed_score`, `mobile_usability_score`, `has_structured_data`,
`has_canonical`, `meta_robots_index`); `onpage_content` family
(`word_count`, `internal_links_count`, `external_links_count`); panel grain.

#### Dev slices

**Progress:** 0 of 6 shipped, 6 open.

1. **[ ] Slice 1 — OnPage fetch + raw lake**
   - `dataforseo_onpage.py`: `fetch_onpage_summary()` per URL; partition
     `raw_responses/endpoint=onpage_summary`.
   - Tests: injected transport; raw schema.

2. **[ ] Slice 2 — Curated + feature marts**
   - `build_onpage_frame()` → `onpage_features` mart; validation bounds.
   - Tests: `test_feature_marts.py`.

3. **[ ] Slice 3 — Family registration + stats wiring**
   - `onpage` kind; families appended; stats consume.
   - Tests: `test_stats_families.py`, `test_stats_family_artifacts.py`.

4. **[ ] Slice 4 — CLI + artifacts**
   - `--live-onpage` flag; artifact blocks.
   - Tests: `test_cli_run.py`.

5. **[ ] Slice 5 — Golden fixtures**
   - Known onpage ↔ rank relationship.
   - Tests: `test_stats_golden_fixtures.py` extension.

6. **[ ] Slice 6 — Docs**
   - `ARCHITECTURE.md`, `TESTING.md`, cost notes.

#### Phase 6.2 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| OnPage raw lake partition with schema round-trip | 1 | Open |
| Feature mart with bounded validation | 2 | Open |
| Families registered and stats consume them | 3 | Open |
| CLI flag + artifact blocks | 4 | Open |
| Golden fixtures prove known relationship | 5 | Open |

---

# Phase 7 — Report and dashboard improvements

Richer `report.md` and optional HTML dashboard: per-keyword factor rankings,
family comparison tables, trend lines across runs (requires Phase 12 panel).

**Primary decision (v1):** extend `stats_report.md` with a `## Family
comparison` section (per-family median ρ, NDCG@20, actionable flag side by
side); optional `report.html` via Jinja2 template with embedded charts (no
external JS dependencies).

#### Dev slices

**Progress:** 0 of 4 shipped, 4 open.

1. **[ ] Slice 1 — Family comparison table in `stats_report.md`**
   - Side-by-side per-family metrics at each rank depth.
   - Tests: `test_stats_family_artifacts.py` extension.

2. **[ ] Slice 2 — HTML dashboard scaffold**
   - Jinja2 template; family comparison chart (bar chart of median ρ); NDCG
     distribution chart.
   - Tests: HTML output exists and contains expected sections.

3. **[ ] Slice 3 — Cross-run trend lines**
   - Join multiple runs on keyword overlap; plot metric trends over time
     (requires Phase 12 panel for real data; synthetic fixture for tests).
   - Tests: trend data structure correct.

4. **[ ] Slice 4 — Golden fixtures + docs**
   - Known multi-family fixture; assert comparison table ordering.

#### Phase 7 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Family comparison table in report | 1 | Open |
| HTML dashboard with charts | 2 | Open |
| Cross-run trend lines | 3 | Open |
| Golden fixtures prove ordering | 4 | Open |

---

# Phase 8 — Performance and cost optimization

Reduce API spend and runtime: batch DataForSEO tasks, cache Gemini embeddings
across runs (identity-keyed), parallelize page_text fetches, and add cost
estimation before live runs.

**Primary decision (v1):** (a) DataForSEO task batching (up to 100 tasks per
POST where the API supports it); (b) Gemini embedding cache keyed by
`(model, text_sha256)` in a persistent store; (c) `concurrent.futures` for
page_text fetches with rate limiting; (d) `--estimate-cost` dry-run mode that
reports projected API calls and cost before executing.

#### Dev slices

**Progress:** 0 of 5 shipped, 5 open.

1. **[ ] Slice 1 — DataForSEO task batching**
   - Batch multiple keywords' SERP tasks into one POST where supported.
   - Tests: batch size respected; results correctly split.

2. **[ ] Slice 2 — Gemini embedding cache**
   - Persistent cache (SQLite or Parquet) keyed `(model, text_sha256)`;
     lookup before API call; store after.
   - Tests: second run with same texts → zero new API calls.

3. **[ ] Slice 3 — Parallel page_text fetches**
   - Thread pool with configurable concurrency + rate limiting.
   - Tests: concurrency limit respected; results correct.

4. **[ ] Slice 4 — Cost estimation mode**
   - `--estimate-cost` flag: count projected API calls per endpoint, apply
     pricing table, report total.
   - Tests: estimation matches actual call count on a live run.

5. **[ ] Slice 5 — Golden fixtures + docs**
   - Cache hit/miss scenarios; cost estimation accuracy.

#### Phase 8 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Task batching reduces API calls | 1 | Open |
| Embedding cache eliminates duplicate calls | 2 | Open |
| Parallel fetches with rate limiting | 3 | Open |
| Cost estimation within 10% of actual | 4 | Open |

---

# Phase 9 — Operational hardening

Stored-run rebuild, schema/key validation, and operational runbooks.

#### Dev slices

**Progress:** 0 of 4 shipped, 4 open.

1. **[ ] Slice 1 — Stored-run rebuild validation**
   - Verify that `--stored-run` replay produces identical parquet trees to the
     original run (schema, keys, row counts).
   - Tests: `test_stored_run_rebuild.py`.

2. **[ ] Slice 2 — Schema/key validation**
   - Assert join keys are unique at expected grains; assert required columns
     present; assert no null primary keys.
   - Tests: `test_schema_validation.py`.

3. **[ ] Slice 3 — Operational runbook**
   - `OPERATIONS.md`: common failure modes, recovery procedures, cost
     monitoring, credential rotation.

4. **[ ] Slice 4 — CI hardening**
   - Integration tests in CI; golden fixture regression in CI; lint/type
     checks.

#### Phase 9 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Stored-run rebuild produces identical trees | 1 | Open |
| Schema/key validation catches violations | 2 | Open |
| Operational runbook covers common failures | 3 | Open |
| CI runs integration tests and golden fixtures | 4 | Open |
