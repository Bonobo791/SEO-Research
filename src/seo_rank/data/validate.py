"""Validation helpers for lazy data-layer frames."""

from collections.abc import Iterable, Mapping

import polars as pl

SERP_DEPTH_BOUND_COLUMNS = frozenset(
    {
        "serp_rank",
        "best_serp_rank",
        "worst_serp_rank",
        "bge_rank",
        "gemini_doc_retrieval_rank",
        "gemini_semantic_similarity_rank",
    }
)


def with_serp_depth_bounds(
    bounded_columns: Mapping[str, tuple[float | int | None, float | int | None]] | None,
    *,
    depth: int,
) -> dict[str, tuple[float | int | None, float | int | None]]:
    """Set persisted SERP-derived rank bounds to a run's requested depth."""

    if depth < 1:
        raise ValueError("SERP depth must be greater than 0")
    return {
        column: (minimum, depth if column in SERP_DEPTH_BOUND_COLUMNS else maximum)
        for column, (minimum, maximum) in (bounded_columns or {}).items()
    }


def align_lazyframe_schema(
    frame: pl.LazyFrame,
    expected_schema: Mapping[str, pl.DataType],
) -> pl.LazyFrame:
    """Insert null-typed columns for keys present in expected_schema but absent from frame."""

    schema = frame.collect_schema()
    additions = [
        pl.lit(None).cast(dtype).alias(column)
        for column, dtype in expected_schema.items()
        if column not in schema
    ]
    if not additions:
        return frame
    return frame.with_columns(additions)


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

    return frame


def validate_materialized_frame_contract(
    frame: pl.DataFrame,
    *,
    unique_columns: Iterable[str] = (),
    non_null_columns: Iterable[str] = (),
    bounded_columns: Mapping[str, tuple[float | int | None, float | int | None]] | None = None,
) -> pl.DataFrame:
    """Ensure a materialized frame satisfies row-level contract rules."""

    unique_columns = tuple(unique_columns)
    non_null_columns = tuple(non_null_columns)
    bounded_columns = dict(bounded_columns or {})
    rows = frame.to_dicts()
    if unique_columns:
        duplicated = len(
            {tuple(row.get(column) for column in unique_columns) for row in rows}
        ) != len(rows)
        if duplicated:
            raise ValueError(
                "Duplicate rows found for unique columns: "
                + ", ".join(unique_columns)
            )

    for column in non_null_columns:
        if any(row.get(column) is None for row in rows):
            raise ValueError("Null values found in required column: " + column)

    for column, (minimum, maximum) in bounded_columns.items():
        values = [row.get(column) for row in rows if row.get(column) is not None]
        if not values:
            continue
        if minimum is not None and min(values) < minimum:
            raise ValueError(f"Column {column} is below minimum {minimum}")
        if maximum is not None and max(values) > maximum:
            raise ValueError(f"Column {column} is above maximum {maximum}")

    return frame


def validate_required_columns(
    frame: pl.LazyFrame,
    *,
    required_columns: Iterable[str],
) -> pl.LazyFrame:
    """Ensure a lazy frame contains the required columns before write."""

    return validate_frame_contract(frame, required_columns=required_columns)
