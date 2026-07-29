"""Per-entity ranking associations from the long-form entity signals mart."""
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md


from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import polars as pl
import statsmodels.api as sm
from scipy.stats import spearmanr

from seo_rank.stats.bh import adjust_p_values


ENTITY_METRICS = (
    "entity_present",
    "entity_mention_count",
    "entity_confidence_mean",
    "entity_relevance_mean",
)
MIN_PRESENT_PAGES = 10
MIN_PRESENT_KEYWORDS = 3
MIN_INFERENCE_KEYWORDS = 10


def summarize_entity_signals(
    entity_signals: pl.DataFrame,
    *,
    entity_ids: set[str] | None = None,
    policy: Mapping[str, int | float] | None = None,
    rank_depth_key: str = "top_20",
) -> pl.DataFrame:
    """Return one typed result per eligible entity and signal metric."""

    policy = policy or {}
    min_present_pages = int(policy.get("min_present_pages", MIN_PRESENT_PAGES))
    min_present_keywords = int(policy.get("min_present_keywords", MIN_PRESENT_KEYWORDS))
    min_inference_keywords = int(policy.get("min_inference_keywords", MIN_INFERENCE_KEYWORDS))
    bh_q = float(policy.get("bh_q", 0.05))
    if entity_signals.is_empty():
        return _empty_results()
    if entity_ids is not None:
        entity_signals = entity_signals.filter(pl.col("entity_id").is_in(sorted(entity_ids)))
    entity_signals = _deduplicate_entity_pages(entity_signals)

    rows: list[dict[str, object]] = []
    for entity_id, frame in entity_signals.group_by("entity_id", maintain_order=True):
        entity_id = str(entity_id[0])
        present = frame.filter(pl.col("entity_present") == 1)
        page_key = (
            ["target_keyword_id", "canonical_url_hash"]
            if "canonical_url_hash" in present.columns
            else ["target_keyword_id", "url"]
        )
        present_page_count = present.select(page_key).unique().height
        present_keyword_count = present.get_column("target_keyword_id").n_unique()
        eligible = (
            present_page_count >= min_present_pages
            and present_keyword_count >= min_present_keywords
        )
        examples = _examples(present)
        for metric in ENTITY_METRICS:
            metric_frame = frame if metric in {"entity_present", "entity_mention_count"} else present
            metric_frame = metric_frame.drop_nulls([metric, "serp_rank"])
            usable_keyword_count = _usable_keyword_count(metric_frame, metric)
            status, median_rho, raw_p_value, coefficient, coefficient_p_value, covariance = _evaluate_metric(
                metric_frame,
                metric=metric,
                eligible=eligible,
                usable_keyword_count=usable_keyword_count,
                min_inference_keywords=min_inference_keywords,
            )
            rows.append(
                {
                    "entity_id": entity_id,
                    "rank_depth_key": rank_depth_key,
                    "metric": metric,
                    "present_page_count": present_page_count,
                    "present_keyword_count": present_keyword_count,
                    "usable_page_count": metric_frame.height,
                    "usable_keyword_count": usable_keyword_count,
                    "median_spearman_rho": median_rho,
                    "spearman_p_value": raw_p_value,
                    "ols_coefficient": coefficient,
                    "ols_p_value": coefficient_p_value,
                    "ols_covariance": covariance,
                    "bh_q_value": None,
                    "status": status,
                    **examples,
                }
            )

    _apply_bh(rows, bh_q=bh_q)
    return pl.DataFrame(rows, schema=_result_schema()).sort(
        ["rank_depth_key", "metric", "entity_id"]
    )


def _evaluate_metric(
    frame: pl.DataFrame,
    *,
    metric: str,
    eligible: bool,
    usable_keyword_count: int,
    min_inference_keywords: int,
) -> tuple[str, float | None, float | None, float | None, float | None, str | None]:
    if frame.height < 3 or frame.get_column(metric).n_unique() < 2:
        return "non-estimable", None, None, None, None, None

    keyword_tests: list[tuple[float, float]] = []
    for _, keyword_frame in frame.group_by("target_keyword_id", maintain_order=True):
        if keyword_frame.height < 3 or keyword_frame.get_column(metric).n_unique() < 2:
            continue
        rho, p_value = spearmanr(
            keyword_frame.get_column(metric).to_numpy(),
            keyword_frame.get_column("serp_rank").to_numpy(),
        )
        if np.isfinite(rho) and np.isfinite(p_value):
            keyword_tests.append((float(rho), float(p_value)))
    if not keyword_tests:
        return "non-estimable", None, None, None, None, None

    median_rho = float(np.median([rho for rho, _ in keyword_tests]))
    spearman_p_value = float(np.median([p for _, p in keyword_tests]))
    coefficient, ols_p_value, covariance = _keyword_fixed_effect_ols(frame, metric)
    if not eligible or usable_keyword_count < min_inference_keywords:
        return "underpowered", median_rho, spearman_p_value, coefficient, ols_p_value, covariance
    if ols_p_value is None:
        return "non-estimable", median_rho, spearman_p_value, coefficient, ols_p_value, covariance
    return "non-significant", median_rho, spearman_p_value, coefficient, ols_p_value, covariance


