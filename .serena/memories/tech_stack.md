# Tech Stack

- Python >=3.11. Package `seo-rank` v0.2.0, src-layout under `src/`, setuptools build.
- Dataframes: **Polars** (LazyFrame-first), **pyarrow** for Parquet lake.
- Stats: numpy, scipy, statsmodels. Config: PyYAML. Plots: matplotlib.
- Optional extras: `dev` = pytest>=8; `similarity` = google-genai, FlagEmbedding (BGE, needs CUDA).
- Package/lock: `uv.lock` present (uv). `requirements.txt` exists but version pins DIVERGE from `pyproject.toml` (e.g. requirements lists pandas/numpy2/pyarrow24) — `pyproject.toml` is authoritative for the installed package.
- No lint/typecheck/build/CI tooling exists — do not search for it (per AGENTS.md).
- Node side-config only: `.codex/hooks/git-guard.cjs` (commit guard), litellm/headroom proxy configs (`config.yaml`, `litellm_config.yaml`) — infra, not app code.
