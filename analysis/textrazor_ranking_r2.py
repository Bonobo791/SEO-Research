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
    load_textrazor_explainability_panel,
    summarize_textrazor_ranking_explainability,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure how much TextRazor page metrics explain SERP rank "
            "using pooled OLS adjusted R²."
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
        f"{'metric':<20} {'n':>6} {'baseline R²':>12} "
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
                f"{label:<20} {int(row_count):>6} {'skipped':>12} "
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
            f"{label:<20} {int(row_count):>6} "
            f"{_format_float(baseline.get('adjusted_r_squared')):>12} "
            f"{_format_float(feature.get('adjusted_r_squared')):>12} "
            f"{_format_float(delta.get('adjusted_r_squared')):>10} "
            f"{_format_float(feature.get('coefficient')):>10} "
            f"{_format_p_value(feature.get('p_value')):>10}"
        )
    return "\n".join(lines)


def _render_multivariate_section(summary: dict[str, object]) -> str:
    multivariate = summary.get("multivariate")
    if not isinstance(multivariate, dict):
        return "Combined model: unavailable"

    if multivariate.get("status") != "computed":
        reason = multivariate.get("skipped_reason", "unknown")
        row_count = multivariate.get("row_count", 0)
        return f"Combined model: skipped ({reason}, n={row_count})"

    baseline = multivariate.get("baseline_model") or {}
    feature = multivariate.get("feature_model") or {}
    delta = multivariate.get("descriptive_fit_delta") or {}
    if not isinstance(baseline, dict) or not isinstance(feature, dict):
        return "Combined model: unavailable"
    if not isinstance(delta, dict):
        delta = {}

    lines = [
        "",
        "Combined model (all five metrics)",
        "-" * 40,
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


def main() -> None:
    args = _parse_args()
    run_dir = args.run.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")

    _require_run_artifacts(run_dir)
    spec = load_analysis_spec()
    panel, rank_depth, limitations, _ = load_textrazor_explainability_panel(
        run_dir,
        rank_depth=args.depth,
        spec=spec,
    )
    summary = summarize_textrazor_ranking_explainability(
        panel,
        run_id=run_dir.name,
        rank_depth=rank_depth,
        spec=spec,
        limitations=limitations,
    )

    print(f"TextRazor ranking explainability — {run_dir.name} ({rank_depth})")
    print(f"outcome: {summary['estimand']['outcome']}")
    print(f"baseline: {summary['estimand']['baseline_formula']}")
    print(f"panel rows: {summary['panel']['rows']}  keywords: {summary['panel']['keywords']}")
    print()
    print(_render_univariate_table(summary))
    print(_render_multivariate_section(summary))

    stats_dir = run_dir / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    output_path = stats_dir / "textrazor_ranking_r2.json"
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print()
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
