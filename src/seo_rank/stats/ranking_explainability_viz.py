"""Visualizations for ranking explainability models."""
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

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from seo_rank.stats.regression import _parameter_confidence_interval, _parameter_value
from seo_rank.stats.textrazor_explainability import (
    CURATED_PREDICTOR_LABELS,
    CURATED_RANKING_SCORE_COLUMNS,
    fit_multivariate_ranking_model,
)

SIGNIFICANCE_ALPHA = 0.05
_INTERACTIVE_BACKENDS = (
    "TkAgg",
    "QtAgg",
    "Qt5Agg",
    "GTK4Agg",
    "GTK3Agg",
    "WXAgg",
)
_MACOS_BACKEND = "MacOSX"


@dataclass(frozen=True)
class ModelVisualizationResult:
    output_path: Path | None
    display_message: str | None = None


CuratedModelVisualizationResult = ModelVisualizationResult

ENTITY_RELEVANCE_SCORE_COLUMN = "textrazor_entity_relevance_score"
ENTITY_RELEVANCE_LABEL = CURATED_PREDICTOR_LABELS["textrazor_entity_relevance_score"]


def write_curated_model_visualization(
    panel: pl.DataFrame,
    multivariate_summary: dict[str, Any],
    *,
    output_path: Path | None = None,
    run_id: str,
    rank_depth: str,
    show: bool = False,
) -> ModelVisualizationResult | None:
    """Build the curated-model chart, optionally save it, and optionally display it."""

    plt, can_show_window = _import_pyplot(interactive=show)
    figure, plt, can_show_window = _build_figure_with_agg_fallback(
        plt,
        can_show_window,
        lambda active_plt: _build_curated_model_figure(
            panel,
            multivariate_summary,
            plt=active_plt,
            run_id=run_id,
            rank_depth=rank_depth,
        ),
        show=show,
    )
    return _publish_figure(
        plt,
        figure,
        output_path=output_path,
        show=show,
        can_show_window=can_show_window,
        chart_name="curated model chart",
    )


def write_entity_relevance_visualization(
    panel: pl.DataFrame,
    univariate_summary: dict[str, Any],
    *,
    output_path: Path | None = None,
    run_id: str,
    rank_depth: str,
    show: bool = False,
) -> ModelVisualizationResult | None:
    """Build the entity-relevance-only chart, optionally save it, and optionally display it."""

    plt, can_show_window = _import_pyplot(interactive=show)
    figure, plt, can_show_window = _build_figure_with_agg_fallback(
        plt,
        can_show_window,
        lambda active_plt: _build_entity_relevance_figure(
            panel,
            univariate_summary,
            plt=active_plt,
            run_id=run_id,
            rank_depth=rank_depth,
        ),
        show=show,
    )
    return _publish_figure(
        plt,
        figure,
        output_path=output_path,
        show=show,
        can_show_window=can_show_window,
        chart_name="entity relevance chart",
    )


def _build_figure_with_agg_fallback(
    plt,
    can_show_window: bool,
    build,
    *,
    show: bool,
):
    try:
        return build(plt), plt, can_show_window
    except (ImportError, RuntimeError):
        if not show or not can_show_window:
            raise

        plt.close("all")
        plt, can_show_window = _import_pyplot(interactive=False)
        return build(plt), plt, can_show_window


def _publish_figure(
    plt,
    figure,
    *,
    output_path: Path | None,
    show: bool,
    can_show_window: bool,
    chart_name: str,
) -> ModelVisualizationResult | None:
    if figure is None:
        plt.close("all")
        return None

    written_path: Path | None = None
    if output_path is not None:
        written_path = Path(output_path)
        written_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(written_path, dpi=160, bbox_inches="tight")

    display_message: str | None = None
    if show:
        display_message = _display_figure(
            plt,
            figure,
            written_path=written_path,
            can_show_window=can_show_window,
            chart_name=chart_name,
        )
    else:
        plt.close(figure)

    return ModelVisualizationResult(
        output_path=written_path,
        display_message=display_message,
    )


def _interactive_backend_candidates() -> tuple[str, ...]:
    backends = list(_INTERACTIVE_BACKENDS)
    if sys.platform == "darwin":
        backends.append(_MACOS_BACKEND)
    return tuple(backends)


def _import_pyplot(*, interactive: bool):
    import matplotlib

    if not interactive:
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        return plt, False

    sys.modules.pop("matplotlib.pyplot", None)
    for backend in _interactive_backend_candidates():
        try:
            matplotlib.use(backend, force=True)
            import matplotlib.pyplot as plt
        except (ImportError, ValueError):
            sys.modules.pop("matplotlib.pyplot", None)
            continue

        if "agg" in matplotlib.get_backend().lower():
            sys.modules.pop("matplotlib.pyplot", None)
            continue

        if _backend_can_create_figure(plt):
            return plt, True

        plt.close("all")
        sys.modules.pop("matplotlib.pyplot", None)

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt, False


def _backend_can_create_figure(plt) -> bool:
    try:
        figure, _axes = plt.subplots(1, 1)
        plt.close(figure)
        return True
    except Exception:
        plt.close("all")
        return False


