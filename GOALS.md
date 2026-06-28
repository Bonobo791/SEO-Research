# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build the first offline-verifiable Python CLI scaffold for SEO ranking
similarity research.

The current active slice is to turn the package scaffold into a deterministic
local workflow that can:

1. Accept a seed keyword and run configuration through the CLI.
2. Expand the seed into a capped keyword set using mocked provider data.
3. Normalize organic top-20 SERP results.
4. Normalize parsed page text into usable passages.
5. Compute deterministic similarity features from fixture embeddings.
6. Write JSON and Markdown run artifacts without network calls.

## In Scope

- Python CLI-first implementation under `src/seo_rank/`.
- Discoverable pytest coverage under `tests/`.
- Offline provider fixtures and mocks for DataForSEO and TextRazor boundaries.
- JSON artifacts and a Markdown report for a local dry run.
- TextRazor entity capture schema and normalization hooks.
- Explicit configuration validation for required live-run credentials.

## Out Of Scope For Active Objective

- Live DataForSEO or TextRazor calls by default.
- Direct page fetching outside DataForSEO.
- Entity-derived ranking features.
- Causal claims about ranking factors.
- CI, deployment, databases, cache layers, and production hosting.
- Large framework additions before the CLI workflow exists.

## Acceptance Criteria

- `python -m pytest` collects and passes meaningful tests for the active
  workflow.
- A local CLI smoke test can write JSON and Markdown artifacts using fixtures or
  mocks only.
- Provider clients keep request construction, authentication handling, and
  response normalization behind testable boundaries.
- Run outputs preserve enough raw and normalized data to support later live
  provider integration.
- Documentation stays aligned with `ARCHITECTURE.md`, `TESTING.md`, and the
  implementation plan.

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then the full configured test command before
  finishing a slice.
- Delete stale scaffolding when replacing it; do not add compatibility layers
  for code that has not shipped.
- Keep scope small enough that each slice can be reviewed and verified.
