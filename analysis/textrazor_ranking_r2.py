from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SRC = REPO_ROOT / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from seo_rank.stats.spec import load_analysis_spec
from seo_rank.stats.textrazor_explainability import (
    load_similarity_explainability_panel,
    load_textrazor_explainability_panel,
    summarize_ranking_explainability,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure how much similarity backends and TextRazor page metrics "
            "explain SERP rank using pooled OLS adjusted R²."
        )
    )
    parser.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Path to a run directory (e.g. runs/RUN_ID)",
    )
    parser.add_argument(
        "--depth",
        default=None,
        choices=["top_20", "top_10", "top_5", "top_3"],
        help="Rank depth filter (default: analysis spec primary depth)",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Skip the interactive plot window (still writes PNG when matplotlib is available)",
    )
    return parser.parse_args()


def _require_run_artifacts(run_dir: Path) -> None:
    analysis_mart = run_dir / "parquet" / "analysis_mart"
    textrazor_metrics = run_dir / "parquet" / "textrazor_page_metrics"
    missing: list[str] = []
    if not analysis_mart.exists():
        missing.append("parquet/analysis_mart")
    if not textrazor_metrics.exists():
        missing.append("parquet/textrazor_page_metrics")
    if missing:
        missing_list = ", ".join(missing)
        raise SystemExit(
            f"Missing required artifacts under {run_dir}: {missing_list}.\n"
            "Run: seo-rank normalize && seo-rank build-features && seo-rank analyze"
        )


