"""Validation shared by statistical model input preparation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
import polars as pl


REQUIRED_CONTROL_COLUMNS = ("site_scale", "authority_proxy")
CONTROL_ERROR_NOTE = "required control data is incomplete; model not fit"
SVD_DID_NOT_CONVERGE = "svd_did_not_converge"


@dataclass(frozen=True)
class SkippedModelFit:
    """Sentinel for a model that was eligible but failed numerically during fit."""

    reason: str


def drop_incomplete_control_rows(
    frame: pl.DataFrame,
    columns: Sequence[str] = REQUIRED_CONTROL_COLUMNS,
) -> pl.DataFrame:
    """
    Drop rows with null values in the available required control columns.
    
    Parameters:
        frame (pl.DataFrame): Input data frame.
        columns (Sequence[str]): Control columns to check.
    
    Returns:
        pl.DataFrame: The filtered data frame, or the original frame when none of
            the specified columns are present.
    """

    present = [column for column in columns if column in frame.columns]
    if not present:
        return frame
    return frame.filter(pl.all_horizontal(pl.col(column).is_not_null() for column in present))


def validate_control_columns(
    model_data: pd.DataFrame,
    columns: Sequence[str] = REQUIRED_CONTROL_COLUMNS,
) -> tuple[dict[str, str], ...]:
    """
    Identify required control columns that are missing or contain null values.
    
    Parameters:
        model_data (pd.DataFrame): Data containing the control columns to validate.
        columns (Sequence[str]): Required control column names.
    
    Returns:
        tuple[dict[str, str], ...]: Validation issues, each containing a column name
        and a reason of either ``"missing_column"`` or ``"missing_values"``.
    """

    issues: list[dict[str, str]] = []
    for column in columns:
        if column not in model_data.columns:
            issues.append({"column": column, "reason": "missing_column"})
        elif model_data[column].isna().any():
            issues.append({"column": column, "reason": "missing_values"})
    return tuple(issues)


def control_error_summary(
    *,
    backend: str,
    score_column: str,
    invalid_controls: Sequence[dict[str, str]],
    row_count: int,
    keyword_count: int,
) -> dict[str, object]:
    return {
        "backend": backend,
        "score_column": score_column,
        "status": "error",
        "error_note": CONTROL_ERROR_NOTE,
        "invalid_controls": [dict(control) for control in invalid_controls],
        "row_count": int(row_count),
        "keyword_count": int(keyword_count),
    }
