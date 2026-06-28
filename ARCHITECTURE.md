# Architecture

## Stack

- Language: Python
- Runtime: CLI
- Source directory: planned `src/seo_rank/`
- Test directory: planned `tests/`
- Deployment: none
- Databases: none
- Cache layer: none
- CI: none configured

## Overview

SEO-Research is planned as a Python CLI application for research-grade SEO
ranking analysis. The first version will expand a seed keyword into a keyword
cluster, collect top-20 organic SERP results through DataForSEO, retrieve
provider-parsed page text, compute passage-to-keyword semantic similarity, and
report whether similarity features explain variation in observed rankings.

TextRazor entities will be captured and normalized from the same DataForSEO page
text, but entity-derived model features are out of scope for the first model.

The detailed product architecture lives in
`docs/architecture/ARCHITECTURE.md`. The first implementation plan lives in
`docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md`.

## Current Components

- `AGENTS.md`: repo process contract. It requires `gpt-5.5` with effort selected
  by task type, strict TDD for code-shaped changes, and all tests passing before
  commit.
- `SDLC-LOOP.md`: operating loop for planning, red/green proof, review, and
  escalation.
- `START-SDLC.md`: session-start prompt for working in SDLC mode.
- `PROVE-IT.md`: pre-commit proof checklist and proof-stamp instructions.
- `.agents/skills/sdlc/SKILL.md`: repo-local SDLC skill entrypoint. Use `$sdlc`
  for implementation work.
- `.codex/config.toml`: repo-local Codex model and hook settings.
- `.codex/hooks.json`: portable hook wiring using Node entrypoints.
- `.codex/hooks/*.cjs`: active hook implementations for session, git, and
  compaction guards.
- `.codex-sdlc/model-profile.json`: selected task-based `gpt-5.5` model
  profile.
- `.codex-sdlc/manifest.json`: setup scan results and confirmed preferences.
- `docs/architecture/`: product architecture and ADRs.
- `docs/implementation/`: first implementation plan.

## Application Surface

No application modules are present yet:

- Source directory: not present
- Test directory: not present
- Package manager or dependency manifest: not present
- Database: not present
- Cache layer: not present
- Deployment target: not present
- CI workflow: not present

The accepted product direction is documented, but implementation has not begun.

## Key Product Components

- CLI: accepts seed keyword, location, language, device, cluster size, SERP
  depth, output directory, model name, JavaScript parsing option, `--dry-run`,
  and `--skip-textrazor`.
- Provider clients: DataForSEO for keyword expansion, SERP collection, and page
  text parsing; TextRazor for entity extraction from parsed page text.
- Normalizers: preserve raw provider responses and normalize them into stable
  internal schemas.
- Text pipeline: split page text into paragraph/headings passages, embed keyword
  and passages, compute cosine similarity, and aggregate page-level features.
- Analysis engine: compare baseline and similarity-feature models over observed
  top-20 rankings.
- Reporters: emit machine-readable JSON artifacts and a Markdown report.

## Data Flow

Seed keyword input flows through keyword expansion, SERP collection, page text
parsing, TextRazor entity capture, passage extraction, similarity feature
generation, rank-feature joining, statistical analysis, and report generation.

Raw provider responses and generated run artifacts should stay out of source
control.

## Decisions

- Build as a CLI-first Python application.
- Use DataForSEO as the canonical SERP and page-text source.
- Send DataForSEO parsed page text to TextRazor; do not send original URLs for
  entity extraction.
- Keep direct page fetching out of v1.
- Treat analysis as observational and censored to observed top-20 rankings.
- Capture TextRazor entities for future work but exclude entity-derived features
  from the first ranking-variation model.
- Add the real package under `src/seo_rank/` and tests under `tests/` when
  implementation begins.
- Keep significant architecture decisions in `docs/architecture/adr/`.

## Codex And SDLC Flow

The canonical implementation entrypoint is `$sdlc`. Codex does not have a
native `/sdlc` command in this repo, and repo docs should not imply one exists.

Execution lane guidance:

- Use CLI for repository edits, tests, docs, hooks, commits, and ordinary
  verification.
- Use Desktop/computer-use first for browser sign-in, Microsoft tenant flows,
  MFA, Office UI, admin portals, screenshots, or desktop-only state. Start it
  from the repo root with `codex app .` on macOS or Windows.
- Keep credentials, MFA, tenant consent, sends, deletes, license/admin changes,
  and policy publishing as explicit human actions.
