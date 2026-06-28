# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 4 live **page-level** similarity scoring for SEO ranking similarity
research.

### Current capability

Phase 3 shipped: offline and gated live runs loop every capped cluster keyword,
group outputs under `keyword_results`, and annotate flattened rows with
`target_keyword`. Similarity today uses deterministic fixture embeddings only
(aggregated from passages internally).

### Phase 4 objective

For each cluster keyword, score **full parsed page text** for every top-20
organic SERP result with **both** live similarity backends (BGE-reranker-v2 +
Gemini cosine).

### Dev slices

1. **Fixture backends** — offline-testable BGE-reranker-v2 and Gemini cosine
   scorers behind a shared page-level interface.
2. **Page scope** — score parsed page text vs `target_keyword` per organic
   result.
3. **Per-keyword wiring** — attach page similarity scores to `keyword_results`
   in offline and live orchestration paths.
4. **Artifacts** — expose raw + normalized page similarity in `run.json` /
   `report.md`.
5. **Live integration** — env-gated live backend calls; extend smoke/integration
   tests.
6. **Docs** — align `ARCHITECTURE.md`, `README.md`, `TESTING.md`, `ROADMAP.md`.

## In Scope (current and near-term)

- Python CLI under `src/seo_rank/`.
- Pytest under `tests/unit/` and integration tests as needed.
- Dual-backend live similarity on every non-dry live run.
- **Page-level** similarity per organic SERP row (full parsed page text).
- JSON + Markdown artifacts with per-keyword page similarity payloads.

## Out Of Scope

- Passage-level similarity scoring.
- Domain-level URL inventory scoring.
- Storing and processing data with Parquet and Polars.
- `statsmodels` OLS, OLS pre-analysis, Benjamini-Hochberg.
- `runs/RUN_ID/` artifact layout and expanded reporting.
- Entity-derived ranking features.
- Direct page fetching outside DataForSEO.
- Causal claims about ranking factors.
- CI, deployment, databases, cache layers, production hosting.

## Acceptance Criteria (Phase 4)

- [ ] Both BGE-reranker-v2 and Gemini cosine run on every live similarity path.
- [ ] Page-level scores computed per top-20 organic result vs `target_keyword`.
- [ ] Scores land in `keyword_results` with `target_keyword` preserved.
- [ ] Offline fixture tests cover both backends at page scope.
- [ ] Documentation aligned with `ARCHITECTURE.md`, `TESTING.md`, `ROADMAP.md`.

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
