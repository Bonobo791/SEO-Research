"""Stats artifact helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from seo_rank.stats.diagnostics import summarize_diagnostics_backends_from_fits
from seo_rank.stats.panel import (
    AnalysisPanelResult,
    load_analysis_panel,
    prepare_rank_depth_panel,
)
from seo_rank.stats.plackett_luce import (
    fit_plackett_luce_backends,
    summarize_plackett_luce_backends_from_fits,
    summarize_plackett_luce_diagnostics_backends_from_fits,
)
from seo_rank.stats.regression import (
    fit_regression_backends,
    summarize_regression_backends_from_fits,
)
from seo_rank.stats.spearman import summarize_spearman_backends
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec


logger = logging.getLogger(__name__)


def build_stats_output_metadata(spec: AnalysisSpec) -> Mapping[str, object]:
    return {
        "analysis_spec_version": spec.version,
        "estimand_version": spec.estimand_version,
        "primary_backend": spec.primary_backend,
        "backend_order": list(spec.backend_order),
        "primary_rank_depth": spec.primary_rank_depth,
        "confirmatory_rank_depths": list(spec.confirmatory_rank_depths),
    }


def build_rank_depth_bundles(
    result: AnalysisPanelResult,
    *,
    spec: AnalysisSpec,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    """Compute confirmatory stats for every rank depth."""

    logger.info(
        "building rank_depth bundles depths=%s",
        list(spec.confirmatory_rank_depths),
    )
    rank_depth_bundles: dict[str, dict[str, object]] = {}
    diagnostics_by_depth: dict[str, dict[str, object]] = {}

    for depth_key in spec.confirmatory_rank_depths:
        depth_mart, depth_panel, guardrails, hard_fail, limitations = prepare_rank_depth_panel(
            result.analysis_mart,
            depth_key=depth_key,
            spec=spec,
        )
        bundle: dict[str, object] = {
            "rank_depth_key": depth_key,
            "max_serp_rank": spec.rank_depth_limit(depth_key),
            "analysis_mart_rows": int(depth_mart.height),
            "panel_rows": int(depth_panel.height),
            "guardrails": guardrails,
            "limitations": limitations,
            "hard_fail": hard_fail,
            "actionable_association": False,
            "spearman": None,
            "regression": None,
            "plackett_luce": None,
        }
        if not hard_fail:
            max_rank = spec.rank_depth_limit(depth_key)
            spearman = summarize_spearman_backends(depth_mart, result.backend_order)
            regression_fits = fit_regression_backends(depth_mart, result.backend_order)
            regression = summarize_regression_backends_from_fits(
                depth_mart,
                result.backend_order,
                fits=regression_fits,
            )
            plackett_luce_fits = fit_plackett_luce_backends(
                depth_mart,
                result.backend_order,
                max_rank=max_rank,
            )
            plackett_luce = summarize_plackett_luce_backends_from_fits(
                depth_mart,
                result.backend_order,
                fits=plackett_luce_fits,
            )
            plackett_luce_diagnostics = summarize_plackett_luce_diagnostics_backends_from_fits(
                depth_mart,
                result.backend_order,
                fits=plackett_luce_fits,
                include_iia_sensitivity=(depth_key == spec.primary_rank_depth),
            )
            diagnostics = summarize_diagnostics_backends_from_fits(
                depth_mart,
                result.backend_order,
                fits=regression_fits,
            )
            bundle["spearman"] = spearman
            bundle["regression"] = regression
            bundle["plackett_luce"] = plackett_luce
            bundle["actionable_association"] = _compute_actionable_association(
                hard_fail=False,
                primary_backend=result.primary_backend,
                spearman=spearman,
                regression=regression,
            )
            diagnostics_by_depth[depth_key] = {
                "regression": diagnostics,
                "plackett_luce": plackett_luce_diagnostics,
            }
        logger.info(
            "rank_depth bundle depth=%s mart_rows=%d hard_fail=%s actionable=%s",
            depth_key,
            bundle["analysis_mart_rows"],
            hard_fail,
            bundle["actionable_association"],
        )
        rank_depth_bundles[depth_key] = bundle

    return rank_depth_bundles, diagnostics_by_depth


def build_stats_summary(
    result: AnalysisPanelResult,
    *,
    rank_depth_bundles: dict[str, dict[str, object]],
    spec: AnalysisSpec,
) -> dict[str, object]:
    primary_depth = spec.primary_rank_depth
    primary_bundle = rank_depth_bundles[primary_depth]
    actionable_by_depth = {
        depth_key: bool(bundle["actionable_association"])
        for depth_key, bundle in rank_depth_bundles.items()
    }

    summary: dict[str, object] = {
        "analysis_spec_version": result.analysis_spec_version,
        "estimand_version": result.estimand_version,
        "primary_backend": result.primary_backend,
        "backend_order": list(result.backend_order),
        "primary_rank_depth": primary_depth,
        "confirmatory_rank_depths": list(spec.confirmatory_rank_depths),
        "rank_depths": {
            depth_key: _public_rank_depth_bundle(bundle)
            for depth_key, bundle in rank_depth_bundles.items()
        },
        "actionable_association_by_rank_depth": actionable_by_depth,
        "panel": {
            "grain": ["target_keyword_id", "canonical_url_hash"],
            "analysis_mart_rows": primary_bundle["analysis_mart_rows"],
            "panel_rows": primary_bundle["panel_rows"],
        },
        "guardrails": primary_bundle["guardrails"],
        "limitations": primary_bundle["limitations"],
        "hard_fail": primary_bundle["hard_fail"],
        "actionable_association": primary_bundle["actionable_association"],
    }
    if primary_bundle["spearman"] is not None:
        summary["spearman"] = primary_bundle["spearman"]
    if primary_bundle["regression"] is not None:
        summary["regression"] = primary_bundle["regression"]
    if primary_bundle["plackett_luce"] is not None:
        summary["plackett_luce"] = primary_bundle["plackett_luce"]
    return summary


def build_stats_diagnostics(
    result: AnalysisPanelResult,
    *,
    diagnostics_by_depth: dict[str, dict[str, object]],
    spec: AnalysisSpec,
) -> dict[str, object]:
    primary_depth = spec.primary_rank_depth
    primary_diagnostics = diagnostics_by_depth.get(primary_depth, {})
    output: dict[str, object] = {
        "analysis_spec_version": result.analysis_spec_version,
        "estimand_version": result.estimand_version,
        "primary_backend": result.primary_backend,
        "backend_order": list(result.backend_order),
        "primary_rank_depth": primary_depth,
        "confirmatory_rank_depths": list(spec.confirmatory_rank_depths),
        "rank_depths": diagnostics_by_depth,
    }
    regression = primary_diagnostics.get("regression")
    plackett_luce = primary_diagnostics.get("plackett_luce")
    if regression is not None:
        output["backends"] = regression["backends"]
    if plackett_luce is not None:
        output["plackett_luce"] = plackett_luce
    return output


def build_stats_report(
    result: AnalysisPanelResult,
    *,
    rank_depth_bundles: dict[str, dict[str, object]],
    diagnostics_by_depth: dict[str, dict[str, object]],
    spec: AnalysisSpec,
) -> str:
    lines = ["# Phase 5 Stats", ""]

    for depth_key in spec.confirmatory_rank_depths:
        bundle = rank_depth_bundles[depth_key]
        depth_diagnostics = diagnostics_by_depth.get(depth_key, {})
        lines.extend(_rank_depth_report_sections(bundle, depth_diagnostics))

    return "\n".join(lines) + "\n"


def _rank_depth_report_sections(
    bundle: dict[str, object],
    depth_diagnostics: dict[str, object],
) -> list[str]:
    depth_key = str(bundle["rank_depth_key"])
    lines = [
        f"## Rank depth: {depth_key}",
        "",
        "### Guardrails",
    ]
    for guardrail in bundle["guardrails"]:
        lines.append(
            f"- {guardrail['name']}: {guardrail['status']} "
            f"(value={json.dumps(guardrail['value'], sort_keys=True)}, "
            f"threshold={json.dumps(guardrail['threshold'])})"
        )

    lines.extend(["", "### Limitations"])
    for name, text in dict(bundle["limitations"]).items():
        lines.append(f"- {name}: {text}")

    spearman = bundle.get("spearman")
    if spearman is not None:
        lines.extend(["", "### Spearman"])
        lines.extend(_format_spearman_lines(spearman))

    regression = bundle.get("regression")
    if regression is not None:
        lines.extend(["", "### Regression"])
        lines.extend(_format_regression_lines(regression))

    plackett_luce = bundle.get("plackett_luce")
    if plackett_luce is not None:
        lines.extend(["", "### Plackett-Luce"])
        plackett_luce_diagnostics = depth_diagnostics.get("plackett_luce")
        lines.extend(_format_plackett_luce_lines(plackett_luce, plackett_luce_diagnostics))

    diagnostics = depth_diagnostics.get("regression")
    if diagnostics is not None:
        lines.extend(["", "### Diagnostics"])
        lines.extend(_format_diagnostics_lines(diagnostics))

    lines.extend(
        [
            "",
            "### Status",
            (
                "Confirmatory inference skipped because hard-fail guardrails did not pass."
                if bundle["hard_fail"]
                else "Guardrails passed; confirmatory inference may proceed."
            ),
            "",
        ]
    )
    return lines


def _format_spearman_lines(spearman: dict[str, object]) -> list[str]:
    lines: list[str] = []
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
    return lines


def _format_regression_lines(regression: dict[str, object]) -> list[str]:
    lines: list[str] = []
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
    return lines


def _format_plackett_luce_lines(
    plackett_luce: dict[str, object],
    plackett_luce_diagnostics: dict[str, object] | None,
) -> list[str]:
    lines: list[str] = []
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
        leave_one_out_top_rank_status = "n/a"
        if plackett_luce_diagnostics is not None:
            diagnostics_summary = dict(plackett_luce_diagnostics["backends"][backend])
            iia_sensitivity = diagnostics_summary.get("iia_sensitivity")
            if isinstance(iia_sensitivity, dict):
                leave_one_out = iia_sensitivity.get("leave_one_out_top_rank")
                if isinstance(leave_one_out, dict) and "status" in leave_one_out:
                    leave_one_out_top_rank_status = leave_one_out["status"]
        lines.append(
            "- "
            f"{backend}: status={status}, "
            f"odds_ratio_per_1sd={main_model.get('odds_ratio_per_1sd', 'n/a')}, "
            f"convergence_confirmed={diagnostics_summary['convergence_confirmed'] if diagnostics_summary else 'n/a'}, "
            f"hessian_condition_number={diagnostics_summary['hessian_condition_number'] if diagnostics_summary else 'n/a'}, "
            f"leave_one_out_top_rank_status={leave_one_out_top_rank_status}"
        )
    return lines


def _format_diagnostics_lines(diagnostics: dict[str, object]) -> list[str]:
    lines: list[str] = []
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
    return lines


def _public_rank_depth_bundle(bundle: dict[str, object]) -> dict[str, object]:
    public = {
        key: bundle[key]
        for key in (
            "rank_depth_key",
            "max_serp_rank",
            "analysis_mart_rows",
            "panel_rows",
            "guardrails",
            "limitations",
            "hard_fail",
            "actionable_association",
        )
    }
    if bundle["spearman"] is not None:
        public["spearman"] = bundle["spearman"]
    if bundle["regression"] is not None:
        public["regression"] = bundle["regression"]
    if bundle["plackett_luce"] is not None:
        public["plackett_luce"] = bundle["plackett_luce"]
    return public


def _compute_actionable_association(
    *,
    hard_fail: bool,
    primary_backend: str,
    spearman: dict[str, object] | None,
    regression: dict[str, object] | None,
) -> bool:
    if hard_fail or spearman is None or regression is None:
        return False

    spearman_summary = spearman["backends"].get(primary_backend)
    regression_summary = regression["backends"].get(primary_backend)
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
    rank_depth_bundles: dict[str, dict[str, object]],
    diagnostics_by_depth: dict[str, dict[str, object]],
    spec: AnalysisSpec,
) -> dict[str, object]:
    stats_dir = Path(run_dir) / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    logger.info("writing stats artifacts run_dir=%s stats_dir=%s", run_dir, stats_dir)

    summary = build_stats_summary(
        result,
        rank_depth_bundles=rank_depth_bundles,
        spec=spec,
    )
    (stats_dir / "stats_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if diagnostics_by_depth:
        diagnostics_summary = build_stats_diagnostics(
            result,
            diagnostics_by_depth=diagnostics_by_depth,
            spec=spec,
        )
        (stats_dir / "stats_diagnostics.json").write_text(
            json.dumps(diagnostics_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (stats_dir / "stats_report.md").write_text(
        build_stats_report(
            result,
            rank_depth_bundles=rank_depth_bundles,
            diagnostics_by_depth=diagnostics_by_depth,
            spec=spec,
        ),
        encoding="utf-8",
    )
    logger.info(
        "wrote stats artifacts run_dir=%s files=%s",
        run_dir,
        ["stats_summary.json", *(["stats_diagnostics.json"] if diagnostics_by_depth else []), "stats_report.md"],
    )
    return summary


def run_phase5_stats(
    run_dir: Path,
    *,
    spec: AnalysisSpec | None = None,
) -> AnalysisPanelResult:
    """Load the panel, write guardrail artifacts, and return the prepared panel."""

    logger.info("running phase5 stats run_dir=%s", run_dir)
    analysis_spec = spec or load_analysis_spec()
    result = load_analysis_panel(run_dir, spec=analysis_spec)
    rank_depth_bundles, diagnostics_by_depth = build_rank_depth_bundles(
        result,
        spec=analysis_spec,
    )
    write_stats_artifacts(
        run_dir,
        result,
        rank_depth_bundles=rank_depth_bundles,
        diagnostics_by_depth=diagnostics_by_depth,
        spec=analysis_spec,
    )
    logger.info(
        "phase5 stats complete run_dir=%s hard_fail=%s depths=%s",
        run_dir,
        result.hard_fail,
        list(analysis_spec.confirmatory_rank_depths),
    )
    return result
