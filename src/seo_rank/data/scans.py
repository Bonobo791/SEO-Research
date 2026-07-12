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
    schema = frame.collect_schema()
    if "request_metadata_json" not in schema:
        frame = frame.with_columns(
            pl.lit(None).cast(pl.Utf8).alias("request_metadata_json")
        )
    if "timestamp" not in schema:
        frame = frame.with_columns(pl.lit(None).cast(pl.Utf8).alias("timestamp"))
    return frame


def scan_curated_table(run_dir: Path, table_name: str) -> pl.LazyFrame:
    """Scan a curated table from the run-scoped Parquet lake."""

    run_dir = Path(run_dir)
    dataset_dir = run_dir / "parquet" / table_name
    parts = sorted(dataset_dir.glob("part-*.parquet"))
    if not parts:
        raise FileNotFoundError(
            f"Stored run {run_dir} has no parquet parts for {table_name} "
            f"(expected {dataset_dir}/part-*.parquet)"
        )
    return pl.scan_parquet(str(dataset_dir))
