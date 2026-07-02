"""Stats artifact helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from seo_rank.stats.spec import AnalysisSpec
from seo_rank.stats.panel import AnalysisPanelResult, load_analysis_panel
from seo_rank.stats.regression import summarize_regression_backends
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
    }
    if spearman is not None:
        summary["spearman"] = spearman
    if regression is not None:
        summary["regression"] = regression
    return summary


def build_stats_report(
    result: AnalysisPanelResult,
    *,
    spearman: dict[str, object] | None = None,
    regression: dict[str, object] | None = None,
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


def write_stats_artifacts(
    run_dir: Path,
    result: AnalysisPanelResult,
    *,
    spearman: dict[str, object] | None = None,
    regression: dict[str, object] | None = None,
) -> dict[str, object]:
    stats_dir = Path(run_dir) / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)

    summary = build_stats_summary(result, spearman=spearman, regression=regression)
    (stats_dir / "stats_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (stats_dir / "stats_report.md").write_text(
        build_stats_report(result, spearman=spearman, regression=regression),
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
    if not result.hard_fail:
        spearman = summarize_spearman_backends(result.analysis_mart, result.backend_order)
        regression = summarize_regression_backends(result.analysis_mart, result.backend_order)
    write_stats_artifacts(run_dir, result, spearman=spearman, regression=regression)
    return result
