"""Phase 5 diagnostics helpers."""

from __future__ import annotations

import logging
import math
import warnings
from collections.abc import Sequence

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.diagnostic import het_breuschpagan, linear_reset

from seo_rank.stats.regression import (
    BackendRegressionFit,
    _regression_skip_reason,
    _fit_backend_regression_from_model_data,
    _parameter_confidence_interval,
    _parameter_value,
    fit_regression_for_score_column,
    fit_regression_backends,
    fit_backend_regression,
)
from seo_rank.stats.families import SignalFamily, SignalFamilyRegistry, source_mart_for_family


logger = logging.getLogger(__name__)

SMALL_SAMPLE_SHAPIRO_CUTOFF = 50
RESET_P_VALUE_THRESHOLD = 0.05
RESET_POWER = 2
MIN_DF_RESID_FOR_RESET = RESET_POWER
BREUSCH_PAGAN_P_VALUE_THRESHOLD = 0.05
STUDENTIZED_RESIDUAL_THRESHOLD = 3.0
MULTIVARIATE_LENGTH_TERM = "np.log(page_text_length + 1)"
MULTIVARIATE_SCORE_COLUMNS = (
    "bge_normalized_score",
    "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity_normalized_score",
)
MULTIVARIATE_SCORE_COLUMNS_TO_BACKEND = {
    "bge_normalized_score": "bge",
    "gemini_doc_retrieval_normalized_score": "gemini_doc_retrieval",
    "gemini_semantic_similarity_normalized_score": "gemini_semantic_similarity",
}
SIMILARITY_SCORE_COLUMNS = {
    backend: score_column
    for score_column, backend in MULTIVARIATE_SCORE_COLUMNS_TO_BACKEND.items()
}


def summarize_diagnostics_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, object]:
    """Summarize pooled OLS diagnostics for every configured backend."""

    logger.info("summarizing diagnostics backends=%s", list(backend_order))
    fits = fit_regression_backends(analysis_mart, backend_order)
    return summarize_diagnostics_backends_from_fits(
        analysis_mart,
        backend_order,
        fits=fits,
    )


def summarize_diagnostics_families(
    source_frames: dict[str, pl.DataFrame],
    *,
    registry: SignalFamilyRegistry,
) -> dict[str, object]:
    """Summarize pooled OLS diagnostics for every family in the registry."""

    return {
        "families": {
            family.key: summarize_diagnostics_family(
                source_frames,
                family=family,
            )
            for family in registry.families
        }
    }


def summarize_diagnostics_backends_from_fits(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    fits: dict[str, BackendRegressionFit | None],
) -> dict[str, object]:
    """Summarize pooled OLS diagnostics from precomputed backend fits."""

    return {
        "backend_order": list(backend_order),
        "backends": {
            backend: _summarize_backend_diagnostics_result(
                analysis_mart,
                backend=backend,
                fit=fits.get(backend),
            )
            for backend in backend_order
        },
    }


def summarize_backend_diagnostics(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
) -> dict[str, object]:
    """Summarize pooled diagnostics for one backend."""

    fit = fit_backend_regression(analysis_mart, backend=backend)
    return _summarize_backend_diagnostics_result(
        analysis_mart,
        backend=backend,
        fit=fit,
    )


def summarize_diagnostics_for_score_column(
    analysis_mart: pl.DataFrame,
    *,
    label: str,
    score_column: str,
) -> dict[str, object]:
    """Fit and summarize pooled diagnostics for an arbitrary signal column."""

    fit = fit_regression_for_score_column(
        analysis_mart,
        label=label,
        score_column=score_column,
    )
    return _summarize_backend_diagnostics_result(
        analysis_mart,
        backend=label,
        fit=fit,
        score_column=score_column,
    )


