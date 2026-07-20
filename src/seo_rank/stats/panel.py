"""Phase 5 panel preparation helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from seo_rank.data.scans import scan_curated_table
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec


logger = logging.getLogger(__name__)

_ANALYSIS_JOIN_KEYS = ("run_id", "target_keyword_id", "canonical_url_hash", "url")
_DOMAIN_CONTROL_COLUMNS = ("site_scale", "authority_proxy")
_PAGE_CONTROL_DTYPES = {
    "deprecated_html_tags": pl.Boolean,
    "time_to_first_byte_ms": pl.Int64,
}
_ANALYSIS_CONTROL_DTYPES = {
    **_PAGE_CONTROL_DTYPES,
    "site_scale": pl.Float64,
    "authority_proxy": pl.Float64,
}

SIMILARITY_RATE_COLUMNS = {
    "bge": "bge_normalized_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}
LIMITATION_TEXT = {
    "observational_only": "Associations are observational, not causal.",
    "top_20_truncation": "Associations are limited to observed top-20 SERP rows per keyword.",
    "top_10_truncation": "Associations are limited to observed top-10 SERP rows per keyword.",
    "top_5_truncation": "Associations are limited to observed top-5 SERP rows per keyword.",
    "top_3_truncation": "Associations are limited to observed top-3 SERP rows per keyword.",
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

    logger.info("loading analysis panel run_dir=%s", run_dir)
    analysis_spec = spec or load_analysis_spec()
    analysis_mart = scan_curated_table(run_dir, "analysis_mart").collect()
    analysis_mart = _normalize_analysis_mart_controls(run_dir, analysis_mart)
    result = prepare_analysis_panel(run_dir, analysis_mart, spec=analysis_spec)
    logger.info(
        "loaded analysis panel run_dir=%s mart_rows=%d panel_rows=%d hard_fail=%s",
        run_dir,
        result.analysis_mart.height,
        result.panel.height,
        result.hard_fail,
    )
    return result


def _normalize_analysis_mart_controls(
    run_dir: Path,
    analysis_mart: pl.DataFrame,
) -> pl.DataFrame:
    """Restore controls omitted by legacy analysis-mart partitions."""
    missing = [
        column for column in _ANALYSIS_CONTROL_DTYPES if column not in analysis_mart.columns
    ]
    if not missing:
        return analysis_mart

    missing_domain = [column for column in missing if column in _DOMAIN_CONTROL_COLUMNS]
    if missing_domain:
        analysis_mart = _restore_domain_controls_from_domain_features(
            run_dir,
            analysis_mart,
            missing_domain,
        )
        missing = [
            column for column in _ANALYSIS_CONTROL_DTYPES if column not in analysis_mart.columns
        ]
        if not missing:
            return analysis_mart

    missing_page = [column for column in missing if column in _PAGE_CONTROL_DTYPES]
    for source_name in ("onpage_features", "onpage_signals", "backlinks"):
        if not missing_page:
            break
        source_path = Path(run_dir) / "parquet" / source_name
        if not source_path.exists():
            continue
        try:
            source = scan_curated_table(run_dir, source_name).collect()
        except OSError:
            continue
        joinable = [
            column
            for column in missing_page
            if column in source.columns and all(key in source.columns for key in _ANALYSIS_JOIN_KEYS)
        ]
        if not joinable:
            continue
        analysis_mart = analysis_mart.join(
            source.select([*_ANALYSIS_JOIN_KEYS, *joinable]),
            on=list(_ANALYSIS_JOIN_KEYS),
            how="left",
        )
        missing_page = [column for column in missing_page if column not in analysis_mart.columns]

    # Null-fill page-grain controls only. Domain controls stay absent when
    # domain_features cannot restore them so rematerialize / validate fails loud.
    if missing_page:
        analysis_mart = analysis_mart.with_columns(
            [
                pl.lit(None).cast(_PAGE_CONTROL_DTYPES[column]).alias(column)
                for column in missing_page
            ]
        )
    return analysis_mart


def _restore_domain_controls_from_domain_features(
    run_dir: Path,
    analysis_mart: pl.DataFrame,
    missing_domain: list[str],
) -> pl.DataFrame:
    """Join missing site_scale / authority_proxy from domain_features by hostname."""
    source_path = Path(run_dir) / "parquet" / "domain_features"
    if not source_path.exists() or not missing_domain:
        return analysis_mart
    if "url" not in analysis_mart.columns or "run_id" not in analysis_mart.columns:
        return analysis_mart
    try:
        domain_features = scan_curated_table(run_dir, "domain_features").collect()
    except OSError:
        logger.warning(
            "failed to scan domain_features for control restore run_dir=%s",
            run_dir,
        )
        return analysis_mart

    present = [column for column in missing_domain if column in domain_features.columns]
    if not present or "domain" not in domain_features.columns:
        return analysis_mart

    domain_lookup = domain_features.select(["run_id", "domain", *present]).unique(
        ["run_id", "domain"]
    )
    return (
        analysis_mart.with_columns(
            pl.col("url").str.extract(r"^https?://([^/]+)", 1).alias("__domain")
        )
        .join(
            domain_lookup,
            left_on=["run_id", "__domain"],
            right_on=["run_id", "domain"],
            how="left",
        )
        .drop("__domain")
    )


def _restore_analysis_controls(
    source_frame: pl.DataFrame,
    analysis_mart: pl.DataFrame,
) -> pl.DataFrame:
    """Restore controls omitted by older optional family-mart schemas."""
    if source_frame.is_empty():
        return source_frame

    missing = [
        column for column in _ANALYSIS_CONTROL_DTYPES if column not in source_frame.columns
    ]
    if not missing:
        return source_frame

    joinable = [
        column
        for column in missing
        if column in analysis_mart.columns
        and all(key in source_frame.columns for key in _ANALYSIS_JOIN_KEYS)
    ]
    if joinable:
        source_frame = source_frame.join(
            analysis_mart.select([*_ANALYSIS_JOIN_KEYS, *joinable]),
            on=list(_ANALYSIS_JOIN_KEYS),
            how="left",
        )

    remaining_page = [
        column
        for column in missing
        if column in _PAGE_CONTROL_DTYPES and column not in source_frame.columns
    ]
    if remaining_page:
        source_frame = source_frame.with_columns(
            [
                pl.lit(None).cast(_PAGE_CONTROL_DTYPES[column]).alias(column)
                for column in remaining_page
            ]
        )
    return source_frame


def prepare_analysis_panel(
    run_dir: Path,
    analysis_mart: pl.DataFrame,
    *,
    spec: AnalysisSpec | None = None,
) -> AnalysisPanelResult:
    """Prepare the panel from an already materialized analysis mart."""

    analysis_spec = spec or load_analysis_spec()
    max_rank = analysis_spec.rank_depth_limit(analysis_spec.primary_rank_depth)
    prepared_mart = (
        analysis_mart.filter(pl.col("serp_rank").is_between(1, max_rank, closed="both"))
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
    guardrails = evaluate_guardrails(prepared_mart, analysis_spec)
    hard_fail = any(
        guardrail["status"] == "fail"
        for guardrail in guardrails
        if guardrail["name"] in _hard_fail_guardrail_names(analysis_spec)
    )
    logger.info(
        "prepared analysis panel mart_rows=%d panel_rows=%d hard_fail=%s",
        prepared_mart.height,
        primary_panel.height,
        hard_fail,
    )
    return AnalysisPanelResult(
        run_dir=Path(run_dir),
        analysis_mart=prepared_mart,
        panel=primary_panel,
        guardrails=guardrails,
        limitations=build_limitations_for_rank_depth(analysis_spec, analysis_spec.primary_rank_depth),
        hard_fail=hard_fail,
        analysis_spec_version=analysis_spec.version,
        estimand_version=analysis_spec.estimand_version,
        primary_backend=analysis_spec.primary_backend,
        backend_order=analysis_spec.backend_order,
    )


def evaluate_guardrails(
    analysis_mart: pl.DataFrame,
    spec: AnalysisSpec,
) -> list[dict[str, Any]]:
    return _evaluate_guardrails(analysis_mart, spec)


def build_limitations_for_rank_depth(
    spec: AnalysisSpec,
    depth_key: str,
) -> dict[str, str]:
    depth_truncation_key = spec.limitation_key_for_rank_depth(depth_key)
    limitation_keys = [*spec.data["limitations"], depth_truncation_key]
    return {name: LIMITATION_TEXT[name] for name in limitation_keys}


def prepare_rank_depth_panel(
    analysis_mart: pl.DataFrame,
    *,
    depth_key: str,
    spec: AnalysisSpec,
) -> tuple[pl.DataFrame, pl.DataFrame, list[dict[str, Any]], bool, dict[str, str]]:
    max_rank = spec.rank_depth_limit(depth_key)
    depth_mart = filter_panel_by_max_rank(analysis_mart, max_rank=max_rank)
    depth_mart = (
        depth_mart.sort(["target_keyword_id", "canonical_url_hash", "serp_rank", "serp_item_id"])
        .unique(
            subset=["run_id", "target_keyword_id", "canonical_url_hash"],
            keep="first",
            maintain_order=True,
        )
        .sort(["target_keyword_id", "canonical_url_hash", "serp_rank", "serp_item_id"])
    )
    depth_panel = depth_mart.filter(
        pl.col(f"{spec.primary_backend}_normalized_score").is_not_null()
    )
    guardrails = _evaluate_guardrails(depth_mart, spec)
    hard_fail = any(
        guardrail["status"] == "fail"
        for guardrail in guardrails
        if guardrail["name"] in _hard_fail_guardrail_names(spec)
    )
    limitations = build_limitations_for_rank_depth(spec, depth_key)
    logger.info(
        "prepared rank_depth_panel depth=%s max_rank=%d mart_rows=%d panel_rows=%d hard_fail=%s",
        depth_key,
        max_rank,
        depth_mart.height,
        depth_panel.height,
        hard_fail,
    )
    return depth_mart, depth_panel, guardrails, hard_fail, limitations


def _evaluate_guardrails(
    analysis_mart: pl.DataFrame,
    spec: AnalysisSpec,
) -> list[dict[str, Any]]:
    serp_rank_variance = _min_keyword_variance(analysis_mart, "serp_rank")
    similarity_variances = {
        backend: _min_keyword_variance(analysis_mart, column)
        for backend, column in SIMILARITY_RATE_COLUMNS.items()
    }

    guardrails: list[dict[str, Any]] = [
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
