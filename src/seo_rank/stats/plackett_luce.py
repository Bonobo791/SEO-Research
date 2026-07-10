"""Phase 5 Plackett-Luce / rank-ordered logit helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Sequence
from math import isfinite

import numpy as np
import pandas as pd
import polars as pl
from seo_rank.stats.families import SignalFamily, SignalFamilyRegistry, plackett_luce_enabled_for_family, source_mart_for_family
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.scale import within_keyword_sd_rms
from seo_rank.stats.spec import AnalysisSpec
from scipy import optimize, stats
from scipy.special import logsumexp


logger = logging.getLogger(__name__)

SIMILARITY_SCORE_COLUMNS = {
    "bge": "bge_normalized_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}
PL_CONTROL_COLUMNS = (
    "deprecated_html_tags",
    "meta_keywords_to_content_consistency",
)
PL_LOG_CONTROL_COLUMNS = frozenset(("deprecated_html_tags",))
PLACKET_LUCE_REQUIRED_COLUMNS = (
    "serp_rank",
    "target_keyword_id",
)
DEFAULT_MAX_SERP_RANK = 20
HESSIAN_CONDITION_NUMBER_THRESHOLD = 100.0
OPTIMIZER_GRADIENT_TOLERANCE = 1e-6
FORMULA = "rank_ordered_logit ~ similarity + log(deprecated_html_tags + 1) + meta_keywords_to_content_consistency"
FAMILY_PLACKETT_LUCE_OPTIMIZER_OPTIONS: dict[str, object] = {"maxiter": 100}


@dataclass(frozen=True)
class PlackettLuceOptimizerResult:
    """Optimizer metadata for a PL fit."""

    converged: bool
    message: str
    iterations: int
    gradient_norm: float
    objective_value: float


@dataclass(frozen=True)
class PlackettLuceFit:
    """Prepared PL fit for one backend."""

    backend: str
    score_column: str
    fitted_control_columns: tuple[str, ...]
    omitted_controls: tuple[dict[str, str], ...]
    model_data: pd.DataFrame
    choice_set_sizes: list[dict[str, object]]
    duplicate_serp_rank_keyword_count: int
    params: np.ndarray
    covariance: np.ndarray
    information: np.ndarray
    log_likelihood: float
    optimizer: PlackettLuceOptimizerResult
    similarity_within_keyword_sd: float


def summarize_plackett_luce_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, object]:
    """Summarize the PL path for every configured backend."""

    logger.info("summarizing plackett-luce backends=%s", list(backend_order))
    fits = fit_plackett_luce_backends(analysis_mart, backend_order)
    return summarize_plackett_luce_backends_from_fits(
        analysis_mart,
        backend_order,
        fits=fits,
    )


def summarize_plackett_luce_families(
    source_frames: dict[str, pl.DataFrame],
    *,
    registry: SignalFamilyRegistry,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
    include_iia_sensitivity: bool = False,
    optimizer_options: dict[str, object] | None = None,
) -> dict[str, object]:
    """Summarize rank-ordered logit models for every family in the registry."""

    family_optimizer_options = (
        optimizer_options
        if optimizer_options is not None
        else FAMILY_PLACKETT_LUCE_OPTIMIZER_OPTIONS
    )
    return {
        "families": {
            family.key: summarize_plackett_luce_family(
                source_frames,
                family=family,
                max_rank=max_rank,
                include_iia_sensitivity=include_iia_sensitivity,
                optimizer_options=family_optimizer_options,
            )
            for family in registry.families
        }
    }


def fit_backend_plackett_luce(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
    optimizer_options: dict[str, object] | None = None,
) -> PlackettLuceFit | None:
    """Fit a PL model for one backend."""

    return fit_plackett_luce_for_score_column(
        analysis_mart,
        label=backend,
        score_column=_score_column_for_backend(backend),
        max_rank=max_rank,
        optimizer_options=optimizer_options,
    )


def fit_plackett_luce_for_score_column(
    analysis_mart: pl.DataFrame,
    *,
    label: str,
    score_column: str,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
    optimizer_options: dict[str, object] | None = None,
) -> PlackettLuceFit | None:
    """Fit a PL model for one arbitrary signal column."""

    logger.debug("fitting plackett-luce backend=%s max_rank=%d", label, max_rank)
    prepared = _prepare_plackett_luce_frame(analysis_mart, max_rank=max_rank)
    if prepared.is_empty():
        logger.debug("plackett-luce backend=%s skipped: no prepared rows", label)
        return None

    raw_model_data = prepared.to_pandas().copy()
    if raw_model_data.empty:
        logger.debug("plackett-luce backend=%s skipped: empty model data", label)
        return None

    return fit_plackett_luce_for_prepared_model_data(
        raw_model_data,
        label=label,
        score_column=score_column,
        optimizer_options=optimizer_options,
    )


def fit_plackett_luce_for_prepared_model_data(
    raw_model_data: pd.DataFrame,
    *,
    label: str,
    score_column: str,
    optimizer_options: dict[str, object] | None = None,
    sorted_model_data: pd.DataFrame | None = None,
) -> PlackettLuceFit | None:
    """Fit a PL model from an already prepared pandas panel."""

    model_data = sorted_model_data if sorted_model_data is not None else raw_model_data
    if score_column not in model_data.columns:
        logger.debug("plackett-luce backend=%s skipped: missing score column", label)
        return None

    if _pl_signal_variance(model_data, score_column) == 0.0:
        logger.debug(
            "plackett-luce backend=%s skipped: insufficient signal variance score_column=%s",
            label,
            score_column,
        )
        return None

    keyword_frames, duplicate_serp_rank_keyword_count = _build_keyword_frames(
        model_data,
        score_column,
        sorted_model_data=model_data,
    )
    eligible_keyword_frames = [frame for frame in keyword_frames if len(frame) >= 2]
    if not eligible_keyword_frames:
        logger.debug("plackett-luce backend=%s skipped: no keyword groups", label)
        return None

    fitted_model_data = pd.concat(eligible_keyword_frames, ignore_index=True)
    fitted_control_columns, omitted_controls = _select_pl_controls(fitted_model_data)
    grouped = _build_keyword_groups(
        eligible_keyword_frames,
        score_column,
        fitted_control_columns,
    )

    if max(group["choice_set_size"] for group in grouped) < 2:
        logger.debug("plackett-luce backend=%s skipped: choice set smaller than 2", label)
        return None

    params, optimizer_result = _maximize_log_likelihood(
        grouped,
        optimizer_options=optimizer_options,
    )
    log_likelihood, gradient, hessian = _loglik_gradient_hessian(
        params,
        grouped,
    )
    information = -hessian
    information_inverse = np.linalg.pinv(information)
    cluster_scores = np.vstack(
        [_group_score_contribution(group["features"], params) for group in grouped]
    )
    meat = cluster_scores.T @ cluster_scores
    covariance = information_inverse @ meat @ information_inverse
    covariance = _symmetrize(covariance)

    choice_set_sizes = [
        {
            "target_keyword_id": group["target_keyword_id"],
            "choice_set_size": group["choice_set_size"],
        }
        for group in grouped
    ]

    if not optimizer_result.converged:
        logger.warning(
            "plackett-luce backend=%s optimizer did not converge: %s",
            label,
            optimizer_result.message,
        )

    return PlackettLuceFit(
        backend=label,
        score_column=score_column,
        fitted_control_columns=fitted_control_columns,
        omitted_controls=omitted_controls,
        model_data=fitted_model_data,
        choice_set_sizes=choice_set_sizes,
        duplicate_serp_rank_keyword_count=duplicate_serp_rank_keyword_count,
        params=params,
        covariance=covariance,
        information=information,
        log_likelihood=log_likelihood,
        optimizer=optimizer_result,
        similarity_within_keyword_sd=within_keyword_sd_rms(fitted_model_data, score_column),
    )


def summarize_plackett_luce_for_score_column(
    analysis_mart: pl.DataFrame,
    *,
    label: str,
    score_column: str,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
    include_diagnostics: bool = True,
    include_iia_sensitivity: bool = False,
) -> dict[str, object]:
    """Fit and summarize the PL path for an arbitrary signal column."""

    fit = fit_plackett_luce_for_score_column(
        analysis_mart,
        label=label,
        score_column=score_column,
        max_rank=max_rank,
    )
    return _summarize_backend_plackett_luce_result(
        analysis_mart,
        backend=label,
        fit=fit,
        include_diagnostics=include_diagnostics,
        include_iia_sensitivity=include_iia_sensitivity,
        max_rank=max_rank,
        score_column=score_column,
    )


def summarize_plackett_luce_family(
    source_frames: dict[str, pl.DataFrame],
    *,
    family: SignalFamily,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
    include_iia_sensitivity: bool = False,
    optimizer_options: dict[str, object] | None = None,
) -> dict[str, object]:
    """Summarize rank-ordered logit for one signal family."""

    source_mart = source_mart_for_family(family)
    if not plackett_luce_enabled_for_family(family):
        return {
            "family": family.key,
            "kind": family.kind,
            "source_mart": source_mart,
            "signal_columns": list(family.signal_columns),
            "signals": {},
            "backends": {},
            "status": "skipped",
            "skipped_reason": "family_pl_deferred",
        }

    source_frame = source_frames.get(source_mart)
    if source_frame is None or source_frame.is_empty():
        return {
            "family": family.key,
            "kind": family.kind,
            "source_mart": source_mart,
            "signal_columns": list(family.signal_columns),
            "signals": {},
            "backends": {},
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
        }

    prepared = _prepare_plackett_luce_frame(source_frame, max_rank=max_rank)
    if prepared.is_empty():
        return {
            "family": family.key,
            "kind": family.kind,
            "source_mart": source_mart,
            "signal_columns": list(family.signal_columns),
            "signals": {},
            "backends": {},
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
        }

    raw_model_data = prepared.to_pandas().copy()
    sorted_model_data = raw_model_data.sort_values(
        by=["keyword_order", "target_keyword_id", "serp_rank", "serp_item_id"],
        kind="mergesort",
    )

    family_optimizer_options = (
        optimizer_options
        if optimizer_options is not None
        else FAMILY_PLACKETT_LUCE_OPTIMIZER_OPTIONS
    )
    signal_summaries: dict[str, dict[str, object]] = {}
    for signal_column in family.signal_columns:
        signal_summaries[signal_column] = _summarize_plackett_luce_for_prepared_model_data(
            raw_model_data,
            sorted_model_data=sorted_model_data,
            label=family.key,
            score_column=signal_column,
            include_diagnostics=True,
            include_iia_sensitivity=include_iia_sensitivity,
            optimizer_options=family_optimizer_options,
        )
    status = (
        "computed"
        if any(summary.get("status") != "skipped" for summary in signal_summaries.values())
        else "skipped"
    )
    family_summary: dict[str, object] = {
        "family": family.key,
        "kind": family.kind,
        "source_mart": source_mart,
        "signal_columns": list(family.signal_columns),
        "signals": signal_summaries,
        "backends": signal_summaries,
        "status": status,
    }
    if status == "skipped":
        family_summary["skipped_reason"] = "no_usable_rows"
    return family_summary


def fit_plackett_luce_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
    optimizer_options: dict[str, object] | None = None,
) -> dict[str, PlackettLuceFit | None]:
    """Fit the PL model once per backend."""

    return {
        backend: fit_backend_plackett_luce(
            analysis_mart,
            backend=backend,
            max_rank=max_rank,
            optimizer_options=optimizer_options,
        )
        for backend in backend_order
    }


def fit_plackett_luce_rank_depths(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    depth_order: Sequence[str],
    spec: AnalysisSpec,
    optimizer_options: dict[str, object] | None = None,
) -> dict[str, dict[str, PlackettLuceFit | None]]:
    """Fit PL once per backend at each confirmatory rank depth."""

    fits_by_depth: dict[str, dict[str, PlackettLuceFit | None]] = {}
    for depth_key in depth_order:
        depth_mart = filter_panel_by_max_rank(
            analysis_mart,
            max_rank=spec.rank_depth_limit(depth_key),
        )
        fits_by_depth[depth_key] = fit_plackett_luce_backends(
            depth_mart,
            backend_order,
            max_rank=spec.rank_depth_limit(depth_key),
            optimizer_options=optimizer_options,
        )
    return fits_by_depth


def summarize_plackett_luce_rank_depths(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    depth_order: Sequence[str],
    spec: AnalysisSpec,
    fits_by_depth: dict[str, dict[str, PlackettLuceFit | None]] | None = None,
) -> dict[str, object]:
    """Summarize PL for every confirmatory rank depth."""

    logger.info("summarizing plackett-luce rank_depths=%s", list(depth_order))
    if fits_by_depth is None:
        fits_by_depth = fit_plackett_luce_rank_depths(
            analysis_mart,
            backend_order,
            depth_order=depth_order,
            spec=spec,
        )
    depths: dict[str, object] = {}
    for depth_key in depth_order:
        depth_mart = filter_panel_by_max_rank(
            analysis_mart,
            max_rank=spec.rank_depth_limit(depth_key),
        )
        depths[depth_key] = summarize_plackett_luce_backends_from_fits(
            depth_mart,
            backend_order,
            fits=fits_by_depth[depth_key],
        )
    return {
        "depth_order": list(depth_order),
        "depths": depths,
    }


def summarize_backend_plackett_luce(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
) -> dict[str, object]:
    """Summarize the PL path for one backend."""

    fit = fit_backend_plackett_luce(analysis_mart, backend=backend)
    return _summarize_backend_plackett_luce_result(
        analysis_mart,
        backend=backend,
        fit=fit,
        include_diagnostics=True,
    )


def summarize_plackett_luce_diagnostics_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, object]:
    """Summarize diagnostics for the PL path for every backend."""

    fits = fit_plackett_luce_backends(analysis_mart, backend_order)
    return summarize_plackett_luce_diagnostics_backends_from_fits(
        analysis_mart,
        backend_order,
        fits=fits,
    )


def summarize_plackett_luce_backends_from_fits(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    fits: dict[str, PlackettLuceFit | None],
) -> dict[str, object]:
    """Summarize PL results from precomputed fits."""

    return {
        "backend_order": list(backend_order),
        "backends": {
            backend: _summarize_backend_plackett_luce_result(
                analysis_mart,
                backend=backend,
                fit=fits.get(backend),
                include_diagnostics=True,
            )
            for backend in backend_order
        },
    }


def summarize_backend_plackett_luce_diagnostics(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
) -> dict[str, object]:
    """Return diagnostics only for one backend."""

    fit = fit_backend_plackett_luce(analysis_mart, backend=backend)
    return _summarize_backend_plackett_luce_result(
        analysis_mart,
        backend=backend,
        fit=fit,
        include_diagnostics=False,
    )


def summarize_plackett_luce_diagnostics_backends_from_fits(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    fits: dict[str, PlackettLuceFit | None],
    include_iia_sensitivity: bool = False,
) -> dict[str, object]:
    """Summarize PL diagnostics from precomputed fits."""

    return {
        "backend_order": list(backend_order),
        "backends": {
            backend: _summarize_backend_plackett_luce_result(
                analysis_mart,
                backend=backend,
                fit=fits.get(backend),
                include_diagnostics=False,
                include_iia_sensitivity=include_iia_sensitivity,
            )
            for backend in backend_order
        },
    }


def _summarize_fit(fit: PlackettLuceFit) -> dict[str, object]:
    similarity_parameter_index = 0
    similarity_raw_coefficient = float(fit.params[similarity_parameter_index])
    similarity_raw_standard_error = float(
        np.sqrt(max(fit.covariance[similarity_parameter_index, similarity_parameter_index], 0.0))
    )
    similarity_confidence_interval = _confidence_interval(
        similarity_raw_coefficient,
        similarity_raw_standard_error,
        df=max(len(fit.choice_set_sizes) - 1, 1),
    )
    similarity_sd = float(fit.similarity_within_keyword_sd)
    log_odds_per_1sd = similarity_raw_coefficient * similarity_sd
    log_odds_standard_error = similarity_raw_standard_error * similarity_sd
    log_odds_confidence_interval = [float(bound * similarity_sd) for bound in similarity_confidence_interval]

    convergence_confirmed = _convergence_confirmed(fit)
    choice_set_size_summary = _choice_set_size_summary(fit.choice_set_sizes)
    main_model: dict[str, object] = {
        "formula": _fitted_formula(fit.fitted_control_columns),
        "omitted_controls": [dict(control) for control in fit.omitted_controls],
        "log_likelihood": float(fit.log_likelihood),
        "similarity_within_keyword_sd": similarity_sd,
        "convergence_confirmed": convergence_confirmed,
    }
    for parameter_index, column in enumerate(fit.fitted_control_columns, start=1):
        values = fit.model_data[column].astype(float)
        transformed = (
            np.log(values + 1.0)
            if column in PL_LOG_CONTROL_COLUMNS
            else values
        )
        spread = float(transformed.std(ddof=1))
        raw_coefficient = float(fit.params[parameter_index])
        raw_standard_error = float(
            np.sqrt(max(fit.covariance[parameter_index, parameter_index], 0.0))
        )
        confidence_interval = _confidence_interval(
            raw_coefficient,
            raw_standard_error,
            df=max(len(fit.choice_set_sizes) - 1, 1),
        )
        spread_key = f"log_{column}_sd" if column in PL_LOG_CONTROL_COLUMNS else f"{column}_sd"
        main_model[spread_key] = spread
        main_model[f"{column}_log_odds_per_1sd"] = raw_coefficient * spread
        main_model[f"{column}_log_odds_per_1sd_confidence_interval"] = [
            float(bound * spread) for bound in confidence_interval
        ]
    main_model.update(
        {
            "log_odds_per_1sd": log_odds_per_1sd,
            "log_odds_per_1sd_confidence_interval": log_odds_confidence_interval,
            "log_odds_per_1sd_standard_error": log_odds_standard_error,
            "odds_ratio_per_1sd": _safe_exp(log_odds_per_1sd),
            "odds_ratio_per_1sd_confidence_interval": [
                _safe_exp(log_odds_confidence_interval[0]),
                _safe_exp(log_odds_confidence_interval[1]),
            ],
            "p_value": _two_sided_p_value(
                similarity_raw_coefficient,
                similarity_raw_standard_error,
                df=max(len(fit.choice_set_sizes) - 1, 1),
            ),
        }
    )
    if not convergence_confirmed:
        main_model["status"] = "unstable"
        main_model["skipped_reason"] = "optimizer_or_hessian_unstable"

    return {
        "backend": fit.backend,
        "score_column": fit.score_column,
        "status": "computed",
        "row_count": int(len(fit.model_data)),
        "keyword_count": int(fit.model_data["target_keyword_id"].nunique()),
        "choice_set_size_summary": choice_set_size_summary,
        "convergence_confirmed": convergence_confirmed,
        "main_model": main_model,
    }


def _summarize_backend_plackett_luce_result(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
    fit: PlackettLuceFit | None,
    include_diagnostics: bool,
    include_iia_sensitivity: bool = False,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
    score_column: str | None = None,
) -> dict[str, object]:
    if fit is None:
        if score_column is None:
            score_column = _score_column_for_backend(backend)
        model_frame = _prepare_plackett_luce_frame(analysis_mart, max_rank=max_rank)
        score_rows = model_frame.filter(pl.col(score_column).is_not_null())
        keyword_frames, _ = _build_keyword_frames(score_rows.to_pandas(), score_column)
        eligible_keyword_frames = [frame for frame in keyword_frames if len(frame) >= 2]
        prepared_rows = int(sum(len(frame) for frame in eligible_keyword_frames))
        keyword_count = len(eligible_keyword_frames)
        if score_rows.is_empty():
            skipped_reason = "no_usable_rows"
        elif not eligible_keyword_frames:
            skipped_reason = "insufficient_choice_set"
        elif _pl_signal_variance(score_rows.to_pandas(), score_column) == 0.0:
            skipped_reason = "insufficient_signal_variance"
        else:
            skipped_reason = "insufficient_design"
        logger.info(
            "plackett-luce backend=%s status=skipped skipped_reason=%s "
            "row_count=%d keyword_count=%d",
            backend,
            skipped_reason,
            prepared_rows,
            keyword_count,
        )
        skipped = {
            "backend": backend,
            "score_column": score_column,
            "status": "skipped",
            "skipped_reason": skipped_reason,
            "row_count": prepared_rows,
            "keyword_count": keyword_count,
        }
        if include_diagnostics:
            skipped["choice_set_size_summary"] = _choice_set_size_summary([])
        return skipped

    convergence_confirmed = _convergence_confirmed(fit)
    if include_diagnostics:
        summary = _summarize_fit(fit)
        summary["status"] = "computed" if convergence_confirmed else "unstable"
        logger.info(
            "plackett-luce backend=%s status=%s row_count=%d keyword_count=%d",
            backend,
            summary["status"],
            summary["row_count"],
            summary["keyword_count"],
        )
        return summary

    diagnostics = _summarize_fit_diagnostics(
        fit,
        include_iia_sensitivity=include_iia_sensitivity,
    )
    diagnostics["status"] = "computed" if convergence_confirmed else "unstable"
    logger.info(
        "plackett-luce backend=%s status=%s row_count=%d keyword_count=%d converged=%s",
        backend,
        diagnostics["status"],
        diagnostics["row_count"],
        diagnostics["keyword_count"],
        diagnostics["optimizer"]["converged"],
    )
    return diagnostics


def _summarize_fit_diagnostics(
    fit: PlackettLuceFit,
    *,
    include_iia_sensitivity: bool,
) -> dict[str, object]:
    information_condition_number = _condition_number(fit.information)
    convergence_confirmed = _convergence_confirmed(fit, information_condition_number)
    fit_diagnostics = {
        "backend": fit.backend,
        "score_column": fit.score_column,
        "status": "computed",
        "row_count": int(len(fit.model_data)),
        "keyword_count": int(fit.model_data["target_keyword_id"].nunique()),
        "choice_set_size_summary": _choice_set_size_summary(fit.choice_set_sizes),
        "optimizer": {
            "converged": fit.optimizer.converged,
            "message": fit.optimizer.message,
            "iterations": fit.optimizer.iterations,
            "gradient_norm": fit.optimizer.gradient_norm,
            "objective_value": fit.optimizer.objective_value,
        },
        "duplicate_serp_rank_keyword_count": fit.duplicate_serp_rank_keyword_count,
        "hessian_condition_number": information_condition_number,
        "convergence_confirmed": convergence_confirmed,
    }
    if include_iia_sensitivity:
        fit_diagnostics["iia_sensitivity"] = _iia_sensitivity(fit)
    return fit_diagnostics


def _iia_sensitivity(fit: PlackettLuceFit) -> dict[str, object]:
    leave_one_out_fit = _fit_subset(
        fit,
        lambda frame: frame[frame["serp_rank"] > 1],
    )
    main_log_odds_per_1sd = float(fit.params[0]) * float(fit.similarity_within_keyword_sd)
    return {
        "leave_one_out_top_rank": _subset_refit_summary(
            leave_one_out_fit,
            main_log_odds_per_1sd,
            reference_similarity_sd=float(fit.similarity_within_keyword_sd),
        ),
    }


def _subset_refit_summary(
    fit: PlackettLuceFit | None,
    main_log_odds_per_1sd: float,
    *,
    reference_similarity_sd: float,
) -> dict[str, object]:
    if fit is None:
        return {
            "status": "skipped",
            "reason": "insufficient_choice_set",
        }

    log_odds_per_1sd = float(fit.params[0]) * reference_similarity_sd
    convergence_confirmed = _convergence_confirmed(fit)
    hessian_condition_number = _condition_number(fit.information)
    return {
        "status": "computed" if convergence_confirmed else "unstable",
        "row_count": int(len(fit.model_data)),
        "keyword_count": int(fit.model_data["target_keyword_id"].nunique()),
        "log_odds_per_1sd": log_odds_per_1sd,
        "odds_ratio_per_1sd": _safe_exp(log_odds_per_1sd),
        "convergence_confirmed": convergence_confirmed,
        "hessian_condition_number": hessian_condition_number,
        "log_odds_per_1sd_drift": float(log_odds_per_1sd - main_log_odds_per_1sd),
        "relative_drift": float((log_odds_per_1sd - main_log_odds_per_1sd) / main_log_odds_per_1sd)
        if main_log_odds_per_1sd != 0
        else None,
    }


def _fit_subset(
    fit: PlackettLuceFit,
    row_selector,
) -> PlackettLuceFit | None:
    subset = row_selector(fit.model_data)
    if subset.empty:
        return None
    max_rank = int(subset["serp_rank"].max())
    return fit_backend_plackett_luce(
        pl.DataFrame(subset),
        backend=fit.backend,
        max_rank=max_rank,
    )


def _prepare_plackett_luce_frame(
    analysis_mart: pl.DataFrame,
    *,
    max_rank: int = DEFAULT_MAX_SERP_RANK,
) -> pl.DataFrame:
    return analysis_mart.filter(
        pl.col("serp_rank").is_between(
            1,
            max_rank,
            closed="both",
        )
    ).drop_nulls(list(PLACKET_LUCE_REQUIRED_COLUMNS))


def _summarize_plackett_luce_for_prepared_model_data(
    raw_model_data: pd.DataFrame,
    *,
    sorted_model_data: pd.DataFrame,
    label: str,
    score_column: str,
    include_diagnostics: bool = True,
    include_iia_sensitivity: bool = False,
    optimizer_options: dict[str, object] | None = None,
) -> dict[str, object]:
    model_data = sorted_model_data
    if score_column not in model_data.columns:
        return {
            "backend": label,
            "score_column": score_column,
            "status": "skipped",
            "skipped_reason": "missing_signal_column",
            "row_count": int(len(raw_model_data)),
            "keyword_count": int(raw_model_data["target_keyword_id"].nunique()),
        }

    usable = model_data[[score_column, "target_keyword_id"]].dropna(subset=[score_column])
    if usable.empty:
        return {
            "backend": label,
            "score_column": score_column,
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
            "row_count": 0,
            "keyword_count": 0,
        }
    if _pl_signal_variance(model_data, score_column) == 0.0:
        return {
            "backend": label,
            "score_column": score_column,
            "status": "skipped",
            "skipped_reason": "insufficient_signal_variance",
            "row_count": int(len(usable)),
            "keyword_count": int(usable["target_keyword_id"].nunique()),
        }

    fit = fit_plackett_luce_for_prepared_model_data(
        raw_model_data,
        label=label,
        score_column=score_column,
        sorted_model_data=sorted_model_data,
        optimizer_options=optimizer_options,
    )
    return _summarize_backend_plackett_luce_result(
        pl.DataFrame(raw_model_data),
        backend=label,
        fit=fit,
        include_diagnostics=include_diagnostics,
        include_iia_sensitivity=include_iia_sensitivity,
        max_rank=int(raw_model_data["serp_rank"].max()) if not raw_model_data.empty else DEFAULT_MAX_SERP_RANK,
        score_column=score_column,
    )


def _coerce_pl_predictor(model_data: pd.DataFrame, score_column: str) -> None:
    if pd.api.types.is_bool_dtype(model_data[score_column]):
        model_data[score_column] = model_data[score_column].astype(float)


def _pl_signal_variance(model_data: pd.DataFrame, score_column: str) -> float:
    variance_frame = model_data[[score_column, "target_keyword_id"]].copy()
    _coerce_pl_predictor(variance_frame, score_column)
    usable = variance_frame.dropna(subset=[score_column])
    if usable.empty:
        return 0.0
    return float(within_keyword_sd_rms(usable, score_column))


def _build_keyword_frames(
    model_data: pd.DataFrame,
    score_column: str,
    *,
    sorted_model_data: pd.DataFrame | None = None,
) -> tuple[list[pd.DataFrame], int]:
    keyword_frames: list[pd.DataFrame] = []
    duplicate_serp_rank_keyword_count = 0
    if sorted_model_data is None:
        sorted_model_data = model_data.sort_values(
            by=["keyword_order", "target_keyword_id", "serp_rank", "serp_item_id"],
            kind="mergesort",
        )
    for keyword_id, keyword_frame in sorted_model_data.groupby("target_keyword_id", sort=False):
        sorted_frame = keyword_frame.sort_values(
            by=["serp_rank", "serp_item_id"],
            kind="mergesort",
        ).reset_index(drop=True)
        sorted_frame = sorted_frame[sorted_frame[score_column].notna()].reset_index(drop=True)
        if sorted_frame.empty:
            continue
        if sorted_frame["serp_rank"].duplicated().any():
            duplicate_serp_rank_keyword_count += 1
            continue
        keyword_frames.append(sorted_frame)
    return keyword_frames, duplicate_serp_rank_keyword_count


def _select_pl_controls(
    model_data: pd.DataFrame,
) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    fitted_controls: list[str] = []
    omitted_controls: list[dict[str, str]] = []
    for column in PL_CONTROL_COLUMNS:
        if column not in model_data.columns:
            omitted_controls.append({"column": column, "reason": "missing_column"})
            continue
        if model_data[column].isna().any():
            omitted_controls.append({"column": column, "reason": "missing_values"})
            continue
        values = model_data[column].to_numpy(dtype=float)
        log_values = np.log(values + 1.0) if column in PL_LOG_CONTROL_COLUMNS else values
        if np.ptp(log_values) == 0.0:
            omitted_controls.append({"column": column, "reason": "constant"})
        else:
            fitted_controls.append(column)
    return tuple(fitted_controls), tuple(omitted_controls)


def _build_keyword_groups(
    keyword_frames: Sequence[pd.DataFrame],
    score_column: str,
    control_columns: Sequence[str],
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for keyword_frame in keyword_frames:
        features = _feature_matrix(keyword_frame, score_column, control_columns)
        groups.append(
            {
                "target_keyword_id": str(keyword_frame["target_keyword_id"].iloc[0]),
                "frame": keyword_frame,
                "features": features,
                "choice_set_size": int(len(keyword_frame)),
            }
        )
    return groups


def _feature_matrix(
    frame: pd.DataFrame,
    score_column: str,
    control_columns: Sequence[str],
) -> np.ndarray:
    similarity_series = frame[score_column]
    if pd.api.types.is_bool_dtype(similarity_series):
        similarity = similarity_series.to_numpy(dtype=float)
    else:
        similarity = similarity_series.to_numpy(dtype=float)
    columns = [similarity]
    columns.extend(
        (
            np.log(frame[column].to_numpy(dtype=float) + 1.0)
            if column in PL_LOG_CONTROL_COLUMNS
            else frame[column].to_numpy(dtype=float)
        )
        for column in control_columns
    )
    return np.column_stack(columns)


def _fitted_formula(control_columns: Sequence[str]) -> str:
    terms = [
        "similarity",
        *(
            f"log({column} + 1)" if column in PL_LOG_CONTROL_COLUMNS else column
            for column in control_columns
        ),
    ]
    return "rank_ordered_logit ~ " + " + ".join(terms)


def _score_column_for_backend(backend: str) -> str:
    try:
        return SIMILARITY_SCORE_COLUMNS[backend]
    except KeyError as exc:
        raise ValueError(f"unsupported backend {backend}") from exc


def _maximize_log_likelihood(
    groups: list[dict[str, object]],
    *,
    optimizer_options: dict[str, object] | None,
) -> tuple[np.ndarray, PlackettLuceOptimizerResult]:
    x0 = np.zeros(groups[0]["features"].shape[1], dtype=float)
    options: dict[str, object] = {"maxiter": 1000, "xtol": 1e-12}
    if optimizer_options:
        options.update(optimizer_options)
    options.pop("gtol", None)

    def objective(params: np.ndarray) -> float:
        log_likelihood, _, _ = _loglik_gradient_hessian(params, groups)
        return -log_likelihood

    def gradient(params: np.ndarray) -> np.ndarray:
        _, grad, _ = _loglik_gradient_hessian(params, groups)
        return -grad

    def hessian(params: np.ndarray) -> np.ndarray:
        _, _, hess = _loglik_gradient_hessian(params, groups)
        return -hess

    result = optimize.minimize(
        objective,
        x0,
        method="Newton-CG",
        jac=gradient,
        hess=hessian,
        options=options,
    )
    final_params = np.asarray(result.x, dtype=float)
    if result.jac is not None and np.all(np.isfinite(result.jac)):
        gradient_norm = float(np.linalg.norm(np.asarray(result.jac, dtype=float)))
    else:
        _, grad, _ = _loglik_gradient_hessian(final_params, groups)
        gradient_norm = float(np.linalg.norm(-grad))
    # Newton-CG can report precision loss even when the gradient is already
    # at numerical noise. Treat those solves as converged so downstream
    # reporting does not surface a false warning.
    converged = bool(result.success or gradient_norm <= OPTIMIZER_GRADIENT_TOLERANCE)
    optimizer_result = PlackettLuceOptimizerResult(
        converged=converged,
        message=str(result.message),
        iterations=int(getattr(result, "nit", 0) or 0),
        gradient_norm=gradient_norm,
        objective_value=float(result.fun),
    )
    return final_params, optimizer_result


def _loglik_gradient_hessian(
    params: np.ndarray,
    groups: list[dict[str, object]],
) -> tuple[float, np.ndarray, np.ndarray]:
    log_likelihood = 0.0
    gradient = np.zeros_like(params, dtype=float)
    hessian = np.zeros((params.size, params.size), dtype=float)

    for group in groups:
        features = group["features"]
        group_loglik, group_gradient, group_hessian = _group_stats(features, params)
        log_likelihood += group_loglik
        gradient += group_gradient
        hessian += group_hessian
    return log_likelihood, gradient, hessian


def _group_stats(
    features: np.ndarray,
    params: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    choice_count, parameter_count = features.shape
    log_likelihood = 0.0
    gradient = np.zeros(parameter_count, dtype=float)
    hessian = np.zeros((parameter_count, parameter_count), dtype=float)

    utilities = features @ params
    for rank_index in range(choice_count):
        remaining_features = features[rank_index:]
        remaining_utilities = utilities[rank_index:]
        log_denominator = float(logsumexp(remaining_utilities))
        weights = np.exp(remaining_utilities - log_denominator)
        expected_feature = weights @ remaining_features
        expected_outer = np.einsum("i,ij,ik->jk", weights, remaining_features, remaining_features)
        current_feature = features[rank_index]

        log_likelihood += float(utilities[rank_index] - log_denominator)
        gradient += current_feature - expected_feature
        hessian -= expected_outer - np.outer(expected_feature, expected_feature)

    return log_likelihood, gradient, hessian


def _group_score_contribution(
    features: np.ndarray,
    params: np.ndarray,
) -> np.ndarray:
    contribution = np.zeros(features.shape[1], dtype=float)
    utilities = features @ params
    for rank_index in range(features.shape[0]):
        remaining_features = features[rank_index:]
        remaining_utilities = utilities[rank_index:]
        log_denominator = float(logsumexp(remaining_utilities))
        weights = np.exp(remaining_utilities - log_denominator)
        expected_feature = weights @ remaining_features
        contribution += features[rank_index] - expected_feature
    return contribution


def _choice_set_size_summary(choice_set_sizes: Sequence[dict[str, object]]) -> dict[str, object]:
    if not choice_set_sizes:
        return {"min": 0, "median": 0.0, "max": 0, "per_keyword": []}
    sizes = [int(item["choice_set_size"]) for item in choice_set_sizes]
    return {
        "min": int(min(sizes)),
        "median": float(np.median(sizes)),
        "max": int(max(sizes)),
        "per_keyword": [
            {
                "target_keyword_id": str(item["target_keyword_id"]),
                "choice_set_size": int(item["choice_set_size"]),
            }
            for item in choice_set_sizes
        ],
    }


def _confidence_interval(coefficient: float, standard_error: float, *, df: int) -> list[float]:
    if standard_error <= 0 or not isfinite(standard_error):
        return [coefficient, coefficient]
    critical_value = float(stats.t.ppf(0.975, df))
    return [
        float(coefficient - (critical_value * standard_error)),
        float(coefficient + (critical_value * standard_error)),
    ]


def _two_sided_p_value(coefficient: float, standard_error: float, *, df: int) -> float:
    if standard_error <= 0 or not isfinite(standard_error):
        return 1.0
    t_statistic = coefficient / standard_error
    return float(2.0 * (1.0 - stats.t.cdf(abs(t_statistic), df)))


def _convergence_confirmed(
    fit: PlackettLuceFit,
    hessian_condition_number: float | None = None,
) -> bool:
    condition_number = (
        hessian_condition_number
        if hessian_condition_number is not None
        else _condition_number(fit.information)
    )
    return bool(
        fit.optimizer.converged
        and isfinite(condition_number)
        and condition_number <= HESSIAN_CONDITION_NUMBER_THRESHOLD
    )


def _condition_number(matrix: np.ndarray) -> float:
    if matrix.size == 0:
        return 0.0
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    if np.any(singular_values <= 0):
        return float("inf")
    return float(singular_values.max() / singular_values.min())


def _symmetrize(matrix: np.ndarray) -> np.ndarray:
    return (matrix + matrix.T) / 2.0


def _safe_exp(value: float) -> float:
    return float(np.exp(np.clip(value, -700.0, 700.0)))
