# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract; keep deferred and historical items here.

## Current Backlog

### Phase 2 — Provider boundaries

- DataForSEO request construction (keyword expansion, SERP, page-text parsing)
- TextRazor request construction from parsed page text
- Authentication validation without secrets in errors or artifacts
- Live calls behind explicit integration checks or non-default flags

### Phase 3 — Full cluster orchestration

- SERP, page text, and downstream features for **every** keyword in the capped
  cluster (today: first keyword only)

### Phase 4 — Live similarity

- Cross-encoder `BGE-reranker-v2` and bi-encoder Gemini cosine — **both every run**
- Per keyword: top-20 SERP; passage, page, and domain URL scoring vs target
  keyword; domain URL cap 1000; skip domains over 1000 URLs

### Phase 5 — Statistical analysis

- OLS pre-analysis preparation (root `ARCHITECTURE.md`)
- `statsmodels` OLS baseline vs similarity-feature models
- Benjamini-Hochberg correction every run

### Phase 6 — Reporting

- Artifact layout under `runs/RUN_ID/`
- Report sections for observational limits and top-20 censoring
- Generated runs out of source control

## Deferred

- Entity-derived ranking features
- Direct page crawling outside DataForSEO
- CI, release packaging, coverage thresholds
- Production deployment, databases, cache

## History

- Repository scaffold: `pyproject.toml`, `src/seo_rank/`, `tests/`.
- **Phase 1 shipped:** offline CLI, DataForSEO/TextRazor fixtures, keyword/SERP/
  passage/similarity/entity normalization, `run.json` + `report.md`, unit tests,
  root product docs (`ARCHITECTURE.md`, `GOALS.md`, `ROADMAP.md`).
- SDLC wizard surface: hooks, manifest, `GOALS.md` active contract.