def _format_float(value: object, *, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def _format_p_value(value: object) -> str:
    if value is None:
        return "n/a"
    p_value = float(value)
    if p_value < 0.0001:
        return "<0.0001"
    return f"{p_value:.4f}"


def _render_univariate_table(summary: dict[str, object]) -> str:
    header = (
        f"{'metric':<28} {'n':>6} {'baseline R²':>12} "
        f"{'feature R²':>12} {'Δ R²':>10} {'coef':>10} {'p-value':>10}"
    )
    lines = [header, "-" * len(header)]
    univariate = summary.get("univariate", [])
    if not isinstance(univariate, list):
        return "\n".join(lines)

    for entry in univariate:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label", ""))
        row_count = entry.get("row_count", 0)
        if entry.get("status") != "computed":
            lines.append(
                f"{label:<28} {int(row_count):>6} {'skipped':>12} "
                f"{str(entry.get('skipped_reason', '')):>12}"
            )
            continue
        baseline = entry.get("baseline_model") or {}
        feature = entry.get("feature_model") or {}
        delta = entry.get("descriptive_fit_delta") or {}
        if not isinstance(baseline, dict) or not isinstance(feature, dict):
            continue
        if not isinstance(delta, dict):
            delta = {}
        lines.append(
            f"{label:<28} {int(row_count):>6} "
            f"{_format_float(baseline.get('adjusted_r_squared')):>12} "
            f"{_format_float(feature.get('adjusted_r_squared')):>12} "
            f"{_format_float(delta.get('adjusted_r_squared')):>10} "
            f"{_format_float(feature.get('coefficient')):>10} "
            f"{_format_p_value(feature.get('p_value')):>10}"
        )
    return "\n".join(lines)


def _render_multivariate_section(multivariate: object, *, title: str) -> str:
    if not isinstance(multivariate, dict):
        return f"{title}: unavailable"

    if multivariate.get("status") != "computed":
        reason = multivariate.get("skipped_reason", "unknown")
        row_count = multivariate.get("row_count", 0)
        return f"{title}: skipped ({reason}, n={row_count})"

    baseline = multivariate.get("baseline_model") or {}
    feature = multivariate.get("feature_model") or {}
    delta = multivariate.get("descriptive_fit_delta") or {}
    if not isinstance(baseline, dict) or not isinstance(feature, dict):
        return f"{title}: unavailable"
    if not isinstance(delta, dict):
        delta = {}

    lines = [
        "",
        title,
        "-" * len(title),
        f"rows: {multivariate.get('row_count', 0)}",
        f"keywords: {multivariate.get('keyword_count', 0)}",
        f"baseline adjusted R²: {_format_float(baseline.get('adjusted_r_squared'))}",
        f"feature adjusted R²: {_format_float(feature.get('adjusted_r_squared'))}",
        f"Δ adjusted R²: {_format_float(delta.get('adjusted_r_squared'))}",
    ]

    coefficients = feature.get("coefficients")
    p_values = feature.get("p_values")
    if isinstance(coefficients, dict) and isinstance(p_values, dict):
        lines.append("coefficients:")
        for column, coefficient in coefficients.items():
            p_value = p_values.get(column)
            lines.append(
                f"  {column}: coef={_format_float(coefficient)}, p={_format_p_value(p_value)}"
            )
    return "\n".join(lines)


def _render_metric_group(
    summary: dict[str, object],
    *,
    section_title: str,
    combined_title: str,
) -> str:
    panel = summary.get("panel")
    panel_rows = 0
    panel_keywords = 0
    if isinstance(panel, dict):
        panel_rows = int(panel.get("rows", 0))
        panel_keywords = int(panel.get("keywords", 0))

    lines = [
        section_title,
        "-" * len(section_title),
        f"panel rows: {panel_rows}  keywords: {panel_keywords}",
        "",
        _render_univariate_table(summary),
        _render_multivariate_section(summary.get("multivariate"), title=combined_title),
    ]
    return "\n".join(lines)


def _entity_relevance_univariate(summary: dict[str, object]) -> dict[str, object] | None:
    textrazor = summary.get("textrazor")
    if not isinstance(textrazor, dict):
        return None
    univariate = textrazor.get("univariate")
    if not isinstance(univariate, list):
        return None
    for entry in univariate:
        if isinstance(entry, dict) and entry.get("label") == "entity_relevance":
            return entry
    return None


def _print_viz_result(viz_result: object, *, no_show: bool) -> None:
    if viz_result is None:
        return
    output_path = getattr(viz_result, "output_path", None)
    display_message = getattr(viz_result, "display_message", None)
    if output_path is not None and no_show:
        print(f"Wrote {output_path}")
    elif display_message is not None:
        print(display_message)
    elif output_path is not None:
        print(f"Wrote {output_path}")


def main() -> None:
    args = _parse_args()
    run_dir = args.run.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")

    _require_run_artifacts(run_dir)
    try:
        from seo_rank.stats.ranking_explainability_viz import (
            write_curated_model_visualization,
            write_entity_relevance_visualization,
        )
    except ModuleNotFoundError as error:
        if error.name != "matplotlib":
            raise
        write_curated_model_visualization = None
        write_entity_relevance_visualization = None
    spec = load_analysis_spec()
    similarity_panel, rank_depth, limitations, _ = load_similarity_explainability_panel(
        run_dir,
        rank_depth=args.depth,
        spec=spec,
    )
    textrazor_panel, _, _, _ = load_textrazor_explainability_panel(
        run_dir,
        rank_depth=args.depth,
        spec=spec,
    )
    summary = summarize_ranking_explainability(
        similarity_panel,
        textrazor_panel,
        run_id=run_dir.name,
        rank_depth=rank_depth,
        spec=spec,
        limitations=limitations,
    )

    print(f"Ranking explainability — {run_dir.name} ({rank_depth})")
    print(f"outcome: {summary['estimand']['outcome']}")
    print(f"baseline: {summary['estimand']['baseline_formula']}")
    print()
    print(
        _render_metric_group(
            summary["similarity"],
            section_title="Similarity backends",
            combined_title="Combined model (all similarity backends)",
        )
    )
    print()
    print(
        _render_metric_group(
            summary["textrazor"],
            section_title="TextRazor page metrics",
            combined_title="Combined model (TextRazor metrics only)",
        )
    )
    print(
        _render_multivariate_section(
            summary["multivariate"],
            title="Combined model (similarity + TextRazor metrics)",
        )
    )
    print(
        _render_multivariate_section(
            summary["multivariate_curated"],
            title=(
                "Combined model (relation, property, entity relevance, "
                "Gemini semantic similarity)"
            ),
        )
    )

    stats_dir = run_dir / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    output_path = stats_dir / "ranking_r2.json"
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print()
    print(f"Wrote {output_path}")

    viz_path = stats_dir / "ranking_r2_curated_model.png"
    if write_curated_model_visualization is None:
        print("Skipped curated model visualization (matplotlib unavailable)")
    else:
        viz_result = write_curated_model_visualization(
            textrazor_panel,
            summary["multivariate_curated"],
            output_path=viz_path,
            run_id=run_dir.name,
            rank_depth=rank_depth,
            show=not args.no_show,
        )
        if viz_result is None:
            print("Skipped curated model visualization (model not computed)")
        else:
            _print_viz_result(viz_result, no_show=args.no_show)

    entity_relevance_summary = _entity_relevance_univariate(summary)
    entity_relevance_path = stats_dir / "ranking_r2_entity_relevance.png"
    if write_entity_relevance_visualization is None:
        print("Skipped entity relevance visualization (matplotlib unavailable)")
    elif entity_relevance_summary is None:
        print("Skipped entity relevance visualization (summary unavailable)")
    else:
        entity_viz_result = write_entity_relevance_visualization(
            textrazor_panel,
            entity_relevance_summary,
            output_path=entity_relevance_path,
            run_id=run_dir.name,
            rank_depth=rank_depth,
            show=not args.no_show,
        )
        if entity_viz_result is None:
            print("Skipped entity relevance visualization (model not computed)")
        else:
            _print_viz_result(entity_viz_result, no_show=args.no_show)


if __name__ == "__main__":
    main()
