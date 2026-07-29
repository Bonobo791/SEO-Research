"""Lazy Parquet scan helpers for stored runs."""
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md


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
