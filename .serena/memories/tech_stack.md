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
# Tech Stack


- Python >=3.11. Package `seo-rank` v0.2.0, src-layout under `src/`, setuptools build.
- Dataframes: **Polars** (LazyFrame-first), **pyarrow** for Parquet lake.
- Stats: numpy, scipy, statsmodels. Config: PyYAML. Plots: matplotlib.
- Optional extras: `dev` = pytest>=8; `similarity` = google-genai, FlagEmbedding (BGE, needs CUDA).
- Package/lock: `uv.lock` present (uv). `requirements.txt` exists but version pins DIVERGE from `pyproject.toml` (e.g. requirements lists pandas/numpy2/pyarrow24) — `pyproject.toml` is authoritative for the installed package.
- No lint/typecheck/build/CI tooling exists — do not search for it (per AGENTS.md).
- Node side-config only: `.codex/hooks/git-guard.cjs` (commit guard), litellm/headroom proxy configs (`config.yaml`, `litellm_config.yaml`) — infra, not app code.
