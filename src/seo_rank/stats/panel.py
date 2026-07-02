"""Phase 5 panel preparation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from seo_rank.data.scans import scan_curated_table
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec

SIMILARITY_RATE_COLUMNS = {
    "bge": "bge_normalized_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}
LIMITATION_TEXT = {
    "observational_only": "Associations are observational, not causal.",
    "top_20_truncation": "Associations are limited to observed top-20 SERP rows per keyword.",
    "no_causal_claims": "Do not interpret coefficients as causal ranking factors.",
    "measurement_error_conservative": "Similarity scores are model outputs and may attenuate effects.",
}


@dataclass(frozen=True)
class AnalysisPanelResult:
    """Prepared analysis panel plus guardrail evaluation."""

    run_dir: Path
    analysis_mart: pl.DataFrame
    panel: pl.DataFrame
    guardrails: list[dict[str, Any]]
    limitations: dict[str, str]
    hard_fail: bool
    analysis_spec_version: str
    estimand_version: str
    primary_backend: str
    backend_order: tuple[str, ...]


def load_analysis_panel(
    run_dir: Path,
    *,
    spec: AnalysisSpec | None = None,
) -> AnalysisPanelResult:
    """Load the analysis mart, prepare the panel, and evaluate guardrails."""

    analysis_spec = spec or load_analysis_spec()
    analysis_mart = scan_curated_table(run_dir, "analysis_mart").collect()
    return prepare_analysis_panel(run_dir, analysis_mart, spec=analysis_spec)


def prepare_analysis_panel(
    run_dir: Path,
    analysis_mart: pl.DataFrame,
    *,
    spec: AnalysisSpec | None = None,
) -> AnalysisPanelResult:
    """Prepare the panel from an already materialized analysis mart."""

    analysis_spec = spec or load_analysis_spec()
    prepared_mart = (
        analysis_mart.filter(pl.col("serp_rank").is_between(1, 20, closed="both"))
        .sort(["target_keyword_id", "canonical_url_hash", "serp_rank", "serp_item_id"])
        .unique(
            subset=["run_id", "target_keyword_id", "canonical_url_hash"],
            keep="first",
            maintain_order=True,
        )
        .sort(["target_keyword_id", "canonical_url_hash", "serp_rank", "serp_item_id"])
    )
    primary_panel = prepared_mart.filter(
        pl.col(f"{analysis_spec.primary_backend}_normalized_score").is_not_null()
    )
    guardrails = _evaluate_guardrails(prepared_mart, analysis_spec)
    hard_fail = any(
        guardrail["status"] == "fail"
        for guardrail in guardrails
        if guardrail["name"] in _hard_fail_guardrail_names(analysis_spec)
    )
    return AnalysisPanelResult(
        run_dir=Path(run_dir),
        analysis_mart=prepared_mart,
        panel=primary_panel,
        guardrails=guardrails,
        limitations={name: LIMITATION_TEXT[name] for name in analysis_spec.data["limitations"]},
        hard_fail=hard_fail,
        analysis_spec_version=analysis_spec.version,
        estimand_version=analysis_spec.estimand_version,
        primary_backend=analysis_spec.primary_backend,
        backend_order=analysis_spec.backend_order,
    )


def _evaluate_guardrails(
    analysis_mart: pl.DataFrame,
    spec: AnalysisSpec,
) -> list[dict[str, Any]]:
    total_rows = analysis_mart.height
    primary_backend_column = f"{spec.primary_backend}_normalized_score"
    complete_primary_keywords = 0
    if total_rows:
        complete_primary_keywords = (
            analysis_mart.group_by("target_keyword_id")
            .agg(pl.col(primary_backend_column).is_not_null().all().alias("complete"))
            .filter(pl.col("complete"))
            .height
        )

    non_null_rates = {}
    for backend, column in SIMILARITY_RATE_COLUMNS.items():
        non_null_count = (
            analysis_mart.select(pl.col(column).is_not_null().sum()).item()
            if total_rows
            else 0
        )
        non_null_rates[backend] = non_null_count / total_rows if total_rows else 0.0

    serp_rank_variance = _min_keyword_variance(analysis_mart, "serp_rank")
    similarity_variances = {
        backend: _min_keyword_variance(analysis_mart, column)
        for backend, column in SIMILARITY_RATE_COLUMNS.items()
    }

    guardrails: list[dict[str, Any]] = [
        {
            "name": "keywords_with_complete_primary_backend_scores",
            "status": "pass" if complete_primary_keywords >= 10 else "fail",
            "value": complete_primary_keywords,
            "threshold": 10,
        },
        {
            "name": "non_null_score_rate_per_backend",
            "status": "pass" if min(non_null_rates.values() or [0.0]) >= 0.90 else "warn",
            "value": non_null_rates,
            "threshold": 0.90,
        },
        {
            "name": "serp_rank_variance_within_keyword",
            "status": "pass" if serp_rank_variance > 0 else "fail",
            "value": serp_rank_variance,
            "threshold": 0,
        },
        {
            "name": "similarity_variance_within_keyword",
            "status": "pass" if min(similarity_variances.values() or [0.0]) > 0 else "warn",
            "value": similarity_variances,
            "threshold": 0,
        },
    ]
    return guardrails


def _min_keyword_variance(analysis_mart: pl.DataFrame, column: str) -> float:
    if analysis_mart.is_empty():
        return 0.0

    per_keyword_variance = (
        analysis_mart.group_by("target_keyword_id")
        .agg(pl.col(column).var(ddof=0).fill_null(0.0).alias("variance"))
        .select(pl.col("variance").min())
        .item()
    )
    return float(per_keyword_variance or 0.0)


def _hard_fail_guardrail_names(spec: AnalysisSpec) -> set[str]:
    return {
        guardrail["name"]
        for guardrail in spec.data["guardrails"]["hard_fail"]
    }
