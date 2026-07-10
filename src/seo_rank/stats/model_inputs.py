"""Validation shared by statistical model input preparation."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


REQUIRED_CONTROL_COLUMNS = ("site_scale",)
CONTROL_ERROR_NOTE = "required control data is incomplete; model not fit"


def validate_control_columns(
    model_data: pd.DataFrame,
    columns: Sequence[str] = REQUIRED_CONTROL_COLUMNS,
) -> tuple[dict[str, str], ...]:
    """Return control issues instead of silently reducing a model formula."""

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
