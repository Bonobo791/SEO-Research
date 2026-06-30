# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 4.75 **page_text curation hardening** so stored-run normalization
produces complete, correct `pages` and `passages` from live DataForSEO
`content_parsing` payloads.

Prior shipped work (page-level similarity and the run-scoped Parquet lake) is
documented in `ROADMAP.md` § History.

### Phase 4.75 objective

Close gaps between live DataForSEO `page_text` response shapes and curated
`pages` / `passages` tables. The CLI and normalize path must share one decoder
(`parsed_page_text()`); empty or failed crawls must not pollute curated tables.

#### Progress

**Slices:** 1 of 3 shipped, 2 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Nested `page_content` decode | Curated | Shipped | `parsed_page_text()` reads `tasks[].result[].items[].page_content`; `build_pages_and_passages_frame()` uses shared parser |
| 2 | Multi-region text extraction | Curated | Open | `_extract_page_content_text()` merges `header` and other `page_content` keys, not only `main_topic` |
| 3 | Empty crawl row filter | Curated | Open | Skip `page_text` rows with no URL and no text (mirrors CLI `if page_text`); fixes duplicate `page_id` warnings |

**Remaining to close Phase 4.75:** slices 2–3.

**Related polish:** `FIXUPS.md` § Phase 4.75 (S475-01 tracks slice 3).

### Dev slices

1. **[x] Slice 1 — Nested `page_content` decode**
   - Extend `parsed_page_text()` for live DataForSEO nested payloads
     (`page_content`, `page_as_markdown`, task-level URL fallback).
   - Route `build_pages_and_passages_frame()` through `parsed_page_text()` instead
     of brittle `tasks[0].result[0]` indexing.
   - Tests: `test_parsed_page_text_extracts_nested_page_content`,
     `test_build_pages_and_passages_frame_parses_nested_page_content`.

2. **[ ] Slice 2 — Multi-region text extraction**
   - Walk all relevant `page_content` regions (e.g. `header`, not only
     `main_topic` primary/secondary/table sections).
   - Merge extracted copy into the synthesized page `text` used by normalization
     and passage splitting.
   - Tests: multi-region fixtures in `test_dataforseo_requests.py` and
     `test_run_normalize.py`.

3. **[ ] Slice 3 — Empty crawl row filter**
   - In `build_pages_and_passages_frame()`, `continue` when `parsed_page_text()`
     yields no URL and no text.
   - Align stored-run behavior with CLI collection (`if page_text` filter).
   - Tests: empty-crawl fixture (`crawl_status: "Page content is empty"`) produces
     no `pages` row; no duplicate `page_id` on re-normalize of affected runs.

See `ROADMAP.md` for Phase 5 (OLS) and Phase 5.5 (passage/domain scoring).

## In Scope (current and near-term)

- `parsed_page_text()` and page-content extractors in `src/seo_rank/dataforseo.py`.
- `build_pages_and_passages_frame()` in `src/seo_rank/data/normalize.py`.
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
- New lake tables, feature marts, or CLI subcommands (shipped in prior phase).

## Phase 4.75 acceptance criteria

**Status:** 1 of 3 slices shipped, 2 open.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Nested live `page_content` payloads decode without `KeyError` | 1 | Complete |
| Header and other `page_content` regions included in page `text` | 2 | Not started |
| Empty or failed crawls omitted from `pages` / `passages` | 3 | Not started |

- [x] `parsed_page_text()` handles nested DataForSEO `content_parsing` items and
  returns `{url, title, text}`. *(Slice 1.)*
- [x] `build_pages_and_passages_frame()` uses `parsed_page_text()` on
  `response_body_bytes`. *(Slice 1.)*
- [ ] Multi-region `page_content` text merged into normalized page body.
  *(Slice 2.)*
- [ ] Normalize skips page_text responses with no extractable URL or text.
  *(Slice 3.)*
- [ ] Unit tests cover multi-region and empty-crawl fixtures. *(Slices 2–3.)*

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
