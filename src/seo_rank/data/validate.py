"""Validation helpers for lazy data-layer frames."""

from collections.abc import Iterable, Mapping

import polars as pl


def validate_frame_contract(
    frame: pl.LazyFrame,
    *,
    required_columns: Iterable[str],
    expected_schema: Mapping[str, pl.DataType] | None = None,
    unique_columns: Iterable[str] = (),
    non_null_columns: Iterable[str] = (),
    bounded_columns: Mapping[str, tuple[float | int | None, float | int | None]] | None = None,
) -> pl.LazyFrame:
    """Ensure a lazy frame satisfies the contract expected by a sink."""

    schema = frame.collect_schema()
    required = tuple(required_columns)
    missing = sorted(column for column in required if column not in schema)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    if expected_schema:
        mismatched = []
        for column, expected_dtype in expected_schema.items():
            if column not in schema:
                mismatched.append(f"{column} missing")
                continue
            if schema[column] != expected_dtype:
                mismatched.append(
                    f"{column} expected {expected_dtype}, found {schema[column]}"
                )
        if mismatched:
            raise ValueError("Schema mismatch: " + "; ".join(mismatched))

    unique_columns = tuple(unique_columns)
    non_null_columns = tuple(non_null_columns)
    bounded_columns = dict(bounded_columns or {})
    check_columns = sorted(
        set(unique_columns) | set(non_null_columns) | set(bounded_columns)
    )
    if check_columns:
        selected = frame.select([pl.col(column) for column in check_columns]).collect()

        if unique_columns:
            duplicated = selected.select(list(unique_columns)).unique().height != selected.height
            if duplicated:
                raise ValueError(
                    "Duplicate rows found for unique columns: "
                    + ", ".join(unique_columns)
                )

        for column in non_null_columns:
            if selected.get_column(column).null_count() > 0:
                raise ValueError("Null values found in required column: " + column)

        for column, (minimum, maximum) in bounded_columns.items():
            series = selected.get_column(column).drop_nulls()
            if series.is_empty():
                continue
            if minimum is not None and series.min() < minimum:
                raise ValueError(f"Column {column} is below minimum {minimum}")
            if maximum is not None and series.max() > maximum:
                raise ValueError(f"Column {column} is above maximum {maximum}")

    return frame


def validate_required_columns(
    frame: pl.LazyFrame,
    *,
    required_columns: Iterable[str],
) -> pl.LazyFrame:
    """Ensure a lazy frame contains the required columns before write."""

    return validate_frame_contract(frame, required_columns=required_columns)
