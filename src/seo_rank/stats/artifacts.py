"""Stats artifact helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from seo_rank.stats.diagnostics import (
    summarize_diagnostics_backends_from_fits,
)
from seo_rank.stats.plackett_luce import (
    fit_plackett_luce_backends,
    summarize_plackett_luce_backends_from_fits,
    summarize_plackett_luce_diagnostics_backends_from_fits,
)
from seo_rank.stats.spec import AnalysisSpec
from seo_rank.stats.panel import AnalysisPanelResult, load_analysis_panel
from seo_rank.stats.regression import (
    fit_regression_backends,
    summarize_regression_backends_from_fits,
)
from seo_rank.stats.spearman import summarize_spearman_backends


def build_stats_output_metadata(spec: AnalysisSpec) -> Mapping[str, object]:
    return {
        "analysis_spec_version": spec.version,
        "estimand_version": spec.estimand_version,
        "primary_backend": spec.primary_backend,
        "backend_order": list(spec.backend_order),
    }


def build_stats_summary(
    result: AnalysisPanelResult,
    *,
    spearman: dict[str, object] | None = None,
    regression: dict[str, object] | None = None,
    plackett_luce: dict[str, object] | None = None,
) -> dict[str, object]:
    summary = {
        "analysis_spec_version": result.analysis_spec_version,
        "estimand_version": result.estimand_version,
        "primary_backend": result.primary_backend,
        "backend_order": list(result.backend_order),
        "panel": {
            "grain": ["target_keyword_id", "canonical_url_hash"],
            "analysis_mart_rows": result.analysis_mart.height,
            "panel_rows": result.panel.height,
        },
        "guardrails": result.guardrails,
        "limitations": result.limitations,
        "hard_fail": result.hard_fail,
        "actionable_association": _compute_actionable_association(
            result,
            spearman=spearman,
            regression=regression,
        ),
    }
    if spearman is not None:
        summary["spearman"] = spearman
    if regression is not None:
        summary["regression"] = regression
    if plackett_luce is not None:
        summary["plackett_luce"] = plackett_luce
    return summary


def build_stats_diagnostics(
    result: AnalysisPanelResult,
    *,
    diagnostics: dict[str, object],
    plackett_luce: dict[str, object] | None = None,
) -> dict[str, object]:
    output = {
        "analysis_spec_version": result.analysis_spec_version,
        "estimand_version": result.estimand_version,
        "primary_backend": result.primary_backend,
        "backend_order": list(result.backend_order),
        "backends": diagnostics["backends"],
    }
    if plackett_luce is not None:
        output["plackett_luce"] = plackett_luce
    return output


def build_stats_report(
    result: AnalysisPanelResult,
    *,
    spearman: dict[str, object] | None = None,
    regression: dict[str, object] | None = None,
    plackett_luce: dict[str, object] | None = None,
    plackett_luce_diagnostics: dict[str, object] | None = None,
    diagnostics: dict[str, object] | None = None,
) -> str:
    lines = [
        "# Phase 5 Stats",
        "",
        "## Guardrails",
    ]
    for guardrail in result.guardrails:
        lines.append(
            f"- {guardrail['name']}: {guardrail['status']} "
            f"(value={json.dumps(guardrail['value'], sort_keys=True)}, "
            f"threshold={json.dumps(guardrail['threshold'])})"
        )

    lines.extend(
        [
            "",
            "## Limitations",
        ]
    )
    for name, text in result.limitations.items():
        lines.append(f"- {name}: {text}")

    if spearman is not None:
        lines.extend(
            [
                "",
                "## Spearman",
            ]
        )
        for backend, backend_summary in spearman["backends"].items():
            backend_summary = dict(backend_summary)
            line = (
                f"- {backend}: keyword_count={backend_summary['keyword_count']}, "
                f"median_rho={backend_summary['median_rho']}, "
                f"rho_iqr={backend_summary['rho_iqr']}, "
                f"fraction_same_sign={backend_summary['fraction_same_sign']}"
            )
            if "bh_q_values" in backend_summary:
                line += ", bh_applied=true"
            else:
                line += f", bh_skipped_reason={backend_summary['bh_skipped_reason']}"
            lines.append(line)

    if regression is not None:
        lines.extend(
            [
                "",
                "## Regression",
            ]
        )
        for backend, backend_summary in regression["backends"].items():
            backend_summary = dict(backend_summary)
            if backend_summary.get("status") == "skipped":
                lines.append(
                    "- "
                    f"{backend}: status=skipped, "
                    f"skipped_reason={backend_summary['skipped_reason']}"
                )
                continue
            feature_model = backend_summary["feature_model"]
            effect_size = backend_summary["effect_size"]
            two_way_cluster = backend_summary["sensitivity"]["two_way_cluster"]
            lines.append(
                "- "
                f"{backend}: coefficient={feature_model['coefficient']}, "
                f"clustered_ci={feature_model['clustered_confidence_interval']}, "
                f"approx_delta_rank_per_1sd={effect_size['approximate_delta_rank_per_1sd']}, "
                f"two_way_cluster_status={two_way_cluster['status']}"
            )

    if plackett_luce is not None:
        lines.extend(
            [
                "",
                "## Plackett-Luce",
            ]
        )
        for backend, backend_summary in plackett_luce["backends"].items():
            backend_summary = dict(backend_summary)
            if backend_summary.get("status") == "skipped":
                lines.append(
                    "- "
                    f"{backend}: status=skipped, "
                    f"skipped_reason={backend_summary['skipped_reason']}"
                )
                continue
            main_model = backend_summary["main_model"]
            status = backend_summary.get("status", "computed")
            diagnostics_summary = None
            if plackett_luce_diagnostics is not None:
                diagnostics_summary = dict(plackett_luce_diagnostics["backends"][backend])
            lines.append(
                "- "
                f"{backend}: status={status}, "
                f"odds_ratio_per_1sd={main_model.get('odds_ratio_per_1sd', 'n/a')}, "
                f"convergence_confirmed={diagnostics_summary['convergence_confirmed'] if diagnostics_summary else 'n/a'}, "
                f"hessian_condition_number={diagnostics_summary['hessian_condition_number'] if diagnostics_summary else 'n/a'}, "
                f"top10_status={diagnostics_summary['iia_sensitivity']['top10']['status'] if diagnostics_summary else 'n/a'}"
            )

    if diagnostics is not None:
        lines.extend(
            [
                "",
                "## Diagnostics",
            ]
        )
        for backend, backend_summary in diagnostics["backends"].items():
            backend_summary = dict(backend_summary)
            if backend_summary.get("status") == "skipped":
                lines.append(
                    "- "
                    f"{backend}: status=skipped, "
                    f"skipped_reason={backend_summary['skipped_reason']}"
                )
                continue
            reset = backend_summary["reset"]
            breusch_pagan = backend_summary["breusch_pagan"]
            influence = backend_summary["influence"]
            line = (
                "- "
                f"{backend}: reset_status={reset['status']}, "
                f"reset_p_value={reset['p_value']}, "
                f"reset_flagged={reset['flagged']}, "
                f"breusch_pagan_p_value={breusch_pagan['lm_p_value']}, "
                f"breusch_pagan_flagged={breusch_pagan['flagged']}, "
                f"recommended_se_type={breusch_pagan['recommended_se_type']}, "
                f"cook_d_count={influence['cook_d_count']}/{influence['row_count']}, "
                f"leverage_count={influence['leverage_count']}, "
                f"studentized_residual_count={influence['studentized_residual_count']}, "
                f"dffits_count={influence['dffits_count']}, "
                f"dfbeta_count={influence['dfbeta_count']}"
            )
            shapiro = backend_summary.get("shapiro")
            if shapiro is not None and shapiro.get("status") != "skipped":
                line += (
                    f", shapiro_status={shapiro['status']}, "
                    f"shapiro_p_value={shapiro['p_value']}"
                )
            lines.append(line)

    lines.extend(
        [
            "",
            "## Status",
            (
                "Confirmatory inference skipped because hard-fail guardrails did not pass."
                if result.hard_fail
                else "Guardrails passed; confirmatory inference may proceed in later slices."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _compute_actionable_association(
    result: AnalysisPanelResult,
    *,
    spearman: dict[str, object] | None,
    regression: dict[str, object] | None,
) -> bool:
    if result.hard_fail or spearman is None or regression is None:
        return False

    backend = result.primary_backend
    spearman_summary = spearman["backends"].get(backend)
    regression_summary = regression["backends"].get(backend)
    if not spearman_summary or not regression_summary:
        return False
    if spearman_summary.get("status") == "skipped" or regression_summary.get("status") == "skipped":
        return False

    median_abs_rho = float(
        np.median([abs(float(test["rho"])) for test in spearman_summary["keyword_tests"]])
    )
    if median_abs_rho < 0.25:
        return False
    if float(spearman_summary["fraction_same_sign"]) < 0.60:
        return False

    confidence_interval = regression_summary["feature_model"]["clustered_confidence_interval"]
    if len(confidence_interval) != 2:
        return False
    lower, upper = float(confidence_interval[0]), float(confidence_interval[1])
    return bool(lower > 0 or upper < 0)


def write_stats_artifacts(
    run_dir: Path,
    result: AnalysisPanelResult,
    *,
    spearman: dict[str, object] | None = None,
    regression: dict[str, object] | None = None,
    diagnostics: dict[str, object] | None = None,
    plackett_luce: dict[str, object] | None = None,
    plackett_luce_diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    stats_dir = Path(run_dir) / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)

    summary = build_stats_summary(
        result,
        spearman=spearman,
        regression=regression,
        plackett_luce=plackett_luce,
    )
    (stats_dir / "stats_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if diagnostics is not None:
        diagnostics_summary = build_stats_diagnostics(
            result,
            diagnostics=diagnostics,
            plackett_luce=plackett_luce_diagnostics,
        )
        (stats_dir / "stats_diagnostics.json").write_text(
            json.dumps(diagnostics_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (stats_dir / "stats_report.md").write_text(
        build_stats_report(
            result,
            spearman=spearman,
            regression=regression,
            plackett_luce=plackett_luce,
            plackett_luce_diagnostics=plackett_luce_diagnostics,
            diagnostics=diagnostics,
        ),
        encoding="utf-8",
    )
    return summary


def run_phase5_stats(
    run_dir: Path,
    *,
    spec: AnalysisSpec | None = None,
) -> AnalysisPanelResult:
    """Load the panel, write guardrail artifacts, and return the prepared panel."""

    result = load_analysis_panel(run_dir, spec=spec)
    spearman = None
    regression = None
    diagnostics = None
    plackett_luce = None
    plackett_luce_diagnostics = None
    if not result.hard_fail:
        spearman = summarize_spearman_backends(result.analysis_mart, result.backend_order)
        regression_fits = fit_regression_backends(result.analysis_mart, result.backend_order)
        regression = summarize_regression_backends_from_fits(
            result.analysis_mart,
            result.backend_order,
            fits=regression_fits,
        )
        diagnostics = summarize_diagnostics_backends_from_fits(
            result.analysis_mart,
            result.backend_order,
            fits=regression_fits,
        )
        plackett_luce_fits = fit_plackett_luce_backends(
            result.analysis_mart,
            result.backend_order,
        )
        plackett_luce = summarize_plackett_luce_backends_from_fits(
            result.analysis_mart,
            result.backend_order,
            fits=plackett_luce_fits,
        )
        plackett_luce_diagnostics = summarize_plackett_luce_diagnostics_backends_from_fits(
            result.analysis_mart,
            result.backend_order,
            fits=plackett_luce_fits,
        )
    write_stats_artifacts(
        run_dir,
        result,
        spearman=spearman,
        regression=regression,
        diagnostics=diagnostics,
        plackett_luce=plackett_luce,
        plackett_luce_diagnostics=plackett_luce_diagnostics,
    )
    return result
