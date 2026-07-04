"""Stats artifact helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from seo_rank.debug_trace import debug_trace
from seo_rank.data.scans import scan_curated_table
from seo_rank.stats.diagnostics import summarize_diagnostics_backends_from_fits
from seo_rank.stats.diagnostics import summarize_diagnostics_families
from seo_rank.stats.diagnostics import summarize_multivariate_sensitivity
from seo_rank.stats.panel import (
    AnalysisPanelResult,
    load_analysis_panel,
    prepare_rank_depth_panel,
)
from seo_rank.stats.plackett_luce import (
    fit_plackett_luce_backends,
    summarize_plackett_luce_families,
    summarize_plackett_luce_backends_from_fits,
    summarize_plackett_luce_diagnostics_backends_from_fits,
)
from seo_rank.stats.regression import (
    fit_regression_backends,
    summarize_regression_families,
    summarize_regression_backends_from_fits,
)
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.spearman import summarize_spearman_backends, summarize_spearman_families
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec


logger = logging.getLogger(__name__)


def build_stats_output_metadata(spec: AnalysisSpec) -> Mapping[str, object]:
    return {
        "analysis_spec_version": spec.version,
        "estimand_version": spec.estimand_version,
        "primary_backend": spec.primary_backend,
        "backend_order": list(spec.backend_order),
        "signal_family_order": list(spec.signal_family_keys),
        "primary_rank_depth": spec.primary_rank_depth,
        "confirmatory_rank_depths": list(spec.confirmatory_rank_depths),
    }


def _inference_mode_for_keyword_count(keyword_count: int) -> str:
    if keyword_count <= 0:
        return "skipped"
    if keyword_count == 1:
        return "underpowered"
    if keyword_count < 10:
        return "exploratory"
    return "confirmatory"


def _annotate_inference_modes(value: object) -> object:
    if isinstance(value, dict):
        annotated = {key: _annotate_inference_modes(item) for key, item in value.items()}
        keyword_count = annotated.get("keyword_count")
        if isinstance(keyword_count, int) and "inference_mode" not in annotated:
            annotated["inference_mode"] = _inference_mode_for_keyword_count(keyword_count)
        return annotated
    if isinstance(value, list):
        return [_annotate_inference_modes(item) for item in value]
    return value


def build_family_source_frames(
    run_dir: Path,
    *,
    analysis_mart: pl.DataFrame,
    spec: AnalysisSpec,
) -> dict[str, pl.DataFrame]:
    """Load the per-family source frames used for registry-driven stats."""

    source_frames: dict[str, pl.DataFrame] = {
        "analysis_mart": analysis_mart,
        "textrazor_page_metrics": _load_textrazor_family_frame(
            run_dir,
            analysis_mart=analysis_mart,
            spec=spec,
        ),
    }
    return source_frames


def _load_textrazor_family_frame(
    run_dir: Path,
    *,
    analysis_mart: pl.DataFrame,
    spec: AnalysisSpec,
) -> pl.DataFrame:
    textrazor_path = Path(run_dir) / "parquet" / "textrazor_page_metrics"
    signal_columns = _textrazor_signal_columns(spec)
    if not textrazor_path.exists():
        return _analysis_mart_with_null_textrazor_columns(analysis_mart, signal_columns)

    try:
        textrazor_page_metrics = scan_curated_table(run_dir, "textrazor_page_metrics").collect()
    except OSError:
        return _analysis_mart_with_null_textrazor_columns(analysis_mart, signal_columns)
    return merge_analysis_mart_with_textrazor_page_metrics(
        analysis_mart,
        textrazor_page_metrics,
        signal_columns=signal_columns,
    )


def merge_keyword_analysis_frame(
    analysis_mart: pl.DataFrame,
    textrazor_page_metrics: pl.DataFrame | None,
) -> pl.DataFrame:
    """Merge keyword inspection rows with TextRazor metrics when available."""

    if textrazor_page_metrics is None or textrazor_page_metrics.is_empty():
        return analysis_mart
    signal_columns = tuple(
        column
        for column in textrazor_page_metrics.columns
        if column not in {"run_id", "target_keyword_id", "target_keyword", "canonical_url_hash", "url", "response_id", "schema_version"}
    )
    return merge_analysis_mart_with_textrazor_page_metrics(
        analysis_mart,
        textrazor_page_metrics,
        signal_columns=signal_columns,
    )


def merge_analysis_mart_with_textrazor_page_metrics(
    analysis_mart: pl.DataFrame,
    textrazor_page_metrics: pl.DataFrame,
    *,
    signal_columns: tuple[str, ...],
) -> pl.DataFrame:
    """Left-join TextRazor page metrics onto the analysis mart."""

    visible_columns = set(signal_columns)
    visible_columns.add("page_metrics_row_id")
    selected_columns = [
        "run_id",
        "target_keyword_id",
        "canonical_url_hash",
        *[column for column in textrazor_page_metrics.columns if column in visible_columns],
    ]
    if "page_metrics_row_id" not in selected_columns and "page_metrics_row_id" in textrazor_page_metrics.columns:
        selected_columns.append("page_metrics_row_id")
    merged = analysis_mart.join(
        textrazor_page_metrics.select(selected_columns),
        on=["run_id", "target_keyword_id", "canonical_url_hash"],
        how="left",
    )
    confidence_column = "textrazor_entity_confidence_score"
    if confidence_column in merged.columns:
        debug_trace(
            hypothesis_id="H4-H5",
            location="artifacts.py:merge_analysis_mart_with_textrazor_page_metrics",
            message="textrazor join coverage",
            data={
                "analysis_mart_rows": analysis_mart.height,
                "textrazor_rows": textrazor_page_metrics.height,
                "merged_rows": merged.height,
                "confidence_non_null": int(
                    merged[confidence_column].is_not_null().sum()
                ),
                "confidence_null": int(merged[confidence_column].is_null().sum()),
            },
        )
    sort_columns = ["target_keyword_id", "canonical_url_hash", "serp_rank", "serp_item_id"]
    if all(column in merged.columns for column in sort_columns):
        merged = merged.sort(sort_columns)
    return merged


def _analysis_mart_with_null_textrazor_columns(
    analysis_mart: pl.DataFrame,
    signal_columns: tuple[str, ...],
) -> pl.DataFrame:
    return analysis_mart.with_columns(
        [pl.lit(None).alias("page_metrics_row_id"), *[pl.lit(None).alias(column) for column in signal_columns]]
    )


def _textrazor_signal_columns(spec: AnalysisSpec) -> tuple[str, ...]:
    columns: list[str] = []
    for family in spec.signal_families.families:
        if family.kind.startswith("textrazor_"):
            for column in family.signal_columns:
                if column not in columns:
                    columns.append(column)
    return tuple(columns)


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
    family_source_frames = build_family_source_frames(
        result.run_dir,
        analysis_mart=result.analysis_mart,
        spec=spec,
    )
    rank_depth_bundles: dict[str, dict[str, object]] = {}
    diagnostics_by_depth: dict[str, dict[str, object]] = {}

    for depth_key in spec.confirmatory_rank_depths:
        depth_mart, depth_panel, guardrails, hard_fail, limitations = prepare_rank_depth_panel(
            result.analysis_mart,
            depth_key=depth_key,
            spec=spec,
        )
        keyword_count = (
            int(depth_mart.get_column("target_keyword_id").n_unique())
            if "target_keyword_id" in depth_mart.columns
            else 0
        )
        bundle: dict[str, object] = {
            "rank_depth_key": depth_key,
            "max_serp_rank": spec.rank_depth_limit(depth_key),
            "analysis_mart_rows": int(depth_mart.height),
            "panel_rows": int(depth_panel.height),
            "keyword_count": keyword_count,
            "inference_mode": _inference_mode_for_keyword_count(keyword_count),
            "guardrails": guardrails,
            "limitations": limitations,
            "hard_fail": hard_fail,
            "actionable_association": False,
            "spearman": None,
            "regression": None,
            "plackett_luce": None,
            "families": None,
        }
        depth_family_frames = _filter_family_source_frames_by_rank_depth(
            family_source_frames,
            max_rank=spec.rank_depth_limit(depth_key),
        )
        if hard_fail:
            depth_family_frames = {
                name: frame.head(0)
                for name, frame in depth_family_frames.items()
            }
        bundle["families"] = build_family_depth_bundles(
            depth_family_frames,
            spec=spec,
            max_rank=spec.rank_depth_limit(depth_key),
            include_iia_sensitivity=(depth_key == spec.primary_rank_depth),
        )
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
            depth_diagnostics: dict[str, object] = {
                "regression": diagnostics,
                "plackett_luce": plackett_luce_diagnostics,
            }
            _append_influential_rows_guardrail(
                bundle,
                spec=spec,
                regression_diagnostics=diagnostics,
            )
            if depth_key == spec.primary_rank_depth:
                depth_diagnostics["multivariate_sensitivity"] = summarize_multivariate_sensitivity(
                    depth_mart,
                    vif_threshold=spec.multivariate_vif_threshold,
                    backend_drop_order=spec.backend_drop_order,
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
            diagnostics_by_depth[depth_key] = depth_diagnostics
        bundle = _annotate_inference_modes(bundle)
        if not hard_fail:
            diagnostics_by_depth[depth_key] = _annotate_inference_modes(
                diagnostics_by_depth.get(depth_key, {})
            )
        logger.info(
            "rank_depth bundle depth=%s mart_rows=%d hard_fail=%s actionable=%s",
            depth_key,
            bundle["analysis_mart_rows"],
            hard_fail,
            bundle["actionable_association"],
        )
        rank_depth_bundles[depth_key] = bundle

    return rank_depth_bundles, diagnostics_by_depth


def _filter_family_source_frames_by_rank_depth(
    source_frames: dict[str, pl.DataFrame],
    *,
    max_rank: int,
) -> dict[str, pl.DataFrame]:
    return {
        name: (
            filter_panel_by_max_rank(frame, max_rank=max_rank)
            if "serp_rank" in frame.columns
            else frame
        )
        for name, frame in source_frames.items()
    }


def build_family_depth_bundles(
    source_frames: dict[str, pl.DataFrame],
    *,
    spec: AnalysisSpec,
    max_rank: int,
    include_iia_sensitivity: bool,
) -> dict[str, dict[str, object]]:
    """Build registry-ordered family bundles for one rank depth."""

    spearman_families = summarize_spearman_families(
        source_frames,
        registry=spec.signal_families,
    )["families"]
    regression_families = summarize_regression_families(
        source_frames,
        registry=spec.signal_families,
    )["families"]
    diagnostics_families = summarize_diagnostics_families(
        source_frames,
        registry=spec.signal_families,
    )["families"]
    plackett_luce_families = summarize_plackett_luce_families(
        source_frames,
        registry=spec.signal_families,
        max_rank=max_rank,
        include_iia_sensitivity=include_iia_sensitivity,
    )["families"]

    family_bundles: dict[str, dict[str, object]] = {}
    for family_key in spec.signal_family_keys:
        family = spec.signal_family(family_key)
        family_bundles[family_key] = {
            "family": family_key,
            "kind": family.kind,
            "source_mart": spec.signal_families.source_mart_for_family(family_key),
            "signal_columns": list(family.signal_columns),
            "spearman": spearman_families[family_key],
            "regression": regression_families[family_key],
            "diagnostics": diagnostics_families[family_key],
            "plackett_luce": plackett_luce_families[family_key],
        }
    return family_bundles


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
        "metadata": build_stats_output_metadata(spec),
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
    rank_depth_bundles: dict[str, dict[str, object]],
    diagnostics_by_depth: dict[str, dict[str, object]],
    spec: AnalysisSpec,
) -> dict[str, object]:
    primary_depth = spec.primary_rank_depth
    primary_diagnostics = diagnostics_by_depth.get(primary_depth, {})
    primary_bundle = rank_depth_bundles[primary_depth]
    output: dict[str, object] = {
        "analysis_spec_version": result.analysis_spec_version,
        "estimand_version": result.estimand_version,
        "primary_backend": result.primary_backend,
        "backend_order": list(result.backend_order),
        "metadata": build_stats_output_metadata(spec),
        "primary_rank_depth": primary_depth,
        "confirmatory_rank_depths": list(spec.confirmatory_rank_depths),
        "rank_depths": {
            depth_key: {
                **diagnostics_by_depth.get(depth_key, {}),
                "families": rank_depth_bundles[depth_key]["families"],
            }
            for depth_key in spec.confirmatory_rank_depths
        },
    }
    regression = primary_diagnostics.get("regression")
    plackett_luce = primary_diagnostics.get("plackett_luce")
    if regression is not None:
        output["backends"] = regression["backends"]
    if plackett_luce is not None:
        output["plackett_luce"] = plackett_luce
    output["guardrails"] = primary_bundle["guardrails"]
    output["limitations"] = primary_bundle["limitations"]
    output["hard_fail"] = primary_bundle["hard_fail"]
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
        lines.extend(["", "### Influence robustness"])
        lines.extend(_format_influence_sensitivity_lines(diagnostics))

    multivariate_sensitivity = depth_diagnostics.get("multivariate_sensitivity")
    if multivariate_sensitivity is not None:
        lines.extend(["", "### Robustness"])
        lines.extend(_format_multivariate_sensitivity_lines(multivariate_sensitivity))

    families = bundle.get("families")
    if isinstance(families, dict) and families:
        lines.extend(["", "### Families"])
        for family_key, family_bundle in families.items():
            lines.extend(_format_family_report_sections(family_key, family_bundle))

    lines.extend(
        [
            "",
            "### Status",
            _rank_depth_status_text(bundle),
            "",
        ]
    )
    return lines


def _rank_depth_status_text(bundle: dict[str, object]) -> str:
    if bundle["hard_fail"]:
        return "Confirmatory inference skipped because hard-fail guardrails did not pass."
    inference_mode = str(bundle.get("inference_mode", "confirmatory"))
    keyword_count = bundle.get("keyword_count", 0)
    if inference_mode == "confirmatory":
        return "Guardrails passed; confirmatory inference may proceed."
    if inference_mode == "underpowered":
        return f"Exploratory inference only: keyword_count={keyword_count}."
    if inference_mode == "exploratory":
        return f"Exploratory inference only: keyword_count={keyword_count} (< 10)."
    return f"Inference mode: {inference_mode}."


def _format_family_report_sections(
    family_key: str,
    family_bundle: dict[str, object],
) -> list[str]:
    lines = [
        f"#### Family: {family_key}",
        "",
    ]
    lines.extend(_format_family_section_lines("Spearman", family_bundle.get("spearman"), _format_spearman_lines))
    lines.extend(
        _format_family_section_lines(
            "Regression",
            family_bundle.get("regression"),
            _format_regression_lines,
        )
    )
    lines.extend(
        _format_family_section_lines(
            "Diagnostics",
            family_bundle.get("diagnostics"),
            _format_diagnostics_lines,
        )
    )
    lines.extend(
        _format_family_section_lines(
            "Plackett-Luce",
            family_bundle.get("plackett_luce"),
            lambda section: _format_plackett_luce_lines(section, None),
        )
    )
    lines.append("")
    return lines


def _format_family_section_lines(
    section_name: str,
    section: dict[str, object] | None,
    formatter,
) -> list[str]:
    lines = [f"##### {section_name}"]
    if not isinstance(section, dict) or not section.get("backends"):
        skipped_reason = (
            section.get("skipped_reason", "no_usable_rows")
            if isinstance(section, dict)
            else "no_usable_rows"
        )
        lines.append("")
        lines.append(f"- status=skipped, skipped_reason={skipped_reason}")
        return lines
    lines.append("")
    lines.extend(formatter(section))
    return lines


def _format_spearman_lines(spearman: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for backend, backend_summary in spearman["backends"].items():
        backend_summary = dict(backend_summary)
        keyword_count = int(backend_summary.get("keyword_count", 0))
        line = (
            f"- {backend}: keyword_count={backend_summary['keyword_count']}, "
            f"median_rho={backend_summary['median_rho']}, "
            f"rho_iqr={backend_summary['rho_iqr']}, "
            f"fraction_same_sign={backend_summary['fraction_same_sign']}, "
            f"inference_mode={backend_summary.get('inference_mode', _inference_mode_for_keyword_count(keyword_count))}"
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
        keyword_count = int(backend_summary.get("keyword_count", 0))
        inference_mode = backend_summary.get(
            "inference_mode",
            _inference_mode_for_keyword_count(keyword_count),
        )
        feature_model = backend_summary["feature_model"]
        effect_size = backend_summary["effect_size"]
        two_way_cluster = backend_summary["sensitivity"]["two_way_cluster"]
        lines.append(
            "- "
            f"{backend}: keyword_count={backend_summary['keyword_count']}, "
            f"inference_mode={inference_mode}, "
            f"coefficient={feature_model['coefficient']}, "
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
                f"skipped_reason={backend_summary['skipped_reason']}, "
                f"keyword_count={backend_summary.get('keyword_count', 0)}, "
                f"inference_mode={backend_summary.get('inference_mode', 'skipped')}"
            )
            continue
        keyword_count = int(backend_summary.get("keyword_count", 0))
        inference_mode = backend_summary.get(
            "inference_mode",
            _inference_mode_for_keyword_count(keyword_count),
        )
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
            f"keyword_count={backend_summary.get('keyword_count', 0)}, "
            f"inference_mode={inference_mode}, "
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
                f"skipped_reason={backend_summary['skipped_reason']}, "
                f"keyword_count={backend_summary.get('keyword_count', 0)}, "
                f"inference_mode={backend_summary.get('inference_mode', 'skipped')}"
            )
            continue
        keyword_count = int(backend_summary.get("keyword_count", 0))
        inference_mode = backend_summary.get(
            "inference_mode",
            _inference_mode_for_keyword_count(keyword_count),
        )
        reset = backend_summary["reset"]
        breusch_pagan = backend_summary["breusch_pagan"]
        influence = backend_summary["influence"]
        if reset.get("status") == "skipped":
            reset_details = (
                f"reset_status=skipped, "
                f"reset_skipped_reason={reset.get('skipped_reason', 'unknown')}"
            )
        else:
            reset_details = (
                f"reset_status={reset['status']}, "
                f"reset_p_value={reset['p_value']}, "
                f"reset_flagged={reset['flagged']}"
            )
        line = (
            "- "
            f"{backend}: {reset_details}, "
            f"keyword_count={backend_summary.get('keyword_count', 0)}, "
            f"inference_mode={inference_mode}, "
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


def _format_influence_sensitivity_lines(diagnostics: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for backend, backend_summary in diagnostics["backends"].items():
        backend_summary = dict(backend_summary)
        influence_sensitivity = backend_summary.get("influence_sensitivity")
        if not isinstance(influence_sensitivity, dict):
            lines.append(f"- {backend}: status=skipped, skipped_reason=no_influence_sensitivity")
            continue
        if influence_sensitivity.get("status") == "skipped":
            lines.append(
                "- "
                f"{backend}: status=skipped, "
                f"skipped_reason={influence_sensitivity['skipped_reason']}, "
                f"row_count={influence_sensitivity.get('row_count', 0)}, "
                f"influential_row_count={influence_sensitivity.get('influential_row_count', 0)}, "
                f"influential_row_rate={influence_sensitivity.get('influential_row_rate', 0.0)}"
            )
            continue
        lines.append(
            "- "
            f"{backend}: status={influence_sensitivity['status']}, "
            f"row_count={influence_sensitivity['row_count']}, "
            f"trimmed_row_count={influence_sensitivity['trimmed_row_count']}, "
            f"influential_row_count={influence_sensitivity['influential_row_count']}, "
            f"influential_row_rate={influence_sensitivity['influential_row_rate']}, "
            f"confirmatory_coefficient={influence_sensitivity['confirmatory_coefficient']}, "
            f"sensitivity_coefficient={influence_sensitivity['sensitivity_coefficient']}, "
            f"coefficient_delta={influence_sensitivity['coefficient_delta']}, "
            f"sensitivity_ci={influence_sensitivity['sensitivity_confidence_interval']}"
        )
    return lines


def _format_multivariate_sensitivity_lines(sensitivity: dict[str, object]) -> list[str]:
    lines: list[str] = []
    drop_path = " -> ".join(sensitivity.get("drop_path", [])) or "none"
    kept_backends = ", ".join(sensitivity.get("kept_backends", [])) or "none"
    max_vif = sensitivity.get("max_vif", "n/a")
    max_vif_term = sensitivity.get("max_vif_term", "n/a")
    line = (
        f"- status={sensitivity['status']}, "
        f"kept_backends={kept_backends}, "
        f"max_vif={max_vif}, "
        f"max_vif_term={max_vif_term}, "
        f"vif_threshold={sensitivity.get('vif_threshold', 'n/a')}, "
        f"drop_path={drop_path}"
    )
    unresolved_reason = sensitivity.get("unresolved_reason")
    if unresolved_reason is not None:
        line += f", unresolved_reason={unresolved_reason}"
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
            "keyword_count",
            "inference_mode",
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
    if bundle.get("families") is not None:
        public["families"] = bundle["families"]
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


def _append_influential_rows_guardrail(
    bundle: dict[str, object],
    *,
    spec: AnalysisSpec,
    regression_diagnostics: dict[str, object],
) -> None:
    guardrail_threshold = _warn_guardrail_threshold(spec, "influential_rows_rate")
    backend_summary = regression_diagnostics.get("backends", {}).get(spec.primary_backend)
    if not isinstance(backend_summary, dict):
        return
    influence = backend_summary.get("influence")
    if not isinstance(influence, dict):
        return

    row_count = int(influence.get("row_count", 0))
    cook_d_count = int(influence.get("cook_d_count", 0))
    if row_count <= 0:
        return

    value = float(cook_d_count / row_count)
    guardrail = {
        "name": "influential_rows_rate",
        "status": "warn" if value > guardrail_threshold else "pass",
        "value": value,
        "threshold": guardrail_threshold,
    }
    guardrails = [
        guardrail_item
        for guardrail_item in bundle.get("guardrails", [])
        if guardrail_item.get("name") != guardrail["name"]
    ]
    guardrails.append(guardrail)
    bundle["guardrails"] = guardrails


def _warn_guardrail_threshold(spec: AnalysisSpec, guardrail_name: str) -> float:
    for guardrail in spec.data["guardrails"]["warn"]:
        if guardrail["name"] == guardrail_name:
            return float(guardrail["threshold"])
    raise KeyError(f"unknown warn guardrail {guardrail_name}")


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
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    if diagnostics_by_depth:
        diagnostics_summary = build_stats_diagnostics(
            result,
            rank_depth_bundles=rank_depth_bundles,
            diagnostics_by_depth=diagnostics_by_depth,
            spec=spec,
        )
        (stats_dir / "stats_diagnostics.json").write_text(
            json.dumps(diagnostics_summary, indent=2) + "\n",
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