def _display_figure(
    plt,
    figure,
    *,
    written_path: Path | None,
    can_show_window: bool,
    chart_name: str,
) -> str:
    if can_show_window:
        plt.show(block=True)
        plt.close(figure)
        return f"Opened {chart_name} in a matplotlib window."

    if written_path is not None and _open_with_system_viewer(written_path):
        plt.close(figure)
        return (
            f"Opened {chart_name} in your default image viewer "
            f"({written_path})."
        )

    plt.close(figure)
    if written_path is not None:
        return (
            f"No interactive matplotlib backend is available; chart saved to "
            f"{written_path}. Install Tk support (e.g. python3-tkinter on Linux) "
            "for an in-app window."
        )
    raise RuntimeError(
        "Could not open an interactive plot window and no output_path was set."
    )


def _open_with_system_viewer(path: Path) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=True)
            return True
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        subprocess.run(["xdg-open", str(path)], check=True)
        return True
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        return False


def _build_curated_model_figure(
    panel: pl.DataFrame,
    multivariate_summary: dict[str, Any],
    *,
    plt,
    run_id: str,
    rank_depth: str,
):
    if multivariate_summary.get("status") != "computed":
        return None

    score_columns = tuple(multivariate_summary.get("score_columns", CURATED_RANKING_SCORE_COLUMNS))
    fit = fit_multivariate_ranking_model(panel, score_columns=score_columns)
    if fit is None or fit.get("status") != "computed":
        return None

    feature_result = fit["feature_result"]
    clustered_result = fit["clustered_result"]
    model_data = fit["model_data"]
    fitted = np.asarray(feature_result.fittedvalues, dtype=float)
    observed = np.asarray(model_data["outcome"], dtype=float)

    labels = [CURATED_PREDICTOR_LABELS.get(column, column) for column in score_columns]
    coefficients = np.array(
        [_parameter_value(clustered_result, column) for column in score_columns],
        dtype=float,
    )
    intervals = np.array(
        [_parameter_confidence_interval(clustered_result, column) for column in score_columns],
        dtype=float,
    )
    lower_error = coefficients - intervals[:, 0]
    upper_error = intervals[:, 1] - coefficients
    p_values = np.array(
        [
            float(multivariate_summary["feature_model"]["p_values"][column])
            for column in score_columns
        ],
        dtype=float,
    )
    colors = [
        "#1b6b3a" if p_value < SIGNIFICANCE_ALPHA else "#8a8a8a"
        for p_value in p_values
    ]

    feature_model = multivariate_summary.get("feature_model") or {}
    baseline_model = multivariate_summary.get("baseline_model") or {}
    adjusted_r_squared = float(feature_model.get("adjusted_r_squared", 0.0))
    delta_r_squared = float(
        (multivariate_summary.get("descriptive_fit_delta") or {}).get("adjusted_r_squared", 0.0)
    )

    figure, axes = plt.subplots(1, 2, figsize=(12, 5.2), constrained_layout=True)
    figure.suptitle(
        f"Curated ranking model — {run_id} ({rank_depth})",
        fontsize=13,
        fontweight="bold",
    )

    coefficient_axis = axes[0]
    y_positions = np.arange(len(score_columns))
    coefficient_axis.errorbar(
        coefficients,
        y_positions,
        xerr=[lower_error, upper_error],
        fmt="none",
        ecolor="#5c7fbf",
        elinewidth=1.5,
        capsize=4,
    )
    for index, (color, coefficient) in enumerate(zip(colors, coefficients, strict=True)):
        coefficient_axis.plot(coefficient, index, "o", color=color, markersize=7)
    coefficient_axis.axvline(0.0, color="#444444", linewidth=1.0, linestyle="--", alpha=0.8)
    coefficient_axis.set_yticks(y_positions, labels=labels)
    coefficient_axis.set_xlabel("Coefficient (keyword-clustered 95% CI)")
    coefficient_axis.set_title("Predictor effects")
    coefficient_axis.grid(axis="x", alpha=0.25)

    fit_axis = axes[1]
    fit_axis.scatter(observed, fitted, alpha=0.55, color="#1f4b99", edgecolors="white", linewidths=0.4)
    min_value = float(min(observed.min(), fitted.min()))
    max_value = float(max(observed.max(), fitted.max()))
    fit_axis.plot(
        [min_value, max_value],
        [min_value, max_value],
        linestyle="--",
        color="#444444",
        linewidth=1.0,
        label="Perfect fit",
    )
    fit_axis.set_xlabel("Observed -log(rank)")
    fit_axis.set_ylabel("Fitted -log(rank)")
    fit_axis.set_title("Model fit")
    fit_axis.grid(alpha=0.25)
    fit_axis.legend(loc="lower right", frameon=False)

    figure.text(
        0.5,
        0.01,
        (
            f"n={multivariate_summary.get('row_count', 0)} rows, "
            f"k={multivariate_summary.get('keyword_count', 0)} keywords | "
            f"adj. R²={adjusted_r_squared:.4f} | Δ adj. R²={delta_r_squared:.4f} | "
            f"baseline adj. R²={float(baseline_model.get('adjusted_r_squared', 0.0)):.4f}"
        ),
        ha="center",
        fontsize=9,
        color="#333333",
    )
    return figure


