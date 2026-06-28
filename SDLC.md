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

No product commands are configured yet because the repo has no application
source, tests, package manifest, build system, or CI.

Current setup verification command:

```bash
test -s TESTING.md && test -s ARCHITECTURE.md && test -s SDLC.md && test -s .codex-sdlc/manifest.json
```

When product code is added, update `TESTING.md` and
`.codex-sdlc/manifest.json` with the real commands before relying on the git
proof shortcut.

## Pre-Commit Proof

Use `PROVE-IT.md` before committing. Because no full product test command exists
yet, pass the setup verification command explicitly when stamping proof for
setup-only changes:

```bash
node .codex/hooks/git-guard.cjs prove --reviewed --check "test -s TESTING.md && test -s ARCHITECTURE.md && test -s SDLC.md && test -s .codex-sdlc/manifest.json"
```

After real test, lint, type-check, or build commands exist and are recorded in
`.codex-sdlc/manifest.json`, `node .codex/hooks/git-guard.cjs prove --reviewed`
can run the configured proof commands directly.

## Product Documentation

- Root architecture summary: `ARCHITECTURE.md`
- Detailed architecture: `docs/architecture/ARCHITECTURE.md`
- First implementation plan:
  `docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md`
- ADR 0001:
  `docs/architecture/adr/0001-keyword-cluster-observational-analysis.md`
- ADR 0002:
  `docs/architecture/adr/0002-censored-top20-validation-and-reporting.md`
