# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 4.76 **structured content_parsing capture** so live and stored-run
normalization walks every field in the DataForSEO `content_parsing/live`
`items[]` response, persists each field for analysis, keeps the aggregate page
body for passage splitting, and stores raw HTML alongside parsed content.

API reference:
https://docs.dataforseo.com/v3/on_page/content_parsing/live/

Prior shipped work (Phase 4.75 page_text curation hardening, the run-scoped
Parquet lake, page-level similarity) is documented in `ROADMAP.md` § History.

### Phase 4.76 objective

Walk the full `tasks[].result[].items[]` payload documented for
`on_page/content_parsing/live`, store extractable fields as individual curated
rows for downstream analysis, and continue emitting one synthesized `pages.text`
per URL (Phase 4.75 aggregate path) for `passages`. Persist the crawled page
HTML when `store_raw_html` is enabled.

#### Live request contract (`build_page_text_request`)

Fixed parameters for US English desktop crawls (no JS, no browser rendering):

| Parameter | Value | Rationale |
| --------- | ----- | --------- |
| `switch_pool` | `false` | Default proxy pool; avoid extra pool charges unless rate limits force it |
| `ip_pool_for_scan` | `"us"` | US proxy pool for American English page content |
| `enable_browser_rendering` | `false` | No CWV / full browser emulation (cost + scope) |
| `enable_javascript` | `false` | Static HTML parse only |
| `accept_language` | `"en-US"` | American English `Accept-Language` (API supports `xx`, `xx-XX`, `xxx-XX`, etc.) |
| `browser_preset` | `"desktop"` | Desktop viewport preset when browser params apply |
| `store_raw_html` | `true` | Retain HTML for audit, replay, and non-parsed analysis |

**Locale note:** `page_text` crawls always use `ip_pool_for_scan: "us"` and
`accept_language: "en-US"` regardless of `--location` / `--language`. Keyword
expansion and SERP requests still honor those CLI flags. A run like
`--language fr --location France` therefore returns French SERP results but
fetches page HTML through the US English desktop contract above. This is
intentional for Phase 4.76; locale-aligned page crawls are out of scope unless
a later phase opens non-US proxy pools.

#### Progress

**Slices:** 2 of 5 shipped, 3 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Request contract | Provider | Shipped | `build_page_text_request()` emits the fixed parameter set above |
| 2 | Item field decoder | Curated | Shipped | Decoder walks `items[]` fields (`type`, `fetch_time`, `status_code`, `page_content` tree, `page_as_markdown`, `ratings`, `offers`, `comments`, `contacts`, …) per API docs |
| 3 | Per-field storage | Curated | Open | New curated table(s): one row per extracted field/element with stable ids and JSON path metadata |
| 4 | Aggregate + HTML wiring | Curated | Open | `pages.text` unchanged (merged content); `raw_html` stored per page/response; passages still from aggregate text only |
| 5 | Tests and re-normalize | Curated | Open | Fixtures cover multi-field items, HTML retention, and stored-run normalize |

**Remaining to close Phase 4.76:** slices 3–5.

#### Dev slices

1. **[x] Slice 1 — Request contract**
   - Update `build_page_text_request()` in `src/seo_rank/dataforseo.py`.
   - Tests: `test_build_page_text_request_uses_content_parsing_endpoint` asserts
     the full parameter object.

2. **[x] Slice 2 — Item field decoder**
   - Add a structured decoder for every documented `items[]` field and nested
     `page_content` region (`header`, `footer`, `main_topic`, `secondary_topic`,
     `primary_content`, `secondary_content`, `table_content`, `ratings`, `offers`,
     `comments`, `contacts`, link `urls`, table cells, topic metadata, etc.).
   - Return both a list of field records (path, field name, value type, text or
     serialized payload) and the aggregate text string.

3. **[ ] Slice 3 — Per-field storage**
   - Define curated schema for `page_content_fields` (or equivalent): `run_id`,
     `response_id`, `page_id`, `field_path`, `field_name`, `value_type`, `text`,
     `structured_value` (JSON), `ordinal`.
   - Sink via existing validation-before-sink contract.

4. **[ ] Slice 4 — Aggregate + HTML wiring**
   - `build_pages_and_passages_frame()` emits aggregate `pages` / `passages` as
     today; add `raw_html` on `pages` or a sibling `page_html` table.
   - Fetch or attach HTML from the OnPage Raw HTML path when
     `store_raw_html=true` (per DataForSEO docs).

5. **[ ] Slice 5 — Tests and re-normalize**
   - Extend `test_dataforseo_requests.py` and `test_run_normalize.py` with
     multi-field fixtures from the API reference.
   - Re-normalize smoke on a stored live run with HTML + per-field rows.

#### Phase 4.76 intent

