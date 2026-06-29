# Testing

Pytest configuration and verification contract for SEO-Research.

## Current State

- Source directory: `src/seo_rank/`
- Test directories: `tests/unit/`, `tests/integration/`
- Test framework: `pytest`
- Run-all-tests command: `python -m pytest`
- Single-test-file command: `python -m pytest tests/unit/test_cli_run.py`
- Git-guard proof command: pinned in `.codex-sdlc/manifest.json` (`/usr/bin/python3`
  plus explicit `PYTHONPATH`) so the Node hook can run pytest without the venv
  interpreter
- Lint / type-check / build / coverage: not configured
- Expected test duration: fast (< 1s)
- **Current verification status:** 46 tests collected; 45 passing, 1 live
  integration smoke skipped by default

## Active Verification Command

```bash
python -m pytest
```

Live provider smoke tests are marked `integration` and skipped unless `.env`
sets the gates explicitly:

```bash
# In .env (loaded automatically):
# SEO_RANK_RUN_LIVE_INTEGRATION=1
# SEO_RANK_ENABLE_LIVE_PROVIDERS=1
# SEO_RANK_ENABLE_BGE=1               # only if using --live-bge
# SEO_RANK_ENABLE_GEMINI=1            # only if using --live-gemini
# SEO_RANK_ENABLE_TEXTRAZOR=1         # only if using --live-textrazor
# DATAFORSEO_LOGIN=...
# DATAFORSEO_PASSWORD=...
# TEXTRAZOR_API_KEY=...
# GEMINI_API_KEY=...

python -m pytest -m integration
```

Use `.env.example` as the local template. Copy it to `.env` at the project root
and fill in real credentials. Pytest loads `.env` automatically via
`tests/conftest.py` (same loader as the CLI). Values in `.env` override
conflicting shell exports. `.env` is ignored by git; `.env.example` must contain
placeholders only.

## Suite coverage (shipped)

| Test file | What it verifies |
|-----------|------------------|
| `test_cli_run.py` | CLI writes grouped per-keyword artifacts, including BGE, Gemini Doc Retrieval, and Gemini Semantic Similarity rows; offline TextRazor include/skip; explicit live-provider gates; opt-in live Gemini, BGE, and TextRazor orchestration |
| `test_keyword_expansion.py` | 25-keyword cap, deduplication, raw provider payload |
| `test_serp_normalization.py` | Organic-only SERP rows, depth cap |
| `test_env.py` | `.env` discovery, parsing, and override of shell exports |
| `test_bge_reranker.py` | Live BGE GPU gate, pinned model loading, and batched score shaping |
| `test_gemini_embeddings.py` | Live Gemini prompt formatting, model args, and score shaping with injected embeddings |
| `test_passage_normalization.py` | Passage split, short-text filter |
| `test_similarity_features.py` | Fixture passage aggregation plus BGE, Gemini Doc Retrieval, and Gemini Semantic Similarity page scoring |
| `test_textrazor_normalization.py` | Entity schema normalization |
| `test_textrazor_requests.py` | TextRazor parsed-text request construction, credential validation, HTTP execution |
| `test_sdlc_docs.py` | GOALS/ROADMAP/README guards and manifest pytest commands |
| `test_live_provider_smoke.py` | Env-gated DataForSEO smoke path with optional live TextRazor, Gemini, and BGE opt-ins |
| `test_live_provider_smoke_config.py` | Optional live similarity flags are included in smoke runs when their env gates are enabled |

Unit tests use fixtures/mocks only. Live provider smoke tests are opt-in and
must never run without the explicit environment gates above. DataForSEO is
always required for a live run; Gemini, BGE, and TextRazor are optional and
require their own CLI flags plus env gates when requested.

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
- Deeper end-to-end live similarity validation beyond env-gated smoke paths
- Passage / domain similarity scopes
- `statsmodels` OLS and Benjamini-Hochberg on synthetic ranking panels
- OLS pre-analysis diagnostic loop

Keep optional live flags aligned with `.env.example` when adding integration tests.

See phased backlog in `ROADMAP.md` and planned pipeline in `ARCHITECTURE.md`.

## Maintaining This File

Update in the same slice that changes the verification contract (commands, test
count, or required gates).
