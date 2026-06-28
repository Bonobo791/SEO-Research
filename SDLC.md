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

Primary verification command:

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

Use `PROVE-IT.md` before committing. The manifest records `python -m pytest` as
the proof command, so the git gate can run it directly:

```bash
node .codex/hooks/git-guard.cjs prove --reviewed
```

For setup-only changes that do not touch product verification, you can still pass
the setup verification command explicitly:

```bash
node .codex/hooks/git-guard.cjs prove --reviewed --check "test -s TESTING.md && test -s ARCHITECTURE.md && test -s SDLC.md && test -s .codex-sdlc/manifest.json"
```

## Product Documentation

- Root architecture summary: `ARCHITECTURE.md`
- Detailed architecture: `docs/architecture/ARCHITECTURE.md`
- First implementation plan:
  `docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md`
- ADR 0001:
  `docs/architecture/adr/0001-keyword-cluster-observational-analysis.md`
- ADR 0002:
  `docs/architecture/adr/0002-censored-top20-validation-and-reporting.md`
