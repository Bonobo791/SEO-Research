#!/usr/bin/env python3
"""Exploratory signal factor vs proxy dossier CLI (Phase 5.6)."""

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

from seo_rank.stats.signal_dossier import (  # noqa: E402
    CHAR_DENSITY_COLUMN,
    build_signal_factor_report,
    load_dossier_panel,
)

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an exploratory signal factor vs proxy dossier for TextRazor "
            "candidates (including entity density) on a stored run."
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
        "--ndcg-k",
        type=int,
        default=10,
        help="NDCG cutoff k (default: 10)",
    )
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="Enable seeded keyword holdout validation",
    )
    parser.add_argument(
        "--holdout-fraction",
        type=float,
        default=0.2,
        help="Holdout fraction when --holdout is set (default: 0.2)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for holdout split (default: 0)",
    )
    parser.add_argument(
        "--compare-run",
        type=Path,
        default=None,
        help="Optional second run directory for time-split overlap comparison",
    )
    return parser.parse_args()


def _render_density_section(report: dict) -> str:
    density = report.get("density", {})
    columns = density.get("columns", [])
    ndcg = report.get("ndcg", {}).get("signals", {})
    lines = [
        "Density metrics",
        "-" * 16,
    ]
    for column in columns:
        entry = ndcg.get(column, {})
        mean = entry.get("macro_mean")
        mean_text = f"{mean:.4f}" if isinstance(mean, float) else "n/a"
        lines.append(f"  {column}: ndcg_macro_mean={mean_text}")
    notes = density.get("notes", {})
    if isinstance(notes, dict) and "word_vs_char_denominator" in notes:
        lines.append("")
        lines.append(f"note: {notes['word_vs_char_denominator']}")
    if CHAR_DENSITY_COLUMN in columns:
        lines.append(f"derived: {CHAR_DENSITY_COLUMN} at panel load (not persisted)")
    return "\n".join(lines)


def _render_candidate_table(report: dict) -> str:
    ladder = report.get("incremental_ols", {}).get("candidates", {})
    lines = [
        "Incremental OLS (Δ adj R² at +candidate after BGE)",
        "-" * 50,
    ]
    for column, payload in ladder.items():
        rungs = payload.get("rungs", {})
        plus = rungs.get("plus_candidate", {})
        delta = plus.get("delta_adj_r2_vs_previous")
        delta_text = f"{delta:+.4f}" if isinstance(delta, float) else "n/a"
        expectation = payload.get("proxy_expectation", "n/a")
        lines.append(f"  {column}: delta={delta_text}  expectation={expectation}")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[seo-rank] %(message)s")
    args = _parse_args()
    run_dir = args.run.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")

    panel, rank_depth, limitations, spec = load_dossier_panel(
        run_dir,
        rank_depth=args.depth,
    )
    compare_panel = None
    if args.compare_run is not None:
        compare_dir = args.compare_run.resolve()
        if not compare_dir.is_dir():
            raise SystemExit(f"Compare run directory not found: {compare_dir}")
        compare_panel, _, _, _ = load_dossier_panel(
            compare_dir,
            rank_depth=rank_depth,
            spec=spec,
        )

    report = build_signal_factor_report(
        panel,
        run_id=run_dir.name,
        rank_depth=rank_depth,
        limitations=limitations,
        spec=spec,
        ndcg_k=args.ndcg_k,
        holdout_fraction=args.holdout_fraction if args.holdout else None,
        holdout_seed=args.seed,
        compare_panel=compare_panel,
    )

    stats_dir = run_dir / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    output_path = stats_dir / "signal_factor_report.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    logger.info("wrote %s", output_path)

    print(f"Signal factor dossier — {run_dir.name} ({rank_depth})")
    print(f"status: {report['status']}  keywords: {report['keyword_count']}  rows: {report['row_count']}")
    print()
    print(_render_density_section(report))
    print()
    print(_render_candidate_table(report))
    if "holdout" in report:
        holdout = report["holdout"]
        print()
        print(
            "Holdout: "
            f"train_k={len(holdout.get('train_keywords', []))} "
            f"holdout_k={len(holdout.get('holdout_keywords', []))} "
            f"seed={holdout.get('seed')}"
        )
    if "time_split" in report:
        time_split = report["time_split"]
        print()
        print(f"Time-split: status={time_split.get('status')} reason={time_split.get('skip_reason', 'n/a')}")
    print()
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
