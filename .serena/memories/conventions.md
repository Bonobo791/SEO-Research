# Conventions

## Data / transforms
- LazyFrame-first: functions take/return `pl.LazyFrame`; materialize only at boundaries (`collect(engine="streaming")`, `sink_parquet(compression="zstd")`).
- Every mart write is preceded by a `validate.py` check (schema/key/null/range). Adding a mart = add its validation.
- Schema versions are explicit constants (e.g. `RAW_RESPONSE_SCHEMA_VERSION`, `RUN_CATALOG_SCHEMA_VERSION` in `cli.py`); bump when shape changes.
- `raw_responses` partitioned only by `endpoint`; never join it into analytical/stats/features code.

## Code style
- Module-private helpers prefixed `_` (heavy use in `cli.py`, e.g. `_load_...`, `_keyword_analysis_...`).
- Env-flag names are module constants ending `_ENV_FLAG` (e.g. `LIVE_PROVIDER_ENV_FLAG`).
- Domain dataclasses/config objects (`RunConfig`, `LiveProviderCredentials`); typed custom errors (`LiveProviderGateError`, `CliCommandError`).

## Workflow (MANDATORY per AGENTS.md)
- TDD: write failing test FIRST (RED), then minimum impl (GREEN), then commit. All existing tests must pass before commit.
- State confidence (HIGH/MEDIUM/LOW) when planning; LOW = research more or ask user.
- Delete legacy code, no back-compat shims; add nothing unasked; treat test failures as bugs.
- BGE = pre-registered primary backend; Gemini backends secondary in fixed order — preserve ordering in outputs/reports (`analysis_spec.v1.yaml`).
