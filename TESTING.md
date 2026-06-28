# Testing

Pytest configuration and verification contract for SEO-Research.

## Current State

- Source directory: `src/seo_rank/`
- Test directories: `tests/unit/`, `tests/integration/`
- Test framework: `pytest`
- Run-all-tests command: `python -m pytest`
- Single-test-file command: `python -m pytest tests/unit/test_cli_run.py`
- Lint / type-check / build / coverage: not configured
- Expected test duration: fast (< 1s)
- **Current verification status:** 24 tests collected; 23 passing, 1 live
  integration smoke skipped by default

## Active Verification Command

```bash
python -m pytest
```

Live provider smoke tests are marked `integration` and skipped unless all live
gates are explicit:

```bash
SEO_RANK_RUN_LIVE_INTEGRATION=1 \
SEO_RANK_ENABLE_LIVE_PROVIDERS=1 \
DATAFORSEO_LOGIN=... \
DATAFORSEO_PASSWORD=... \
TEXTRAZOR_API_KEY=... \
python -m pytest -m integration
```

Use `.env.example` as the local template for these values. Copy it to `.env`,
fill in real credentials, then source `.env` in the shell before running live
tests. `.env` is ignored by git; `.env.example` must contain placeholders only.

## Suite coverage (shipped)

| Test file | What it verifies |
|-----------|------------------|
| `test_cli_run.py` | CLI writes grouped per-keyword artifacts; TextRazor skip vs include; live-provider gate; injected live cluster orchestration |
| `test_keyword_expansion.py` | 25-keyword cap, deduplication, raw provider payload |
| `test_serp_normalization.py` | Organic-only SERP rows, depth cap |
| `test_dataforseo_requests.py` | DataForSEO request construction, credential validation, HTTP execution |
| `test_passage_normalization.py` | Passage split, short-text filter |
| `test_similarity_features.py` | Fixture embedding cosine aggregation |
| `test_textrazor_normalization.py` | Entity schema normalization |
| `test_textrazor_requests.py` | TextRazor parsed-text request construction, credential validation, HTTP execution |
| `test_sdlc_docs.py` | GOALS/ROADMAP/README guards and manifest pytest commands |
| `test_live_provider_smoke.py` | Env-gated DataForSEO/TextRazor smoke path |

Unit tests use fixtures/mocks only. Live provider smoke tests are opt-in and
must never run without the explicit environment gates above.

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

- Broader live DataForSEO / TextRazor integration coverage beyond smoke checks
- Live similarity backends (`BGE-reranker-v2`, Gemini cosine)
- Passage / page / domain similarity scopes
- `statsmodels` OLS and Benjamini-Hochberg on synthetic ranking panels
- OLS pre-analysis diagnostic loop

See phased backlog in `ROADMAP.md` and planned pipeline in `ARCHITECTURE.md`.

## Maintaining This File

Update in the same slice that changes the verification contract (commands, test
count, or required gates).