def _build_entity_relevance_figure(
    panel: pl.DataFrame,
    univariate_summary: dict[str, Any],
    *,
    plt,
    run_id: str,
    rank_depth: str,
):
    if univariate_summary.get("status") != "computed":
        return None

    fit = fit_multivariate_ranking_model(
        panel,
        score_columns=(ENTITY_RELEVANCE_SCORE_COLUMN,),
    )
    if fit is None or fit.get("status") != "computed":
        return None

    feature_result = fit["feature_result"]
    clustered_result = fit["clustered_result"]
    model_data = fit["model_data"]
    fitted = np.asarray(feature_result.fittedvalues, dtype=float)
    observed = np.asarray(model_data["outcome"], dtype=float)
    relevance = np.asarray(model_data[ENTITY_RELEVANCE_SCORE_COLUMN], dtype=float)

    coefficient = float(_parameter_value(clustered_result, ENTITY_RELEVANCE_SCORE_COLUMN))
    interval = _parameter_confidence_interval(clustered_result, ENTITY_RELEVANCE_SCORE_COLUMN)
    p_value = float(univariate_summary["feature_model"]["p_value"])
    coefficient_color = "#1b6b3a" if p_value < SIGNIFICANCE_ALPHA else "#8a8a8a"

    feature_model = univariate_summary.get("feature_model") or {}
    baseline_model = univariate_summary.get("baseline_model") or {}
    adjusted_r_squared = float(feature_model.get("adjusted_r_squared", 0.0))
    delta_r_squared = float(
        (univariate_summary.get("descriptive_fit_delta") or {}).get("adjusted_r_squared", 0.0)
    )

    figure, axes = plt.subplots(1, 2, figsize=(12, 5.2), constrained_layout=True)
    figure.suptitle(
        f"Entity relevance model — {run_id} ({rank_depth})",
        fontsize=13,
        fontweight="bold",
    )

    relevance_axis = axes[0]
    relevance_axis.scatter(
        relevance,
        observed,
        alpha=0.55,
        color="#1f4b99",
        edgecolors="white",
        linewidths=0.4,
    )
    if relevance.size >= 2 and np.ptp(relevance) > 0:
        slope, intercept = np.polyfit(relevance, observed, 1)
        x_line = np.linspace(relevance.min(), relevance.max(), 100)
        relevance_axis.plot(
            x_line,
            slope * x_line + intercept,
            color="#c44e52",
            linewidth=1.5,
            label="OLS trend",
        )
        relevance_axis.legend(loc="best", frameon=False)
    relevance_axis.set_xlabel(ENTITY_RELEVANCE_LABEL)
    relevance_axis.set_ylabel("Observed -log(rank)")
    relevance_axis.set_title("Entity relevance vs rank outcome")
    relevance_axis.grid(alpha=0.25)

    summary_axis = axes[1]
    summary_axis.errorbar(
        coefficient,
        0.0,
        xerr=[[coefficient - interval[0]], [interval[1] - coefficient]],
        fmt="o",
        color=coefficient_color,
        ecolor="#5c7fbf",
        elinewidth=1.5,
        capsize=5,
        markersize=8,
    )
    summary_axis.axvline(0.0, color="#444444", linewidth=1.0, linestyle="--", alpha=0.8)
    summary_axis.set_yticks([0.0], labels=[ENTITY_RELEVANCE_LABEL])
    summary_axis.set_xlabel("Coefficient (keyword-clustered 95% CI)")
    summary_axis.set_title("Univariate predictor effect")
    summary_axis.set_ylim(-1.0, 1.0)
    summary_axis.grid(axis="x", alpha=0.25)

    fit_axis = summary_axis.inset_axes([0.55, 0.08, 0.42, 0.42])
    fit_axis.scatter(observed, fitted, alpha=0.55, color="#1f4b99", edgecolors="white", linewidths=0.4)
    min_value = float(min(observed.min(), fitted.min()))
    max_value = float(max(observed.max(), fitted.max()))
    fit_axis.plot(
        [min_value, max_value],
        [min_value, max_value],
        linestyle="--",
        color="#444444",
        linewidth=1.0,
    )
    fit_axis.set_xlabel("Observed", fontsize=8)
    fit_axis.set_ylabel("Fitted", fontsize=8)
    fit_axis.set_title("Model fit", fontsize=8)
    fit_axis.tick_params(labelsize=7)
    fit_axis.grid(alpha=0.25)

    figure.text(
        0.5,
        0.01,
        (
            f"n={univariate_summary.get('row_count', 0)} rows, "
            f"k={univariate_summary.get('keyword_count', 0)} keywords | "
            f"coef={coefficient:.4f}, p={p_value:.4f} | "
            f"adj. R²={adjusted_r_squared:.4f} | Δ adj. R²={delta_r_squared:.4f} | "
            f"baseline adj. R²={float(baseline_model.get('adjusted_r_squared', 0.0)):.4f}"
        ),
        ha="center",
        fontsize=9,
        color="#333333",
    )
    return figure
