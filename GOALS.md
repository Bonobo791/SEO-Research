# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build the first offline-verifiable Python CLI scaffold for SEO ranking
similarity research.

### Phase 1 status: **complete**

The offline scaffold can:

1. Accept a seed keyword and run configuration through the CLI. **Done**
2. Expand the seed into a capped keyword set using mocked provider data. **Done**
3. Normalize organic top-20 SERP results. **Done**
4. Normalize parsed page text into usable passages. **Done**
5. Compute deterministic similarity features from fixture embeddings. **Done**
6. Write JSON and Markdown run artifacts without network calls. **Done**

Additional Phase 1 delivery: offline TextRazor entity capture with
`--skip-textrazor` support.

**Known Phase 1 limitation:** SERP, page text, and similarity run against the
first expanded keyword only, not every keyword in the cluster.

### Next objective (Phase 2)

Live provider boundaries: DataForSEO and TextRazor request construction,
authentication validation, and integration tests behind explicit flags.

## In Scope (current and near-term)

- Python CLI under `src/seo_rank/`.
- Pytest coverage under `tests/unit/`.
- Offline DataForSEO and TextRazor fixtures with normalization.
- JSON + Markdown run artifacts for dry runs.
- Product documentation in root markdown: `ARCHITECTURE.md`, `GOALS.md`,
  `ROADMAP.md`, `README.md`, `TESTING.md`.
- Explicit credential validation before live runs (Phase 2).

## Out Of Scope

- Live provider calls by default until Phase 2+ gates exist.
- Direct page fetching outside DataForSEO.
- Entity-derived ranking features.
- Causal claims about ranking factors.
- CI, deployment, databases, cache layers, production hosting.
- Live similarity backends and `statsmodels` analysis until their phases ship.

## Acceptance Criteria (Phase 1)

- [x] `python -m pytest` passes meaningful tests for the offline workflow.
- [x] CLI smoke test writes JSON and Markdown from fixtures/mocks only.
- [x] Provider normalization behind testable module boundaries.
- [x] Run outputs preserve raw and normalized provider data.
- [x] Documentation aligned with `ARCHITECTURE.md`, `TESTING.md`, and
  `ROADMAP.md`.

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
