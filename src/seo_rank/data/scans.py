"""Lazy Parquet scan helpers for stored runs."""

from pathlib import Path

import polars as pl


def scan_raw_responses(run_dir: Path) -> pl.LazyFrame:
    """Scan the authoritative raw response lake for a completed run."""

    return pl.scan_parquet(
        str(Path(run_dir) / "parquet" / "raw_responses"),
        hive_partitioning=True,
    )
