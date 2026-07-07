# SDLC

This repository uses repo-local SDLC docs and hooks instead of a native Codex
slash command.

## Entrypoints

- `$sdlc`: implementation, bug fixes, refactors, tests, release, publish, or
  deploy work.
- `$setup-wizard`: first-time setup or setup refresh.
- `$update-wizard`: maintenance updates to the setup surface.
- `$feedback`: feedback about the SDLC wizard experience.

Do not treat `/sdlc` as a real Codex command for this repo.

## Required Loop

1. Read `AGENTS.md`.
2. Restate the task in one sentence.
3. Set a scope guard.
4. State confidence as HIGH, MEDIUM, or LOW.
5. Define the red check before editing.
6. Write the failing test first for code-shaped work.
7. For setup, auth, or environment repair, define the failing observable first.
8. Implement the smallest useful change.
9. Run targeted verification, then the full relevant suite.
10. Self-review the diff.
11. Commit only after proof is current and all required checks pass.

## Current Setup Defaults

- Response detail: concise by default, with proof details when results matter.
- Testing approach: strict TDD and a practical test diamond once code exists.
- Mocking philosophy: mock nondeterministic or destructive external side effects;
  prefer real integration checks at important boundaries.
- CI shepherd: off until CI exists.

## Current Commands

Primary verification command (unit tests only; see `TESTING.md` for opt-in live
integration):

```bash
python -m pytest
```

Targeted single-file example:

```bash
python -m pytest tests/unit/test_cli_run.py
```

Setup verification command:

```bash
test -s TESTING.md && test -s ARCHITECTURE.md && test -s SDLC.md && test -s .codex-sdlc/manifest.json
```

Lint, type-check, build, and CI commands are not configured yet.

## Pre-Commit Proof

Use `PROVE-IT.md` before committing. The manifest records a host-pinned pytest
command (`/usr/bin/python3` with explicit `PYTHONPATH`) so the Node git-guard
hook can run tests without invoking the repo venv interpreter directly. Day-to-day
verification still uses `python -m pytest` from an activated environment (unit
tests only; live smoke is not collected by default):

```bash
python -m pytest
```

The git gate reads the pinned command from `.codex-sdlc/manifest.json` and runs
it directly:

```bash
node .codex/hooks/git-guard.cjs prove --reviewed
```

For setup-only changes that do not touch product verification, you can still pass
the setup verification command explicitly:

```bash
node .codex/hooks/git-guard.cjs prove --reviewed --check "test -s TESTING.md && test -s ARCHITECTURE.md && test -s SDLC.md && test -s .codex-sdlc/manifest.json"
```

## Product Documentation

Product architecture and planning live in root markdown files (there is no
`docs/` tree in this repo):

- **Architecture and planned pipeline:** `ARCHITECTURE.md` — stack, shipped
  Phase 1 modules, offline data flow, planned live similarity and statistical
  analysis
- **Active scope:** `GOALS.md` — Phase 5 statistical analysis on
  `analysis_mart` (Spearman + pooled OLS, guardrails, `stats_*` artifacts)
- **Backlog and history:** `ROADMAP.md` — Phases 2–6 backlog
- **Verification contract:** `TESTING.md` — pytest suite and coverage map
- **Quick start:** `README.md` — what works today and repo layout
- **Implementation surface:** `src/seo_rank/` — `cli.py`, `dataforseo.py`,
  `text.py`, `similarity.py`, `textrazor.py`
