# Configurable keyword-limit implementation slices

## Goal

Support `--keyword-limit N` for new runs and stored-run replay. Accept every
positive integer, keep the single-seed Google Ads expansion request unchanged,
and require DataForSEO to return at least `N` case-insensitive unique keywords
(including the seed) before SERP or downstream work begins.

If expansion returns fewer keywords, fail with the exact count. The limit is a
requested maximum, not a guarantee that the provider can supply that many.

## Coding slices

### Slice 1 — CLI contract

- Keep `positive_int` as the sole validation for `--keyword-limit`.
- Ensure both `--keyword-limit=50` and `--keyword-limit 50` resolve to `50`.
- Preserve the existing Google Ads expansion request and single-seed input.
- Preserve the persisted manifest limit when replay omits the option.

Done when positive values parse in both forms and omitted replay uses the
stored value; zero and negative values remain rejected.

### Slice 2 — Shared completeness rule

- Add one helper in `src/seo_rank/cli.py`.
- Count case-insensitive unique keywords after normalization, including the
  seed.
- Compare the count with the resolved limit.
- Raise `CliCommandError` using:
  `Requested N keywords, but DataForSEO returned M unique keywords`.

Done when the helper is the only completeness implementation and reports the
provider count before any SERP call.

### Slice 3 — New live runs

- Normalize the initial expansion response in `build_live_payload()`.
- Invoke the shared helper immediately afterward.
- Stop the command with exit code `2` when expansion is short.
- Do not invoke SERP, page, backlink, TextRazor, similarity, or materialization
  work after that failure.

Done when 24 returned keywords with limit 50 fails, while 50 unique keywords
produce 50 keyword results.

### Slice 4 — Stored replay

- Resolve the effective limit from the stored manifest plus explicit CLI scope.
- Validate the stored normalized expansion before replay downstream work.
- Keep the existing one-refresh behavior when an explicit higher limit is
  requested with live providers.
- Normalize and validate the refreshed response before any downstream call.
- Persist the refreshed expansion response when it replaces the old response.

Done when refresh success replaces the expansion, refresh failure reports the
exact `N/M` message, and neither path performs downstream work before passing.

### Slice 5 — Documentation and verification

- Document that the option is a requested maximum and provider availability
  can terminate a run early.
- Run focused keyword-limit/replay tests.
- Run all `tests/unit/test_cli_run.py`, then `python -m pytest`.
- Run `graphify update .` and `git diff --check`.

## Constraints

Do not add endpoints, recursive expansion, synthetic keywords, or multi-seed
behavior. Keep the diff limited to the CLI, its tests, and the relevant CLI
documentation.
