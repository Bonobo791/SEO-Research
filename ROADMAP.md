# Roadmap

This file tracks backlog and history. When `GOALS.md` exists, it is the active
scope contract.

## Current Backlog

### 1. Offline CLI Workflow

- Add CLI argument parsing for the planned `seo-rank run` command.
- Add configuration objects for seed, location, language, device, depth, output
  directory, model name, JavaScript parsing, dry-run mode, and TextRazor skip
  mode.
- Add deterministic tests for the CLI smoke path.
- Emit local JSON and Markdown artifacts from fixtures without network calls.

### 2. Provider Boundaries

- Implement DataForSEO request construction for keyword expansion, organic SERP
  collection, and page-text parsing.
- Implement TextRazor request construction for entity extraction from parsed
  page text.
- Add authentication validation without exposing secrets in errors or artifacts.
- Keep live calls behind explicit integration checks.

### 3. Normalization Pipeline

- Normalize keyword expansion results with case-insensitive deduplication and a
  default 25-keyword cap.
- Normalize organic top-20 SERP observations.
- Normalize DataForSEO parsed headings and paragraphs into text passages.
- Normalize TextRazor entities for future feature work.

### 4. Similarity And Analysis

- Add passage filtering for empty or short text blocks.
- Add embedding and cosine similarity boundaries that can be tested with
  deterministic vectors.
- Aggregate page-level similarity features.
- Add baseline and similarity-feature analysis outputs for observed top-20
  rankings.

### 5. Reporting And Artifacts

- Finalize run artifact layout under `runs/RUN_ID/`.
- Preserve raw provider responses when live integrations are enabled.
- Write report sections that describe observational limits and censored top-20
  ranking constraints.
- Keep generated run artifacts out of source control.

## Deferred

- Entity-derived ranking features.
- Direct page crawling outside DataForSEO.
- CI setup and release packaging.
- Coverage thresholds.
- Production deployment.
- Database or cache integration.

## History

- Repository scaffold exists with `pyproject.toml`, `src/seo_rank/`, and
  `tests/`.
- Architecture and ADR docs define a CLI-first, DataForSEO-backed,
  observational analysis product direction.
- The configured test command is `python -m pytest`; the first offline CLI smoke
  test and SDLC doc guards are present under `tests/unit/`.
