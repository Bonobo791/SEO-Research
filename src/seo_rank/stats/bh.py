"""Phase 5 Benjamini-Hochberg helpers."""

from __future__ import annotations

from collections.abc import Sequence


def adjust_p_values(p_values: Sequence[float]) -> list[float]:
    """Return Benjamini-Hochberg adjusted q-values in input order."""

    count = len(p_values)
    if count == 0:
        return []

    ranked = sorted(enumerate(float(value) for value in p_values), key=lambda item: item[1])
    adjusted = [0.0] * count
    running_min = 1.0
    for offset, (index, p_value) in enumerate(reversed(ranked), start=1):
        rank = count - offset + 1
        q_value = min(1.0, (p_value * count) / rank)
        running_min = min(running_min, q_value)
        adjusted[index] = running_min
    return adjusted
