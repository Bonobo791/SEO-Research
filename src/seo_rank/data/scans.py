"""Lazy Parquet scan helpers for stored runs."""

from pathlib import Path

import polars as pl


def scan_raw_responses(run_dir: Path) -> pl.LazyFrame:
    """Scan the authoritative raw response lake for a completed run."""

    frame = pl.scan_parquet(
        str(Path(run_dir) / "parquet" / "raw_responses"),
        hive_partitioning=True,
        missing_columns="insert",
    )
    if "request_metadata_json" not in frame.collect_schema():
        frame = frame.with_columns(
            pl.lit(None).cast(pl.Utf8).alias("request_metadata_json")
        )
    return frame


def scan_curated_table(run_dir: Path, table_name: str) -> pl.LazyFrame:
    """Scan a curated table from the run-scoped Parquet lake."""

    return pl.scan_parquet(str(Path(run_dir) / "parquet" / table_name))
