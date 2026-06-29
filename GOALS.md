# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 4.5 **database storage** for SEO ranking similarity research outputs.

### Current capability

**Phase 4 shipped:** offline and gated live runs loop every capped cluster keyword,
group outputs under `keyword_results`, and annotate flattened rows with
`target_keyword`. Page-level **BGE**, **Gemini Doc Retrieval**, and **Gemini Semantic
Similarity** scores land in `run.json` and `report.md` for every organic SERP row.

- **Offline / default live:** deterministic fixture scorers in `similarity.py`.
- **`--live-gemini`:** real `gemini-embedding-2` embeddings via `google-genai`.
- **`--live-bge`:** real `BAAI/bge-reranker-v2-m3` cross-encoder via `FlagEmbedding`
  on CUDA (loaded once per live run).
- **`--live-textrazor`:** opt-in live entity extraction; default live runs skip it.
- **Provider gates:** `--live-providers` plus per-provider env flags; hard failures
  when flags or credentials are missing.

### Phase 4.5 objective

Begin storing analysis data from DataForSEO and TextRazor in Parquet, process with
Polars, and add a mechanism to read stored data instead of always calling APIs.

See `ROADMAP.md` for Phase 5 (OLS) and Phase 5.5 (passage/domain scoring).

## In Scope (current and near-term)

- Python CLI under `src/seo_rank/`.
- Pytest under `tests/unit/` and `tests/integration/`.
- Parquet/Polars persistence for provider and similarity outputs.
- Read path for stored runs vs live API pulls.

## Out Of Scope

- Passage-level similarity scoring (Phase 5.5).
- Domain-level URL inventory scoring (Phase 5.5).
- `statsmodels` OLS, OLS pre-analysis, Benjamini-Hochberg (Phase 5).
- `runs/RUN_ID/` artifact layout and expanded reporting (Phase 6).
- Entity-derived ranking features.
- Direct page fetching outside DataForSEO.
- Causal claims about ranking factors.
- CI, deployment, production hosting.

## Phase 4 acceptance criteria (complete)

- [x] Page-level fixture scores for **BGE**, **Gemini Doc Retrieval**, and
  **Gemini Semantic Similarity** exposed per SERP row in artifacts.
- [x] Scores land in `keyword_results` with `target_keyword` preserved.
- [x] Offline fixture tests cover `bge`, `gemini_doc_retrieval`, and
  `gemini_semantic_similarity` at page scope.
- [x] Optional live provider flags (`--live-gemini`, `--live-bge`,
  `--live-textrazor`) with env gates and hard failures when misconfigured.
- [x] Live TextRazor is opt-in only; default live runs skip entity extraction.
- [x] Documentation and `.env.example` aligned with `ARCHITECTURE.md`,
  `TESTING.md`, `ROADMAP.md`.
- [x] Live **Gemini Doc Retrieval** and **Gemini Semantic Similarity** via
  Gen AI SDK (`gemini-embedding-2`) when `--live-gemini` is enabled.
- [x] Live **BGE** cross-encoder via FlagEmbedding (`BAAI/bge-reranker-v2-m3`)
  with documented score calibration notes.
- [x] `pyproject.toml` `similarity` optional extra for `google-genai` and
  `FlagEmbedding`.
- [x] Opt-in integration smoke coverage for live Gemini and BGE flags.

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
