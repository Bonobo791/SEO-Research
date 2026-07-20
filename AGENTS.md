# AGENTS.md

Guidance for AI coding agents working in this repository. Assumes no prior
knowledge of the project.

## NON NEGOTIABLES

- Always use rtk filtering — don't use rtk proxy (see RTK section below).
- Always fail loudly — all errors should be caught immediately, never silently.
- Always create logging for all files except tests.
- Do not run the full test suite until all given tasks are complete.
- Tests should NEVER export or output to `domain_blocklist.txt` — it should go to `blocklist.txt`.

## Project overview

`seo-rank` is an **offline-first Python CLI for research-grade SEO ranking
analysis**. It quantifies how observed page variables (semantic similarity
scores, TextRazor NLP signals, OnPage technical checks, backlink counts) relate
to SERP rank, comparing multiple similarity backends against a pre-registered
statistical estimand. It emits guardrail-aware `stats_*` artifacts with
explicit limitations — **no causal claims**.

- Providers: **DataForSEO** (SERP, staged page text, OnPage, backlinks),
  **TextRazor** (entities/topics/categories/etc.), **BGE** cross-encoder
  (`BAAI/bge-reranker-v2-m3` via FlagEmbedding, local/CUDA), **Gemini**
  embeddings (`google-genai`).
- Data lives in a **file-based Parquet lake** under `runs/{run_id}/`
  (gitignored). No database, no cache layer, no deployment, no CI.
- **Phase 5 statistical analysis is the active scope** — `GOALS.md` is the
  active-scope contract; `ROADMAP.md` is backlog/history; `FIXUPS.md` tracks
  small known fixes. Read `GOALS.md` before scoping any task.

## Technology stack

- Python ≥ 3.12, setuptools build backend, `src/` layout. Package manifest:
  `pyproject.toml` (console script `seo-rank = seo_rank.cli:main`). A
  `requirements.txt` / `uv.lock` also exist; `pyproject.toml` is authoritative.
- **Polars LazyFrames** are the core data abstraction — see conventions below.
- Stats: `statsmodels`, `scipy`, `numpy` (primary); `pandas`/`patsy` present.
- `pytest` is the only test runner. **No lint, typecheck, build, coverage, or
  CI commands exist.** Do not search for or invent them.
- CLI entry: `src/seo_rank/cli.py` (argparse). Progress goes to **stderr**
  with a `[seo-rank]` prefix; stdout stays clean for piping.
- The small `package.json` / `node_modules/headroom-ai` at root are for the
  headroom token-optimization tooling, not the application itself.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/seo_rank/cli.py` | CLI: `run`, `normalize`, `build-features`, `analyze`, `replay` subcommands |
| `src/seo_rank/dataforseo.py`, `textrazor.py`, `gemini_embeddings.py`, `bge_reranker.py` | Provider boundaries (offline-verifiable request construction, env-gated live paths) |
| `src/seo_rank/similarity.py`, `text.py`, `progress.py`, `env.py`, `domain_blocklist.py` | Fixture scorers, passage splitting, stderr progress, `.env` loading, domain blocklist |
| `src/seo_rank/data/` | Polars lake layers: `scans.py`, `normalize.py`, `features.py`, `marts.py`, `ranks.py`, `validate.py` |
| `src/seo_rank/stats/` | Phase 5 stats: `spec.py`, `families.py`, `panel.py`, `rank_depth.py`, `spearman.py`, `regression.py`, `diagnostics.py`, `bh.py`, `plackett_luce.py`, `artifacts.py`, plus explainability helpers |
| `tests/unit/` | Unit tests (default suite; one file per area, e.g. `test_cli_run.py`, `test_stats_*.py`) |
| `tests/integration/` | Live provider smoke tests (opt-in, `integration` marker, not collected by default) |
| `tests/fixtures/` | Shared fixture builders (e.g. `onpage_pipeline.py`) |
| `analysis/` | Standalone research scripts (`textrazor_ranking_r2.py`, `gemini_nwh_similarity.py`) — not part of the default pipeline |
| `runs/` | Gitignored Parquet lake, one directory per run |
| `analysis_spec.v1.yaml` | Pre-registered estimand: outcome `-log(serp_rank)`, keyword FE, BH family, guardrails, signal families |

Run-tree layout (written by the CLI):

```text
runs/{run_id}/
  run.json  report.md
  parquet/
    raw_responses/endpoint={keyword_expansion|serp|page_text|entities|
      backlinks_summary|backlinks_dofollow_summary|onpage_instant_pages}/part-*.parquet
    keywords/  serp_items/  pages/  passages/  entities/
    backlinks/  onpage_signals/  textrazor_page_metrics_curated/  similarity_scores/
    keyword_serp/  page_features/  passage_features/  domain_features/
    backlinks_analysis/  onpage_features/  textrazor_page_metrics/  analysis_mart/
  stats/  stats_summary.json  stats_diagnostics.json  stats_report.md