def _deduplicate_entity_pages(frame: pl.DataFrame) -> pl.DataFrame:
    page_key = "canonical_url_hash" if "canonical_url_hash" in frame.columns else "url"
    return (
        frame.sort(["entity_id", "target_keyword_id", "serp_rank", "url"])
        .unique(["entity_id", "target_keyword_id", page_key], keep="first", maintain_order=True)
    )


def _keyword_fixed_effect_ols(
    frame: pl.DataFrame,
    metric: str,
) -> tuple[float | None, float | None, str | None]:
    values = frame.get_column(metric).cast(pl.Float64).to_numpy()
    outcome = -np.log(frame.get_column("serp_rank").cast(pl.Float64).to_numpy())
    keyword_codes = frame.get_column("target_keyword_id").cast(pl.Categorical).to_physical().to_numpy()
    dummy_columns = [
        (keyword_codes == code).astype(float)
        for code in sorted(set(keyword_codes))[1:]
    ]
    design = np.column_stack([np.ones(frame.height), values, *dummy_columns])
    try:
        result = sm.OLS(outcome, design).fit()
        if len(set(keyword_codes)) < 2:
            return float(result.params[1]), None, None
        clustered = result.get_robustcov_results(
            cov_type="cluster",
            groups=keyword_codes,
        )
    except (np.linalg.LinAlgError, ValueError):
        return None, None, None
    return float(result.params[1]), float(clustered.pvalues[1]), "cluster"


def _usable_keyword_count(frame: pl.DataFrame, metric: str) -> int:
    return sum(
        1
        for _, keyword_frame in frame.group_by("target_keyword_id", maintain_order=True)
        if keyword_frame.height >= 3 and keyword_frame.get_column(metric).n_unique() >= 2
    )


def _examples(present: pl.DataFrame) -> dict[str, object]:
    examples = present.sort(["serp_rank", "target_keyword", "url"]).head(3)
    return {
        "example_urls": examples.get_column("url").to_list(),
        "example_matched_texts": [
            ", ".join(values)
            for values in examples.get_column("matched_texts").to_list()
        ],
        "example_entity_types": [
            ", ".join(values)
            for values in examples.get_column("entity_types").to_list()
        ],
    }


def _apply_bh(rows: list[dict[str, object]], *, bh_q: float) -> None:
    for metric in ENTITY_METRICS:
        eligible_rows = [
            row
            for row in rows
            if row["metric"] == metric
            and row["status"] == "non-significant"
            and isinstance(row["ols_p_value"], float)
            and math.isfinite(row["ols_p_value"])
        ]
        if not eligible_rows:
            continue
        for row, q_value in zip(
            eligible_rows,
            adjust_p_values([float(row["ols_p_value"]) for row in eligible_rows]),
            strict=True,
        ):
            row["bh_q_value"] = q_value
            if q_value <= bh_q:
                row["status"] = "significant"


def _result_schema() -> dict[str, pl.DataType]:
    return {
        "entity_id": pl.Utf8,
        "rank_depth_key": pl.Utf8,
        "metric": pl.Utf8,
        "present_page_count": pl.Int64,
        "present_keyword_count": pl.Int64,
        "usable_page_count": pl.Int64,
        "usable_keyword_count": pl.Int64,
        "median_spearman_rho": pl.Float64,
        "spearman_p_value": pl.Float64,
        "ols_coefficient": pl.Float64,
        "ols_p_value": pl.Float64,
        "ols_covariance": pl.Utf8,
        "bh_q_value": pl.Float64,
        "status": pl.Utf8,
        "example_urls": pl.List(pl.Utf8),
        "example_matched_texts": pl.List(pl.Utf8),
        "example_entity_types": pl.List(pl.Utf8),
    }


def _empty_results() -> pl.DataFrame:
    return pl.DataFrame(schema=_result_schema())

# randomized-text: quiet marbles cross the paper sky 82fc8a3d674cf75a
