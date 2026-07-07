# AGENTS.md

## What this is

Python CLI (`seo-rank`) for research-grade SEO ranking similarity analysis using DataForSEO, TextRazor, BGE, and Gemini backends. Parquet lake under `runs/` (gitignored). Phase 5 statistical analysis is the active scope (`GOALS.md`).

## Before Every Task

1. Plan before coding — outline steps, state confidence (`HIGH` / `MEDIUM` / `LOW`)
2. `LOW` confidence? Research more or ASK USER
3. If `GOALS.md` exists, treat it as the active-scope contract; `ROADMAP.md` is backlog/history
4. Write failing test FIRST (TDD RED), then implement (TDD GREEN)
5. If tests exist, ALL tests must pass before commit — no exceptions

## Commands

**Unit tests (primary verification):**
```bash
python -m pytest
```

**Single file:**
```bash
python -m pytest tests/unit/test_cli_run.py
```

**Live integration (opt-in only — not collected by default):**
```bash
# Requires .env with SEO_RANK_RUN_LIVE_INTEGRATION=1 and provider credentials
python -m pytest tests/integration -m integration
```

**No lint, typecheck, build, or CI commands exist.** Do not search for them.

## Key Commands That an Agent Would Guess Wrong

| Goal | Command |
|------|---------|
| Fast smoke (1 keyword, fixtures, no network) | `seo-rank run --seed "technical seo" --dry-run` |
| Full offline cluster (25 keywords) | `seo-rank run --seed "technical seo" --dry-run --keyword-limit 25` |
| Resume stored run in place | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID` |
| Backfill TextRazor only | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only` |
| Backfill DataForSEO backlinks | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-providers --live-backlinks` |
| Materialize downstream layers | `seo-rank normalize --run runs/RUN_ID` then `seo-rank build-features --run runs/RUN_ID` then `seo-rank analyze --run runs/RUN_ID` |
| Inspect one keyword | `seo-rank analyze --run runs/RUN_ID --keyword "technical seo"` |

`seo-rank run` **chains the full pipeline** (normalize → build-features → analyze → stats) automatically after raw artifacts. You do NOT need to call each step separately unless working on an existing run tree.

## Things You Would Miss Without Help

- **`.env` auto-loads** — the CLI and pytest both load `.env` from project root automatically via `env.py`. Do not `source .env` in the shell.
- **Progress goes to stderr** — `[seo-rank]` prefix on stderr; stdout stays clean for piping.
- **`--dry-run` skips Phase 5 stats** via `run_manifest_is_dry_run()`. Fixture/offline runs do not produce `stats_*` artifacts.
- **`--skip-textrazor` is sticky** on stored-run replay — it suppresses TextRazor even if the saved run had it enabled.
- **`raw_responses` is excluded from analytical joins** — only used for `seo-rank replay` and explicit re-normalization. Do not join on it in stats or features code.
- **Polars LazyFrame throughout** — all transforms use `pl.scan_parquet()` and return `pl.LazyFrame`. Only `collect(engine="streaming")` or `sink_parquet(compression="zstd")` at boundaries.
- **Validation before every mart write** — `validate.py` schema/key/null/range checks run before `sink_parquet`. Tests assert this.
- **`raw_responses` is partitioned only by `endpoint`** — never by keyword, URL, task ID, or rank.
- **BGE is the pre-registered primary backend** — Gemini backends are secondary comparisons in fixed order (semantic similarity → doc retrieval). See `analysis_spec.v1.yaml`.
- **No CI** — the git-guard hook requires `node .codex/hooks/git-guard.cjs prove --reviewed` before commit. The manifest pins a host-specific pytest command.

## TDD Workflow (MANDATORY)

1. Write the test file FIRST — the test MUST FAIL initially
2. Run the test — confirm it fails (RED)
3. Write the minimum implementation to make the test pass
4. Run the test — confirm it passes (GREEN)
5. Only then: commit

## Rules

- Delete legacy code — no backwards compatibility hacks
- Less is more — don't add what wasn't asked for
- Tests ARE code — treat test failures as bugs
- NEVER commit without running the relevant tests first when tests exist
- During setup, environment repair, and auth-heavy workflows, prefer full access

## graphify

This project has a knowledge graph at `graphify-out/` with `graph.json`.

Before exploring the codebase, use graphify:
- `graphify query "<question>"` — scoped subgraph for codebase or architecture questions
- `graphify path "<A>" "<B>"` — dependency path between two symbols
- `graphify explain "<concept>"` — all nodes related to a concept

After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost). Dirty `graphify-out/` files are expected; they are not a reason to skip graphify.
