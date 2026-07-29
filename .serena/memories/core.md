<!--
SEO Research — SEO Factors Research Tool
Copyright (C) 2026 Andrew Philip Weilbacher

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md
-->
# Core


`seo-rank` — Python CLI for research-grade SEO ranking similarity analysis (DataForSEO, TextRazor, BGE, Gemini backends). Active scope: Phase 5 statistical analysis (`GOALS.md` = scope contract; `ROADMAP.md` = backlog/history, huge).

## Source map
- `src/seo_rank/` — package (installed via `pyproject.toml`, entrypoint `seo_rank.cli:main`).
- `cli.py` — massive orchestration layer (~150 funcs): run modes, replay, backfill, combined-analysis, raw-response persistence. All commands route through `main`/`build_parser`.
- `data/` — curated-layer transforms: `normalize`, `marts`, `features`, `ranks`, `scans`, `validate`.
- `stats/` — Phase 5 statistical analysis: `regression`, `spearman`, `plackett_luce`, `bh` (Benjamini-Hochberg), `diagnostics`, `families`, `panel`, `rank_depth`, `scale`, `spec`, `model_inputs`, `artifacts`, explainability viz.
- Providers: `dataforseo.py`, `textrazor.py`, `gemini_embeddings.py`, `bge_reranker.py`, `similarity.py`, `text.py`, `env.py`.
- `analysis/`, `scripts/` — standalone research scripts, not part of installed package.
- Data lake: `runs/{run_id}/` Parquet, gitignored.

## Project-wide invariants
- Polars LazyFrame throughout: `pl.scan_parquet()` in, return LazyFrame, `collect(engine="streaming")` / `sink_parquet(compression="zstd")` only at boundaries.
- `validate.py` schema/key/null/range checks run before every mart `sink_parquet` (tests assert this).
- `raw_responses` partitioned ONLY by `endpoint` — never keyword/URL/task-id/rank. Excluded from analytical joins; used only by `replay` and re-normalization.
- BGE is pre-registered PRIMARY backend; Gemini secondary in fixed order (semantic similarity then doc retrieval). See `analysis_spec.v1.yaml`.
- `.env` auto-loads via `env.py` for both CLI and pytest — never `source .env`.
- Progress → stderr (`[seo-rank]` prefix); stdout clean for piping.

## Authoritative docs (read for detail, don't duplicate here)
- `AGENTS.md` — task rules, command cheatsheet, gotchas. Primary agent contract.
- Domains: `mem:tech_stack`, `mem:suggested_commands`, `mem:conventions`, `mem:task_completion`.

Knowledge graph exists at `graphify-out/graph.json` — AGENTS.md instructs querying graphify before exploring.