def summarize_multivariate_sensitivity(
    analysis_mart: pl.DataFrame,
    *,
    vif_threshold: float,
    backend_drop_order: Sequence[str],
) -> dict[str, object]:
    """Fit the joint multivariate sensitivity model and apply the configured drop order."""

    logger.info(
        "summarizing multivariate sensitivity vif_threshold=%s backend_drop_order=%s",
        vif_threshold,
        list(backend_drop_order),
    )
    active_backends = _multivariate_active_backends(backend_drop_order)
    if not active_backends:
        return _skipped_multivariate_sensitivity_summary(
            skipped_reason="no_supported_backends",
            vif_threshold=vif_threshold,
            backend_drop_order=backend_drop_order,
        )

    model_data, skipped_reason = _prepare_multivariate_sensitivity_data(
        analysis_mart,
        active_backends=active_backends,
    )
    if model_data is None:
        return _skipped_multivariate_sensitivity_summary(
            skipped_reason=skipped_reason,
            vif_threshold=vif_threshold,
            backend_drop_order=backend_drop_order,
        )

    protected_backend = str(backend_drop_order[-1]) if backend_drop_order else active_backends[-1]
    drop_log: list[dict[str, object]] = []
    dropped_backends: list[str] = []
    current_backends = active_backends

    while True:
        fit = _fit_multivariate_sensitivity_model(model_data, current_backends)
        fit_summary = _summarize_multivariate_sensitivity_fit(fit, model_data, current_backends)
        max_vif = float(fit_summary["max_vif"])
        if max_vif <= float(vif_threshold):
            return {
                **fit_summary,
                "status": "computed",
                "vif_threshold": float(vif_threshold),
                "backend_drop_order": list(backend_drop_order),
                "drop_path": list(dropped_backends),
                "drop_log": drop_log,
                "dropped_backends": list(dropped_backends),
            }

        next_drop_backend = _next_multivariate_drop_backend(
            current_backends,
            backend_drop_order,
            protected_backend=protected_backend,
        )
        if next_drop_backend is None:
            final_log = {
                "status": "unresolved",
                "kept_backends": list(current_backends),
                "max_vif": fit_summary["max_vif"],
                "max_vif_term": fit_summary["max_vif_term"],
                "vif_threshold": float(vif_threshold),
                "unresolved_reason": "threshold_exceeded_with_protected_backend_only",
            }
            drop_log.append(final_log)
            return {
                **fit_summary,
                "status": "unresolved",
                "unresolved_reason": "threshold_exceeded_with_protected_backend_only",
                "vif_threshold": float(vif_threshold),
                "backend_drop_order": list(backend_drop_order),
                "drop_path": list(dropped_backends),
                "drop_log": drop_log,
                "dropped_backends": list(dropped_backends),
            }

        drop_log.append(
            {
                "status": "dropped",
                "kept_backends": list(current_backends),
                "dropped_backend": next_drop_backend,
                "max_vif": fit_summary["max_vif"],
                "max_vif_term": fit_summary["max_vif_term"],
                "vif_threshold": float(vif_threshold),
            }
        )
        dropped_backends.append(next_drop_backend)
        current_backends = tuple(
            backend for backend in current_backends if backend != next_drop_backend
        )


def _prepare_multivariate_sensitivity_data(
    analysis_mart: pl.DataFrame,
    *,
    active_backends: Sequence[str],
) -> tuple[pd.DataFrame | None, str]:
    required_columns = [
        "target_keyword_id",
        "serp_rank",
        "page_text_length",
        *[SIMILARITY_SCORE_COLUMNS[backend] for backend in active_backends],
    ]
    missing_columns = [column for column in required_columns if column not in analysis_mart.columns]
    if missing_columns:
        return None, "missing_required_columns"

    model_frame = analysis_mart.drop_nulls(required_columns)
    if model_frame.is_empty():
        return None, "no_usable_rows"
    if model_frame.height < 3:
        return None, "insufficient_rows"

    model_data = model_frame.select(required_columns).to_pandas().copy()
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))
    return model_data, ""


def _fit_multivariate_sensitivity_model(
    model_data: pd.DataFrame,
    active_backends: Sequence[str],
):
    formula = _multivariate_formula(active_backends)
    return smf.ols(formula, data=model_data).fit()


