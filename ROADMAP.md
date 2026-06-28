# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract; keep deferred and historical items here.

## Current Backlog

Active scope contract: `GOALS.md` (Phase 3).

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
- **Phase 2 shipped:** provider request builders (DataForSEO keyword expansion,
  organic SERP, page-text parsing; TextRazor parsed-text entities), credential
  validation without secrets in errors, non-default CLI live-provider gate
  (`--live-providers` + `SEO_RANK_ENABLE_LIVE_PROVIDERS=1`), standard-library
  HTTP clients with injectable transports, env-gated live smoke integration test
  (`SEO_RANK_RUN_LIVE_INTEGRATION=1`), and Phase 2 documentation/test coverage.
- **Phase 2 deferred to later backlog:** broader live provider integration beyond
  the minimal smoke path.
- **GOALS retargeted to Phase 3:** full cluster orchestration for every capped
  keyword in offline and live paths.
- **Phase 3 shipped:** offline and env-gated live provider orchestration now run
  every capped cluster keyword, preserve per-keyword raw provider payloads in
  `keyword_results`, and keep aggregate artifact fields for reporting.
