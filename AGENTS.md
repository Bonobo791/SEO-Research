# SDLC Enforcement

## Before Every Task
1. Plan before coding - outline steps, state confidence (HIGH/MEDIUM/LOW)
2. LOW confidence? Research more or ASK USER
3. Reasoning policy - always use `gpt-5.5`; select effort by task type
4. Documentation tasks use `gpt-5.5` with `low` reasoning
5. Coding tasks use `gpt-5.5` with `medium` reasoning
6. Review, QA, and security tasks use `gpt-5.5` with `high` reasoning
7. Installs and configuration tasks use `gpt-5.5` with `xhigh` reasoning
8. Do not switch wizard-repo work to `mixed`, mini-only, or non-`gpt-5.5` profiles
9. If `GOALS.md` exists, treat it as the active-scope contract and keep `ROADMAP.md` as backlog/history
10. Write failing test FIRST (TDD RED), then implement (TDD GREEN)
11. ALL tests must pass before commit - no exceptions

## TDD Workflow (MANDATORY)
1. Write the test file FIRST - the test MUST FAIL initially
2. Run the test - confirm it fails (RED)
3. Write the minimum implementation to make the test pass
4. Run the test - confirm it passes (GREEN)
5. Only then: commit

## After Implementation
1. Self-review: read back your changes, check for bugs
2. Run full test suite - ALL tests must pass
3. Only then: commit and push

## Rules
- Delete legacy code - no backwards compatibility hacks
- Less is more - don't add what wasn't asked for
- Tests ARE code - treat test failures as bugs
- NEVER commit without running tests first
- During setup, environment repair, and auth-heavy workflows, prefer full access
