# Testing

This repository now has an initial Python package scaffold and pytest
configuration. There are currently no discoverable test source files in the
working tree, so pytest completes with `0` collected tests.

## Current State

- Source directory: `src/seo_rank/`
- Test directory: `tests/`
- Test framework: `pytest`
- Run-all-tests command: `python -m pytest`
- Single-test-file command: not available until test source files are restored
- Lint command: not configured yet
- Type-check command: not configured yet
- Production build command: not configured yet
- Coverage config: not configured yet
- Expected test duration: fast
- Current verification status: `python -m pytest` exits with `0` collected tests

## Active Verification Command

The primary verification command is:

```bash
python -m pytest
```

Current observed result:

- Pytest discovers the configured `tests/` root
- Pytest collects `0` tests from the current working tree

## Required Workflow

Follow `AGENTS.md` and `SDLC-LOOP.md` for every code-shaped change:

1. Define the red check before editing.
2. Write the failing test first.
3. Run the test and confirm it fails for the expected reason.
4. Implement the smallest useful change.
5. Re-run the targeted test and then the full relevant suite.
6. If no test exists yet for a setup-only or documentation-only slice, define a
   concrete observable and verify that instead.
7. Self-review the diff before commit.

For setup, auth, or environment repair where a unit test would be artificial,
define a failing observable first and use a health check or file/config
verification as the red/green gate.

## Testing Approach

Until the product shape is clearer, use a practical test diamond:

- Unit tests for deterministic local logic.
- Integration tests around real boundaries, including APIs, browsers,
  filesystem behavior, auth handoffs, or external services that carry the
  actual risk.
- A small number of end-to-end checks for critical workflows.

Do not use fake percentage targets before the architecture exists. Add coverage
config only when there is code to measure and a meaningful threshold to enforce.

## Mocking Philosophy

Mock only nondeterministic or destructive external side effects by default:
network calls, paid APIs, credentials, time, randomness, email sends, deletes,
admin changes, and tenant-affecting operations. Prefer real integration checks
when a mocked test would hide the risk the change is meant to control.

## Maintaining The Test Stack

Update this file in the same slice that changes the verification contract.
Record:

- The run-all-tests command.
- The single-test-file command.
- Any lint, format, type-check, build, and coverage commands.
- Which tests are required before commit.
- Which checks CI runs, if CI exists.

## Required First-Slice Tests

When test source files are added or restored, the DataForSEO + TextRazor
ranking-similarity scaffold should start with deterministic tests using
fixtures and mocked providers:

- DataForSEO request construction and auth handling.
- TextRazor request construction and auth handling.
- Keyword expansion deduplication and 25-keyword cap.
- SERP normalization for organic top-20 results.
- Page text normalization and empty/short passage filtering.
- Cosine similarity aggregation for multi-passage pages.
- Run orchestration with mocked provider clients.
- Analysis model comparison with synthetic ranking data.
- CLI smoke test that writes JSON and Markdown artifacts without network calls.

Live provider tests are out of scope for the first slice. Network calls must be
behind explicit integration tests or manual checks after the offline scaffold is
stable.
