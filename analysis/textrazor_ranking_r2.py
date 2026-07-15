from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SRC = REPO_ROOT / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from seo_rank.stats.spec import load_analysis_spec
from seo_rank.stats.textrazor_explainability import (
    load_ranking_importance_panel,
    load_similarity_explainability_panel,
    load_textrazor_explainability_panel,
    summarize_ranking_explainability,
    summarize_ranking_relative_importance,
)

logger = logging.getLogger(__name__)

FAST_RESAMPLING_DEFAULTS = {
    "cv_folds": 3,
    "cv_repeats": 2,
    "bootstraps": 100,
    "shapley_permutations": 200,
    "domain_cv_repeats": 2,
}
EXHAUSTIVE_RESAMPLING_DEFAULTS = {
    "cv_folds": 5,
    "cv_repeats": 5,
    "bootstraps": 500,
    "shapley_permutations": 2000,
    "domain_cv_repeats": 10,
}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {parsed}")
    return parsed


def _cv_folds(value: str) -> int:
    parsed = int(value)
    if parsed < 2:
        raise argparse.ArgumentTypeError(f"must be >= 2, got {parsed}")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure how much similarity backends and TextRazor page metrics "
            "explain SERP rank using fixed-effects OLS, Ridge cross-validation, "
            "and domain-held-out portability."
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
    parser.add_argument(
        "--exhaustive",
        action="store_true",
        help="Use the legacy exhaustive resampling defaults; explicit values still override",
    )
    parser.add_argument(
        "--cv-folds",
        type=_cv_folds,
        default=None,
        help="Keyword-grouped CV folds for out-of-sample delta R² (fast: 3, exhaustive: 5)",
    )
    parser.add_argument(
        "--cv-repeats",
        type=_positive_int,
        default=None,
        help="Repeated keyword GroupKFold repeats for OOF R² (fast: 2, exhaustive: 5)",
    )
    parser.add_argument(
        "--bootstraps",
        type=_positive_int,
        default=None,
        help="Keyword-bootstrap draws for OOS delta R² CIs (fast: 100, exhaustive: 500)",
    )
    parser.add_argument(
        "--shapley-permutations",
        type=_positive_int,
        default=None,
        help="Permutation-Shapley draws (fast: 200, exhaustive: 2000)",
    )
    parser.add_argument(
        "--domain-cv-repeats",
        type=_positive_int,
        default=None,
        help="Domain-held-out CV repeats (fast: 2, exhaustive: 10)",
    )
    args = parser.parse_args()
    defaults = (
        EXHAUSTIVE_RESAMPLING_DEFAULTS
        if args.exhaustive
        else FAST_RESAMPLING_DEFAULTS
    )
    for name, value in defaults.items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    return args


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




