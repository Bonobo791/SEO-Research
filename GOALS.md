# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 4.77 **adapter schema validation** so every DataForSEO response is
validated at the provider adapter boundary against explicit endpoint schemas
before normalization or curated writes. Schema drift must fail loud with a typed
parse error, not leak silently into downstream tables.

API reference:
https://docs.dataforseo.com/v3/on_page/content_parsing/live/

Prior shipped work (Phase 4.76 structured content_parsing capture, the run-scoped
Parquet lake, page-level similarity) is documented in `ROADMAP.md` § History.
Completed: Phase 4.76 is recorded there as shipped work.

### Phase 4.77 objective

Validate every DataForSEO response at the adapter boundary against explicit
endpoint schemas before normalization or curated writes. Required fields,
types, and known semantics must be enforced; unvalidated payloads must not reach
normalization or re-normalization code.

#### Progress

**Slices:** 3 of 3 shipped, 0 open.

| # | Slice | Layer | Status | Primary deliverable |
| - | ----- | ----- | ------ | ------------------- |
| 1 | Schema contracts | Provider | Shipped | Explicit schemas for `keyword_expansion`, `serp`, and `content_parsing/live` payloads |
| 2 | Boundary enforcement | Provider | Shipped | Live and stored-run responses validated at the adapter seam with endpoint-scoped parse errors |
| 3 | Drift coverage | Provider | Shipped | Fixtures for missing fields, type mismatches, and valid pass-through cases |

**Remaining to close Phase 4.77:** none.

#### Dev slices

1. **[x] Slice 1 — Schema contracts**
   - Define explicit schemas for DataForSEO adapter payloads.
   - Choose the smallest library that gives typed parse errors in Python
     (`Pydantic` or JSON Schema validation).

2. **[x] Slice 2 — Boundary enforcement**
   - Validate live and stored-run DataForSEO responses at the adapter seam.
   - Surface endpoint-specific parse errors before curated normalization.

3. **[x] Slice 3 — Drift coverage**
   - Add fixtures for missing fields, type mismatches, and extra/renamed
     `content_parsing/live` fields.
   - Verify valid responses still pass through unchanged.

#### Phase 4.77 intent

- **boundary validation** — parse `keyword_expansion`, `serp`,
  `content_parsing/live`, and stored-run raw responses with explicit schemas in
  the provider adapter layer.
- **Typed errors** — raise endpoint-scoped parse errors when required fields
  are missing, types drift, or unknown semantics would otherwise flow downstream.
- **No silent fallback** — keep raw JSON for audit, but do not hand unvalidated
  payloads to normalization or re-normalization code.
- **Tests** — fixture drift cases for `content_parsing/live`, a valid payload
  pass-through case, and stored-run failure coverage.

See `ROADMAP.md` for Phase 5 (10 dev slices + acceptance criteria) and Phase 5.5
(passage/domain scoring). Phase 5 backlog is fully specified there; retarget
`GOALS.md` active scope when Phase 5 implementation starts.

## In Scope (current and near-term)

- Explicit endpoint schemas and validation helpers in `src/seo_rank/dataforseo.py`
  (or a sibling provider schema module).
- Adapter-boundary enforcement for live and stored-run DataForSEO responses.
- Unit tests with drift fixtures and valid pass-through cases in
  `tests/unit/test_dataforseo_requests.py` and related normalize tests.

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
- Changing Phase 4.76 crawl contract, per-field storage, or HTML wiring unless
  schema validation requires it.

## Phase 4.77 acceptance criteria

**Status:** 3 of 3 slices shipped, 0 open.

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Explicit schemas cover `keyword_expansion`, `serp`, and `content_parsing/live` | 1 | Complete |
| Adapter validates live and stored-run responses before normalization | 2 | Complete |
| Drift fixtures fail loud; valid payloads pass through unchanged | 3 | Complete |

- [x] Endpoint schemas defined with typed parse errors. *(Slice 1.)*
- [x] Adapter boundary rejects unvalidated payloads before curated writes.
  *(Slice 2.)*
- [x] Drift and pass-through tests cover `content_parsing/live` and stored-run
  paths. *(Slice 3.)*

---

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