- **Individual fields** — every `items[]` field listed in the
  [content_parsing/live](https://docs.dataforseo.com/v3/on_page/content_parsing/live/)
  response reference is addressable in curated storage for analysis (topic
  titles, section text, table cells, ratings, offers, contacts, etc.).
- **Aggregate content** — one merged `pages.text` per URL (Phase 4.75 behavior)
  for passage splitting and similarity features.
- **Raw HTML** — store full page HTML for pages where the crawl succeeds, linked
  by `page_id` / `response_id`.
- **Stable US English desktop crawls** — request parameters above on every live
  `page_text` call.

See `ROADMAP.md` for Phase 5 (OLS) and Phase 5.5 (passage/domain scoring).

## In Scope (current and near-term)

- `build_page_text_request()` and item-field decoders in `src/seo_rank/dataforseo.py`.
- `build_pages_and_passages_frame()` and new curated sinks in
  `src/seo_rank/data/normalize.py`.
- Unit tests in `tests/unit/test_dataforseo_requests.py` and
  `tests/unit/test_run_normalize.py`.
- Re-normalize validation on stored live runs (e.g. `seo-rank normalize --run …`).

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
- `enable_javascript`, `enable_browser_rendering`, or non-US proxy pools unless
  a later phase explicitly opens them.

## Phase 4.76 acceptance criteria

**Status:** 1 of 5 slices shipped, 4 open.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `build_page_text_request()` uses US English desktop contract (`switch_pool=false`, `ip_pool_for_scan=us`, `accept_language=en-US`, `browser_preset=desktop`, JS/rendering off, `store_raw_html=true`) | 1 | Complete |
| Every documented `items[]` field decodes to storable records | 2 | Complete |
| Per-field rows land in curated Parquet with stable ids | 3 | Not started |
| Aggregate `pages.text` preserved; raw HTML stored per page | 4 | Not started |
| Unit tests + stored-run re-normalize cover fields, aggregate, and HTML | 5 | Not started |

- [x] Live `page_text` requests emit the fixed parameter set. *(Slice 1.)*
- [x] Item decoder walks full `items[]` / `page_content` tree per API docs.
  *(Slice 2.)*
- [ ] Curated per-field table(s) materialize on normalize. *(Slice 3.)*
- [ ] `pages` / `passages` aggregate path unchanged; HTML persisted. *(Slice 4.)*
- [ ] Tests and re-normalize smoke pass. *(Slice 5.)*

---

## Completed: Phase 4.75 (page_text curation hardening)

### Phase 4.75 objective

Close gaps between live DataForSEO `page_text` response shapes and curated
`pages` / `passages` tables. The CLI and normalize path must share one decoder
(`parsed_page_text()`); empty or failed crawls must not pollute curated tables.

#### Progress

**Slices:** 3 of 3 shipped, 0 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Nested `page_content` decode | Curated | Shipped | `parsed_page_text()` reads `tasks[].result[].items[].page_content`; `build_pages_and_passages_frame()` uses shared parser |
| 2 | Multi-region text extraction | Curated | Shipped | `_extract_page_content_text()` merges `header` and other `page_content` keys, not only `main_topic` |
| 3 | Empty crawl row filter | Curated | Shipped | Skip `page_text` rows with no URL and no text (mirrors CLI `if page_text`); fixes duplicate `page_id` warnings |

**Phase 4.75:** complete.

**Related polish:** `FIXUPS.md` § Phase 4.75 (S475-01 tracks slice 3).

### Dev slices

1. **[x] Slice 1 — Nested `page_content` decode**
   - Extend `parsed_page_text()` for live DataForSEO nested payloads
     (`page_content`, `page_as_markdown`, task-level URL fallback).
   - Route `build_pages_and_passages_frame()` through `parsed_page_text()` instead
     of brittle `tasks[0].result[0]` indexing.
   - Tests: `test_parsed_page_text_extracts_nested_page_content`,
     `test_build_pages_and_passages_frame_parses_nested_page_content`.

2. **[x] Slice 2 — Multi-region text extraction**
   - Walk all relevant `page_content` regions (e.g. `header`, not only
     `main_topic` primary/secondary/table sections).
   - Merge extracted copy into the synthesized page `text` used by normalization
     and passage splitting.
   - Tests: multi-region fixtures in `test_dataforseo_requests.py` and
     `test_run_normalize.py`.

3. **[x] Slice 3 — Empty crawl row filter**
   - In `build_pages_and_passages_frame()`, `continue` when `parsed_page_text()`
     yields no URL or no text.
   - Align stored-run behavior with CLI collection (`if page_text` filter).
   - Tests: empty-crawl fixture (`crawl_status: "Page content is empty"`) produces
     no `pages` row; no duplicate `page_id` on re-normalize of affected runs.

### Phase 4.75 acceptance criteria

**Status:** complete (3 of 3 slices shipped).

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Nested live `page_content` payloads decode without `KeyError` | 1 | Complete |
| Header and other `page_content` regions included in page `text` | 2 | Complete |
| Empty or failed crawls omitted from `pages` / `passages` | 3 | Complete |

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