def _format_ci(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    lower = value.get("lower")
    upper = value.get("upper")
    if lower is None or upper is None:
        return "n/a"
    return f"[{_format_float(lower)}, {_format_float(upper)}]"


def _render_relative_importance_table(relative_importance: object) -> str:
    if not isinstance(relative_importance, dict):
        return "Relative importance: unavailable"

    if relative_importance.get("status") != "computed":
        reason = relative_importance.get("skipped_reason", "unknown")
        row_count = relative_importance.get("row_count", 0)
        return f"Relative importance: skipped ({reason}, n={row_count})"

    groups = relative_importance.get("groups", [])
    if not isinstance(groups, list):
        groups = []

    lines = [
        "",
        "A. Within-keyword fixed-effects explanation",
        "Within-keyword fixed-effects OLS — descriptive, in-sample",
        "-" * 64,
        f"rows: {relative_importance.get('row_count', 0)}  "
        f"keywords: {relative_importance.get('keyword_count', 0)}  "
        f"Shapley: permutation ({relative_importance.get('shapley_permutations', 'n/a')})",
        f"Shapley raw ΔR² MCSE: "
        f"{relative_importance.get('shapley_raw_delta_r2_mcse', relative_importance.get('shapley_mcse', 'n/a'))}",
        f"Shapley raw ΔR² first-vs-second-half difference: "
        f"{relative_importance.get('shapley_raw_delta_r2_convergence_difference', relative_importance.get('shapley_convergence_difference', 'n/a'))}",
        "",
        f"{'Group':<24} {'Predictors':>10} {'Rows':>8} "
        f"{'Keywords':>9} {'Partial R²':>11} {'Shapley':>9}",
        "-" * 78,
    ]
    for group in groups:
        if not isinstance(group, dict):
            continue
        partial = group.get("full_model_partial_r2")
        shapley = group.get("shapley_share")
        lines.append(
            f"{str(group.get('factor', '')):<24} "
            f"{int(group.get('in_sample_predictor_count', 0)):>10} "
            f"{str(group.get('in_sample_rows', 'n/a')):>8} "
            f"{str(group.get('in_sample_keywords', 'n/a')):>9} "
            f"{_format_float(partial) if partial is not None else 'n/a — not included':>11} "
            f"{_format_float(shapley) if shapley is not None else 'n/a':>9}"
        )
        columns = group.get("in_sample_predictor_columns", [])
        if columns:
            lines.append("  predictors: " + ", ".join(columns))

    lines.extend([
        "",
        "B. Keyword-held-out predictive importance",
        "Repeated keyword-grouped CV — predictive importance",
        "-" * 64,
        f"{'Group':<24} {'Full R²':>9} {'Without':>9} {'ΔR²':>9} "
        f"{'ΔR² CI':>21} {'ΔNDCG':>9} {'ΔNDCG CI':>21} {'R² status':>18} {'NDCG status':>18}",
        "-" * 150,
    ])
    for group in groups:
        if not isinstance(group, dict):
            continue
        lines.append(
            f"{str(group.get('factor', '')):<24} "
            f"{_format_float(group.get('out_of_sample_full_r2')):>9} "
            f"{_format_float(group.get('out_of_sample_reduced_r2')):>9} "
            f"{_format_float(group.get('out_of_sample_delta_r2')):>9} "
            f"{_format_ci(group.get('out_of_sample_delta_r2_ci')):>21} "
            f"{_format_float(group.get('out_of_sample_ndcg_delta')):>9} "
            f"{_format_ci(group.get('out_of_sample_ndcg_delta_ci')):>21} "
            f"{str(group.get('evidence_status', 'n/a')):>18} "
            f"{str(group.get('ndcg_evidence_status', 'n/a')):>18}"
        )
        lines.append(
            f"  repeat ΔR² mean/sd/range: "
            f"{_format_float(group.get('repeat_mean_delta_r2'))} / "
            f"{_format_float(group.get('repeat_sd_delta_r2'))} / "
            f"[{_format_float(group.get('repeat_min_delta_r2'))}, "
            f"{_format_float(group.get('repeat_max_delta_r2'))}]"
        )
        lines.append(
            f"  repeat ΔNDCG mean/sd/range: "
            f"{_format_float(group.get('repeat_mean_ndcg_delta'))} / "
            f"{_format_float(group.get('repeat_sd_ndcg_delta'))} / "
            f"[{_format_float(group.get('repeat_min_ndcg_delta'))}, "
            f"{_format_float(group.get('repeat_max_ndcg_delta'))}]"
        )
        columns = group.get("oos_predictor_columns", [])
        lines.append(
            f"  predictors ({group.get('oos_predictor_count', 0)}): "
            + ", ".join(columns)
        )
        for signal in group.get("metrics", []):
            if not isinstance(signal, dict):
                continue
            lines.append(
                f"  signal {signal.get('column', 'n/a')}: "
                f"partial R²={_format_float(signal.get('full_model_partial_r2'))}; "
                f"Shapley={_format_float(signal.get('shapley_share'))}; "
                f"ΔR²={_format_float(signal.get('out_of_sample_delta_r2'))} "
                f"{_format_ci(signal.get('out_of_sample_delta_r2_ci'))}; "
                f"ΔNDCG={_format_float(signal.get('out_of_sample_ndcg_delta'))} "
                f"{_format_ci(signal.get('out_of_sample_ndcg_delta_ci'))}; "
                f"domain ΔR²={_format_float(signal.get('domain_holdout_delta_r2'))}; "
                f"status={signal.get('evidence_status', 'n/a')}"
            )

    lines.extend([
        "",
        "C. Domain-held-out portability",
        "Domain-held-out CV — transfer to unseen websites",
        "-" * 64,
        f"{'Group':<24} {'ΔR²':>9} {'CI':>21}",
        "-" * 58,
    ])
    for group in groups:
        if not isinstance(group, dict):
            continue
        lines.append(
            f"{str(group.get('factor', '')):<24} "
            f"{_format_float(group.get('domain_holdout_delta_r2')):>9} "
            f"{_format_ci(group.get('domain_holdout_delta_r2_ci')):>21}"
        )
        lines.append(
            f"  overall domain rows/count: {group.get('domain_rows', 'n/a')} / "
            f"{group.get('domain_count', 'n/a')}"
        )
        lines.append(
            f"  paired domain rows/count: {group.get('domain_paired_rows', 'n/a')} / "
            f"{group.get('domain_paired_count', 'n/a')}"
        )
        lines.append(
            f"  domains/fold: {group.get('domains_per_fold', 'n/a')}  "
            f"extraction failures: {group.get('domain_rows_with_extraction_failure', 'n/a')}"
        )
        lines.append(
            "  repeat domain ΔR²: "
            + ", ".join(_format_float(value) for value in group.get("domain_repeat_deltas", []))
        )

    lines.extend([
        "",
        "D. Standalone family models",
        "Family-level univariate and curated model results remain above.",
        "",
        "E. Predictor coverage and exclusions",
        f"in-sample predictors: {', '.join(relative_importance.get('predictor_columns', []))}",
        "fold inclusion rates: "
        + ", ".join(
            f"{column}={_format_float(rate)}"
            for column, rate in relative_importance.get(
                "predictor_fold_inclusion_rates", {}
            ).items()
        ),
        f"excluded predictors: {len(relative_importance.get('excluded_predictors', []))}",
        "",
        "F. Warnings and interpretation",
    ])
    for excluded in relative_importance.get("excluded_predictors", []):
        if isinstance(excluded, dict):
            lines.append(
                f"excluded: {excluded.get('column', 'n/a')} "
                f"({excluded.get('reason', 'unknown')})"
            )
    for warning in relative_importance.get("warnings", []):
        lines.append(f"WARNING: {warning}")
    note = relative_importance.get("oos_note")
    if isinstance(note, str) and note:
        lines.append(note)
    return "\n".join(lines)


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
    logging.basicConfig(level=logging.INFO, format="[seo-rank] %(message)s")
    args = _parse_args()
    logger.info(
        "Relative importance budget folds=%d repeats=%d bootstraps=%d "
        "shapley_permutations=%d domain_repeats=%d exhaustive=%s",
        args.cv_folds,
        args.cv_repeats,
        args.bootstraps,
        args.shapley_permutations,
        args.domain_cv_repeats,
        args.exhaustive,
    )
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
    importance_panel, _, _, _ = load_ranking_importance_panel(
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
    relative_importance = summarize_ranking_relative_importance(
        importance_panel,
        spec=spec,
        cv_folds=args.cv_folds,
        cv_repeats=args.cv_repeats,
        bootstraps=args.bootstraps,
        shapley_permutations=args.shapley_permutations,
        domain_cv_repeats=args.domain_cv_repeats,
    )
    summary["relative_importance"] = relative_importance

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
    print(_render_relative_importance_table(summary.get("relative_importance")))

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
