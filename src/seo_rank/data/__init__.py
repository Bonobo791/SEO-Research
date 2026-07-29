"""Run-scoped data layer helpers."""
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


from seo_rank.data.features import (
    build_analysis_mart,
    build_feature_marts,
    ensure_feature_marts_for_analysis,
)
from seo_rank.data.marts import build_analysis_lazyframe
from seo_rank.data.normalize import normalize_run
from seo_rank.data.scans import scan_raw_responses
from seo_rank.data.validate import validate_frame_contract, validate_required_columns

__all__ = [
    "build_analysis_mart",
    "build_analysis_lazyframe",
    "build_feature_marts",
    "ensure_feature_marts_for_analysis",
    "normalize_run",
    "scan_raw_responses",
    "validate_frame_contract",
    "validate_required_columns",
]