```

## Build and test commands

**Unit tests (primary verification):**

```bash
python -m pytest                      # collects tests/unit only (testpaths)
python -m pytest tests/unit/test_cli_run.py   # single file
```

**Live integration (opt-in only — never run casually; costs real API money):**

```bash
# Requires .env with SEO_RANK_RUN_LIVE_INTEGRATION=1 plus provider gates/credentials
python -m pytest tests/integration -m integration
```

**CLI smoke (fixture/offline, no network):**

```bash
seo-rank run --seed "technical seo" --dry-run
seo-rank run --seed "technical seo" --dry-run --keyword-limit 25
```

## Key commands an agent would guess wrong

| Goal | Command |
|------|---------|
| Resume stored run in place | `seo-rank run --seed "technical seo" --stored-run runs/RUN_ID` |
| Re-fetch non-usable stored page text | `seo-rank run --seed "..." --stored-run runs/RUN_ID --live-providers` |
| Backfill TextRazor only (no DataForSEO HTTP) | `seo-rank run --seed "..." --stored-run runs/RUN_ID --live-textrazor-only` |
| Backfill backlinks + OnPage | `seo-rank run --seed "..." --stored-run runs/RUN_ID --live-providers --live-backlinks` |
| Materialize downstream layers individually | `seo-rank normalize --run runs/RUN_ID`, `seo-rank build-features --run runs/RUN_ID`, `seo-rank analyze --run runs/RUN_ID` |
| Re-run Phase 5 stats only | `seo-rank analyze --run runs/RUN_ID` (exit `1` on guardrail hard-fail, `2` on missing data) |
| Audit one raw provider response | `seo-rank replay --run runs/RUN_ID --response-id RESPONSE_ID` |

`seo-rank run` **chains the full pipeline** (normalize → build-features →
analyze → stats) automatically after raw artifacts; only call the steps
individually on an existing run tree.

## Conventions and architecture rules

- **`.env` auto-loads** — the CLI and pytest load `.env` from the project root
  via `env.py`. Never `source .env` in the shell. Copy `.env.example` for live work.
- **Polars LazyFrame throughout** — all transforms use `pl.scan_parquet()` and
  return `pl.LazyFrame`. Only `collect(engine="streaming")` or
  `sink_parquet(compression="zstd")` at boundaries.
- **Validation before every mart write** — `data/validate.py` schema/key/null/
  range checks run before `sink_parquet`. Tests assert this.
- **`raw_responses` is excluded from analytical joins** — it exists for
  `seo-rank replay` and re-normalization only. It is partitioned **only by
  `endpoint`** — never by keyword, URL, task ID, or rank.
- **`--dry-run` skips Phase 5 stats** via `run_manifest_is_dry_run()`.
- **`--skip-textrazor` is sticky** on stored-run replay — it suppresses
  TextRazor even if the saved run had it enabled.
- **Non-usable `page_text` re-fetches automatically** on `--stored-run
  --live-providers` (no extra flag); refreshed URLs invalidate cached
  similarity and TextRazor rows (`PAGE_TEXT_RETRIEVAL_PLAN.md`).
- **BGE is the pre-registered primary backend**; Gemini backends are secondary
  comparisons in fixed order (semantic similarity → doc retrieval). See
  `analysis_spec.v1.yaml`.
- **Stats are additive by signal family** — TextRazor, OnPage, and backlinks
  signals live on their own marts (`textrazor_page_metrics`,
  `onpage_features`, `backlinks_analysis`) and join into stats via
  `SOURCE_MART_BY_KIND`; the similarity `analysis_mart` contract
  (`analysis_mart.v1`) stays unchanged.
- **Exit codes:** `0` success; `1` guardrail hard-fail on non-dry-run analyze;
  `2` missing data / unknown ids. Storage commands write errors to stderr only.

## TDD workflow (MANDATORY)

1. Write the test file FIRST — the test MUST FAIL initially (RED).
2. Run the test — confirm it fails.
3. Write the minimum implementation to make it pass (GREEN).
4. Run the test — confirm it passes.
5. Only then: commit. If tests exist, ALL relevant tests must pass before
   commit — no exceptions.

## Rules

- Delete legacy code — no backwards-compatibility hacks for unshipped code.
- Less is more — don't add what wasn't asked for.
- Tests ARE code — treat test failures as bugs.
- Plan before coding; state confidence (`HIGH` / `MEDIUM` / `LOW`). If `LOW`,
  research more or ask the user.
- During setup, environment repair, and auth-heavy workflows, prefer full access.
- `LOW`-confidence guesses about CLI flags are common — read `README.md`'s
  flag reference first.

## Security considerations

- All provider credentials live in `.env` (gitignored), loaded automatically:
  `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD` (Basic Auth), `TEXTRAZOR_API_KEY`
  (header), `GEMINI_API_KEY`. BGE is local (CUDA), no key.
- Live API access is **double-gated**: an env flag (`SEO_RANK_ENABLE_LIVE_PROVIDERS`,
  `SEO_RANK_ENABLE_GEMINI`, `SEO_RANK_ENABLE_BGE`, `SEO_RANK_ENABLE_TEXTRAZOR`)
  AND the matching CLI flag (`--live-providers`, `--live-gemini`, `--live-bge`,
  `--live-textrazor`). Never bypass these gates in code or tests.
- Never commit `.env`, credentials, or live API responses containing secrets.
- Live calls cost money — default to fixture/offline paths in tests and examples.

## Agent operating modes and tooling

- **Caveman:** `/caveman full` for progress and handoff messages — terse wording,
  full technical detail.
- **Ponytail:** `/ponytail full` when planning or changing code — reuse existing
  helpers, smallest working diff, no speculative abstractions.
- **Serena:** activate the `SEO-Research` project from `.serena/project.yml`
  before code work; prefer Serena semantic search/symbol tools; use file-based
  patches for Markdown.
- **SDLC:** follow `SDLC.md` and the `$sdlc` skill for implementation slices.
  The git-guard hook requires `node .codex/hooks/git-guard.cjs prove --reviewed`
  before commit; the manifest pins a host-specific pytest command
  (`.codex-sdlc/manifest.json`).

## graphify

This project has a knowledge graph at `graphify-out/` with `graph.json`.

Before exploring the codebase, use graphify:
- `graphify query "<question>"` — scoped subgraph for codebase or architecture questions
- `graphify path "<A>" "<B>"` — dependency path between two symbols
- `graphify explain "<concept>"` — all nodes related to a concept

After modifying code, run `graphify update .` to keep the graph current
(AST-only, no API cost). Dirty `graphify-out/` files are expected; they are
not a reason to skip graphify.

## RTK (Rust Token Killer) — token-optimized shell commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60–90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

```bash
rtk git status / rtk git diff / rtk git log      # git
rtk ls <path> / rtk read <file> / rtk grep <pat> # files & search
rtk pytest tests/                                # failures only
rtk err <cmd> / rtk json <file> / rtk deps       # analysis
```

Rules: in command chains, prefix each segment
(`rtk git add . && rtk git commit -m "msg"`); for debugging, use the raw
command without the rtk prefix.

## Things You Would Miss

- The active pre-registered spec is `analysis_spec.v1.2.yaml` (adds the
  `authority_proxy` control alongside `site_scale`). Older stored runs whose
  `analysis_mart`/`domain_features` predate the control will report
  control-error status until `seo-rank build-features --run runs/RUN_ID`
  re-materializes `domain_features`.

## Documentation map

- `README.md` — user-facing commands, flag reference, storage layout
- `ARCHITECTURE.md` — architecture and data flow
- `GOALS.md` — active-scope contract (Phase 5 stats; slice tracker)
- `ROADMAP.md` — backlog and shipped-history
- `TESTING.md` — verification contract
- `FIXUPS.md` — small-fixes backlog (e.g. S5-11 null `result` schema drift)
- `PAGE_TEXT_RETRIEVAL_PLAN.md` — staged page-text retrieval design
- `analysis_spec.v1.yaml` — pre-registered estimand and guardrails
- `SDLC.md` — delivery process
