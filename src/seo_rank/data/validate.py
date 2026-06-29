"""Validation helpers for lazy data-layer frames."""

from collections.abc import Iterable

import polars as pl


def validate_required_columns(
    frame: pl.LazyFrame,
    *,
    required_columns: Iterable[str],
) -> pl.LazyFrame:
    """Ensure a lazy frame contains the required columns before write."""

    schema = frame.collect_schema()
    missing = sorted(column for column in required_columns if column not in schema)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    return frame
