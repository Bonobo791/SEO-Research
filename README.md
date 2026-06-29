# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

## What works today

Offline `seo-rank run` expands a seed keyword from fixtures, loops over every
capped cluster keyword, normalizes SERP rows and passages, computes fixture
page-level **BGE**, **Gemini Doc Retrieval**, and **Gemini Semantic Similarity**
scores, and writes JSON and Markdown artifacts with **no network calls**. Provider
request builders and credential validators are available for offline
verification. The CLI also has a non-default `--live-providers` gate,
standard-library HTTP clients, env-gated live DataForSEO and TextRazor paths,
and env-gated live Gemini page scoring via `gemini-embedding-2`.

```bash
python -m pytest
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts
```

For live provider smoke tests, copy `.env.example` to `.env` in the project root
and fill in real credentials. The CLI and pytest **load `.env` automatically**
(project root is detected via `pyproject.toml`); you do not need to `source` it in
the shell. Values in `.env` override conflicting shell exports.

Live-provider contract:

- `--live-providers` always uses live DataForSEO.
- `--live-bge` additionally enables live local BGE reranking and requires
  `SEO_RANK_ENABLE_BGE=1` plus a CUDA GPU.
- `--live-gemini` additionally enables Gemini live scoring and requires
  `SEO_RANK_ENABLE_GEMINI=1` plus `GEMINI_API_KEY`.
- `--live-textrazor` additionally enables live TextRazor entity extraction and
  requires `SEO_RANK_ENABLE_TEXTRAZOR=1` plus `TEXTRAZOR_API_KEY`.
- If an optional live flag is not passed, that provider is skipped.

## Product direction (Phase 4)

Phase 3 shipped full cluster orchestration: offline and gated live runs process
every capped keyword, group per-keyword outputs under `keyword_results`, and
annotate flattened rows with `target_keyword`.

Phase 4 adds three page-level measurements on each top-20 organic SERP row:

| Name | JSON key |
|------|----------|
| BGE | `bge` |
| Gemini Doc Retrieval | `gemini_doc_retrieval` |
| Gemini Semantic Similarity | `gemini_semantic_similarity` |

Fixture wiring, artifact exposure, live Gemini scoring, and live BGE scoring are
**done**.

Details: `GOALS.md` (developer instructions) and `ARCHITECTURE.md`.

Passage and domain scopes are Phase 5.5. Later: `statsmodels` OLS with
Benjamini-Hochberg (Phase 5) and `runs/RUN_ID/` reporting (Phase 6).

## Repository layout

| Path | Purpose |
|------|---------|
| `src/seo_rank/` | CLI and provider boundaries |
| `tests/unit/` | pytest unit tests |
| `ARCHITECTURE.md` | Product architecture, data flow, planned pipeline |
| `GOALS.md` | Active-scope contract |
| `ROADMAP.md` | Phased backlog and history |
| `TESTING.md` | Verification contract |

## Documentation

- Architecture and planned pipeline: `ARCHITECTURE.md`
- Active scope: `GOALS.md`
- Backlog: `ROADMAP.md`
- Testing: `TESTING.md`
- Process: `AGENTS.md`, `SDLC.md`

Verification: `python -m pytest`
