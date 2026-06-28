# Testing

Pytest configuration and verification contract for SEO-Research.

## Current State

- Source directory: `src/seo_rank/`
- Test directory: `tests/unit/`
- Test framework: `pytest`
- Run-all-tests command: `python -m pytest`
- Single-test-file command: `python -m pytest tests/unit/test_cli_run.py`
- Lint / type-check / build / coverage: not configured
- Expected test duration: fast (< 1s)
- **Current verification status:** 9 tests collected, all passing

## Active Verification Command

```bash
python -m pytest
```

## Suite coverage (shipped)

| Test file | What it verifies |
|-----------|------------------|
| `test_cli_run.py` | CLI writes artifacts; TextRazor skip vs include |
| `test_keyword_expansion.py` | 25-keyword cap, deduplication, raw provider payload |
| `test_serp_normalization.py` | Organic-only SERP rows, depth cap |
| `test_passage_normalization.py` | Passage split, short-text filter |
| `test_similarity_features.py` | Fixture embedding cosine aggregation |
| `test_textrazor_normalization.py` | Entity schema normalization |
| `test_sdlc_docs.py` | GOALS/ROADMAP guards and manifest pytest commands |

All tests use fixtures/mocks only. No live provider or network tests.

## Required Workflow

Follow `AGENTS.md` and `SDLC-LOOP.md` for code-shaped changes:

1. Define the red check before editing.
2. Write the failing test first.
3. Confirm RED, implement minimal fix, confirm GREEN.
4. Run `python -m pytest` before commit.

## Mocking Philosophy

Mock nondeterministic or destructive external effects (network, paid APIs,
credentials). Prefer integration tests at real boundaries once live clients
exist.

## Planned tests (not yet in suite)

- DataForSEO / TextRazor request construction and auth handling
- Full cluster keyword orchestration (not first keyword only)
- Live similarity backends (`BGE-reranker-v2`, Gemini cosine)
- Passage / page / domain similarity scopes
- `statsmodels` OLS and Benjamini-Hochberg on synthetic ranking panels
- OLS pre-analysis diagnostic loop

See phased backlog in `ROADMAP.md` and planned pipeline in `ARCHITECTURE.md`.

## Maintaining This File

Update in the same slice that changes the verification contract (commands, test
count, or required gates).
