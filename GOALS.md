# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 3 full cluster orchestration for SEO ranking similarity research.

### Current capability

SERP, page text, passages, offline similarity features, and TextRazor entities
run against **every keyword** in the capped cluster (up to 25 keywords after seed
expansion).

### Phase 3 objective

For **each keyword** in the capped cluster, run the provider pipeline with that
keyword as the **target keyword** for all SERP-derived outputs:

1. Collect organic SERP results (depth-capped, default top 20).
2. Fetch or fixture-load parsed page text for each organic result.
3. Normalize passages from that page text.
4. Compute offline fixture similarity features against the target keyword.
5. Capture TextRazor entities from parsed text when not skipped.

Apply the same per-keyword loop in **offline** (`seo-rank run`) and **live**
(`--live-providers` with explicit env gates) paths.

Phase 3 status:

- Per-keyword offline orchestration: **Shipped**
- Per-keyword live orchestration: **Shipped**
- Run artifacts grouped by target keyword: **Shipped**
- Cluster orchestration tests (offline + injected live transports): **Shipped**

## In Scope (current and near-term)

- Python CLI under `src/seo_rank/`.
- Pytest coverage under `tests/unit/` and orchestration tests as needed.
- Offline and live provider paths extended to the full capped keyword cluster.
- JSON + Markdown run artifacts that preserve per-keyword raw and normalized
  provider data.
- Product documentation in root markdown: `ARCHITECTURE.md`, `GOALS.md`,
  `ROADMAP.md`, `README.md`, `TESTING.md`.

## Out Of Scope

- Live similarity backends (`BGE-reranker-v2`, Gemini cosine) until Phase 4.
- Passage / page / domain live similarity scopes until Phase 4.
- `statsmodels` OLS, OLS pre-analysis, and Benjamini-Hochberg until Phase 5.
- `runs/RUN_ID/` artifact layout and expanded reporting until Phase 6.
- Entity-derived ranking features.
- Direct page fetching outside DataForSEO.
- Causal claims about ranking factors.
- CI, deployment, databases, cache layers, production hosting.

## Acceptance Criteria (Phase 3)

- [x] Offline `seo-rank run` processes **every** keyword in the capped cluster,
  not only the first.
- [x] Live `--live-providers` smoke orchestration processes **every** keyword in
  the capped cluster when explicitly enabled.
- [x] Each keyword's SERP, page text, passages, similarity features, and
  TextRazor entities use that keyword as the target keyword.
- [x] `run.json` and `report.md` expose per-keyword results without losing raw
  provider payloads.
- [x] `python -m pytest` includes meaningful cluster-orchestration coverage.
- [x] Documentation aligned with `ARCHITECTURE.md`, `TESTING.md`, and
  `ROADMAP.md`.

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