def _summarize_multivariate_sensitivity_fit(
    fit,
    model_data: pd.DataFrame,
    active_backends: Sequence[str],
) -> dict[str, object]:
    parameter_table = _multivariate_parameter_table(fit)
    vif_table = _multivariate_vif_table(fit, active_backends)
    max_vif_entry = max(vif_table, key=lambda row: row["vif"])
    max_vif = float(max_vif_entry["vif"])
    return {
        "row_count": int(fit.nobs),
        "keyword_count": int(model_data["target_keyword_id"].nunique()),
        "model_formula": fit.model.formula,
        "kept_backends": list(active_backends),
        "parameter_table": parameter_table,
        "vif_table": vif_table,
        "max_vif": max_vif,
        "max_vif_term": max_vif_entry["term"],
    }


def _multivariate_parameter_table(fit) -> list[dict[str, object]]:
    conf_int = np.asarray(fit.conf_int())
    parameters: list[dict[str, object]] = []
    exog_names = list(fit.model.exog_names)
    for index, term in enumerate(exog_names):
        parameters.append(
            {
                "term": term,
                "estimate": _json_value(np.asarray(fit.params)[index]),
                "standard_error": _json_value(np.asarray(fit.bse)[index]),
                "t_value": _json_value(np.asarray(fit.tvalues)[index]),
                "p_value": _json_value(np.asarray(fit.pvalues)[index]),
                "confidence_interval": [
                    _json_value(conf_int[index, 0]),
                    _json_value(conf_int[index, 1]),
                ],
                "term_kind": _multivariate_term_kind(term),
            }
        )
    return parameters


def _multivariate_vif_table(
    fit,
    active_backends: Sequence[str],
) -> list[dict[str, object]]:
    exog_names = list(fit.model.exog_names)
    exog = np.asarray(fit.model.exog, dtype=float)
    selected_terms = [
        *[SIMILARITY_SCORE_COLUMNS[backend] for backend in active_backends],
        MULTIVARIATE_LENGTH_TERM,
    ]
    selected_indices = [
        exog_names.index(term)
        for term in selected_terms
        if term in exog_names
    ]
    selected_exog = exog[:, selected_indices]
    vif_rows: list[dict[str, object]] = []
    for vif_index, term in enumerate(term for term in selected_terms if term in exog_names):
        if term not in exog_names:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            vif = variance_inflation_factor(selected_exog, vif_index)
        vif_rows.append(
            {
                "term": term,
                "vif": float(vif),
                "term_kind": _multivariate_term_kind(term),
            }
        )
    return vif_rows


def _multivariate_formula(active_backends: Sequence[str]) -> str:
    score_terms = [SIMILARITY_SCORE_COLUMNS[backend] for backend in active_backends]
    return (
        "outcome ~ "
        + " + ".join([*score_terms, MULTIVARIATE_LENGTH_TERM, "C(target_keyword_id)"])
    )


def _multivariate_active_backends(backend_drop_order: Sequence[str]) -> tuple[str, ...]:
    configured = {str(backend) for backend in backend_drop_order}
    return tuple(
        backend for backend in SIMILARITY_SCORE_COLUMNS.keys() if backend in configured
    )


def _next_multivariate_drop_backend(
    active_backends: Sequence[str],
    backend_drop_order: Sequence[str],
    *,
    protected_backend: str,
) -> str | None:
    active = set(active_backends)
    for backend in backend_drop_order:
        backend = str(backend)
        if backend == protected_backend:
            continue
        if backend in active:
            return backend
    return None


def _multivariate_term_kind(term: str) -> str:
    if term == "Intercept":
        return "intercept"
    if term == MULTIVARIATE_LENGTH_TERM:
        return "page_text_length"
    if term in MULTIVARIATE_SCORE_COLUMNS_TO_BACKEND:
        return "similarity_backend"
    if term.startswith("C(target_keyword_id)"):
        return "keyword_fixed_effect"
    return "other"


