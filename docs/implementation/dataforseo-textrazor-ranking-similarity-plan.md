# Implementation Plan: DataForSEO + TextRazor Ranking Similarity

Phased delivery plan. **Bold** = shipped in the repo today. Phase 1 runs in
**offline** mode (fixtures only, no network).

## Phase 1 — Offline CLI scaffold **(shipped)**

| Item | Status | Location |
|------|--------|----------|
| `seo-rank run` CLI and `RunConfig` | **Done** | `cli.py` |
| Keyword expansion fixture + normalize (cap 25, dedupe) | **Done** | `dataforseo.py` |
| SERP fixture + organic normalize (depth cap) | **Done** | `dataforseo.py` |
| Page-text fixture + passage normalize | **Done** | `dataforseo.py`, `text.py` |
| Fixture embedding similarity (page-level) | **Done** | `similarity.py` |
| TextRazor entity fixture + normalize (`--skip-textrazor`) | **Done** | `textrazor.py`, `cli.py` |
| `run.json` + `report.md` artifacts, `network_calls: []` | **Done** | `cli.py` |
| Unit tests + CLI smoke tests | **Done** | `tests/unit/` |

**Limitation:** SERP, page text, and similarity run against the **first**
expanded keyword only, not the full cluster.

## Phase 2 — Provider clients (not started)

- DataForSEO request construction: keyword expansion, SERP, page-text parsing
- TextRazor request construction from parsed page text
- Credential validation without leaking secrets in errors or artifacts
- Live calls gated behind integration tests or explicit non-default flags

## Phase 3 — Full cluster orchestration (not started)

- Loop all keywords in the capped cluster for SERP and downstream steps
- Preserve per-keyword target-keyword semantics in normalized outputs

## Phase 4 — Live similarity (not started)

Per cluster keyword, top-20 SERP; for each result score against the target
keyword at:

- Passage scope (each passage)
- Page scope (full parsed content)
- Domain scope (URL list proxy; max 1000 URLs; skip domains over 1000)

**Both** backends required on every live run:

- Cross-encoder `BGE-reranker-v2`
- Bi-encoder Gemini embedding + cosine similarity alone

## Phase 5 — Statistical analysis (not started)

Before interpretation on each run:

1. OLS pre-analysis preparation (linearity, multicollinearity, exogeneity
   review, homoscedasticity, normality, influence) — see root `ARCHITECTURE.md`
2. `statsmodels` OLS baseline vs similarity-feature models
3. Benjamini-Hochberg correction across keyword- and feature-level comparisons
4. Diagnostic and model outputs in run artifacts

Planned libraries: `statsmodels`, `numpy`, `scipy`, `patsy`, `linearmodels`.

## Phase 6 — Reporting and artifact layout (not started)

- Standard layout under `runs/RUN_ID/`
- Markdown sections for observational limits and top-20 censoring
- Keep generated runs out of source control

## Verification

Current gate: `python -m pytest` (10 tests).

Future gates: integration tests for live providers; analysis tests with synthetic
ranking panels once Phase 5 begins.
