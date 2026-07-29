"""Phase 5 Benjamini-Hochberg helpers."""
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
