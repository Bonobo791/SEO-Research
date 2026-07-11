# Task Completion

No lint, typecheck, format, or build step exists in this project (confirmed AGENTS.md — do not search for them). Verification = tests.

Definition of done for a coding task:
1. Relevant tests written first and passing (TDD). If touching a module, run its unit test file.
2. Full unit suite green: `python -m pytest` (collects `tests/unit` only).
3. NEVER commit with failing tests. Live integration tests (`-m integration`) are opt-in and not required for normal completion.
4. Commit gate (no CI): `node .codex/hooks/git-guard.cjs prove --reviewed` must pass before commit.
5. After code changes, refresh knowledge graph: `graphify update .` (AST-only, no API cost).

Commit only when the user asks.