def _skipped_multivariate_sensitivity_summary(
    *,
    skipped_reason: str,
    vif_threshold: float,
    backend_drop_order: Sequence[str],
) -> dict[str, object]:
    return {
        "status": "skipped",
        "skipped_reason": skipped_reason,
        "vif_threshold": float(vif_threshold),
        "backend_drop_order": list(backend_drop_order),
        "drop_path": [],
        "drop_log": [],
        "dropped_backends": [],
    }


def summarize_diagnostics_family(
    source_frames: dict[str, pl.DataFrame],
    *,
    family: SignalFamily,
) -> dict[str, object]:
    """Summarize pooled diagnostics for one signal family."""

    source_mart = source_mart_for_family(family)
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

    signal_summaries: dict[str, dict[str, object]] = {}
    for signal_column in family.signal_columns:
        signal_summaries[signal_column] = summarize_diagnostics_for_score_column(
            source_frame,
            label=family.key,
            score_column=signal_column,
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


def _summarize_backend_diagnostics_result(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
    fit: BackendRegressionFit | None,
    score_column: str | None = None,
) -> dict[str, object]:
    if fit is None:
        if score_column is None:
            score_column = _score_column_for_backend(backend)
        model_frame = analysis_mart.filter(pl.col(score_column).is_not_null()).drop_nulls(
            [score_column, "serp_rank", "page_text_length"]
        )
        skipped_reason = _regression_skip_reason(model_frame)
        row_count = model_frame.height
        keyword_count = (
            model_frame["target_keyword_id"].n_unique() if not model_frame.is_empty() else 0
        )
        logger.info(
            "diagnostics backend=%s status=skipped skipped_reason=%s row_count=%d keyword_count=%d",
            backend,
            skipped_reason,
            row_count,
            keyword_count,
        )
        return _skipped_backend_summary(
            backend=backend,
            score_column=score_column,
            skipped_reason=skipped_reason,
            row_count=row_count,
            keyword_count=keyword_count,
        )
    return summarize_backend_diagnostics_from_fit(fit)


def _refit_backend_regression_from_model_data(
    model_data: pd.DataFrame,
    *,
    backend: str,
    score_column: str,
) -> BackendRegressionFit | None:
    return _fit_backend_regression_from_model_data(
        model_data,
        label=backend,
        score_column=score_column,
    )


def summarize_backend_diagnostics_from_fit(
    fit: BackendRegressionFit,
) -> dict[str, object]:
    """Summarize pooled diagnostics from a prepared backend regression fit."""

    residuals = np.asarray(fit.feature_result.resid, dtype=float)
    fitted = np.asarray(fit.feature_result.fittedvalues, dtype=float)
    nobs = int(fit.feature_result.nobs)
    parameter_count = len(fit.feature_result.model.exog_names)
    influence = fit.feature_result.get_influence()

    cooks_d, leverage, studentized, dffits, dfbetas = _safe_influence_arrays(influence)
    leverage = np.clip(leverage, 0.0, 1.0)

    cooks_d_threshold = 4.0 / nobs
    leverage_threshold = (2.0 * parameter_count) / nobs
    dffits_threshold = 2.0 * math.sqrt(parameter_count / nobs)
    dfbeta_threshold = 2.0 / math.sqrt(nobs)

    row_flags = (
        (cooks_d > cooks_d_threshold)
        | (leverage > leverage_threshold)
        | (np.abs(studentized) > STUDENTIZED_RESIDUAL_THRESHOLD)
        | (np.abs(dffits) > dffits_threshold)
        | (np.abs(dfbetas).max(axis=1) > dfbeta_threshold)
    )
    influential_rows = [
        _row_influence_summary(
            fit=fit,
            row_index=row_index,
            cooks_d=float(cooks_d[row_index]),
            leverage=float(leverage[row_index]),
            studentized_residual=float(studentized[row_index]),
            dffits=float(dffits[row_index]),
            dfbetas=dfbetas[row_index],
            cooks_d_threshold=cooks_d_threshold,
            leverage_threshold=leverage_threshold,
            dffits_threshold=dffits_threshold,
            dfbeta_threshold=dfbeta_threshold,
        )
        for row_index in np.flatnonzero(row_flags)
    ]

    reset_summary = _reset_summary(fit.feature_result)
    breusch_pagan = het_breuschpagan(
        residuals,
        fit.feature_result.model.exog,
        robust=True,
    )
    shapiro = _shapiro_summary(residuals)
    influence_sensitivity = _summarize_influence_sensitivity(
        fit,
        cooks_d=cooks_d,
        cooks_d_threshold=cooks_d_threshold,
    )

    influential_count = len(influential_rows)
    logger.info(
        "diagnostics backend=%s status=computed row_count=%d keyword_count=%d influential_count=%d",
        fit.backend,
        nobs,
        int(fit.model_data["target_keyword_id"].nunique()),
        influential_count,
    )

    return {
        "backend": fit.backend,
        "score_column": fit.score_column,
        "status": "computed",
        "row_count": nobs,
        "keyword_count": int(fit.model_data["target_keyword_id"].nunique()),
        "model_formula": fit.feature_result.model.formula,
        "baseline_formula": fit.baseline_result.model.formula,
        "residuals_vs_fitted": _residuals_vs_fitted_summary(residuals, fitted),
        "reset": reset_summary,
        "breusch_pagan": _breusch_pagan_summary(
            breusch_pagan,
            flagged=_breusch_pagan_flagged(breusch_pagan),
        ),
        "influence": {
            "status": "computed",
            "row_count": nobs,
            "nobs": nobs,
            "parameter_count": parameter_count,
            "cook_d_threshold": cooks_d_threshold,
            "leverage_threshold": leverage_threshold,
            "studentized_residual_threshold": STUDENTIZED_RESIDUAL_THRESHOLD,
            "dffits_threshold": dffits_threshold,
            "dfbeta_threshold": dfbeta_threshold,
            "cook_d_count": int(np.sum(cooks_d > cooks_d_threshold)),
            "leverage_count": int(np.sum(leverage > leverage_threshold)),
            "studentized_residual_count": int(
                np.sum(np.abs(studentized) > STUDENTIZED_RESIDUAL_THRESHOLD)
            ),
            "dffits_count": int(np.sum(np.abs(dffits) > dffits_threshold)),
            "dfbeta_count": int(np.sum(np.abs(dfbetas).max(axis=1) > dfbeta_threshold)),
            "influential_count": int(len(influential_rows)),
            "influential_rate": float(len(influential_rows) / nobs),
            "rows": influential_rows,
        },
        "influence_sensitivity": influence_sensitivity,
    } | ({"shapiro": shapiro} if shapiro is not None else {})


def _reset_summary(feature_result) -> dict[str, object]:
    df_resid = float(feature_result.df_resid)
    nobs = float(feature_result.nobs)
    if df_resid < MIN_DF_RESID_FOR_RESET or (nobs > 50 and df_resid < 40):
        return {
            "status": "skipped",
            "skipped_reason": "insufficient_df_resid",
            "df_resid": df_resid,
            "min_df_resid": MIN_DF_RESID_FOR_RESET,
        }

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            reset_result = linear_reset(
                feature_result,
                power=RESET_POWER,
                use_f=True,
                cov_type="nonrobust",
            )
    except ValueError as error:
        return {
            "status": "skipped",
            "skipped_reason": "reset_test_failed",
            "df_resid": df_resid,
            "error": str(error),
        }

    return {
        "status": "computed",
        "statistic": _finite_float(reset_result.statistic),
        "p_value": _finite_float(reset_result.pvalue),
        "df_denom": _finite_float(getattr(reset_result, "df_denom", None)),
        "flagged": _finite_float(reset_result.pvalue) is not None
        and _finite_float(reset_result.pvalue) < RESET_P_VALUE_THRESHOLD,
    }


def _safe_influence_arrays(
    influence,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract influence arrays without surfacing statsmodels precision warnings."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        cooks_d = np.asarray(influence.cooks_distance[0], dtype=float)
        leverage = np.asarray(influence.hat_matrix_diag, dtype=float)
        studentized = np.asarray(influence.resid_studentized_external, dtype=float)
        dffits = np.asarray(influence.dffits[0], dtype=float)
        dfbetas = np.asarray(influence.dfbetas, dtype=float)
    return cooks_d, leverage, studentized, dffits, dfbetas


def _residuals_vs_fitted_summary(
    residuals: np.ndarray,
    fitted: np.ndarray,
) -> dict[str, object]:
    pearson = stats.pearsonr(fitted, residuals)
    spearman = stats.spearmanr(fitted, residuals)
    return {
        "status": "computed",
        "pearson_r": _finite_float(pearson.statistic),
        "pearson_p_value": _finite_float(pearson.pvalue),
        "spearman_r": _finite_float(spearman.statistic),
        "spearman_p_value": _finite_float(spearman.pvalue),
        "residual_mean": _finite_float(np.mean(residuals)),
        "residual_sd": _finite_float(np.std(residuals, ddof=1)),
        "fitted_mean": _finite_float(np.mean(fitted)),
        "fitted_sd": _finite_float(np.std(fitted, ddof=1)),
    }


def _breusch_pagan_summary(
    breusch_pagan: tuple[float, float, float, float],
    *,
    flagged: bool,
) -> dict[str, object]:
    lm_statistic, lm_p_value, f_statistic, f_p_value = breusch_pagan
    return {
        "status": "computed",
        "lm_statistic": _finite_float(lm_statistic),
        "lm_p_value": _finite_float(lm_p_value),
        "f_statistic": _finite_float(f_statistic),
        "f_p_value": _finite_float(f_p_value),
        "flagged": flagged,
        "recommended_se_type": "HC3" if flagged else "clustered",
    }


def _breusch_pagan_flagged(breusch_pagan: tuple[float, float, float, float]) -> bool:
    lm_statistic, lm_p_value, f_statistic, f_p_value = breusch_pagan
    del lm_statistic, f_statistic
    return any(
        p_value is not None and p_value < BREUSCH_PAGAN_P_VALUE_THRESHOLD
        for p_value in (_finite_float(lm_p_value), _finite_float(f_p_value))
    )


def _row_influence_summary(
    *,
    fit: BackendRegressionFit,
    row_index: int,
    cooks_d: float,
    leverage: float,
    studentized_residual: float,
    dffits: float,
    dfbetas: np.ndarray,
    cooks_d_threshold: float,
    leverage_threshold: float,
    dffits_threshold: float,
    dfbeta_threshold: float,
) -> dict[str, object]:
    row = fit.model_data.iloc[row_index]
    parameter_names = list(fit.feature_result.model.exog_names)
    dfbeta_series = [
        {
            "parameter": parameter_name,
            "value": _finite_float(dfbeta_value),
            "flagged": abs(float(dfbeta_value)) > dfbeta_threshold,
        }
        for parameter_name, dfbeta_value in zip(parameter_names, dfbetas, strict=True)
    ]
    return {
        "row_index": int(row_index),
        "target_keyword_id": _json_value(row.get("target_keyword_id")),
        "canonical_url_hash": _json_value(row.get("canonical_url_hash")),
        "cooks_d": cooks_d,
        "leverage": leverage,
        "studentized_residual": studentized_residual,
        "dffits": dffits,
        "max_abs_dfbeta": _finite_float(np.max(np.abs(dfbetas))),
        "dfbetas": dfbeta_series,
        "flags": {
            "cooks_d": cooks_d > cooks_d_threshold,
            "leverage": leverage > leverage_threshold,
            "studentized_residual": abs(studentized_residual) > STUDENTIZED_RESIDUAL_THRESHOLD,
            "dffits": abs(dffits) > dffits_threshold,
            "dfbeta": bool(np.max(np.abs(dfbetas)) > dfbeta_threshold),
        },
    }


def _summarize_influence_sensitivity(
    fit: BackendRegressionFit,
    *,
    cooks_d: np.ndarray,
    cooks_d_threshold: float,
) -> dict[str, object]:
    influential_row_indices = np.flatnonzero(cooks_d > cooks_d_threshold)
    influential_row_count = int(influential_row_indices.size)
    row_count = int(fit.feature_result.nobs)
    keyword_count = int(fit.model_data["target_keyword_id"].nunique())
    influential_row_rate = float(influential_row_count / row_count) if row_count else 0.0

    trimmed_model_data = fit.model_data.drop(index=influential_row_indices).reset_index(drop=True)
    trimmed_fit = _refit_backend_regression_from_model_data(
        trimmed_model_data,
        backend=fit.backend,
        score_column=fit.score_column,
    )
    if trimmed_fit is None:
        return {
            "status": "skipped",
            "skipped_reason": "trimmed_subset_unusable",
            "cook_d_threshold": cooks_d_threshold,
            "row_count": row_count,
            "trimmed_row_count": int(trimmed_model_data.shape[0]),
            "keyword_count": keyword_count,
            "trimmed_keyword_count": int(trimmed_model_data["target_keyword_id"].nunique())
            if not trimmed_model_data.empty
            else 0,
            "influential_row_count": influential_row_count,
            "influential_row_rate": influential_row_rate,
        }

    confirmatory_coefficient = _parameter_value(fit.clustered_result, fit.score_column)
    sensitivity_coefficient = _parameter_value(trimmed_fit.clustered_result, trimmed_fit.score_column)
    sensitivity_confidence_interval = _parameter_confidence_interval(
        trimmed_fit.clustered_result,
        trimmed_fit.score_column,
    )
    trimmed_row_count = int(trimmed_fit.feature_result.nobs)
    trimmed_keyword_count = int(trimmed_fit.model_data["target_keyword_id"].nunique())
    logger.info(
        "diagnostics backend=%s influence_sensitivity status=computed row_count=%d trimmed_row_count=%d influential_count=%d",
        fit.backend,
        row_count,
        trimmed_row_count,
        influential_row_count,
    )
    return {
        "status": "computed",
        "cook_d_threshold": cooks_d_threshold,
        "row_count": row_count,
        "trimmed_row_count": trimmed_row_count,
        "keyword_count": keyword_count,
        "trimmed_keyword_count": trimmed_keyword_count,
        "influential_row_count": influential_row_count,
        "influential_row_rate": influential_row_rate,
        "confirmatory_coefficient": confirmatory_coefficient,
        "sensitivity_coefficient": sensitivity_coefficient,
        "sensitivity_confidence_interval": sensitivity_confidence_interval,
        "coefficient_delta": float(sensitivity_coefficient - confirmatory_coefficient),
    }


def _shapiro_summary(residuals: np.ndarray) -> dict[str, object] | None:
    if residuals.size >= SMALL_SAMPLE_SHAPIRO_CUTOFF:
        return {
            "status": "skipped",
            "skipped_reason": "nobs_gte_50",
            "nobs_cutoff": SMALL_SAMPLE_SHAPIRO_CUTOFF,
        }
    statistic, p_value = stats.shapiro(residuals)
    return {
        "status": "informational",
        "statistic": _finite_float(statistic),
        "p_value": _finite_float(p_value),
        "nobs_cutoff": SMALL_SAMPLE_SHAPIRO_CUTOFF,
    }


def _skipped_backend_summary(
    *,
    backend: str,
    score_column: str,
    skipped_reason: str = "no_usable_rows",
    row_count: int = 0,
    keyword_count: int = 0,
) -> dict[str, object]:
    return {
        "backend": backend,
        "score_column": score_column,
        "status": "skipped",
        "skipped_reason": skipped_reason,
        "row_count": row_count,
        "keyword_count": keyword_count,
    }


def _score_column_for_backend(backend: str) -> str:
    from seo_rank.stats.regression import SIMILARITY_SCORE_COLUMNS

    try:
        return SIMILARITY_SCORE_COLUMNS[backend]
    except KeyError as exc:
        raise ValueError(f"unsupported backend {backend}") from exc


def _finite_float(value: object) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (np.floating, float, int, np.integer)):
        return _finite_float(value)
    return value.item() if hasattr(value, "item") else value
