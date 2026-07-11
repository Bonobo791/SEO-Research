# Suggested Commands

Full cheatsheet + gotchas in `AGENTS.md`. Non-obvious essentials:

## Test (primary verification — no lint/typecheck exists)
- `python -m pytest` — unit suite (`testpaths=tests/unit`, `pythonpath=["."]`).
- `python -m pytest tests/unit/test_cli_run.py` — single file.
- Live integration opt-in only, not collected by default: `python -m pytest tests/integration -m integration` (needs `.env` `SEO_RANK_RUN_LIVE_INTEGRATION=1` + provider creds).

## CLI (agents guess these wrong)
- Fast smoke, no network: `seo-rank run --seed "technical seo" --dry-run`.
- `seo-rank run` CHAINS full pipeline (normalize -> build-features -> analyze -> stats) automatically. Only call sub-steps on an existing run tree.
- `--dry-run` skips Phase 5 stats (`run_manifest_is_dry_run()`); offline runs emit no `stats_*` artifacts.
- Resume in place: `seo-rank run --seed "..." --stored-run runs/RUN_ID`.
- Sub-steps on existing tree: `seo-rank normalize|build-features|analyze --run runs/RUN_ID`.
- `--skip-textrazor` is STICKY on replay — suppresses TextRazor even if stored run enabled it.

## Env gates (in `.env`, auto-loaded)
- `SEO_RANK_ENABLE_LIVE_PROVIDERS=1` (DataForSEO), `SEO_RANK_ENABLE_TEXTRAZOR=1`, plus provider keys. `--live-providers` / `--live-textrazor-only` / `--live-backlinks` flags gate the paths.

## Repo tooling
- Commit guard (no CI): `node .codex/hooks/git-guard.cjs prove --reviewed` required before commit.
- graphify: `graphify query "<q>"`, `graphify path A B`, `graphify explain "<c>"`; `graphify update .` after code changes.
- Shell commands wrapped with `rtk` prefix (token-saving proxy, behavior-transparent).
